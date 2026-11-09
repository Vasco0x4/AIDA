"""
Command execution + history API.

- /api/assessments/{id}/commands: history list/get, execute, execute-with-
  credentials ({{PLACEHOLDER}} substitution for every credential type),
  python-exec, http-request. Container execution is stubbed — no docker.
- /api/commands (global view, api/commands.py global_router) + /api/commands/stats
  (api/global_commands.py).

NOTE (documented bug, not fixed here): GET /api/commands is registered twice —
api.commands.global_router is mounted first and serves every request, so
api.global_commands.list_all_commands is unreachable dead code (only its
/stats route is live). The shadowed handler is covered by direct call below.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from models.assessment import Assessment
from models.command_history import CommandHistory
from models.credential import Credential


def _request_for(path="/x"):
    """Real starlette Request (slowapi's decorator inspects it)."""
    return Request({"type": "http", "method": "POST", "path": path,
                    "headers": [], "query_string": "",
                    "client": ("testclient", 123)})


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from slowapi import Limiter
    import main as main_mod
    monkeypatch.setattr(main_mod.app.state, "limiter",
                        Limiter(key_func=lambda r: "test", storage_uri="memory://"))
    from middleware.rate_limit import limiter as global_limiter
    global_limiter.reset()


@pytest.fixture()
def async_sessions(monkeypatch, engine):
    """get_async_db endpoints must run on the TEST database, not the dev one.
    NullPool: connections are created/closed per request, so they never cross
    the TestClient's per-request event loops."""
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
    a = Assessment(name="cmd-assessment", scope="example.com")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _hist(db, assessment, command="nmap -sV example.com", **kw):
    row = CommandHistory(
        assessment_id=assessment.id, command=command,
        stdout=kw.pop("stdout", ""), stderr=kw.pop("stderr", ""),
        returncode=kw.pop("returncode", 0),
        execution_time=kw.pop("execution_time", 1.5),
        success=kw.pop("success", True), phase=kw.pop("phase", "recon"),
        command_type=kw.pop("command_type", "shell"), **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _exec_result(assessment_id=1, command="cmd", **kw):
    return SimpleNamespace(
        id=kw.pop("id", 1), assessment_id=assessment_id, command=command,
        container_name="exegol", stdout=kw.pop("stdout", "out"),
        stderr=kw.pop("stderr", ""), returncode=kw.pop("returncode", 0),
        execution_time=kw.pop("execution_time", 0.1),
        success=kw.pop("success", True), phase=kw.pop("phase", "recon"),
        status="completed", command_type=kw.pop("command_type", "shell"),
        source_code=kw.pop("source_code", None), created_at=datetime.utcnow())


# ------------------------------------------------------------------ history
def test_list_commands_requires_auth(client):
    assert client.get("/api/assessments/1/commands").status_code == 401


def test_list_commands_unknown_assessment_404(client, admin_headers):
    r = client.get("/api/assessments/999/commands", headers=admin_headers)
    assert r.status_code == 404


def test_list_commands_newest_first_with_limit(client, db, admin_headers, assessment):
    _hist(db, assessment, "first")
    _hist(db, assessment, "second")
    r = client.get(f"/api/assessments/{assessment.id}/commands",
                   headers=admin_headers)
    assert r.status_code == 200
    assert [c["command"] for c in r.json()] == ["second", "first"]

    r = client.get(f"/api/assessments/{assessment.id}/commands",
                   params={"limit": 1}, headers=admin_headers)
    assert [c["command"] for c in r.json()] == ["second"]


def test_get_command_by_id(client, db, admin_headers, assessment):
    row = _hist(db, assessment, "the-command")
    r = client.get(f"/api/assessments/{assessment.id}/commands/{row.id}",
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["command"] == "the-command"


def test_get_command_wrong_assessment_or_missing_404(client, db, admin_headers, assessment):
    other = Assessment(name="other")
    db.add(other)
    db.commit()
    row = _hist(db, assessment)
    assert client.get(f"/api/assessments/{other.id}/commands/{row.id}",
                      headers=admin_headers).status_code == 404
    assert client.get(f"/api/assessments/{assessment.id}/commands/999",
                      headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ execute
# The execute family runs on get_async_db; inside TestClient the tracer loses
# the continuation after SQLAlchemy's first greenlet-spawned await, so the
# happy paths call the endpoint functions directly on pytest's own loop (the
# RBAC/auth/validation paths above stay covered through the client).
async def test_execute_command(db, assessment, async_sessions, monkeypatch):
    from api.commands import execute_command
    from schemas.command import CommandExecute
    from services.container_service import ContainerService
    seen = {}

    async def _fake(self, assessment_id, command, phase, db):
        seen.update(command=command, phase=phase, assessment_id=assessment_id)
        return _exec_result(command=command)

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake)
    async with async_sessions() as adb:
        res = await execute_command(_request_for(), assessment.id,
                                    CommandExecute(command="nmap example.com",
                                                   phase="recon"), db=adb)
    assert res.command == "nmap example.com"
    assert seen == {"command": "nmap example.com", "phase": "recon",
                    "assessment_id": assessment.id}


def test_execute_command_unknown_assessment_404(client, admin_headers, async_sessions):
    r = client.post("/api/assessments/4242/commands/execute",
                    headers=admin_headers, json={"command": "ls"})
    assert r.status_code == 404


def test_execute_command_body_validation_422(client, admin_headers, assessment):
    r = client.post(f"/api/assessments/{assessment.id}/commands/execute",
                    headers=admin_headers, json={"phase": "recon"})
    assert r.status_code == 422


# ------------------------------------------- credential substitution
def _cred(db, assessment, ctype, placeholder, **kw):
    row = Credential(assessment_id=assessment.id, credential_type=ctype,
                     name=kw.pop("name", ctype), placeholder=placeholder, **kw)
    db.add(row)
    db.commit()
    return row


async def test_execute_with_credentials_substitutes_every_type(
        db, assessment, async_sessions, monkeypatch):
    from api.commands import execute_command_with_credentials
    from schemas.command import CommandExecute
    from services.container_service import ContainerService
    import base64
    _cred(db, assessment, "bearer_token", "{{BEARER}}", token="tok-1")
    _cred(db, assessment, "api_key", "{{APIKEY}}", token="key-2")
    _cred(db, assessment, "cookie", "{{COOKIE}}", cookie_value="sess=3")
    _cred(db, assessment, "basic_auth", "{{BASIC}}",
          username="u", password="p")
    _cred(db, assessment, "ssh", "{{SSH}}", username="root", password="pw")
    _cred(db, assessment, "custom", "{{CUSTOM}}", token="cust-tok")
    _cred(db, assessment, "mystery", "{{MYSTERY}}")

    seen = {}

    async def _fake(self, assessment_id, command, phase, db):
        seen["command"] = command
        return _exec_result(command=command)

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake)

    cmd = ("curl -H 'Authorization: Bearer {{BEARER}}' -H 'X-Key: {{APIKEY}}' "
           "-b '{{COOKIE}}' -u {{BASIC}} ssh {{SSH}} x {{CUSTOM}} y {{MYSTERY}}")
    async with async_sessions() as adb:
        await execute_command_with_credentials(
            assessment.id, CommandExecute(command=cmd), db=adb)
    expected_b64 = base64.b64encode(b"u:p").decode()
    assert seen["command"] == (
        f"curl -H 'Authorization: Bearer tok-1' -H 'X-Key: key-2' "
        f"-b 'sess=3' -u {expected_b64} ssh root:pw x cust-tok y ")


async def test_execute_with_credentials_unknown_placeholder_404(
        db, assessment, async_sessions):
    from api.commands import execute_command_with_credentials
    from schemas.command import CommandExecute
    from fastapi import HTTPException
    async with async_sessions() as adb:
        with pytest.raises(HTTPException) as ei:
            await execute_command_with_credentials(
                assessment.id,
                CommandExecute(command="echo {{NOPE_NOT_HERE}}"), db=adb)
    assert ei.value.status_code == 404
    assert "NOPE_NOT_HERE" in ei.value.detail


async def test_execute_with_credentials_passthrough_without_placeholders(
        db, assessment, async_sessions, monkeypatch):
    from api.commands import execute_command_with_credentials
    from schemas.command import CommandExecute
    from services.container_service import ContainerService
    seen = {}

    async def _fake(self, assessment_id, command, phase, db):
        seen["command"] = command
        return _exec_result(command=command)

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake)
    async with async_sessions() as adb:
        await execute_command_with_credentials(
            assessment.id, CommandExecute(command="plain command"), db=adb)
    assert seen["command"] == "plain command"


async def test_python_exec_substitutes_credentials(
        db, assessment, async_sessions, monkeypatch):
    from api.commands import execute_python
    from schemas.command import PythonExecRequest
    from services.container_service import ContainerService
    _cred(db, assessment, "bearer_token", "{{TOKEN}}", token="py-tok")
    seen = {}

    async def _fake(self, assessment_id, code, phase, db):
        seen.update(code=code, phase=phase)
        return _exec_result(command="<python>", command_type="python",
                            source_code=code)

    monkeypatch.setattr(ContainerService, "execute_and_log_python", _fake)
    async with async_sessions() as adb:
        res = await execute_python(
            assessment.id, PythonExecRequest(code="print('{{TOKEN}}')",
                                              phase="enum"), db=adb)
    assert res.command_type == "python"
    assert seen["code"] == "print('py-tok')"
    assert seen["phase"] == "enum"


async def test_http_request_substitutes_url_headers_cookies_auth(
        db, assessment, async_sessions, monkeypatch):
    from api.commands import http_request_endpoint
    from schemas.command import HttpRequestRequest
    from services.container_service import ContainerService
    _cred(db, assessment, "cookie", "{{SESS}}", cookie_value="sid=99")
    _cred(db, assessment, "basic_auth", "{{BASIC}}", username="au", password="se")
    seen = {}

    async def _fake(self, assessment_id, params, db):
        seen["params"] = params
        return _exec_result(command="<http>", command_type="http")

    monkeypatch.setattr(ContainerService, "execute_and_log_http_request", _fake)
    payload = HttpRequestRequest(
        url="http://{{SESS}}/x", method="POST",
        headers={"Cookie": "{{SESS}}"},
        cookies={"session": "{{SESS}}"},
        auth=["{{SESS}}", "{{BASIC}}"])
    async with async_sessions() as adb:
        await http_request_endpoint(assessment.id, payload, db=adb)
    import base64
    p = seen["params"]
    assert p.url == "http://sid=99/x"
    assert p.headers == {"Cookie": "sid=99"}
    assert p.cookies == {"session": "sid=99"}
    assert p.auth == ["sid=99", base64.b64encode(b"au:se").decode()]


# ------------------------------------------------------------------ global
def _seed_global(db):
    a1 = Assessment(name="alpha-corp")
    a2 = Assessment(name="beta-corp")
    db.add_all([a1, a2])
    db.commit()
    _hist(db, a1, "nmap alpha", command_type=None, success=True)
    _hist(db, a1, "gobuster alpha", command_type="shell", success=False,
          returncode=1, phase="enum")
    _hist(db, a2, "python probe", command_type="python", success=True,
          phase="recon")
    _hist(db, a2, "http fetch", command_type="http", success=True)
    return a1, a2


def test_global_commands_list_defaults(client, db, admin_headers):
    _seed_global(db)
    r = client.get("/api/commands", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    assert len(body["commands"]) == 4
    assert all(c["assessment_name"] for c in body["commands"])
    # default command_type display for NULL rows
    types = {c["command"] for c in body["commands"]
             if c["command_type"] == "shell"}
    assert types == {"nmap alpha", "gobuster alpha"}


def test_global_commands_status_filter(client, db, admin_headers):
    _seed_global(db)
    r = client.get("/api/commands", params={"status": "success"},
                   headers=admin_headers)
    assert r.json()["total"] == 3
    r = client.get("/api/commands", params={"status": "failed"},
                   headers=admin_headers)
    assert r.json()["total"] == 1
    assert r.json()["commands"][0]["command"] == "gobuster alpha"
    # unknown status value → no filter applied
    r = client.get("/api/commands", params={"status": "all"},
                   headers=admin_headers)
    assert r.json()["total"] == 4


def test_global_commands_type_filter(client, db, admin_headers):
    _seed_global(db)
    r = client.get("/api/commands", params={"command_type": "shell"},
                   headers=admin_headers)
    # 'shell' bucket includes NULL command_type rows
    assert {c["command"] for c in r.json()["commands"]} == \
        {"nmap alpha", "gobuster alpha"}
    r = client.get("/api/commands", params={"command_type": "python"},
                   headers=admin_headers)
    assert r.json()["total"] == 1
    r = client.get("/api/commands", params={"command_type": "all"},
                   headers=admin_headers)
    assert r.json()["total"] == 4


def test_global_commands_search(client, db, admin_headers):
    _seed_global(db)
    for term, expected in (("nmap", 1), ("beta-corp", 2), ("enum", 1),
                           ("nomatch", 0)):
        r = client.get("/api/commands", params={"search": term},
                       headers=admin_headers)
        assert r.json()["total"] == expected, term


def test_global_commands_pagination(client, db, admin_headers):
    _seed_global(db)
    r = client.get("/api/commands", params={"skip": 0, "limit": 2},
                   headers=admin_headers)
    assert r.json()["has_more"] is True
    r = client.get("/api/commands", params={"skip": 2, "limit": 2},
                   headers=admin_headers)
    assert r.json()["has_more"] is False
    assert {c["command"] for c in r.json()["commands"]} == \
        {"gobuster alpha", "nmap alpha"}


def test_global_commands_stats(client, db, admin_headers):
    _seed_global(db)
    r = client.get("/api/commands/stats", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"total": 4, "passed": 3, "failed": 1,
                        "avg_execution_time": 1.5}


def test_global_commands_stats_empty_db(client, db, admin_headers):
    r = client.get("/api/commands/stats", headers=admin_headers)
    assert r.json() == {"total": 0, "passed": 0, "failed": 0,
                        "avg_execution_time": 0}


def test_global_commands_requires_auth(client):
    assert client.get("/api/commands").status_code == 401
    assert client.get("/api/commands/stats").status_code == 401


# ------------------- shadowed handler in api/global_commands.py ---------------
async def test_shadowed_global_commands_handler_direct(db):
    """api.global_commands.list_all_commands is unreachable through the app
    (shadowed by api.commands.global_router's identical path). Direct call to
    pin its behavior: filters + pagination + Query-bounds semantics."""
    from api.global_commands import list_all_commands
    _seed_global(db)
    body = await list_all_commands(skip=0, limit=3, status="success",
                                   search=None, command_type=None, db=db)
    assert body.total == 3
    assert len(body.commands) == 3
    assert body.has_more is False
    body = await list_all_commands(skip=0, limit=3, status=None, search=None,
                                   command_type="http", db=db)
    assert body.total == 1
    assert body.commands[0].command_type == "http"
    # 'failed' status filter + shell bucket (shell + NULL types)
    body = await list_all_commands(skip=0, limit=50, status="failed",
                                   search=None, command_type=None, db=db)
    assert body.total == 1
    body = await list_all_commands(skip=0, limit=50, status=None, search=None,
                                   command_type="shell", db=db)
    assert {c.command for c in body.commands} == {"nmap alpha", "gobuster alpha"}


async def test_shadowed_global_commands_handler_search(db):
    from api.global_commands import list_all_commands
    _seed_global(db)
    body = await list_all_commands(skip=0, limit=50, status=None,
                                   search="alpha", command_type=None, db=db)
    assert body.total == 2
    assert {c.assessment_name for c in body.commands} == {"alpha-corp"}
