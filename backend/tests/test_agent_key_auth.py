"""
Who may use /mcp with which API key (auth.verify_mcp_api_key), and how agent
keys are minted (POST /api/api-keys).
"""
import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import inspect, text

from api import api_keys
from auth import create_access_token, get_current_user, verify_mcp_api_key
from database import _ensure_columns, engine

AGENT_NET = "172.20.0.5"   # an agent container on its Docker bridge
LAN = "192.168.1.20"
PUBLIC = "8.8.8.8"
LOOPBACK = "127.0.0.1"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/mcp-probe")
    def probe(key=Depends(verify_mcp_api_key)):
        return {"key_id": key.id, "assessment_id": key.assessment_id}

    app.include_router(api_keys.router, prefix="/api", dependencies=[Depends(get_current_user)])
    return app


async def _probe(key: str | None, client_ip: str, query: bool = False) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(), client=(client_ip, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://aida") as client:
        if key is None:
            return await client.get("/mcp-probe")
        if query:
            return await client.get("/mcp-probe", params={"api_key": key})
        return await client.get("/mcp-probe", headers={"Authorization": f"Bearer {key}"})


# --- agent keys --------------------------------------------------------------

@pytest.mark.parametrize("ip", [AGENT_NET, LAN, LOOPBACK])
async def test_agent_key_works_from_private_addresses_with_http_mcp_disabled(make, ip):
    user, assessment = make.user(), make.assessment()
    key = make.api_key(user, scope="agent", assessment=assessment)
    # HTTP MCP is off by default (no platform setting).
    r = await _probe(key, ip)
    assert r.status_code == 200, r.text
    assert r.json()["assessment_id"] == assessment.id


async def test_agent_key_refused_from_public_address(make):
    key = make.api_key(make.user(), scope="agent", assessment=make.assessment())
    r = await _probe(key, PUBLIC)
    assert r.status_code == 403


async def test_agent_key_follows_an_explicit_any_policy(make):
    make.setting("mcp_http_network_policy", "any")
    key = make.api_key(make.user(), scope="agent", assessment=make.assessment())
    assert (await _probe(key, PUBLIC)).status_code == 200


async def test_unbound_agent_key_is_refused(make):
    # Minted before keys were bound to an assessment: it would see them all.
    key = make.api_key(make.user(), scope="agent", assessment=None)
    r = await _probe(key, AGENT_NET)
    assert r.status_code == 401
    assert "not bound" in r.json()["detail"]


async def test_revoked_agent_key_is_refused(make):
    key = make.api_key(make.user(), scope="agent", assessment=make.assessment(), revoked=True)
    r = await _probe(key, AGENT_NET)
    assert r.status_code in (401, 503)  # unknown key: treated like an external one


async def test_agent_key_of_inactive_user_is_refused(make):
    key = make.api_key(make.user(active=False), scope="agent", assessment=make.assessment())
    assert (await _probe(key, AGENT_NET)).status_code == 401


async def test_agent_key_dies_with_its_assessment(make, db):
    assessment = make.assessment()
    key = make.api_key(make.user(), scope="agent", assessment=assessment)
    db.delete(assessment)
    db.commit()
    assert (await _probe(key, AGENT_NET)).status_code != 200


# --- regular MCP keys (external clients) -------------------------------------

async def test_mcp_key_needs_http_mcp_enabled(make):
    key = make.api_key(make.user())
    assert (await _probe(key, LOOPBACK)).status_code == 503


async def test_mcp_key_follows_network_policy(make):
    make.setting("mcp_http_enabled", "true")
    key = make.api_key(make.user())
    assert (await _probe(key, LOOPBACK)).status_code == 200
    # Default policy "localhost": the agent-key exception doesn't extend to it.
    assert (await _probe(key, AGENT_NET)).status_code == 403
    make.setting("mcp_http_network_policy", "lan")
    assert (await _probe(key, AGENT_NET)).status_code == 200
    assert (await _probe(key, PUBLIC)).status_code == 403


async def test_mcp_key_in_query_string(make):
    make.setting("mcp_http_enabled", "true")
    key = make.api_key(make.user())
    assert (await _probe(key, LOOPBACK, query=True)).status_code == 200


@pytest.mark.parametrize("key", [None, "not-a-key", "aida_sk_definitely-not-a-real-key-000000"])
async def test_missing_or_unknown_key(make, key):
    make.setting("mcp_http_enabled", "true")
    assert (await _probe(key, LOOPBACK)).status_code == 401


# --- minting keys --------------------------------------------------------------

async def _api(user, method: str, path: str, **kwargs) -> httpx.Response:
    token = create_access_token(user.id, user.username)
    transport = httpx.ASGITransport(app=_app(), client=(LOOPBACK, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://aida") as client:
        return await client.request(method, f"/api{path}",
                                    headers={"Authorization": f"Bearer {token}"}, **kwargs)


async def test_agent_key_requires_an_assessment(make):
    user = make.user()
    r = await _api(user, "POST", "/api-keys", json={"name": "agent: x", "scope": "agent"})
    assert r.status_code == 422


async def test_agent_key_for_unknown_assessment(make):
    user = make.user()
    r = await _api(user, "POST", "/api-keys",
                   json={"name": "agent: x", "scope": "agent", "assessment_id": 999999})
    assert r.status_code == 404


async def test_agent_key_is_bound_and_listed_with_its_assessment(make):
    user, assessment = make.user(), make.assessment()
    r = await _api(user, "POST", "/api-keys",
                   json={"name": "agent: a", "scope": "agent", "assessment_id": assessment.id})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["assessment_id"] == assessment.id
    assert (await _probe(created["full_key"], AGENT_NET)).status_code == 200

    listed = (await _api(user, "GET", "/api-keys")).json()
    assert [(k["id"], k["scope"], k["assessment_id"]) for k in listed] == [
        (created["id"], "agent", assessment.id)
    ]


# --- schema upgrade --------------------------------------------------------------

def test_existing_databases_get_the_assessment_id_column(make):
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE api_keys DROP COLUMN assessment_id"))
    try:
        _ensure_columns()
        columns = {c["name"] for c in inspect(engine).get_columns("api_keys")}
        assert "assessment_id" in columns
        fks = inspect(engine).get_foreign_keys("api_keys")
        assert any(fk["referred_table"] == "assessments" and
                   fk.get("options", {}).get("ondelete") == "CASCADE" for fk in fks)
    finally:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS assessment_id INTEGER"
                " REFERENCES assessments(id) ON DELETE CASCADE"
            ))
