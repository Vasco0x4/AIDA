"""
Pending Commands + Command Settings API.

- /api/command-settings: get/put with every validation branch, keyword add/remove.
- /api/pending-commands: list/count/get with the auto-timeout sweeper, the MCP
  create endpoint, and the approve/reject flows (container execution stubbed;
  exploit-class admin gate; approver identity = the authenticated user; python
  and http command routing; execution failure marks the command failed).

The approve/reject endpoints run on get_async_db: happy paths call the endpoint
functions directly (TestClient + SQLAlchemy-async loses coverage attribution
after the first greenlet await — behavior via HTTP is still asserted for the
auth-gated paths).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from models.assessment import Assessment
from models.pending_command import PendingCommand
from models.platform_settings import PlatformSettings


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from slowapi import Limiter
    import main as main_mod
    monkeypatch.setattr(main_mod.app.state, "limiter",
                        Limiter(key_func=lambda r: "test", storage_uri="memory://"))


@pytest.fixture(autouse=True)
def _audit_sessions(monkeypatch, runtime_sessions):
    """approve/reject/reject audit() opens SessionLocal() — keep it on test DB."""
    import api.pending_commands as pc
    monkeypatch.setattr(pc, "SessionLocal", runtime_sessions)


@pytest.fixture()
def async_sessions(monkeypatch, engine):
    url = engine.url.render_as_string(hide_password=False).replace(
        "postgresql://", "postgresql+asyncpg://", 1)
    eng = create_async_engine(url, poolclass=NullPool)
    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("database.AsyncSessionLocal", maker)
    yield maker
    import asyncio
    asyncio.run(eng.dispose())


@pytest.fixture()
def assessment(db):
    a = Assessment(name="pc-assessment", scope="example.com")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture()
def users(db):
    from auth import hash_password
    from models.user import User
    admin = User(username="pc-admin", email="pc-admin@t.l",
                 hashed_password=hash_password("pw"), role="admin",
                 is_active=True)
    auditor = User(username="pc-auditor", email="pc-aud@t.l",
                   hashed_password=hash_password("pw"), role="auditor",
                   is_active=True)
    db.add_all([admin, auditor])
    db.commit()
    return {"admin": admin, "auditor": auditor}


@pytest.fixture()
def auditor_headers(users):
    from auth import create_access_token
    return {"Authorization":
            f"Bearer {create_access_token(users['auditor'].id, 'pc-auditor')}"}


def _pending(db, assessment, command="rm -rf /tmp/x", **kw):
    row = PendingCommand(
        assessment_id=assessment.id, command=command,
        phase=kw.pop("phase", "recon"),
        command_type=kw.pop("command_type", "shell"),
        status=kw.pop("status", "pending"),
        risk_level=kw.pop("risk_level", "normal"),
        risk_reason=kw.pop("risk_reason", None),
        matched_keywords=kw.pop("matched_keywords", ["rm"]),
        created_at=kw.pop("created_at", datetime.utcnow()),
        timeout_seconds=kw.pop("timeout_seconds", None))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _exec_ok(stdout="done", **kw):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=0,
                           success=True, **kw)


def _request_for(user, path="/api/pending-commands/x/approve"):
    """Real starlette Request carrying the RBAC-resolved user."""
    req = Request({"type": "http", "method": "POST", "path": path,
                   "headers": [], "query_string": "",
                   "client": ("testclient", 123)})
    req.state.user = user
    return req


# ================================================================== settings
def test_settings_defaults(client, db, admin_headers):
    r = client.get("/api/command-settings", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["execution_mode"] == "open"
    assert body["timeout_seconds"] == 30
    assert "rm" in body["filter_keywords"] and "sudo" in body["filter_keywords"]
    assert body["http_method_rules"] == {}
    assert body["exploit_approval"] == "on"
    assert body["exploit_admin_approval"] is True
    assert body["exploit_approval_timeout"] == 600


def test_settings_put_updates_every_field(client, db, admin_headers):
    r = client.put("/api/command-settings", headers=admin_headers, json={
        "execution_mode": "filter",
        "filter_keywords": ["shred", "wipe"],
        "timeout_seconds": 120,
        "http_method_rules": {"DELETE": "require_approval", "GET": "inherit"},
        "exploit_approval": "off",
        "exploit_admin_approval": False,
        "exploit_approval_timeout": 900})
    assert r.status_code == 200
    body = r.json()
    assert body["execution_mode"] == "filter"
    assert body["filter_keywords"] == ["shred", "wipe"]
    assert body["timeout_seconds"] == 120
    assert body["http_method_rules"] == {"DELETE": "require_approval",
                                         "GET": "inherit"}
    assert body["exploit_approval"] == "off"
    assert body["exploit_admin_approval"] is False
    assert body["exploit_approval_timeout"] == 900

    keys = {k for (k,) in db.query(PlatformSettings.key).all()}
    assert {"command_execution_mode", "command_filter_keywords",
            "command_timeout_seconds", "command_http_method_rules",
            "exploit_approval"} <= keys


def test_settings_put_partial_only_sends_given_fields(client, db, admin_headers):
    r = client.put("/api/command-settings", headers=admin_headers,
                   json={"execution_mode": "closed"})
    assert r.status_code == 200
    assert r.json()["execution_mode"] == "closed"
    assert r.json()["timeout_seconds"] == 30  # untouched default
    assert db.query(PlatformSettings).filter(
        PlatformSettings.key == "command_timeout_seconds").count() == 0


@pytest.mark.parametrize("payload,detail_bit", [
    ({"execution_mode": "permissive"}, "execution_mode"),
    ({"http_method_rules": {"POST": "always_allow"}}, "Invalid action"),
    ({"exploit_approval": "maybe"}, "exploit_approval"),
    ({"exploit_approval_timeout": 10}, "30..86400"),
    ({"exploit_approval_timeout": 100000}, "30..86400"),
])
def test_settings_put_validation_400(client, admin_headers, payload, detail_bit):
    r = client.put("/api/command-settings", headers=admin_headers,
                   json=payload)
    assert r.status_code == 400
    assert detail_bit in r.json()["detail"]


def test_settings_get_falls_back_to_defaults_on_db_error(
        client, db, admin_headers, monkeypatch):
    import api.pending_commands as pc

    def _boom(db):
        raise RuntimeError("settings table melted")

    monkeypatch.setattr(pc, "get_command_settings", _boom)
    r = client.get("/api/command-settings", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["execution_mode"] == "open"
    assert r.json()["timeout_seconds"] == 30


def test_settings_write_requires_admin(client, db, viewer_headers,
                                       auditor_headers):
    assert client.put("/api/command-settings", headers=viewer_headers,
                      json={"execution_mode": "closed"}).status_code == 403
    # The main settings route (PUT /api/command-settings, no trailing slash)
    # is admin-gated alongside the keyword sub-routes below.
    assert client.put("/api/command-settings", headers=auditor_headers,
                      json={"execution_mode": "closed"}).status_code == 403
    # sub-routes under /command-settings/ ARE admin-gated
    assert client.post("/api/command-settings/keywords", headers=auditor_headers,
                       json={"keyword": "x"}).status_code == 403
    assert client.post("/api/command-settings/keywords", headers=viewer_headers,
                       json={"keyword": "x"}).status_code == 403
    assert client.put("/api/command-settings", json={}).status_code == 401


def test_settings_keyword_add_and_remove(client, db, admin_headers):
    r = client.post("/api/command-settings/keywords", headers=admin_headers,
                    json={"keyword": "  SHRED  "})
    assert r.status_code == 200
    assert "shred" in r.json()["filter_keywords"]

    # idempotent: adding again doesn't duplicate
    r = client.post("/api/command-settings/keywords", headers=admin_headers,
                    json={"keyword": "shred"})
    assert r.json()["filter_keywords"].count("shred") == 1

    # blank keyword is a no-op
    r = client.post("/api/command-settings/keywords", headers=admin_headers,
                    json={"keyword": "   "})
    assert r.status_code == 200

    r = client.delete("/api/command-settings/keywords/shred",
                      headers=admin_headers)
    assert "shred" not in r.json()["filter_keywords"]
    # removing something absent stays a 200 no-op
    assert client.delete("/api/command-settings/keywords/never-there",
                         headers=admin_headers).status_code == 200


# ================================================================== listing
def test_pending_endpoints_require_auth(client):
    assert client.get("/api/pending-commands").status_code == 401
    assert client.get("/api/pending-commands/count").status_code == 401
    assert client.get("/api/pending-commands/1").status_code == 401


def test_list_pending_filters(client, db, admin_headers, assessment):
    other = Assessment(name="pc-other")
    db.add(other)
    db.commit()
    _pending(db, assessment, command="p1")
    _pending(db, assessment, command="p2", status="executed")
    _pending(db, other, command="p3")

    r = client.get("/api/pending-commands", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["pending_count"] == 2
    assert all(c["assessment_name"] for c in body["commands"])

    r = client.get("/api/pending-commands", params={"status_filter": "pending"},
                   headers=admin_headers)
    assert {c["command"] for c in r.json()["commands"]} == {"p1", "p3"}

    r = client.get("/api/pending-commands",
                   params={"assessment_id": assessment.id},
                   headers=admin_headers)
    assert {c["command"] for c in r.json()["commands"]} == {"p1", "p2"}


def test_expired_pending_commands_time_out_on_list(
        client, db, admin_headers, assessment):
    _pending(db, assessment, command="fresh")
    _pending(db, assessment, command="stale",
             created_at=datetime.utcnow() - timedelta(hours=2))
    _pending(db, assessment, command="stale-custom-timeout",
             created_at=datetime.utcnow() - timedelta(minutes=5),
             timeout_seconds=60)

    r = client.get("/api/pending-commands", headers=admin_headers)
    body = r.json()
    assert body["pending_count"] == 1
    statuses = {c["command"]: c["status"] for c in body["commands"]}
    assert statuses["fresh"] == "pending"
    assert statuses["stale"] == "timeout"
    assert statuses["stale-custom-timeout"] == "timeout"
    stale = [c for c in body["commands"] if c["command"] == "stale"][0]
    assert "exceeded 30s timeout" in stale["rejection_reason"]
    assert stale["resolved_at"] is not None


def test_count_endpoint_times_out_first(client, db, admin_headers, assessment):
    _pending(db, assessment, command="stale",
             created_at=datetime.utcnow() - timedelta(hours=1))
    _pending(db, assessment, command="fresh")
    r = client.get("/api/pending-commands/count", headers=admin_headers)
    assert r.json() == {"pending_count": 1}


def test_get_pending_command_by_id(client, db, admin_headers, assessment):
    row = _pending(db, assessment, command="single")
    r = client.get(f"/api/pending-commands/{row.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["command"] == "single"
    assert r.json()["assessment_name"] == "pc-assessment"
    assert client.get("/api/pending-commands/4242",
                      headers=admin_headers).status_code == 404


# ================================================================== create
def test_create_pending_command(client, db, admin_headers, assessment):
    r = client.post("/api/pending-commands/create", headers=admin_headers,
                    json={"assessment_id": assessment.id,
                          "command": "nuclei -u example.com",
                          "phase": "recon", "matched_keywords": []})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["timeout_seconds"] == 30   # from the (default) settings
    assert body["assessment_name"] == "pc-assessment"
    assert db.query(PendingCommand).one().command_type == "shell"


def test_create_pending_command_unknown_assessment_404(client, admin_headers):
    r = client.post("/api/pending-commands/create", headers=admin_headers,
                    json={"assessment_id": 987, "command": "ls"})
    assert r.status_code == 404


# ================================================================== approve
async def test_approve_shell_executes_and_records_identity(
        db, assessment, users, async_sessions, monkeypatch):
    from api.pending_commands import approve_command
    from schemas.pending_command import PendingCommandApprove
    from services.container_service import ContainerService
    row = _pending(db, assessment)
    seen = {}

    async def _fake(self, assessment_id, command, phase, db):
        seen.update(command=command, phase=phase)
        return _exec_ok(stdout="removed")

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake)
    async with async_sessions() as adb:
        res = await approve_command(row.id,
                                    PendingCommandApprove(approved_by="spoofed"),
                                    _request_for(users["admin"]), db=adb)
    assert res.status == "executed"
    assert res.resolved_by == "pc-admin"        # identity wins over "spoofed"
    assert res.execution_result["stdout"] == "removed"
    assert res.assessment_name == "pc-assessment"
    assert seen["command"] == "rm -rf /tmp/x"


async def test_approve_routes_python_and_http_types(
        db, assessment, users, async_sessions, monkeypatch):
    from api.pending_commands import approve_command
    from schemas.pending_command import PendingCommandApprove
    from services.container_service import ContainerService
    py = _pending(db, assessment, command="print('hi')", command_type="python")
    http = _pending(db, assessment,
                    command='{"url": "http://x", "method": "GET"}',
                    command_type="http")
    calls = []

    async def _fake_py(self, assessment_id, code, phase, db):
        calls.append(("python", code))
        return _exec_ok()

    async def _fake_http(self, assessment_id, params, db):
        calls.append(("http", params.url, params.method))
        return _exec_ok()

    monkeypatch.setattr(ContainerService, "execute_and_log_python", _fake_py)
    monkeypatch.setattr(ContainerService, "execute_and_log_http_request",
                        _fake_http)
    async with async_sessions() as adb:
        res = await approve_command(py.id, PendingCommandApprove(),
                                    _request_for(users["admin"]), db=adb)
        assert res.status == "executed"
        res = await approve_command(http.id, PendingCommandApprove(),
                                    _request_for(users["admin"]), db=adb)
        assert res.status == "executed"
    assert calls == [("python", "print('hi')"), ("http", "http://x", "GET")]


async def test_approve_exploit_class_requires_admin(
        db, assessment, users, async_sessions):
    from api.pending_commands import approve_command
    from schemas.pending_command import PendingCommandApprove
    from fastapi import HTTPException
    row = _pending(db, assessment, command="sqlmap -u http://x --batch",
                   risk_level="high", risk_reason="sqlmap-exploitation")
    # exploit_admin_approval unset → defaults ON → auditor denied…
    async with async_sessions() as adb:
        with pytest.raises(HTTPException) as ei:
            await approve_command(row.id, PendingCommandApprove(),
                                  _request_for(users["auditor"]), db=adb)
        assert ei.value.status_code == 403
        await adb.rollback()
    # …and the denial left it pending (an admin can still sign off).
    db.refresh(row)
    assert row.status == "pending"


async def test_approve_exploit_class_admin_allowed(
        db, assessment, users, async_sessions, monkeypatch):
    from api.pending_commands import approve_command
    from schemas.pending_command import PendingCommandApprove
    from services.container_service import ContainerService
    row = _pending(db, assessment, command="hydra -L u.txt ssh://x",
                   risk_level="high", risk_reason="brute-force")

    async def _fake(self, assessment_id, command, phase, db):
        return _exec_ok(stdout="3 valid")

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake)
    async with async_sessions() as adb:
        res = await approve_command(row.id, PendingCommandApprove(),
                                    _request_for(users["admin"]), db=adb)
    assert res.status == "executed"


async def test_approve_execution_failure_marks_failed_500(
        db, assessment, users, async_sessions, monkeypatch):
    from api.pending_commands import approve_command
    from schemas.pending_command import PendingCommandApprove
    from services.container_service import ContainerService
    row = _pending(db, assessment)

    async def _boom(self, assessment_id, command, phase, db):
        raise RuntimeError("container down")

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _boom)
    async with async_sessions() as adb:
        with pytest.raises(Exception) as ei:
            await approve_command(row.id, PendingCommandApprove(),
                                  _request_for(users["admin"]), db=adb)
        assert "container down" in str(ei.value)
    db.refresh(row)
    assert row.status == "failed"
    assert row.resolved_by == "pc-admin"
    assert "Execution failed" in row.rejection_reason
    assert row.execution_result["success"] is False


async def test_approve_reject_nonexistent_or_already_resolved(
        db, assessment, users, async_sessions):
    from api.pending_commands import approve_command, reject_command
    from schemas.pending_command import (PendingCommandApprove,
                                         PendingCommandReject)
    from fastapi import HTTPException
    done = _pending(db, assessment, status="executed")
    async with async_sessions() as adb:
        with pytest.raises(HTTPException) as ei:
            await approve_command(98765, PendingCommandApprove(),
                                  _request_for(users["admin"]), db=adb)
        assert ei.value.status_code == 404
        with pytest.raises(HTTPException) as ei:
            await approve_command(done.id, PendingCommandApprove(),
                                  _request_for(users["admin"]), db=adb)
        assert ei.value.status_code == 400
        assert "already executed" in ei.value.detail
        with pytest.raises(HTTPException) as ei:
            await reject_command(done.id, PendingCommandReject(),
                                 _request_for(users["admin"]), db=adb)
        assert ei.value.status_code == 400


# ================================================================== reject
async def test_reject_records_reason_and_identity(
        db, assessment, users, async_sessions):
    from api.pending_commands import reject_command
    from schemas.pending_command import PendingCommandReject
    row = _pending(db, assessment, command="chmod 777 /")
    async with async_sessions() as adb:
        res = await reject_command(
            row.id, PendingCommandReject(rejected_by="spoofed",
                                         rejection_reason="too risky"),
            _request_for(users["auditor"]), db=adb)
    assert res.status == "rejected"
    assert res.resolved_by == "pc-auditor"
    assert res.rejection_reason == "too risky"
    assert res.resolved_at is not None


async def test_reject_nonexistent_404(db, assessment, users, async_sessions):
    from api.pending_commands import reject_command
    from schemas.pending_command import PendingCommandReject
    from fastapi import HTTPException
    async with async_sessions() as adb:
        with pytest.raises(HTTPException) as ei:
            await reject_command(31337, PendingCommandReject(),
                                 _request_for(users["admin"]), db=adb)
        assert ei.value.status_code == 404


def test_delete_pending_command(client, db, admin_headers, assessment):
    row = _pending(db, assessment)
    r = client.delete(f"/api/pending-commands/{row.id}",
                      headers=admin_headers)
    assert r.status_code == 200
    assert "deleted" in r.json()["message"]
    assert db.query(PendingCommand).count() == 0
    assert client.delete(f"/api/pending-commands/{row.id}",
                         headers=admin_headers).status_code == 404


def test_pending_commands_write_requires_auditor(client, db, viewer_headers,
                                                 assessment):
    r = client.post("/api/pending-commands/create", headers=viewer_headers,
                    json={"assessment_id": assessment.id, "command": "ls"})
    assert r.status_code == 403
