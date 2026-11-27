"""
HTTP MCP integration — mounts the Streamable-HTTP transport on the FastAPI
backend at ``/mcp``.

Uses ``StreamableHTTPSessionManager`` in stateful mode (see
``get_session_manager``).

One client context per API key
------------------------------
The tool handlers keep per-client state on an ``AidaMCPService``: the loaded
assessment, the bearer token for the backend REST calls, caches. Over stdio
there is one process per client; over HTTP every client shares this backend
process, so each API key gets its own service (``_clients``):

- two agents (`aida run`) on two assessments run side by side without
  seeing each other's assessment;
- each service calls the REST API with a JWT of its own key's owner, so
  concurrent clients of different users can't borrow each other's token
  (the previous single service swapped one shared token per request);
- keys bound to an assessment (agent keys) are pinned to it.

The service is picked per HTTP request, from the key that authenticated that
request (``_SCOPE_KEY`` in the ASGI scope, read back through the MCP request
context), not per MCP session: a session id replayed with another key still
acts as that other key.

Lifecycle — the session manager requires its ``run()`` context to be active
while handling requests. ``mcp_lifespan`` exposes an async context manager
that the FastAPI ``lifespan`` function chains with its own startup code.
"""
from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from starlette.requests import Request

# ``backend/mcp/`` is intentionally not a Python package (no ``__init__.py``)
# because a package named ``mcp`` would collide with the installed MCP SDK.
# Put its loose modules on sys.path so they resolve as top-level imports.
_BACKEND_DIR = Path(__file__).parent
_MCP_DIR = _BACKEND_DIR / "mcp"
_MODULES_DIR = _MCP_DIR / "modules"
for _p in (str(_MODULES_DIR), str(_MCP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager  # noqa: E402
from starlette.responses import Response  # noqa: E402

from auth import create_access_token  # noqa: E402
from config import settings  # noqa: E402
from mcp_classes import AidaMCPService  # noqa: E402
from server_builder import build_mcp_server  # noqa: E402


class _AlreadySentResponse(Response):
    """No-op response used when the MCP session manager has already driven
    the ASGI protocol itself. Prevents Starlette from emitting a second
    ``http.response.start`` message on top of ours.
    """

    def __init__(self) -> None:
        super().__init__(content=b"", status_code=200)

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[override]
        return None


# The access token minted for a client lives 24h; re-mint it hourly.
_TOKEN_REFRESH_SECONDS = 3600
# Where handle_mcp_request leaves the client's service for the tool handlers.
_SCOPE_KEY = "aida.mcp_service"


@dataclass
class _Client:
    service: AidaMCPService
    user_id: int
    token_minted_at: float


_session_manager: StreamableHTTPSessionManager | None = None
_clients: dict[int, _Client] = {}  # API key id -> its client context


def _service_for_request(ctx: Any) -> AidaMCPService:
    """Return the service of the API key that authenticated this request."""
    request = getattr(ctx, "request", None)
    service = request.scope.get(_SCOPE_KEY) if request is not None else None
    if service is None:
        # Never fall back to a shared context: that is what leaked one
        # client's assessment into another's.
        raise RuntimeError("MCP request without an authenticated API key")
    return service


def get_session_manager() -> StreamableHTTPSessionManager:
    """Lazily construct the session manager + MCP server.

    Safe to call multiple times; only the first invocation does work.
    """
    global _session_manager
    if _session_manager is not None:
        return _session_manager

    server = build_mcp_server(service_for_request=_service_for_request)
    # Stateful mode — the manager issues an ``Mcp-Session-Id`` on initialize
    # and clients (OpenWebUI, Claude Desktop, Cursor) echo it on subsequent
    # requests. Stateless mode breaks clients that keep a session between
    # ``initialize`` and ``tools/list``.
    _session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=False,
        stateless=False,
    )
    return _session_manager


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Run the session-manager task group; close the client contexts after.

    Intended to be composed inside the FastAPI app's own lifespan.
    """
    manager = get_session_manager()
    try:
        async with manager.run():
            yield
    finally:
        clients = list(_clients.values())
        _clients.clear()
        for client in clients:
            await client.service.cleanup()


def _pinned_assessment(api_key) -> Optional[dict]:
    if api_key.assessment_id is None:
        return None
    assessment = api_key.assessment
    name = assessment.name if assessment is not None else str(api_key.assessment_id)
    return {"id": api_key.assessment_id, "name": name}


def client_service(api_key) -> AidaMCPService:
    """Return the MCP service of ``api_key``, creating it on first use.

    Called with the key's DB row while the request's DB session is open.
    """
    now = time.monotonic()
    pinned = _pinned_assessment(api_key)
    client = _clients.get(api_key.id)

    if client is None:
        container = None
        if pinned is not None and api_key.scope == "agent":
            # The agent runs in its own container (`aida run`): the helpers
            # that docker-exec directly target it, not the shared one.
            container = f"{settings.AGENT_CONTAINER_PREFIX}{pinned['id']}"
        service = AidaMCPService(
            token=create_access_token(api_key.owner_user_id, api_key.owner.username),
            pinned_assessment=pinned,
            container=container,
        )
        # No await since the lookup: concurrent first requests of one key
        # can't create two contexts.
        client = _Client(service=service, user_id=api_key.owner_user_id, token_minted_at=now)
        _clients[api_key.id] = client
    else:
        if now - client.token_minted_at >= _TOKEN_REFRESH_SECONDS:
            client.service.set_token(
                create_access_token(api_key.owner_user_id, api_key.owner.username)
            )
            client.token_minted_at = now
        if pinned is not None and pinned["name"] != client.service.pinned_assessment_name:
            # Assessment renamed in the UI.
            client.service.pin_assessment(pinned["id"], pinned["name"])

    return client.service


async def handle_mcp_request(request: Request, api_key) -> Response:
    """Forward the request to the session manager and return a no-op Response.

    ``api_key`` is the key ``verify_mcp_api_key`` accepted for this request;
    the tool handlers run with that key's own client context.

    The session manager uses the raw ASGI ``send`` callable to emit its own
    response, so we return a sentinel that suppresses Starlette's own send.
    """
    request.scope[_SCOPE_KEY] = client_service(api_key)
    manager = get_session_manager()
    await manager.handle_request(request.scope, request.receive, request._send)
    return _AlreadySentResponse()
