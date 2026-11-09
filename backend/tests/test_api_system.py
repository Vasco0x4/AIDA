"""
Integration tests for system endpoints (api/system.py).

Status/info, platform settings GET defaults + PUT validation matrix, Exegol
container listing (docker discovery mocked — hermetic), tool-usage stats, and
the open-folder path allowlist. All Exegol/docker interactions are stubbed via
the module-level ``container_service``.
"""
from __future__ import annotations

import os

import pytest

import api.system as system_api
from config import settings
from middleware.rate_limit import limiter
from models.assessment import Assessment
from models.command_history import CommandHistory


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


def _patch_containers(monkeypatch, containers=None, error=None):
    async def fake_discover(force_refresh: bool = False):
        if error:
            raise error
        return containers or []
    monkeypatch.setattr(system_api.container_service, "discover_containers",
                        fake_discover)


def _make_assessment(db, name="asmt") -> Assessment:
    a = Assessment(name=name, scope="127.0.0.1", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _cmd(db, assessment_id: int, command: str, success=True) -> CommandHistory:
    row = CommandHistory(assessment_id=assessment_id, command=command,
                         success=success, returncode=0 if success else 2)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- status / info ---------------------------------------------------------------

def test_system_status_connected(db, client, admin_headers, monkeypatch):
    _patch_containers(monkeypatch,
                      containers=[{"name": settings.DEFAULT_CONTAINER_NAME,
                                   "status": "running"}])
    r = client.get("/api/system/status", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["backend"]["status"] == "connected"
    assert body["backend"]["version"] == settings.VERSION
    assert body["database"]["connected"] is True
    assert body["database"]["version"].count(".") >= 1
    assert body["exegol"]["status"] == "connected"
    assert body["exegol"]["running"] is True
    assert body["exegol"]["container"] == settings.DEFAULT_CONTAINER_NAME


def test_system_status_exegol_variants(db, client, admin_headers, monkeypatch):
    # No containers at all → not_found
    _patch_containers(monkeypatch, containers=[])
    body = client.get("/api/system/status", headers=admin_headers).json()
    assert body["exegol"] == {"status": "not_found", "running": False, "container": ""}

    # Default container absent, another one present → first container used
    _patch_containers(monkeypatch,
                      containers=[{"name": "other-box", "status": "exited"}])
    body = client.get("/api/system/status", headers=admin_headers).json()
    assert body["exegol"]["container"] == "other-box"
    assert body["exegol"]["running"] is False

    # Discovery blows up → error status, endpoint still 200
    _patch_containers(monkeypatch, error=RuntimeError("docker socket gone"))
    body = client.get("/api/system/status", headers=admin_headers).json()
    assert body["exegol"]["status"] == "error"


def test_system_info(db, client, admin_headers):
    r = client.get("/api/system/info", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["platform_name"] == settings.PROJECT_NAME
    assert body["version"] == settings.VERSION
    assert body["container_name"] == settings.DEFAULT_CONTAINER_NAME
    assert body["workspace_base"] == settings.CONTAINER_WORKSPACE_BASE


def test_system_status_requires_auth(client, db):
    assert client.get("/api/system/status").status_code == 401


# --- settings: GET -----------------------------------------------------------------

def test_get_setting_defaults(db, client, admin_headers):
    cases = {
        "command_timeout": str(settings.COMMAND_TIMEOUT),
        "output_max_length": "5000",
        "mcp_http_enabled": "false",
        "mcp_http_network_policy": "localhost",
        "command_history_limit": "10",
        "theme": "light",
        "primary_color": "cyan",
        "telegram_bot_enabled": "false",
    }
    for key, expected in cases.items():
        r = client.get(f"/api/system/settings/{key}", headers=admin_headers)
        assert r.status_code == 200, key
        assert r.json()["value"] == expected, key
    assert client.get("/api/system/settings/no_such_key",
                      headers=admin_headers).status_code == 404


def test_get_stored_setting(db, client, admin_headers):
    from models.platform_settings import PlatformSettings
    db.add(PlatformSettings(key="custom_flag", value="on",
                            description="A custom flag"))
    db.commit()
    r = client.get("/api/system/settings/custom_flag", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"key": "custom_flag", "value": "on",
                        "description": "A custom flag"}


def test_settings_readable_by_viewer(client, db, viewer_headers):
    assert client.get("/api/system/settings/command_timeout",
                      headers=viewer_headers).status_code == 200


# --- settings: PUT validation matrix -------------------------------------------------

def test_put_setting_requires_admin(client, db, viewer_headers):
    r = client.put("/api/system/settings/command_timeout",
                   headers=viewer_headers, json={"value": "90"})
    assert r.status_code == 403


def test_put_setting_roundtrip(db, client, admin_headers):
    r = client.put("/api/system/settings/command_timeout",
                   headers=admin_headers, json={"value": "90"})
    assert r.status_code == 200
    assert r.json()["value"] == "90"
    again = client.get("/api/system/settings/command_timeout",
                       headers=admin_headers)
    assert again.json()["value"] == "90"


@pytest.mark.parametrize("key,value", [
    # command_timeout: integer, 30..1800
    ("command_timeout", "abc"), ("command_timeout", "10"), ("command_timeout", "9999"),
    # output length variants: -1 or 500..100000
    ("output_max_length", "100"), ("output_max_length", "abc"),
    ("python_exec_output_max_length", "499"),
    ("http_request_output_max_length", "100001"),
    # command history limit: 0..100
    ("command_history_limit", "-1"), ("command_history_limit", "101"),
    ("command_history_limit", "abc"),
    # mcp flags
    ("mcp_http_enabled", "yes"),
    ("mcp_http_network_policy", "internet"),
    # file size limits: 1..2000 MB
    ("max_context_file_size", "0"), ("max_context_file_size", "abc"),
    ("max_source_zip_size", "5000"),
])
def test_put_setting_rejects_bad_values(db, client, admin_headers, key, value):
    r = client.put(f"/api/system/settings/{key}", headers=admin_headers,
                   json={"value": value})
    assert r.status_code == 400, (key, value)


@pytest.mark.parametrize("key,value,expected", [
    ("command_timeout", "120", "120"),
    ("output_max_length", "-1", "-1"),
    ("python_exec_output_max_length", "2000", "2000"),
    ("http_request_output_max_length", "600", "600"),
    ("command_history_limit", "50", "50"),
    ("mcp_http_enabled", "TRUE", "true"),          # normalized to lowercase
    ("mcp_http_network_policy", "lan", "lan"),
    ("max_context_file_size", "25", "25"),
    ("max_source_zip_size", "100", "100"),
])
def test_put_setting_accepts_good_values(db, client, admin_headers,
                                         key, value, expected):
    r = client.put(f"/api/system/settings/{key}", headers=admin_headers,
                   json={"value": value})
    assert r.status_code == 200, key
    assert r.json()["value"] == expected, key


def test_put_setting_container_name(db, client, admin_headers, monkeypatch):
    _patch_containers(monkeypatch, containers=[{"name": "exegol-test",
                                                "status": "running"}])
    original = settings.DEFAULT_CONTAINER_NAME
    original_current = system_api.container_service.current_container
    try:
        # Unknown container → 404
        r = client.put("/api/system/settings/container_name",
                       headers=admin_headers, json={"value": "ghost-box"})
        assert r.status_code == 404
        # Empty → 400
        r = client.put("/api/system/settings/container_name",
                       headers=admin_headers, json={"value": "   "})
        assert r.status_code == 400
        # Known container → selected + becomes the platform default
        r = client.put("/api/system/settings/container_name",
                       headers=admin_headers, json={"value": "exegol-test"})
        assert r.status_code == 200
        assert r.json()["value"] == "exegol-test"
        assert settings.DEFAULT_CONTAINER_NAME == "exegol-test"
        assert system_api.container_service.current_container == "exegol-test"
    finally:
        settings.DEFAULT_CONTAINER_NAME = original
        system_api.container_service.current_container = original_current


# --- exegol container listing ---------------------------------------------------------

def test_list_exegol_containers(db, client, admin_headers, monkeypatch):
    _patch_containers(monkeypatch,
                      containers=[{"name": "box1", "status": "running"}])
    r = client.get("/api/system/exegol/containers", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["containers"][0]["name"] == "box1"
    assert body["current"] == settings.DEFAULT_CONTAINER_NAME


def test_list_exegol_containers_error(db, client, admin_headers, monkeypatch):
    _patch_containers(monkeypatch, error=RuntimeError("boom"))
    assert client.get("/api/system/exegol/containers",
                      headers=admin_headers).status_code == 500


# --- tool usage stats -----------------------------------------------------------------

def test_tool_usage_stats_empty(db, client, admin_headers):
    r = client.get("/api/system/tool-usage-stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_commands"] == 0
    assert body["most_used_tools"] == []
    assert body["by_assessment"] == []


def test_tool_usage_stats_aggregation(db, client, admin_headers):
    a1 = _make_assessment(db, "alpha")
    a2 = _make_assessment(db, "beta")
    _cmd(db, a1.id, "nmap -sV target.example")
    _cmd(db, a1.id, "nmap -p- target.example")
    _cmd(db, a1.id, "sqlmap -u http://target.example/?id=1", success=False)
    _cmd(db, a2.id, "weirdtool scan stuff")

    r = client.get("/api/system/tool-usage-stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_commands"] == 4
    assert body["total_assessments"] == 2

    tools = {t["tool"]: t for t in body["most_used_tools"]}
    assert tools["nmap"]["count"] == 2
    assert tools["nmap"]["success_rate"] == 100.0
    assert tools["sqlmap"]["success_rate"] == 0.0
    # Unknown tools land in the "other" category and are surfaced
    assert "weirdtool" in body["unknown_tools"]
    assert "recon" in body["tool_categories"]

    by_name = {a["assessment_name"]: a for a in body["by_assessment"]}
    assert by_name["alpha"]["total_commands"] == 3
    assert len(by_name["alpha"]["top_tools"]) <= 5


def test_tool_usage_stats_filters(db, client, admin_headers):
    a = _make_assessment(db, "filtered")
    _cmd(db, a.id, "nmap -sV x", success=True)
    _cmd(db, a.id, "ffuf /wordlist.txt", success=False)

    # only successful commands
    body = client.get("/api/system/tool-usage-stats",
                      headers=admin_headers, params={"include_failed": "false"}).json()
    assert body["total_commands"] == 1
    assert body["most_used_tools"][0]["tool"] == "nmap"

    # scoped to one assessment
    body = client.get("/api/system/tool-usage-stats",
                      headers=admin_headers, params={"assessment_id": a.id}).json()
    assert body["total_commands"] == 2

    # top_n clamped to >= 1
    body = client.get("/api/system/tool-usage-stats",
                      headers=admin_headers, params={"top_n": 0}).json()
    assert len(body["most_used_tools"]) == 1


# --- open folder ------------------------------------------------------------------------

def test_open_folder_denies_outside_paths(db, client, admin_headers):
    r = client.post("/api/system/open-folder", headers=admin_headers,
                    json={"path": "/etc"})
    assert r.status_code == 403


def test_open_folder_container_path(db, client, admin_headers):
    r = client.post("/api/system/open-folder", headers=admin_headers,
                    json={"path": f"{settings.CONTAINER_WORKSPACE_BASE}/jobs/1"})
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_open_folder_missing_host_path(db, client, admin_headers):
    home = os.path.expanduser("~")
    r = client.post("/api/system/open-folder", headers=admin_headers,
                    json={"path": f"{home}/.exegol/workspaces/definitely-missing"})
    assert r.status_code == 404


def test_open_folder_requires_auditor(client, db, viewer_headers):
    r = client.post("/api/system/open-folder", headers=viewer_headers,
                    json={"path": "/workspace/x"})
    assert r.status_code == 403
