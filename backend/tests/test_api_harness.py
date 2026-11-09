"""Harness sanity: the client fixture exercises the real app + RBAC."""
from __future__ import annotations

from models.assessment import Assessment


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_protected_route_requires_token(client, db):
    r = client.get("/api/assessments")
    assert r.status_code == 401


def test_admin_can_list_assessments(client, db, admin_headers):
    db.add(Assessment(name="harness", scope="127.0.0.1", status="active"))
    db.commit()
    r = client.get("/api/assessments", headers=admin_headers)
    assert r.status_code == 200
    names = [a.get("name") for a in r.json()]
    assert "harness" in names
