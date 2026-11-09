"""
Integration tests for MCP API keys (api/api_keys.py + auth.verify_mcp_api_key).

The router is mounted under an admin-only RBAC prefix, so the HTTP surface is
exercised as admin; the ownership checks inside the handlers are additionally
defense-in-depth (the middleware already rejects non-admins — noted, not
reachable through the real app).

``auth-with-key`` is tested by invoking the ``verify_mcp_api_key`` dependency
directly with synthetic ASGI scopes: feature flag, network policy, token
format, happy path (last_used_at bookkeeping), revocation, and the
``?api_key=`` query-parameter transport.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import auth as auth_mod
from conftest import make_user
from middleware.rate_limit import limiter
from models.api_key import ApiKey
from models.platform_settings import PlatformSettings


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def auditor_headers(db):
    from auth import create_access_token
    u = make_user(db, "aud2", "auditor")
    return {"Authorization": f"Bearer {create_access_token(u.id, u.username)}"}


def _set_setting(db, key: str, value: str):
    row = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSettings(key=key, value=value))
    db.commit()


def _request(headers: dict | None = None, client_ip: str = "127.0.0.1") -> Request:
    scope: dict[str, Any] = {
        "type": "http", "method": "GET", "path": "/mcp", "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (client_ip, 54321), "server": ("testserver", 80), "scheme": "http",
    }
    return Request(scope)


async def _verify(db, headers: dict | None = None, client_ip: str = "127.0.0.1",
                  api_key: Optional[str] = None) -> ApiKey:
    """Invoke the dependency the way FastAPI's DI would (header → credentials)."""
    from fastapi.security import HTTPAuthorizationCredentials
    token = None
    authz = (headers or {}).get("Authorization", "")
    if authz.lower().startswith("bearer "):
        token = authz[7:]
    creds = (HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
             if token else None)
    return await auth_mod.verify_mcp_api_key(
        _request(headers=headers, client_ip=client_ip), creds, api_key, db)


def _mint_key_row(db, user, revoked: bool = False) -> str:
    full, prefix, hashed = auth_mod.generate_api_key()
    db.add(ApiKey(name="k", key_prefix=prefix, key_hash=hashed,
                  owner_user_id=user.id, scope="mcp",
                  revoked_at=datetime.now(timezone.utc) if revoked else None))
    db.commit()
    return full


# --- router surface --------------------------------------------------------------

def test_keys_are_admin_only(client, db, viewer_headers, auditor_headers):
    assert client.get("/api/api-keys", headers=viewer_headers).status_code == 403
    assert client.get("/api/api-keys", headers=auditor_headers).status_code == 403
    assert client.post("/api/api-keys", headers=auditor_headers,
                       json={"name": "x"}).status_code == 403
    assert client.get("/api/api-keys").status_code == 401


def test_create_and_list_keys(client, db, admin_headers, admin_user):
    r = client.post("/api/api-keys", headers=admin_headers, json={"name": "claude-cli"})
    assert r.status_code == 201
    body = r.json()
    full = body["full_key"]
    assert full.startswith("aida_sk_")
    assert len(full) > 40
    assert body["key_prefix"] == full[:auth_mod.API_KEY_PREFIX_LEN]
    assert body["scope"] == "mcp"
    assert body["owner_user_id"] == admin_user.id
    assert body["revoked_at"] is None
    # Only the hash is persisted — the plaintext never round-trips
    row = db.query(ApiKey).filter(ApiKey.id == body["id"]).one()
    assert row.key_hash != full and full not in row.key_hash

    lst = client.get("/api/api-keys", headers=admin_headers)
    assert lst.status_code == 200
    assert [k["name"] for k in lst.json()] == ["claude-cli"]
    assert "full_key" not in lst.json()[0]
    assert "key_hash" not in lst.json()[0]


def test_create_key_validation(client, db, admin_headers):
    assert client.post("/api/api-keys", headers=admin_headers,
                       json={"name": ""}).status_code == 422
    assert client.post("/api/api-keys", headers=admin_headers,
                       json={"name": "x" * 101}).status_code == 422


def test_list_by_owner_filter(client, db, admin_headers, viewer_user):
    r = client.get(f"/api/api-keys?owner_user_id={viewer_user.id}",
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []  # viewer has none yet


def test_revoke_key(client, db, admin_headers):
    created = client.post("/api/api-keys", headers=admin_headers,
                          json={"name": "temp"}).json()
    key_id = created["id"]

    r = client.delete(f"/api/api-keys/{key_id}", headers=admin_headers)
    assert r.status_code == 204
    row = db.query(ApiKey).filter(ApiKey.id == key_id).one()
    assert row.revoked_at is not None

    # Idempotent: a second revoke still returns 204
    assert client.delete(f"/api/api-keys/{key_id}",
                         headers=admin_headers).status_code == 204


def test_revoke_missing_key(client, db, admin_headers):
    assert client.delete("/api/api-keys/9999", headers=admin_headers).status_code == 404


def test_admin_revokes_another_users_key(client, db, admin_headers):
    other = make_user(db, "keyowner", "viewer")
    full = _mint_key_row(db, other)
    row = db.query(ApiKey).filter(ApiKey.key_prefix == full[:12]).one()
    assert client.delete(f"/api/api-keys/{row.id}", headers=admin_headers).status_code == 204


# --- verify_mcp_api_key (auth-with-key) -------------------------------------------

async def test_mcp_disabled_returns_503(db, admin_user):
    with pytest.raises(HTTPException) as ei:
        await _verify(db, headers={"Authorization": "Bearer aida_sk_whatever"})
    assert ei.value.status_code == 503


async def test_mcp_requires_token(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    with pytest.raises(HTTPException) as ei:
        await _verify(db)
    assert ei.value.status_code == 401


async def test_mcp_rejects_malformed_token(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    with pytest.raises(HTTPException) as ei:
        await _verify(db, headers={"Authorization": "Bearer short"})
    assert ei.value.status_code == 401


async def test_mcp_accepts_valid_key_and_stamps_usage(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    full = _mint_key_row(db, admin_user)
    row = db.query(ApiKey).filter(ApiKey.key_prefix == full[:12]).one()
    assert row.last_used_at is None

    key = await _verify(db, headers={"Authorization": f"Bearer {full}"})
    assert key.id == row.id
    db.refresh(row)
    assert row.last_used_at is not None


async def test_mcp_accepts_query_param_token(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    full = _mint_key_row(db, admin_user)
    key = await _verify(db, api_key=full)
    assert key.key_prefix == full[:auth_mod.API_KEY_PREFIX_LEN]


async def test_mcp_rejects_revoked_key(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    full = _mint_key_row(db, admin_user, revoked=True)
    with pytest.raises(HTTPException) as ei:
        await _verify(db, headers={"Authorization": f"Bearer {full}"})
    assert ei.value.status_code == 401


async def test_mcp_rejects_wrong_key(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    _mint_key_row(db, admin_user)
    other = "aida_sk_" + "z" * 50
    with pytest.raises(HTTPException) as ei:
        await _verify(db, headers={"Authorization": f"Bearer {other}"})
    assert ei.value.status_code == 401


async def test_mcp_network_policy_blocks_external_client(db, admin_user):
    _set_setting(db, "mcp_http_enabled", "true")
    # default policy: localhost
    full = _mint_key_row(db, admin_user)
    with pytest.raises(HTTPException) as ei:
        await _verify(db, headers={"Authorization": f"Bearer {full}"},
                      client_ip="203.0.113.9")
    assert ei.value.status_code == 403

    # policy "any" lets the same client through
    _set_setting(db, "mcp_http_network_policy", "any")
    key = await _verify(db, headers={"Authorization": f"Bearer {full}"},
                        client_ip="203.0.113.9")
    assert key is not None

    # policy "lan" allows RFC1918
    _set_setting(db, "mcp_http_network_policy", "lan")
    assert await _verify(db, headers={"Authorization": f"Bearer {full}"},
                         client_ip="192.168.1.10")
