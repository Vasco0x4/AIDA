"""
Integration tests for the audit trail (api/audit.py) and the SSO
configuration API (api/sso.py).

Audit: filters (action prefix / actor / resource type / success), pagination,
newest-first ordering, admin-only exposure. SSO: config round-trip with the
never-leaks-secret rule and enable-time validation. (Crypto-level OIDC
behavior is covered in test_oidc.py; the auth-facing flow in
test_api_auth.py.)
"""
from __future__ import annotations

import pytest

from conftest import make_user
from middleware.rate_limit import limiter
from models.audit_log import AuditLog
from models.platform_settings import PlatformSettings


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


def _seed_audit(db, n=3):
    """n audit rows with distinct actions + actors, ascending ids."""
    rows = []
    for i in range(n):
        row = AuditLog(actor_id=1, actor_username=f"user{i}",
                       action=f"auth.event{i}", resource_type="auth",
                       success=(i % 2 == 0), detail={"i": i})
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


# --- audit exposure -----------------------------------------------------------------

def test_audit_admin_only(client, db, viewer_headers):
    assert client.get("/api/audit", headers=viewer_headers).status_code == 403
    assert client.get("/api/audit").status_code == 401


def test_audit_list_newest_first(client, db, admin_headers):
    _seed_audit(db, 3)
    r = client.get("/api/audit", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    ids = [item["id"] for item in body["items"]]
    assert ids == sorted(ids, reverse=True)
    item = body["items"][0]
    for key in ("created_at", "actor_username", "action", "success", "detail"):
        assert key in item


def test_audit_action_prefix_filter(client, db, admin_headers):
    _seed_audit(db, 3)
    db.add(AuditLog(actor_id=1, actor_username="admin",
                    action="user.created", resource_type="user"))
    db.commit()

    r = client.get("/api/audit", headers=admin_headers,
                   params={"action": "auth."})
    body = r.json()
    assert body["total"] == 3
    assert all(item["action"].startswith("auth.") for item in body["items"])

    r = client.get("/api/audit", headers=admin_headers,
                   params={"resource_type": "user"})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["action"] == "user.created"


def test_audit_success_and_actor_filters(client, db, admin_headers):
    _seed_audit(db, 3)
    r = client.get("/api/audit", headers=admin_headers,
                   params={"success": "false"})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["success"] is False

    viewer = make_user(db, "auditviewer", "viewer")
    db.add(AuditLog(actor_id=viewer.id, actor_username=viewer.username,
                    action="custom.act"))
    db.commit()
    r = client.get("/api/audit", headers=admin_headers,
                   params={"actor_id": viewer.id})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["action"] == "custom.act"


def test_audit_pagination(client, db, admin_headers):
    _seed_audit(db, 5)
    page1 = client.get("/api/audit", headers=admin_headers,
                       params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/api/audit", headers=admin_headers,
                       params={"limit": 2, "offset": 2}).json()
    assert page1["total"] == 5 and len(page1["items"]) == 2
    assert page2["total"] == 5 and len(page2["items"]) == 2
    assert page1["items"][0]["id"] > page2["items"][0]["id"]
    assert {i["id"] for i in page1["items"]}.isdisjoint(
        {i["id"] for i in page2["items"]})
    assert client.get("/api/audit", headers=admin_headers,
                      params={"limit": 0}).status_code == 422
    assert client.get("/api/audit", headers=admin_headers,
                      params={"limit": 501}).status_code == 422


def test_audit_rows_written_by_real_requests(client, db, admin_headers):
    """Actions recorded through actual API calls show up (and are filtered)."""
    client.post("/api/auth/login",
                json={"username": "admin", "password": "wrong"})
    r = client.get("/api/audit", headers=admin_headers,
                   params={"action": "auth.login"})
    assert r.json()["total"] >= 1
    item = r.json()["items"][0]
    assert item["action"] == "auth.login.failed"
    assert item["success"] is False


# --- SSO configuration -----------------------------------------------------------------

def test_sso_config_defaults(client, db, admin_headers):
    r = client.get("/api/sso/config", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"enabled": False, "issuer": "", "client_id": "",
                    "has_secret": False, "default_role": "viewer",
                    "redirect_base": ""}


def test_sso_config_admin_only(client, db, viewer_headers):
    assert client.get("/api/sso/config", headers=viewer_headers).status_code == 403
    assert client.post("/api/sso/config", headers=viewer_headers,
                       json={"enabled": False}).status_code == 403


def test_sso_save_disabled_config(client, db, admin_headers):
    r = client.post("/api/sso/config", headers=admin_headers, json={
        "enabled": False, "issuer": "https://sso.corp.example",
        "client_id": "aida", "default_role": "auditor",
        "redirect_base": "http://localhost:5174"})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["default_role"] == "auditor"
    assert body["redirect_base"] == "http://localhost:5174"

    row = (db.query(AuditLog).filter(AuditLog.action == "sso.config_updated")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None
    assert row.detail == {"enabled": False, "default_role": "auditor"}


def test_sso_enable_requires_complete_setup(client, db, admin_headers):
    base = {"enabled": True}
    # No issuer / client_id
    r = client.post("/api/sso/config", headers=admin_headers, json=base)
    assert r.status_code == 422
    assert "issuer" in r.json()["detail"]
    # Issuer but no client_id
    r = client.post("/api/sso/config", headers=admin_headers,
                    json={**base, "issuer": "https://sso.corp.example"})
    assert r.status_code == 422
    assert "client_id" in r.json()["detail"]
    # Complete identifiers but no secret anywhere
    r = client.post("/api/sso/config", headers=admin_headers,
                    json={**base, "issuer": "https://sso.corp.example",
                          "client_id": "aida"})
    assert r.status_code == 422
    assert "client secret" in r.json()["detail"]


def test_sso_enable_with_secret_never_reads_it_back(client, db, admin_headers):
    r = client.post("/api/sso/config", headers=admin_headers, json={
        "enabled": True, "issuer": "https://sso.corp.example/",
        "client_id": "aida", "client_secret": "hunter2",
        "default_role": "viewer"})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["has_secret"] is True
    assert "client_secret" not in body
    assert "hunter2" not in r.text

    # Stored encrypted at rest
    row = (db.query(PlatformSettings)
           .filter(PlatformSettings.key == "oidc_client_secret").one())
    assert row.value != "hunter2"
    assert row.value.startswith("enc::")
    # Issuer is stored without a trailing slash
    stored = (db.query(PlatformSettings)
              .filter(PlatformSettings.key == "oidc_issuer_url").one())
    assert stored.value == "https://sso.corp.example"


def test_sso_reenable_keeps_stored_secret(client, db, admin_headers):
    client.post("/api/sso/config", headers=admin_headers, json={
        "enabled": False, "issuer": "https://sso.corp.example",
        "client_id": "aida", "client_secret": "first-secret"})
    # Empty client_secret = keep the stored one → enabling is allowed
    r = client.post("/api/sso/config", headers=admin_headers, json={
        "enabled": True, "issuer": "https://sso.corp.example",
        "client_id": "aida", "client_secret": ""})
    assert r.status_code == 200
    assert r.json()["has_secret"] is True


def test_sso_invalid_default_role_rejected(client, db, admin_headers):
    r = client.post("/api/sso/config", headers=admin_headers,
                    json={"enabled": False, "default_role": "root"})
    assert r.status_code == 422
