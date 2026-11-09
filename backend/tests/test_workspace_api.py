"""api/workspace.py — open/recreate/resolve endpoints; the workspace_service
singleton's docker-touching methods are faked on the instance."""
from __future__ import annotations

import pytest

import services.workspace_service as ws_mod
from config import settings
from models.assessment import Assessment
from models.platform_settings import PlatformSettings


class FakeWS:
    """Records calls; individual tests override the result attrs."""

    validate = True
    host_path = "/host/exegol/ws"
    open_result = {"success": True, "os": "Darwin"}

    def __init__(self):
        self.calls = []

    async def validate_workspace_in_container(self, container_path, container_name):
        self.calls.append(("validate", container_path, container_name))
        return FakeWS.validate

    async def get_host_workspace_path(self, container_path, container_name):
        self.calls.append(("host_path", container_path, container_name))
        return FakeWS.host_path

    async def open_folder_in_explorer(self, host_path):
        self.calls.append(("open", host_path))
        return dict(FakeWS.open_result, **{})

    async def _run_command(self, cmd):
        self.calls.append(("run", list(cmd)))
        return {"returncode": 0, "stdout": "running\n", "stderr": ""}


@pytest.fixture(autouse=True)
def fake_ws(monkeypatch):
    fake = FakeWS()
    FakeWS.validate = True
    FakeWS.host_path = "/host/exegol/ws"
    FakeWS.open_result = {"success": True, "os": "Darwin"}
    # patch the singleton instance the API module imported
    monkeypatch.setattr(ws_mod.workspace_service, "validate_workspace_in_container",
                        fake.validate_workspace_in_container)
    monkeypatch.setattr(ws_mod.workspace_service, "get_host_workspace_path",
                        fake.get_host_workspace_path)
    monkeypatch.setattr(ws_mod.workspace_service, "open_folder_in_explorer",
                        fake.open_folder_in_explorer)
    monkeypatch.setattr(ws_mod.workspace_service, "_run_command", fake._run_command)
    return fake


def _seed(db, workspace_path="/workspace/A", container_name="exegol-a"):
    asn = Assessment(name="Asn A", scope="t.example", workspace_path=workspace_path,
                     container_name=container_name)
    db.add(asn)
    db.commit()
    db.refresh(asn)
    return asn


# ── open root workspace ───────────────────────────────────────────────────────

def test_open_root_requires_auth(client, db):
    res = client.post("/api/workspace/open")
    assert res.status_code == 401


def test_open_root_not_in_container(client, db, admin_headers, fake_ws):
    FakeWS.validate = False
    res = client.post("/api/workspace/open", headers=admin_headers)
    assert res.status_code == 404
    assert "Is the container running?" in res.json()["detail"]


def test_open_root_success_and_unopenable(client, db, admin_headers, fake_ws):
    res = client.post("/api/workspace/open", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body == {"success": True, "opened": True,
                    "container_name": fake_ws.calls[0][2],
                    "container_path": "/workspace",
                    "host_path": "/host/exegol/ws", "os": "Darwin",
                    "message": "Folder opened"}
    # explorer failure (Docker env) still returns 200 with path info
    FakeWS.open_result = {"success": False, "os": "Linux", "error": "no GUI"}
    res = client.post("/api/workspace/open", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["opened"] is False
    assert body["message"] == "Path: /host/exegol/ws (copy to open manually)"


def test_open_root_host_path_failure(client, db, admin_headers, fake_ws):
    FakeWS.host_path = None
    res = client.post("/api/workspace/open", headers=admin_headers)
    assert res.status_code == 500


# ── open assessment workspace ─────────────────────────────────────────────────

def test_open_assessment_not_found(client, db, admin_headers):
    res = client.post("/api/workspace/assessments/999999/open", headers=admin_headers)
    assert res.status_code == 404


def test_open_assessment_no_workspace(client, db, admin_headers):
    asn = _seed(db, workspace_path=None)
    res = client.post(f"/api/workspace/assessments/{asn.id}/open", headers=admin_headers)
    assert res.status_code == 400
    assert "no workspace" in res.json()["detail"]


def test_open_assessment_host_exists(client, db, admin_headers, fake_ws, tmp_path):
    host_dir = tmp_path / "ws"
    host_dir.mkdir()
    FakeWS.host_path = str(host_dir)
    asn = _seed(db)
    res = client.post(f"/api/workspace/assessments/{asn.id}/open", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["container_name"] == "exegol-a"
    assert body["container_path"] == "/workspace/A"
    assert body["host_path"] == str(host_dir)
    # found on host → container never queried
    assert [c[0] for c in fake_ws.calls] == ["host_path", "open"]


def test_open_assessment_validates_in_container(client, db, admin_headers,
                                                fake_ws, tmp_path):
    FakeWS.host_path = str(tmp_path / "missing")  # not on host
    asn = _seed(db)
    res = client.post(f"/api/workspace/assessments/{asn.id}/open", headers=admin_headers)
    assert res.status_code == 200
    assert [c[0] for c in fake_ws.calls] == ["host_path", "validate", "open"]


def test_open_assessment_auto_recreates_missing(client, db, admin_headers,
                                                fake_ws, tmp_path):
    FakeWS.host_path = str(tmp_path / "missing")
    FakeWS.validate = False
    asn = _seed(db)
    res = client.post(f"/api/workspace/assessments/{asn.id}/open", headers=admin_headers)
    assert res.status_code == 200
    run_calls = [c for c in fake_ws.calls if c[0] == "run"]
    assert run_calls and run_calls[0][1][:3] == ["docker", "exec", "exegol-a"]
    mkdir = run_calls[0][1][-1]
    assert mkdir.startswith("mkdir -p /workspace/A")
    for sub in ("recon", "exploits", "loot", "notes", "scripts", "context"):
        assert f"/A/{sub}" in mkdir


def test_open_assessment_recreation_failure(client, db, admin_headers,
                                             fake_ws, tmp_path, monkeypatch):
    FakeWS.host_path = str(tmp_path / "missing")
    FakeWS.validate = False

    async def failing_run(cmd):
        return {"returncode": 1, "stdout": "", "stderr": "container not running"}

    monkeypatch.setattr(ws_mod.workspace_service, "_run_command", failing_run)
    asn = _seed(db)
    res = client.post(f"/api/workspace/assessments/{asn.id}/open", headers=admin_headers)
    assert res.status_code == 500
    assert "Failed to recreate workspace" in res.json()["detail"]
    assert "container not running" in res.json()["detail"]


def test_recreate_workspace(client, db, admin_headers, monkeypatch):
    from api import workspace as api_ws

    asn = _seed(db, workspace_path="/workspace/old", container_name="old-c")
    db.add(PlatformSettings(key="container_name", value="new-c"))
    db.commit()

    created = {}

    class FakeContainerService:
        def __init__(self):
            self.current_container = None

        async def create_workspace(self, assessment_name, db=None):
            created["name"] = assessment_name
            created["container"] = self.current_container
            return {"workspace_path": "/workspace/new", "container_name": "new-c"}

    monkeypatch.setattr(api_ws, "ContainerService", FakeContainerService)
    res = client.post(f"/api/workspace/assessments/{asn.id}/recreate",
                      headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["workspace_path"] == "/workspace/new"
    assert body["container_name"] == "new-c"
    assert "recreated in container 'new-c'" in body["message"]
    assert created == {"name": "Asn A", "container": "new-c"}
    db.refresh(asn)
    assert asn.workspace_path == "/workspace/new"
    assert asn.container_name == "new-c"


def test_recreate_workspace_not_found(client, db, admin_headers, monkeypatch):
    from api import workspace as api_ws

    monkeypatch.setattr(api_ws, "ContainerService", object)
    res = client.post("/api/workspace/assessments/999999/recreate",
                      headers=admin_headers)
    assert res.status_code == 404


# ── resolve ───────────────────────────────────────────────────────────────────

def test_resolve_requires_params(client, db, admin_headers):
    res = client.get("/api/workspace/resolve", headers=admin_headers)
    assert res.status_code == 400
    assert "Provide either" in res.json()["detail"]


def test_resolve_not_found(client, db, admin_headers):
    res = client.get("/api/workspace/resolve", params={"assessment_id": 999999},
                     headers=admin_headers)
    assert res.status_code == 404


def test_resolve_by_id_running(client, db, admin_headers, fake_ws):
    asn = _seed(db)
    res = client.get("/api/workspace/resolve", params={"assessment_id": asn.id},
                     headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["assessment_name"] == "Asn A"
    assert body["container_name"] == "exegol-a"
    assert body["container_path"] == "/workspace/A"
    assert body["host_path"] == "/host/exegol/ws"
    assert body["exists"] is True
    assert body["container_running"] is True  # fake inspect says "running"
    # inspect ran against the assessment's container
    run_calls = [c for c in fake_ws.calls if c[0] == "run"]
    assert run_calls[0][1][:2] == ["docker", "inspect"]


def test_resolve_by_name_case_insensitive_and_container_override(
        client, db, admin_headers, fake_ws):
    asn = _seed(db)
    res = client.get("/api/workspace/resolve",
                     params={"assessment_name": "  asn a ", "container": "other-c"},
                     headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["assessment_id"] == asn.id
    assert body["container_name"] == "other-c"


def test_resolve_stopped_container_uses_host_check(client, db, admin_headers,
                                                    fake_ws, monkeypatch, tmp_path):
    host_dir = tmp_path / "ws"
    host_dir.mkdir()
    FakeWS.host_path = str(host_dir)

    async def stopped(cmd):
        return {"returncode": 0, "stdout": "exited\n", "stderr": ""}

    monkeypatch.setattr(ws_mod.workspace_service, "_run_command", stopped)
    asn = _seed(db)
    res = client.get("/api/workspace/resolve", params={"assessment_id": asn.id},
                     headers=admin_headers)
    body = res.json()
    assert body["container_running"] is False
    assert body["exists"] is True  # host dir present
    # container never queried for validation
    assert not [c for c in fake_ws.calls if c[0] == "validate"]


def test_resolve_default_workspace_path(client, db, admin_headers, fake_ws):
    asn = _seed(db, workspace_path=None, container_name=None)
    res = client.get("/api/workspace/resolve", params={"assessment_id": asn.id},
                     headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["container_path"] == "/workspace/Asn A"  # constructed default
    assert body["container_name"] == settings.DEFAULT_CONTAINER_NAME


def test_resolve_host_path_failure(client, db, admin_headers, fake_ws):
    FakeWS.host_path = None
    asn = _seed(db)
    res = client.get("/api/workspace/resolve", params={"assessment_id": asn.id},
                     headers=admin_headers)
    assert res.status_code == 500
    assert "Failed to resolve host path" in res.json()["detail"]
