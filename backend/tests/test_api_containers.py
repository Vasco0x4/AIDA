"""
Container management API — /api/containers.

Docker boundaries (discover/select/create-workspace) are stubbed at the
ContainerService layer; the workspace GET/POST routes' DB behavior (404s,
assessment updates) is tested for real.
"""
from __future__ import annotations

import pytest

from models.assessment import Assessment


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from slowapi import Limiter
    import main as main_mod
    monkeypatch.setattr(main_mod.app.state, "limiter",
                        Limiter(key_func=lambda r: "test", storage_uri="memory://"))


@pytest.fixture()
def assessment(db):
    a = Assessment(name="cont-assess", scope="example.com")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_list_containers(client, monkeypatch, admin_headers):
    from services.container_service import ContainerService

    async def _fake(self, force_refresh=False):
        return [{"name": "exegol-1", "image": "exegol:full", "state": "running"},
                {"name": "exegol-2", "image": "exegol:lite", "state": "exited"}]

    monkeypatch.setattr(ContainerService, "discover_containers", _fake)
    r = client.get("/api/containers", headers=admin_headers)
    assert r.status_code == 200
    assert [c["name"] for c in r.json()] == ["exegol-1", "exegol-2"]


def test_list_containers_requires_auth(client):
    assert client.get("/api/containers").status_code == 401


def test_select_container(client, monkeypatch, admin_headers):
    from services.container_service import ContainerService
    seen = {}

    async def _fake(self, container_name):
        seen["name"] = container_name
        return {"success": True, "selected": container_name}

    monkeypatch.setattr(ContainerService, "select_container", _fake)
    r = client.post("/api/containers/select", headers=admin_headers,
                    params={"container_name": "exegol-1"})
    assert r.status_code == 200
    assert r.json() == {"success": True, "selected": "exegol-1"}
    assert seen == {"name": "exegol-1"}


def test_select_container_requires_name_422(client, admin_headers):
    r = client.post("/api/containers/select", headers=admin_headers)
    assert r.status_code == 422


def test_get_workspace_path(client, db, admin_headers, assessment):
    assessment.workspace_path = "/workspace/cont-assess"
    db.commit()
    r = client.get(f"/api/containers/workspace/{assessment.id}",
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"assessment_id": assessment.id,
                        "workspace_path": "/workspace/cont-assess"}


def test_get_workspace_unknown_assessment_404(client, admin_headers):
    assert client.get("/api/containers/workspace/555",
                      headers=admin_headers).status_code == 404


def test_create_workspace_updates_assessment(client, db, admin_headers,
                                             monkeypatch, assessment):
    from services.container_service import ContainerService

    async def _fake(self, assessment_name, db=None):
        assert assessment_name == "cont-assess"
        return {"workspace_path": f"/workspace/{assessment_name}",
                "container_name": "exegol-1"}

    monkeypatch.setattr(ContainerService, "create_workspace", _fake)
    r = client.post(f"/api/containers/workspace/{assessment.id}",
                    headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["workspace_path"] == "/workspace/cont-assess"
    assert body["container_name"] == "exegol-1"
    assert "successfully" in body["message"]

    db.refresh(assessment)
    assert assessment.workspace_path == "/workspace/cont-assess"
    assert assessment.container_name == "exegol-1"


def test_create_workspace_unknown_assessment_404(client, admin_headers):
    assert client.post("/api/containers/workspace/556",
                       headers=admin_headers).status_code == 404


def test_container_writes_require_auditor(client, viewer_headers):
    assert client.post("/api/containers/select", headers=viewer_headers,
                       params={"container_name": "x"}).status_code == 403
