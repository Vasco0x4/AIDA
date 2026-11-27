"""
Each API key gets its own MCP client context (mcp_http_app.py).

Runs the real /mcp endpoint and the REST routers the tool handlers call, in
a uvicorn server, and drives it with the MCP SDK client over HTTP, the way
Claude Code inside an `aida run` container does.
"""
import asyncio
import json
import os
import socket
import threading
import time
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from fastapi import Depends, FastAPI, Request
from jose import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from models.card import Card

# Every /api request the MCP services made: (user id in their JWT, path).
REST_CALLS: list[tuple[int, str]] = []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url():
    port = _free_port()
    # The MCP services call the REST API of this same server.
    os.environ["BACKEND_API_URL"] = f"http://127.0.0.1:{port}/api"

    import mcp_http_app
    from api import assessments, cards
    from auth import SECRET_KEY, ALGORITHM, get_current_user, verify_mcp_api_key

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_http_app.mcp_lifespan():
            yield

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def record_rest_calls(request: Request, call_next):
        auth = request.headers.get("authorization", "")
        if request.url.path.startswith("/api/") and auth.startswith("Bearer "):
            claims = jwt.decode(auth[7:], SECRET_KEY, algorithms=[ALGORITHM])
            REST_CALLS.append((int(claims["sub"]), request.url.path))
        return await call_next(request)

    for router in (assessments.router, cards.router):
        app.include_router(router, prefix="/api", dependencies=[Depends(get_current_user)])

    @app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
    async def mcp_endpoint(request: Request, api_key=Depends(verify_mcp_api_key)):
        return await mcp_http_app.handle_mcp_request(request, api_key)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def _reset_calls():
    REST_CALLS.clear()


@asynccontextmanager
async def mcp_client(server_url: str, key: str):
    http = httpx.AsyncClient(headers={"Authorization": f"Bearer {key}"},
                             timeout=httpx.Timeout(30, read=60))
    async with http:
        async with streamable_http_client(f"{server_url}/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def call(session: ClientSession, tool: str, **arguments) -> str:
    result = await session.call_tool(tool, arguments)
    return "\n".join(c.text for c in result.content if c.type == "text")


def _assessment_in(path: str):
    """Assessment id in a /api/assessments/<id>/... path, else None."""
    parts = path.split("/")
    if len(parts) > 3 and parts[1:3] == ["api", "assessments"] and parts[3].isdigit():
        return int(parts[3])
    return None


def card_titles(text: str) -> set[str]:
    return {word for word in text.replace("\n", " ").split() if word.startswith("obs-")}


# --- agents (keys bound to an assessment) -------------------------------------

async def test_two_agents_side_by_side(server_url, make, db):
    user = make.user()
    a, b = make.assessment("target-a"), make.assessment("target-b")
    key_a = make.api_key(user, scope="agent", assessment=a)
    key_b = make.api_key(user, scope="agent", assessment=b)

    async with mcp_client(server_url, key_a) as agent_a, mcp_client(server_url, key_b) as agent_b:
        assert "loaded" in await call(agent_a, "load_assessment", name="target-a", skip_data=True)
        assert "loaded" in await call(agent_b, "load_assessment", name="target-b", skip_data=True)

        async def work(agent, tag):
            for i in range(6):
                await call(agent, "add_card", card_type="observation", title=f"obs-{tag}-{i}")
                await call(agent, "list_cards")

        # Interleaved: with one shared context, cards landed in whichever
        # assessment was loaded last.
        await asyncio.gather(work(agent_a, "a"), work(agent_b, "b"))

        seen_a = card_titles(await call(agent_a, "list_cards"))
        seen_b = card_titles(await call(agent_b, "list_cards"))

    assert seen_a == {f"obs-a-{i}" for i in range(6)}
    assert seen_b == {f"obs-b-{i}" for i in range(6)}
    stored = {(c.assessment_id, c.title) for c in db.query(Card).all()}
    assert stored == {(a.id, f"obs-a-{i}") for i in range(6)} | {(b.id, f"obs-b-{i}") for i in range(6)}


async def test_agent_only_sees_its_assessment(server_url, make):
    user = make.user()
    mine, other = make.assessment("mine"), make.assessment("someone-elses")
    key = make.api_key(user, scope="agent", assessment=mine)

    async with mcp_client(server_url, key) as agent:
        tools = {t.name for t in (await agent.list_tools()).tools}
        assert "create_assessment" not in tools
        assert {"load_assessment", "list_assessments", "list_cards"} <= tools

        # Loaded from the start: no load_assessment needed.
        await call(agent, "add_card", card_type="observation", title="obs-mine")

        refused = await call(agent, "load_assessment", name="someone-elses")
        assert "bound to assessment 'mine'" in refused
        listed = await call(agent, "list_assessments")
        assert "mine" in listed and "someone-elses" not in listed
        assert "cannot create" in await call(agent, "create_assessment", name="new-one")

        # Still on its own assessment after the refusals.
        assert card_titles(await call(agent, "list_cards")) == {"obs-mine"}

    touched = {_assessment_in(path) for _, path in REST_CALLS} - {None}
    assert touched == {mine.id}, f"also reached assessment(s) {touched - {mine.id}} (other is {other.id})"


async def test_agent_follows_a_rename(server_url, make, db):
    assessment = make.assessment("old-name")
    key = make.api_key(make.user(), scope="agent", assessment=assessment)
    async with mcp_client(server_url, key) as agent:
        assert "loaded" in await call(agent, "load_assessment", name="old-name", skip_data=True)
        assessment.name = "new-name"
        db.commit()
        assert "loaded" in await call(agent, "load_assessment", name="new-name", skip_data=True)


# --- external MCP clients (one key each) --------------------------------------

async def test_clients_of_different_users_keep_their_own_context_and_token(server_url, make):
    make.setting("mcp_http_enabled", "true")
    alice, bob = make.user("alice"), make.user("bob")
    a, b = make.assessment("alice-target"), make.assessment("bob-target")
    key_alice, key_bob = make.api_key(alice), make.api_key(bob)

    async with mcp_client(server_url, key_alice) as c_alice, mcp_client(server_url, key_bob) as c_bob:
        # Unbound keys may pick any assessment...
        await call(c_alice, "load_assessment", name="alice-target", skip_data=True)
        await call(c_bob, "load_assessment", name="bob-target", skip_data=True)

        async def work(client, tag):
            for i in range(6):
                await call(client, "add_card", card_type="observation", title=f"obs-{tag}-{i}")

        await asyncio.gather(work(c_alice, "alice"), work(c_bob, "bob"))
        # ...but loading one doesn't change the other client's.
        assert card_titles(await call(c_alice, "list_cards")) == {f"obs-alice-{i}" for i in range(6)}
        assert card_titles(await call(c_bob, "list_cards")) == {f"obs-bob-{i}" for i in range(6)}

    # Every backend call ran as its own key's owner (the old shared service
    # swapped one token per request, so concurrent calls could borrow it).
    by_assessment = {}
    for user_id, path in REST_CALLS:
        if _assessment_in(path) is not None:
            by_assessment.setdefault(_assessment_in(path), set()).add(user_id)
    assert by_assessment == {a.id: {alice.id}, b.id: {bob.id}}


async def test_replayed_session_id_acts_as_the_caller(server_url, make):
    """A request carrying someone else's MCP session id still gets the
    context of the key that authenticated it."""
    user = make.user()
    a, b = make.assessment("replay-a"), make.assessment("replay-b")
    key_a = make.api_key(user, scope="agent", assessment=a)
    key_b = make.api_key(user, scope="agent", assessment=b)

    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    def rpc(method, params, id_=None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if id_ is not None:
            msg["id"] = id_
        return json.dumps(msg)

    def result_of(response: httpx.Response) -> dict:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])["result"]
        return response.json()["result"]

    async with httpx.AsyncClient(timeout=30) as http:
        init = await http.post(f"{server_url}/mcp", headers={**headers, "Authorization": f"Bearer {key_a}"},
                               content=rpc("initialize", {
                                   "protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "0"}}, 1))
        session_id = init.headers["mcp-session-id"]
        await http.post(f"{server_url}/mcp",
                        headers={**headers, "Authorization": f"Bearer {key_a}", "Mcp-Session-Id": session_id},
                        content=rpc("notifications/initialized", {}))
        reply = await http.post(
            f"{server_url}/mcp",
            headers={**headers, "Authorization": f"Bearer {key_b}", "Mcp-Session-Id": session_id},
            content=rpc("tools/call", {"name": "list_assessments", "arguments": {}}, 2))
        text = result_of(reply)["content"][0]["text"]

    assert "replay-b" in text and "replay-a" not in text
