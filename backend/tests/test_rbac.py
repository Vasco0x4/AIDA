"""
E2 — RBAC middleware matrix, exercised over the real ASGI app.

The middleware (and get_db) create their sessions through the module-level
``SessionLocal`` — patched here onto the isolated test engine, so requests see
only the users this test creates and audit rows land in the test DB.

The 422 trick: for "allowed" writes we POST an empty body and accept 422 —
validation errors prove the request got PAST RBAC into the handler.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from auth import create_access_token, hash_password
from models.audit_log import AuditLog
from models.user import User


@pytest.fixture()
def _users(db):
    """One user per role, committed so the middleware's own sessions see them."""
    rows = {}
    for role in ("admin", "auditor", "viewer"):
        u = User(username=f"rbx-{role}", email=f"{role}@t.local",
                 hashed_password=hash_password("pw-no-matter"), role=role,
                 is_active=True)
        db.add(u)
        rows[role] = u
    db.commit()
    return rows


class ASGI:
    """Sync facade over httpx.AsyncClient+ASGITransport (the container's httpx
    predates sync-Client ASGI support). One loop per request is fine here."""

    def __init__(self, app):
        self._app = app

    def request(self, method, path, **kw):
        import asyncio

        async def _run():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                return await c.request(method, path, **kw)

        return asyncio.run(_run())

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)


@pytest.fixture()
def client(engine, db, _users):
    import database as database_mod
    import middleware.rbac as rbac_mod
    import main

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    saved = (rbac_mod.SessionLocal, database_mod.SessionLocal)
    rbac_mod.SessionLocal = Session
    database_mod.SessionLocal = Session
    try:
        yield ASGI(main.app)
    finally:
        rbac_mod.SessionLocal, database_mod.SessionLocal = saved


def _auth(client, user):
    token = create_access_token(user.id, user.username)
    return {"Authorization": f"Bearer {token}"}


def test_public_paths_skip_rbac(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_unauthenticated_is_401(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/users").status_code == 401


def test_viewer_readonly(client, _users):
    v = _users["viewer"]
    assert client.get("/api/tasks", headers=_auth(client, v)).status_code == 200
    # writes are denied before validation kicks in
    assert client.post("/api/tasks", headers=_auth(client, v)).status_code == 403
    # admin-only surfaces
    assert client.get("/api/users", headers=_auth(client, v)).status_code == 403
    assert client.get("/api/audit", headers=_auth(client, v)).status_code == 403
    assert client.get("/api/sso/config", headers=_auth(client, v)).status_code == 403


def test_auditor_operates_but_not_admin(client, _users):
    a = _users["auditor"]
    assert client.get("/api/tasks", headers=_auth(client, a)).status_code == 200
    # operational write passes RBAC (422 = reached the handler's validation)
    assert client.post("/api/tasks", headers=_auth(client, a)).status_code == 422
    assert client.get("/api/users", headers=_auth(client, a)).status_code == 403
    assert client.get("/api/audit", headers=_auth(client, a)).status_code == 403


def test_admin_everywhere(client, _users):
    adm = _users["admin"]
    assert client.get("/api/tasks", headers=_auth(client, adm)).status_code == 200
    assert client.get("/api/users", headers=_auth(client, adm)).status_code == 200
    assert client.get("/api/audit", headers=_auth(client, adm)).status_code == 200
    assert client.get("/api/sso/config", headers=_auth(client, adm)).status_code == 200


def test_denial_is_audited(client, _users, db):
    v = _users["viewer"]
    client.post("/api/tasks", headers=_auth(client, v))
    row = (db.query(AuditLog).filter(AuditLog.action == "rbac.denied")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None
    assert row.actor_username == v.username
    assert row.success is False
    assert row.detail["method"] == "POST"
    assert row.detail["required_role"] == "auditor"


def test_inactive_user_is_401(client, _users, db):
    v = _users["viewer"]
    v.is_active = False
    db.commit()
    assert client.get("/api/tasks", headers=_auth(client, v)).status_code == 401


def test_login_audited_success_and_failure(client, _users, db):
    # failure first (wrong password)
    r = client.post("/api/auth/login",
                    json={"username": _users["auditor"].username, "password": "wrong"})
    assert r.status_code == 401
    row = (db.query(AuditLog).filter(AuditLog.action == "auth.login.failed")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None and row.success is False

    # the seeded users have unusable passwords; set a real one and log in
    _users["auditor"].hashed_password = hash_password("Sup3rSecret!")
    _users["auditor"].must_change_password = False
    db.commit()
    r = client.post("/api/auth/login",
                    json={"username": _users["auditor"].username, "password": "Sup3rSecret!"})
    assert r.status_code == 200
    assert r.json()["access_token"]
    row = (db.query(AuditLog).filter(AuditLog.action == "auth.login.success")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None and row.actor_username == _users["auditor"].username
