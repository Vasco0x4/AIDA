"""
Integration tests for user management (api/users.py, admin-only router).

Covers: list/create/update/reset-password/delete happy paths, conflict and
validation errors, self-protection and last-admin guards, and RBAC denials.

NOTE: the "Cannot remove the last active admin" guard on PATCH and DELETE is
effectively unreachable through the API: it only triggers when the *target* is
an active admin and exactly one active admin exists — but the caller must be
an active admin themselves (require_admin + middleware), so the count is
always >= 2 whenever the target is someone else. It is defense-in-depth; the
reachable self-protection branches are tested here instead.
"""
from __future__ import annotations

import pytest

from conftest import make_user
from middleware.rate_limit import limiter
from models.audit_log import AuditLog
from models.user import User


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def auditor_headers(db):
    from auth import create_access_token
    u = make_user(db, "aud1", "auditor")
    return {"Authorization": f"Bearer {create_access_token(u.id, u.username)}"}


# --- listing / RBAC --------------------------------------------------------------

def test_users_require_admin(client, db, viewer_headers, auditor_headers):
    assert client.get("/api/users", headers=viewer_headers).status_code == 403
    assert client.get("/api/users", headers=auditor_headers).status_code == 403


def test_list_users(client, db, admin_headers):
    r = client.get("/api/users", headers=admin_headers)
    assert r.status_code == 200
    usernames = [u["username"] for u in r.json()]
    assert usernames == ["admin"]
    # No password material ever leaves the API
    assert "hashed_password" not in r.json()[0]


# --- create ----------------------------------------------------------------------

def test_create_user_flow(client, db, admin_headers):
    r = client.post("/api/users", headers=admin_headers,
                    json={"username": "newguy", "password": "Sup3rSecret!x",
                          "email": "newguy@corp.example", "role": "viewer"})
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "newguy"
    assert body["role"] == "viewer"
    assert body["is_active"] is True
    # Forced password rotation on first login
    assert body["must_change_password"] is True

    row = (db.query(AuditLog).filter(AuditLog.action == "user.created")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None and row.resource_id == str(body["id"])


def test_create_user_duplicate_username(client, db, admin_headers):
    r = client.post("/api/users", headers=admin_headers,
                    json={"username": "admin", "password": "Sup3rSecret!x"})
    assert r.status_code == 409


def test_create_user_duplicate_email(client, db, admin_headers):
    r = client.post("/api/users", headers=admin_headers,
                    json={"username": "other", "password": "Sup3rSecret!x",
                          "email": "admin@aida.local"})
    assert r.status_code == 409


def test_create_user_validation(client, db, admin_headers):
    base = {"password": "Sup3rSecret!x"}
    assert client.post("/api/users", headers=admin_headers,
                       json={**base, "username": "ab"}).status_code == 422
    assert client.post("/api/users", headers=admin_headers,
                       json={**base, "username": "okname", "password": "short"}).status_code == 422
    assert client.post("/api/users", headers=admin_headers,
                       json={**base, "username": "okname", "role": "root"}).status_code == 422


# --- update ----------------------------------------------------------------------

def test_update_user_fields(client, db, admin_headers):
    target = make_user(db, "victim", "viewer")
    r = client.patch(f"/api/users/{target.id}", headers=admin_headers,
                     json={"email": "renamed@corp.example", "role": "auditor",
                           "is_active": False})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "renamed@corp.example"
    assert body["role"] == "auditor"
    assert body["is_active"] is False


def test_update_user_not_found(client, db, admin_headers):
    assert client.patch("/api/users/9999", headers=admin_headers,
                        json={"role": "viewer"}).status_code == 404


def test_update_user_email_conflict(client, db, admin_headers):
    other = make_user(db, "other", "viewer")
    r = client.patch(f"/api/users/{other.id}", headers=admin_headers,
                     json={"email": "admin@aida.local"})
    assert r.status_code == 409


def test_admin_cannot_demote_self(client, db, admin_headers, admin_user):
    r = client.patch(f"/api/users/{admin_user.id}", headers=admin_headers,
                     json={"role": "viewer"})
    assert r.status_code == 400
    assert "demote yourself" in r.json()["detail"]


def test_admin_cannot_deactivate_self(client, db, admin_headers, admin_user):
    r = client.patch(f"/api/users/{admin_user.id}", headers=admin_headers,
                     json={"is_active": False})
    assert r.status_code == 400


def test_admin_can_manage_other_admins(client, db, admin_headers):
    second = make_user(db, "second", "admin")
    # Demote + deactivate another admin is allowed (the caller still remains)
    assert client.patch(f"/api/users/{second.id}", headers=admin_headers,
                        json={"role": "viewer"}).status_code == 200
    assert client.patch(f"/api/users/{second.id}", headers=admin_headers,
                        json={"is_active": False}).status_code == 200


def test_update_invalid_role_rejected_by_schema(client, db, admin_headers):
    target = make_user(db, "schemacheck", "viewer")
    assert client.patch(f"/api/users/{target.id}", headers=admin_headers,
                        json={"role": "superuser"}).status_code == 422


# --- reset password ----------------------------------------------------------------

def test_reset_password_flow(client, db, admin_headers):
    target = make_user(db, "resetme", "viewer", "OldPass123!")
    r = client.post(f"/api/users/{target.id}/reset-password", headers=admin_headers,
                    json={"new_password": "BrandNewPass99!"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True

    # The new password authenticates; the old one no longer does
    assert client.post("/api/auth/login",
                       json={"username": "resetme", "password": "OldPass123!"}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": "resetme", "password": "BrandNewPass99!"}).status_code == 200


def test_reset_password_not_found_and_validation(client, db, admin_headers):
    assert client.post("/api/users/4242/reset-password", headers=admin_headers,
                       json={"new_password": "BrandNewPass99!"}).status_code == 404
    assert client.post("/api/users/4242/reset-password", headers=admin_headers,
                       json={"new_password": "short"}).status_code == 422


# --- delete ------------------------------------------------------------------------

def test_delete_user(client, db, admin_headers):
    target = make_user(db, "goner", "viewer")
    r = client.delete(f"/api/users/{target.id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.query(User).filter(User.username == "goner").count() == 0
    assert client.post("/api/auth/login",
                       json={"username": "goner", "password": "Sup3rSecret!x"}).status_code == 401

    row = (db.query(AuditLog).filter(AuditLog.action == "user.deleted")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None and row.detail["username"] == "goner"


def test_delete_user_not_found(client, db, admin_headers):
    assert client.delete("/api/users/9999", headers=admin_headers).status_code == 404


def test_admin_cannot_delete_self(client, db, admin_headers, admin_user):
    assert client.delete(f"/api/users/{admin_user.id}",
                         headers=admin_headers).status_code == 400


def test_viewer_cannot_delete(client, db, viewer_headers):
    target = make_user(db, "stillhere", "viewer")
    assert client.delete(f"/api/users/{target.id}",
                         headers=viewer_headers).status_code == 403
    assert db.query(User).filter(User.username == "stillhere").count() == 1
