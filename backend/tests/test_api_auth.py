"""
Integration tests for the authentication API (api/auth.py) over the real app.

Covers: setup wizard, login branches (success / bad password / unknown user /
disabled account), /me, long-lived API tokens, password change, token expiry,
and the OIDC status/login/callback HTTP surface (IdP interaction mocked —
see test_oidc.py for the crypto-level unit tests).
"""
from __future__ import annotations

import time

import pytest
from jose import jwt as jose_jwt

import auth as auth_mod
import services.oidc_service as oidc
from conftest import make_user
from middleware.rate_limit import limiter
from models.audit_log import AuditLog
from models.user import User

ISSUER = "https://sso.example.com/realms/aida"
CLIENT_ID = "aida-client"


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """The limiter's memory storage is process-global; keep tests independent."""
    limiter.reset()
    yield
    limiter.reset()


def _token_for(user: User) -> dict:
    return {"Authorization":
            f"Bearer {auth_mod.create_access_token(user.id, user.username)}"}


# --- setup wizard ---------------------------------------------------------------

def test_setup_status_on_empty_db(db, client):
    r = client.get("/api/auth/setup-status")
    assert r.status_code == 200
    assert r.json() == {"setup_required": True}


def test_setup_creates_first_admin(db, client):
    r = client.post("/api/auth/setup",
                    json={"username": "root", "password": "LongEnough1!",
                          "email": "root@aida.local"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["user"]["role"] == "admin"
    assert body["user"]["must_change_password"] is False

    # The account works immediately
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "root"

    # Setup is now closed
    assert client.get("/api/auth/setup-status").json() == {"setup_required": False}
    again = client.post("/api/auth/setup",
                        json={"username": "evil", "password": "LongEnough1!"})
    assert again.status_code == 403


def test_setup_validation(db, client):
    assert client.post("/api/auth/setup",
                       json={"username": "ab", "password": "LongEnough1!"}).status_code == 422
    assert client.post("/api/auth/setup",
                       json={"username": "abc", "password": "short"}).status_code == 422


# --- login -----------------------------------------------------------------------

def test_login_success_updates_last_login(db, client):
    u = make_user(db, "alice", "auditor", "Sup3rSecret!x")
    assert u.last_login_at is None
    r = client.post("/api/auth/login",
                    json={"username": "alice", "password": "Sup3rSecret!x"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "alice"
    db.refresh(u)
    assert u.last_login_at is not None

    # The issued token authenticates elsewhere
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_login_wrong_password(db, client):
    make_user(db, "bob", "viewer", "Sup3rSecret!x")
    r = client.post("/api/auth/login",
                    json={"username": "bob", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid username or password"


def test_login_unknown_user(db, client):
    r = client.post("/api/auth/login",
                    json={"username": "ghost", "password": "whatever"})
    assert r.status_code == 401


def test_login_disabled_account(db, client):
    u = make_user(db, "carol", "viewer", "Sup3rSecret!x")
    u.is_active = False
    db.commit()
    r = client.post("/api/auth/login",
                    json={"username": "carol", "password": "Sup3rSecret!x"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Account is disabled"


def test_login_validation(db, client):
    assert client.post("/api/auth/login", json={"username": "x"}).status_code == 422


# --- /me and token validation ----------------------------------------------------

def test_me_requires_token(db, client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(db, client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_me_rejects_expired_token(db, client):
    make_user(db, "admin", "admin")
    expired = jose_jwt.encode(
        {"sub": "1", "username": "admin", "exp": int(time.time()) - 30},
        auth_mod.SECRET_KEY, algorithm=auth_mod.ALGORITHM)
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_me_rejects_deleted_user(db, client, admin_headers, admin_user):
    db.delete(admin_user)
    db.commit()
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 401


# --- long-lived API tokens --------------------------------------------------------

def test_api_token_roundtrip(db, client, admin_headers):
    r = client.post("/api/auth/api-token", headers=admin_headers)
    assert r.status_code == 200
    token = r.json()["api_token"]
    payload = auth_mod.decode_token(token)
    assert payload["type"] == "api"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_api_token_requires_auth(db, client):
    assert client.post("/api/auth/api-token").status_code == 401


# --- password change --------------------------------------------------------------

def test_change_password_flow(db, client):
    u = make_user(db, "dave", "viewer", "OldPass123!")
    headers = _token_for(u)
    r = client.post("/api/auth/change-password", headers=headers,
                    json={"current_password": "wrong", "new_password": "NewPass456!"})
    assert r.status_code == 401

    r = client.post("/api/auth/change-password", headers=headers,
                    json={"current_password": "OldPass123!", "new_password": "OldPass123!"})
    assert r.status_code == 400

    r = client.post("/api/auth/change-password", headers=headers,
                    json={"current_password": "OldPass123!", "new_password": "NewPass456!"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False

    # Old password is dead, new one works
    assert client.post("/api/auth/login",
                       json={"username": "dave", "password": "OldPass123!"}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": "dave", "password": "NewPass456!"}).status_code == 200


def test_change_password_clears_must_change_flag(db, client):
    u = make_user(db, "erin", "auditor", "OldPass123!")
    u.must_change_password = True
    db.commit()
    r = client.post("/api/auth/change-password", headers=_token_for(u),
                    json={"current_password": "OldPass123!", "new_password": "NewPass456!"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False


def test_change_password_validation(db, client, viewer_headers):
    assert client.post("/api/auth/change-password", headers=viewer_headers,
                       json={"current_password": "x"}).status_code == 422


# --- OIDC HTTP surface ------------------------------------------------------------

def test_oidc_status_unconfigured(db, client):
    r = client.get("/api/auth/oidc/status")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "provider": None}


def test_oidc_status_configured(db, client):
    oidc.save_config(db, enabled=True, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret="s3cret", default_role="viewer", redirect_base="")
    r = client.get("/api/auth/oidc/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["provider"] == "sso.example.com"  # issuer netloc


def test_oidc_login_unconfigured_redirects_to_error(db, client):
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("http://testserver/sso#error=")


def test_oidc_login_redirects_to_provider(db, client, monkeypatch):
    oidc.save_config(db, enabled=True, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret="s3cret", default_role="viewer", redirect_base="")

    async def fake_discovery(issuer):
        return {"authorization_endpoint": f"{issuer}/authorize",
                "token_endpoint": f"{issuer}/token",
                "jwks_uri": f"{issuer}/jwks"}

    monkeypatch.setattr(oidc, "_discovery", fake_discovery)
    r = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith(f"{ISSUER}/authorize?")
    assert "code_challenge_method=S256" in loc
    assert f"client_id={CLIENT_ID}" in loc


def test_oidc_callback_provider_error(db, client):
    r = client.get("/api/auth/oidc/callback",
                   params={"error": "access_denied",
                           "error_description": "User denied"},
                   follow_redirects=False)
    assert r.status_code == 302
    assert "error=User%20denied" in r.headers["location"]


def test_oidc_callback_missing_params(db, client):
    r = client.get("/api/auth/oidc/callback", params={"code": "c"},
                   follow_redirects=False)
    assert r.status_code == 302
    assert "error=Missing%20code/state" in r.headers["location"]


def test_oidc_callback_invalid_state(db, client):
    r = client.get("/api/auth/oidc/callback",
                   params={"code": "c", "state": "garbage"},
                   follow_redirects=False)
    assert r.status_code == 302
    assert "Invalid%20or%20expired%20SSO%20state" in r.headers["location"]


def test_oidc_callback_success_provisions_user(db, client, monkeypatch):
    oidc.save_config(db, enabled=True, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret="s3cret", default_role="auditor", redirect_base="")

    verifier = "test-verifier-value"
    state = oidc._sign_state({"v": verifier, "e": int(time.time()) + 60})

    async def fake_exchange(cfg, code, redirect_uri, v):
        assert code == "auth-code"
        assert v == verifier
        return {"id_token": "signed-but-opaque", "access_token": "provider-access-token"}

    async def fake_verify(cfg, token, access_token):
        assert access_token == "provider-access-token"
        return {"sub": "idp-42", "preferred_username": "sso.joe",
                "email": "sso.joe@corp.example"}

    monkeypatch.setattr(oidc, "exchange_code", fake_exchange)
    monkeypatch.setattr(oidc, "verify_id_token", fake_verify)

    r = client.get("/api/auth/oidc/callback",
                   params={"code": "auth-code", "state": state},
                   follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("http://testserver/sso#token=")
    token = loc.split("#token=", 1)[1]
    assert auth_mod.decode_token(token)["sub"] != ""

    # JIT-provisioned user exists with the configured default role
    user = db.query(User).filter(User.username == "sso.joe").first()
    assert user is not None
    assert user.role == "auditor"

    row = (db.query(AuditLog).filter(AuditLog.action == "auth.sso.login")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None and row.actor_username == "sso.joe"


def test_oidc_callback_failure_audited(db, client, monkeypatch):
    oidc.save_config(db, enabled=True, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret="s3cret", default_role="viewer", redirect_base="")
    state = oidc._sign_state({"v": "v", "e": int(time.time()) + 60})

    async def boom(cfg, code, redirect_uri, v):
        raise oidc.OIDCError("token exchange failed")

    monkeypatch.setattr(oidc, "exchange_code", boom)
    r = client.get("/api/auth/oidc/callback",
                   params={"code": "c", "state": state}, follow_redirects=False)
    assert r.status_code == 302
    assert "error=token%20exchange%20failed" in r.headers["location"]
    row = (db.query(AuditLog).filter(AuditLog.action == "auth.sso.failed")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None and row.success is False
