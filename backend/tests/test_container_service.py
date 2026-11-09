"""ContainerService — docker CLI boundary mocked (run_subprocess /
subprocess exec), DB parts on the isolated test Postgres."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

import services.container_service as cs_mod
from models.assessment import Assessment
from models.command_history import CommandHistory
from models.platform_settings import PlatformSettings
from schemas.command import HttpRequestRequest
from services.container_service import ContainerService


def docker_ps_payload(*containers):
    return "\n".join(json.dumps(c) for c in containers)


def make_container(name, state="running", image="exegol:latest", cid="abcdef123456"):
    return {"Names": "/" + name, "Image": image, "State": state, "ID": cid}


class SubprocessScript:
    """Replaces container_service.run_subprocess; first matching reply wins."""

    def __init__(self, replies):
        self.replies = list(replies)  # (matcher, result-dict)
        self.calls = []

    async def __call__(self, command, timeout=30.0):
        self.calls.append((list(command), timeout))
        for matcher, result in self.replies:
            if matcher(command):
                return dict(result)
        return {"status": "ok", "success": True, "returncode": 0,
                "stdout": "", "stderr": ""}


def ok(stdout="", stderr=""):
    return {"status": "ok", "success": True, "returncode": 0,
            "stdout": stdout, "stderr": stderr}


def rc(returncode, stdout="", stderr=""):
    return {"status": "ok", "success": returncode == 0, "returncode": returncode,
            "stdout": stdout, "stderr": stderr}


class FakeWS:
    def __init__(self):
        self.events = []

    async def broadcast(self, event, assessment_id=None):
        self.events.append((event, assessment_id))


@pytest.fixture()
def ws(monkeypatch):
    fake = FakeWS()
    monkeypatch.setattr(cs_mod, "manager", fake)
    return fake


@pytest.fixture()
def svc():
    return ContainerService()


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_sanitize_output_strips_nulls_and_bad_utf8():
    assert ContainerService._sanitize_output("a\x00b") == "ab"
    assert ContainerService._sanitize_output("") == ""
    assert ContainerService._sanitize_output(None) is None
    assert ContainerService._sanitize_output("\udcff\udcfe legible").endswith(" legible")


def test_clean_health_cache_evicts_expired_and_overflow(svc):
    now = time.time()
    svc.health_cache_ttl = 30
    svc.container_health_cache = {
        "fresh": (now - 1, "running", True),
        "stale": (now - 100, "running", True),
    }
    svc._clean_health_cache()
    assert set(svc.container_health_cache) == {"fresh"}

    svc.max_health_cache_entries = 2
    svc.container_health_cache = {f"c{i}": (now - i, "running", True) for i in range(5)}
    svc._clean_health_cache()
    assert set(svc.container_health_cache) == {"c0", "c1"}  # newest kept


# ── discovery / selection ─────────────────────────────────────────────────────

async def test_discover_containers_filters_by_prefix_and_caches(svc, monkeypatch):
    script = SubprocessScript([
        (lambda cmd: cmd[1] == "ps", ok(docker_ps_payload(
            make_container("aida-pentest"),
            make_container("exegol-claude", state="exited"),
            make_container("unrelated-db"),
        ))),
    ])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)

    found = await svc.discover_containers()
    assert [c["name"] for c in found] == ["aida-pentest", "exegol-claude"]
    assert found[0] == {"name": "aida-pentest", "image": "exegol:latest",
                        "status": "running", "id": "abcdef123456"}

    # Malformed JSON lines are skipped, not fatal.
    script.replies[0] = (lambda cmd: cmd[1] == "ps",
                         ok("{not json}\n" + json.dumps(make_container("aida-two"))))
    assert [c["name"] for c in await svc.discover_containers(force_refresh=True)] == ["aida-two"]

    # Cache: a second call within TTL does not hit docker again.
    before = len(script.calls)
    await svc.discover_containers()
    assert len(script.calls) == before

    # Docker failure → empty list, not an exception.
    script.replies[0] = (lambda cmd: cmd[1] == "ps",
                         {"status": "failed", "success": False, "returncode": -1,
                          "stdout": "", "stderr": "boom", "raw_error": "boom"})
    assert await svc.discover_containers(force_refresh=True) == []


async def test_discover_containers_docker_binary_missing(svc, monkeypatch):
    script = SubprocessScript([
        (lambda cmd: True,
         {"status": "not_found", "success": False, "returncode": -1, "stdout": "",
          "stderr": "Command not found: docker", "raw_error": "FileNotFoundError"}),
    ])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)
    assert await svc.discover_containers(force_refresh=True) == []
    assert script.calls[0][0][:2] == ["docker", "ps"]


async def test_select_container(svc, monkeypatch):
    monkeypatch.setattr(cs_mod, "run_subprocess", SubprocessScript([
        (lambda cmd: cmd[1] == "ps", ok(docker_ps_payload(make_container("aida-pentest")))),
    ]))
    res = await svc.select_container("aida-pentest")
    assert res["success"] and svc.current_container == "aida-pentest"
    res = await svc.select_container("ghost")
    assert not res["success"] and "not found" in res["error"]


# ── health validation ─────────────────────────────────────────────────────────

async def test_validate_no_container_selected(svc):
    svc.current_container = None
    assert (await svc.validate_container_status())["error"] == "No container selected"


async def test_validate_running_and_cache(svc, monkeypatch):
    script = SubprocessScript([(lambda cmd: cmd[1] == "inspect", ok("running"))])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)
    assert await svc.validate_container_status() == {"success": True, "status": "running"}
    before = len(script.calls)  # cached now — no further docker calls
    assert await svc.validate_container_status() == {"success": True, "status": "running"}
    assert len(script.calls) == before


async def test_validate_cache_negative_entry(svc):
    svc.current_container = "c"
    svc.container_health_cache["c"] = (9999999999.0, "paused", False)  # fresh entry
    res = await svc.validate_container_status()
    assert res["success"] is False and "paused" in res["error"]


async def test_validate_starts_stopped_container(svc, monkeypatch):
    script = SubprocessScript([
        (lambda cmd: cmd[1] == "inspect", ok("exited")),
        (lambda cmd: cmd[1] == "start", ok()),
    ])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)
    assert await svc.validate_container_status() == {"success": True, "status": "started"}


async def test_validate_start_failure_and_invalid_state(svc, monkeypatch):
    script = SubprocessScript([
        (lambda cmd: cmd[1] == "inspect", ok("created")),
        (lambda cmd: cmd[1] == "start", rc(1, stderr="cannot start")),
    ])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)
    res = await svc.validate_container_status()
    assert res["success"] is False and res["error"] == "Failed to start container"
    assert "cannot start" in res["details"]

    svc.container_health_cache.clear()
    script.replies = [(lambda cmd: cmd[1] == "inspect", ok("paused"))]
    res = await svc.validate_container_status()
    assert res["success"] is False and "paused" in res["error"]


async def test_validate_inspect_failure(svc, monkeypatch):
    monkeypatch.setattr(cs_mod, "run_subprocess", SubprocessScript([
        (lambda cmd: cmd[1] == "inspect", rc(125, stderr="No such object")),
    ]))
    res = await svc.validate_container_status()
    assert res["success"] is False and res["error"] == "Container not found"


# ── command execution ─────────────────────────────────────────────────────────

async def test_execute_container_command_gates_and_wraps(svc, monkeypatch):
    svc.current_container = None
    res = await svc.execute_container_command("echo hi")
    assert res["success"] is False and res["error"] == "No container selected"

    svc.current_container = "c"
    script = SubprocessScript([
        (lambda cmd: cmd[1] == "inspect", ok("running")),
        (lambda cmd: cmd[1] == "exec", ok("hi\n", stderr="chpwd: hook noise\nreal err")),
    ])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)
    res = await svc.execute_container_command("echo hi", working_directory="/ws/x")
    assert res["success"] is True  # rc==0 → success despite stderr
    assert res["stdout"] == "hi\n"
    assert res["stderr"] == "real err"  # chpwd noise filtered
    exec_cmd = [c for c, _ in script.calls if c[1] == "exec"][0]
    assert exec_cmd[:3] == ["docker", "exec", "c"]
    assert "cd /ws/x" in exec_cmd[-1] and "echo hi" in exec_cmd[-1]

    # Validation failure short-circuits with returncode -1.
    script.replies = [(lambda cmd: cmd[1] == "inspect", rc(1, stderr="gone"))]
    svc.container_health_cache.clear()
    res = await svc.execute_container_command("ls")
    assert res["success"] is False and res["returncode"] == -1
    assert "Container validation failed" in res["error"]


async def test_execute_container_command_failed_run(svc, monkeypatch):
    svc.current_container = "c"
    monkeypatch.setattr(cs_mod, "run_subprocess", SubprocessScript([
        (lambda cmd: cmd[1] == "inspect", ok("running")),
        (lambda cmd: cmd[1] == "exec", rc(2, stdout="partial", stderr="boom")),
    ]))
    res = await svc.execute_container_command("false")
    assert res["success"] is False and res["returncode"] == 2


# ── async DB helpers ──────────────────────────────────────────────────────────

class FakeAsyncSession:
    """Async façade over the sync test session."""

    def __init__(self, sync):
        self._s = sync

    def __getattr__(self, item):
        return getattr(self._s, item)

    async def execute(self, *a, **kw):
        return self._s.execute(*a, **kw)

    async def commit(self):
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def refresh(self, obj):
        self._s.refresh(obj)


@pytest.fixture()
def adb(db):
    return FakeAsyncSession(db)


def _seed(db, name="cnt", **kw):
    asn = Assessment(name=name, scope="127.0.0.1", **kw)
    db.add(asn)
    db.commit()
    db.refresh(asn)
    return asn


@pytest.fixture()
def discover_running(monkeypatch):
    async def fake_discover(force_refresh=False):
        return [{"name": "c1", "status": "running"}]

    monkeypatch.setattr(ContainerService, "discover_containers", fake_discover)
    return fake_discover


async def test_resolve_active_container_priority(svc, db, adb, monkeypatch):
    db.add(PlatformSettings(key="container_name", value="aida-configured"))
    db.commit()

    async def discover(force_refresh=False):
        return [{"name": "other-running", "status": "running"},
                {"name": "stopped-one", "status": "exited"}]

    monkeypatch.setattr(svc, "discover_containers", discover)
    # Configured not running → auto-select first running container.
    assert await svc._resolve_active_container(adb) == "other-running"

    async def discover2(force_refresh=False):
        return [{"name": "aida-configured", "status": "running"}]

    monkeypatch.setattr(svc, "discover_containers", discover2)
    assert await svc._resolve_active_container(adb) == "aida-configured"

    async def none_running(force_refresh=False):
        return []

    monkeypatch.setattr(svc, "discover_containers", none_running)
    # Nothing running → configured name returned (validation reports the error).
    assert await svc._resolve_active_container(adb) == "aida-configured"


async def test_resolve_active_container_default_when_unset(svc, db, adb, monkeypatch):
    async def none_running(force_refresh=False):
        return []

    monkeypatch.setattr(svc, "discover_containers", none_running)
    assert await svc._resolve_active_container(adb) == cs_mod.settings.DEFAULT_CONTAINER_NAME


async def test_prepare_execution_context_timeout_from_settings(svc, db, adb,
                                                               monkeypatch, discover_running):
    asn = _seed(db, name="prep", workspace_path="/workspace/prep")
    db.add(PlatformSettings(key="command_timeout", value="42"))
    db.commit()
    script = SubprocessScript([(lambda cmd: cmd[3] == "test", ok())])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)

    timeout, wd, loaded = await svc._prepare_execution_context(asn.id, adb, timeout=None)
    assert timeout == 42
    assert wd == "/workspace/prep"
    assert loaded.id == asn.id
    assert script.calls and script.calls[0][0][:3] == ["docker", "exec", "c1"]

    timeout2, _, _ = await svc._prepare_execution_context(asn.id, adb, timeout=7)
    assert timeout2 == 7  # explicit override wins

    db.query(PlatformSettings).filter(
        PlatformSettings.key == "command_timeout").one().value = "not-a-number"
    db.commit()
    timeout3, _, _ = await svc._prepare_execution_context(asn.id, adb, timeout=None)
    assert timeout3 == cs_mod.settings.COMMAND_TIMEOUT  # bad value → config default


async def test_prepare_execution_context_creates_missing_workspace(
        svc, db, adb, monkeypatch, discover_running):
    asn = _seed(db, name="no-ws")  # no workspace_path
    created = {}

    async def fake_create_workspace(assessment_name, db=None):
        created["name"] = assessment_name
        return {"workspace_path": f"/workspace/{assessment_name}",
                "container_name": "c1"}

    monkeypatch.setattr(svc, "create_workspace", fake_create_workspace)
    timeout, wd, _ = await svc._prepare_execution_context(asn.id, adb, timeout=5)
    assert created["name"] == "no-ws"
    assert wd == "/workspace/no-ws"
    db.refresh(asn)
    assert asn.workspace_path == "/workspace/no-ws"
    assert asn.container_name == "c1"


async def test_prepare_execution_context_recreates_missing_dir(
        svc, db, adb, monkeypatch, discover_running):
    asn = _seed(db, name="gone-dir", workspace_path="/workspace/gone")
    script = SubprocessScript([
        (lambda cmd: cmd[3] == "test", rc(1)),        # dir missing in container
        (lambda cmd: cmd[3] == "bash", ok("mkdir")),  # recreate
    ])
    monkeypatch.setattr(cs_mod, "run_subprocess", script)
    _, wd, _ = await svc._prepare_execution_context(asn.id, adb, timeout=5)
    assert wd == "/workspace/gone"
    mkdir = [c for c, _ in script.calls if c[-3] == "bash"][0]
    assert mkdir[-1].startswith("mkdir -p /workspace/gone")
    for sub in ("recon", "exploits", "loot", "notes", "scripts", "context"):
        assert f"/workspace/gone/{sub}" in mkdir[-1]


# ── execute_and_log_command ───────────────────────────────────────────────────

def log_script():
    """docker replies for a successful execute_and_log_command run."""
    return SubprocessScript([
        (lambda cmd: cmd[3] == "test", ok()),                           # test -d
        (lambda cmd: cmd[1] == "inspect", ok("running")),               # validate
        (lambda cmd: cmd[3] == "bash", ok("out", "err\nchpwd noise")),  # exec
    ])


async def test_execute_and_log_command_success(svc, db, adb, monkeypatch,
                                               discover_running, ws):
    asn = _seed(db, name="log-ok", workspace_path="/workspace/log-ok")
    monkeypatch.setattr(cs_mod, "run_subprocess", log_script())

    log = await svc.execute_and_log_command(asn.id, "nmap target", "recon", adb)
    assert log.command == "nmap target"
    assert log.status == "completed" and log.success is True
    assert log.stdout == "out" and log.stderr == "err"
    assert log.container_name == "c1"
    assert log.phase == "recon"
    assert log.returncode == 0
    row = db.query(CommandHistory).filter(CommandHistory.id == log.id).one()
    assert row.status == "completed"
    assert len(ws.events) == 1 and ws.events[0][1] == asn.id


async def test_execute_and_log_command_display_command_hides_secret(
        svc, db, adb, monkeypatch, discover_running, ws):
    asn = _seed(db, name="log-secret", workspace_path="/workspace/log-secret")
    monkeypatch.setattr(cs_mod, "run_subprocess", log_script())
    log = await svc.execute_and_log_command(
        asn.id, command="curl -H 'Auth: real-secret' http://x", phase=None, db=adb,
        display_command="curl -H 'Auth: {{TOKEN}}' http://x")
    assert log.command == "curl -H 'Auth: {{TOKEN}}' http://x"


async def test_execute_and_log_command_failure_and_timeout(
        svc, db, adb, monkeypatch, discover_running, ws):
    asn = _seed(db, name="log-fail", workspace_path="/workspace/log-fail")
    monkeypatch.setattr(cs_mod, "run_subprocess", log_script())

    async def timing_out(command, working_directory=None):
        raise asyncio.TimeoutError

    monkeypatch.setattr(svc, "execute_container_command", timing_out)
    log = await svc.execute_and_log_command(asn.id, "slow-scan", "recon", adb, timeout=1)
    assert log.status == "timeout" and log.success is False
    assert log.stderr == "Command exceeded 1s timeout limit"
    assert log.execution_time == 1
    assert log.timeout_at is not None

    async def crashing(command, working_directory=None):
        raise RuntimeError("container exploded")

    monkeypatch.setattr(svc, "execute_container_command", crashing)
    log = await svc.execute_and_log_command(asn.id, "boom", None, adb, timeout=5)
    assert log.status == "failed" and "container exploded" in log.stderr


async def test_execute_and_log_python(svc, db, adb, monkeypatch,
                                      discover_running, ws):
    asn = _seed(db, name="log-py", workspace_path="/workspace/log-py")
    monkeypatch.setattr(cs_mod, "run_subprocess", log_script())

    async def fake_py(code, working_directory=None, timeout=300.0):
        return {"success": True, "stdout": "py-out", "stderr": "", "returncode": 0,
                "execution_time": 0.1, "container": "c1"}

    monkeypatch.setattr(svc, "execute_python_stdin", fake_py)
    log = await svc.execute_and_log_python(asn.id, "print('hi')", "recon", adb)
    assert log.status == "completed"
    assert log.command_type == "python"
    assert log.source_code == "print('hi')"
    assert log.command == "python3 -"
    assert log.stdout == "py-out"

    async def timing_out(code, working_directory=None, timeout=300.0):
        raise asyncio.TimeoutError

    monkeypatch.setattr(svc, "execute_python_stdin", timing_out)
    log = await svc.execute_and_log_python(asn.id, "x", None, adb, timeout=1)
    assert log.status == "timeout"
    assert log.stderr == "Python execution exceeded 1s timeout limit"


# ── python stdin + http script generation ─────────────────────────────────────

def test_generate_http_python_script_content():
    params = HttpRequestRequest(
        url="https://t.example/api", method="post",
        headers={"X-A": "1"}, params={"q": "z"},
        json_body={"k": "v"}, cookies={"sid": "1"},
        auth=["user", "pass"], proxy="http://127.0.0.1:8080",
        timeout=12, follow_redirects=False, verify_ssl=False, phase="recon")
    script = ContainerService()._generate_http_python_script(params)
    assert "method='POST'" in script
    assert "url='https://t.example/api'" in script
    assert "auth=('user', 'pass')" in script                  # auth tuple
    assert "'http': 'http://127.0.0.1:8080'" in script        # proxy dict
    assert 'json=\'{"k": "v"}\'' in script                    # json body wins
    assert "verify = False" in script
    assert "allow_redirects=False" in script
    assert "requests.exceptions.SSLError" in script


def test_generate_http_python_script_defaults():
    params = HttpRequestRequest(url="http://t.example", method="get")
    script = ContainerService()._generate_http_python_script(params)
    assert "auth=None" in script
    assert "proxies=None" in script
    assert "data=None" in script
    assert "verify = True" in script
    assert "allow_redirects=True" in script


async def test_execute_python_stdin_no_container(svc):
    svc.current_container = None
    res = await svc.execute_python_stdin("print(1)")
    assert res["success"] is False and res["returncode"] == -1


async def test_execute_python_stdin_timeout(svc, monkeypatch):
    svc.current_container = "c"

    class Proc:
        def __init__(self):
            self.calls = 0
            self.returncode = None

        def kill(self):
            self.returncode = -9

        async def communicate(self, input=None):
            self.calls += 1
            if self.calls == 1:
                await asyncio.sleep(30)
            return b"", b""

    def fake_exec(*a, **kw):
        async def coro():
            return Proc()
        return coro()

    monkeypatch.setattr(cs_mod.asyncio, "create_subprocess_exec", fake_exec)
    res = await svc.execute_python_stdin("while True: pass", timeout=0.2)
    assert res["success"] is False
    assert res["stderr"] == "Python execution timed out after 0.2s"
    assert res["returncode"] == -1


# ── workspace creation ────────────────────────────────────────────────────────

async def test_create_workspace_builds_tree_and_methodology(svc, monkeypatch):
    executed = []

    async def fake_exec(command, working_directory=None):
        executed.append(command)
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(svc, "execute_container_command", fake_exec)
    res = await svc.create_workspace("My Eng! 2024")
    assert res["workspace_path"] == "/workspace/My_Eng_2024"
    assert executed[0].startswith("mkdir -p /workspace/My_Eng_2024")
    for sub in ("recon", "exploits", "exploits", "loot", "notes", "scripts", "context"):
        assert f"/My_Eng_2024/{sub}" in executed[0]
    assert "methodology.md" in executed[1]
    assert executed[1].startswith("printf")


async def test_create_workspace_uses_db_container_setting(svc, db, monkeypatch):
    db.add(PlatformSettings(key="container_name", value="from-db"))
    db.commit()
    executed = []

    async def fake_exec(command, working_directory=None):
        executed.append(command)
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(svc, "execute_container_command", fake_exec)
    res = await svc.create_workspace("named", db=db)
    assert res["container_name"] == "from-db"
    assert svc.current_container == "from-db"
