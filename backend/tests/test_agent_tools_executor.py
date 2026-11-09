"""services/agent/tools.py — ToolExecutor paths: scope/mode/approval gates,
credential substitution, adaptive timeouts, evidence tools. The container
boundary, settings reads and the async session factory are faked; nothing
executes for real."""
from __future__ import annotations

import pytest

import services.agent.tools as tools_mod
from models.assessment import Assessment
from services.agent.scope import parse_scope
from services.agent.tools import ToolExecutor


class StubLog:
    def __init__(self, id=1, stdout="", stderr="", returncode=0, success=True):
        self.id = id
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = success


class StubContainer:
    """Replaces executor.container — records calls, returns canned results."""

    def __init__(self):
        self.calls = []
        self.next_log = StubLog()
        self.python_result = {}

    async def execute_and_log_command(self, **kw):
        self.calls.append(("shell", kw))
        return self.next_log

    async def _resolve_active_container(self, adb):
        self.calls.append(("resolve", adb))

    async def execute_python_stdin(self, script, timeout=None):
        self.calls.append(("python", script, timeout))
        return self.python_result


class _FakeAsyncSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


@pytest.fixture()
def no_async_db(monkeypatch):
    monkeypatch.setattr(tools_mod, "AsyncSessionLocal", lambda: _FakeAsyncSession())


async def _make_exec(db, scope_text="example.com"):
    ex = ToolExecutor(db, 1, parse_scope(scope_text))
    ex.container = StubContainer()
    return ex


def _seed(db, scope="t.example"):
    asn = Assessment(name="Agent Tools", scope=scope)
    db.add(asn)
    db.commit()
    db.refresh(asn)
    return asn


def _exec(db, asn, scope="example.com"):
    ex = ToolExecutor(db, asn.id, parse_scope(scope))
    ex.container = StubContainer()
    return ex


# ── dispatch ──────────────────────────────────────────────────────────────────

async def test_execute_unknown_tool(db, no_async_db):
    ex = await _make_exec(db)
    res = await ex.execute("does_not_exist", {})
    assert res == {"ok": False, "error": "unknown tool 'does_not_exist'"}


async def test_execute_swallows_handler_exception(db, no_async_db, monkeypatch):
    ex = await _make_exec(db)

    async def boom(args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ex, "_run_shell", boom)
    res = await ex.execute("run_shell", {"command": "true"})
    assert res == {"ok": False, "error": "kaboom"}


# ── run_shell gates ───────────────────────────────────────────────────────────

async def test_run_shell_rejects_empty_command(db, no_async_db):
    ex = await _make_exec(db)
    res = await ex.execute("run_shell", {"command": "   "})
    assert res["ok"] is False and res["error"] == "empty command"


async def test_run_shell_no_scope(db, no_async_db):
    ex = await _make_exec(db, scope_text="")
    res = await ex.execute("run_shell", {"command": "nmap example.com"})
    assert res["ok"] is False and res["blocked"] == "no_scope"
    assert "No authorized scope" in res["error"]
    assert ex.blocked_actions == 1 and ex.executed_actions == 0


async def test_run_shell_unparsed_scope_gives_hint(db, no_async_db):
    ex = await _make_exec(db, scope_text="just do the thing")
    res = await ex.execute("run_shell", {"command": "nmap example.com"})
    assert res["blocked"] == "no_scope"
    assert "authorized_scope" in res["error"]
    assert "*.example.com" in res["error"]


async def test_run_shell_out_of_scope(db, no_async_db):
    ex = await _make_exec(db)
    events = []

    async def rec(kind, data):
        events.append((kind, data))

    ex.on_event = rec
    res = await ex.execute("run_shell", {"command": "curl http://evil.com/x"})
    assert res["ok"] is False and res["blocked"] == "out_of_scope"
    assert "evil.com" in res["error"]
    assert ex.container.calls == []  # never reached the container
    assert ex.blocked_actions == 1
    assert events == [("blocked", {"command": "curl http://evil.com/x",
                                   "out_of_scope": ["evil.com"]})]


async def test_run_shell_mode_closed(db, no_async_db, monkeypatch):
    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "closed"})
    ex = await _make_exec(db)
    res = await ex.execute("run_shell", {"command": "echo hi"})
    assert res["blocked"] == "mode_closed"
    assert "a human must run this" in res["error"]
    assert ex.container.calls == []


async def test_run_shell_filter_keyword(db, no_async_db, monkeypatch):
    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "filter",
                                    "filter_keywords": ["sqlmap", "HASHCAT"]})
    ex = await _make_exec(db)
    res = await ex.execute("run_shell", {"command": "hashcat -m 0 hashes.txt"})
    assert res["blocked"] == "filter_match"
    assert "filter keyword" in res["error"]


# ── run_shell success path ────────────────────────────────────────────────────

async def test_run_shell_success(db, no_async_db, monkeypatch):
    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "open"})
    events = []

    async def rec(kind, data):
        events.append((kind, data))

    ex = await _make_exec(db)
    ex.on_event = rec
    ex.container.next_log = StubLog(id=7, stdout="80/tcp open", stderr="", returncode=0)
    res = await ex.execute("run_shell", {"command": "nmap example.com",
                                         "purpose": "port scan"})
    assert res["ok"] is True and res["returncode"] == 0
    assert res["stdout"] == "80/tcp open" and res["command_id"] == 7
    assert ex.executed_actions == 1 and ex.blocked_actions == 0
    kw = ex.container.calls[0][1]
    assert kw["command"] == "nmap example.com"
    assert kw["phase"] == "autonomous"
    assert kw["timeout"] == 900  # nmap → long scan timeout
    assert kw["display_command"] is None
    assert [e[0] for e in events] == ["run_shell", "shell_result"]


async def test_run_shell_truncates_long_stdout(db, no_async_db, monkeypatch):
    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "open"})
    ex = await _make_exec(db)
    ex.container.next_log = StubLog(stdout="A" * 7000, stderr="B" * 3000,
                                    returncode=1, success=False)
    res = await ex.execute("run_shell", {"command": "echo hi"})
    assert len(res["stdout"]) == 6000
    assert len(res["stderr"]) == 2000
    assert res["ok"] is False and res["returncode"] == 1
    assert "truncated to 6000 of 7000" in res["note"]
    assert "grep_output" in res["note"]


# ── exploit approval chain ────────────────────────────────────────────────────

async def test_run_shell_exploit_needs_approval(db, no_async_db, monkeypatch):
    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "open"})
    monkeypatch.setattr(tools_mod, "get_setting", lambda key, d: "on")
    monkeypatch.setattr(tools_mod, "int_setting",
                        lambda key, d: 0)  # timeout 0 → immediate expiry
    asn = _seed(db)
    ex = _exec(db, asn)
    res = await ex.execute("run_shell", {
        "command": "sqlmap -u http://example.com/?id=1 --batch", "purpose": "sqli"})
    assert res["ok"] is False and res["blocked"] == "approval_timeout"
    assert "No human approved" in res["error"]
    assert ex.container.calls == []          # never executed
    assert ex.blocked_actions == 1
    from models.pending_command import PendingCommand

    row = db.query(PendingCommand).one()
    assert row.risk_level == "high" and row.status == "pending"
    assert row.phase == "autonomous" and "sqlmap" in row.command


async def test_run_shell_exploit_approval_disabled(db, no_async_db, monkeypatch):
    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "open"})
    monkeypatch.setattr(tools_mod, "get_setting", lambda key, d: "off")
    ex = await _make_exec(db)
    ex.container.next_log = StubLog(id=3)
    res = await ex.execute("run_shell", {"command": "sqlmap -u http://example.com --batch"})
    assert res["ok"] is True and res["command_id"] == 3


# ── credential substitution ───────────────────────────────────────────────────

async def test_substitute_credentials_basic_auth_and_token(db, no_async_db):
    from models.credential import Credential

    asn = _seed(db)
    db.add(Credential(assessment_id=asn.id, credential_type="basic_auth",
                      name="Web basic", placeholder="{{BASIC}}",
                      username="root", password="toor"))
    db.add(Credential(assessment_id=asn.id, credential_type="bearer_token",
                      name="API token", placeholder="{{API_TOKEN}}",
                      token="tok-123"))
    db.commit()
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    out, used = ex._substitute_credentials(
        "curl -u {{BASIC}} -H 'X-Api: {{API_TOKEN}}' http://example.com/x")
    assert out == "curl -u root:toor -H 'X-Api: tok-123' http://example.com/x"
    assert used == ["{{BASIC}}", "{{API_TOKEN}}"]


async def test_substitute_credentials_fallback_secret_order(db, no_async_db):
    from models.credential import Credential

    asn = _seed(db)
    # No token → password; no password → cookie; none → username.
    db.add(Credential(assessment_id=asn.id, credential_type="cookie",
                      name="Session", placeholder="{{SESS}}", cookie_value="abc"))
    db.add(Credential(assessment_id=asn.id, credential_type="ssh",
                      name="SSH", placeholder="{{SSHU}}", username="svc"))
    db.commit()
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    out, used = ex._substitute_credentials("t {{SESS}} {{SSHU}}")
    assert out == "t abc svc"
    assert used == ["{{SESS}}", "{{SSHU}}"]
    # No placeholders at all → command untouched without touching the DB
    assert ex._substitute_credentials("plain command") == ("plain command", [])


async def test_run_shell_substitutes_and_masks_display(db, no_async_db, monkeypatch):
    from models.credential import Credential

    monkeypatch.setattr(tools_mod, "get_command_settings",
                        lambda db: {"execution_mode": "open"})
    asn = _seed(db)
    db.add(Credential(assessment_id=asn.id, credential_type="bearer_token",
                      name="Token", placeholder="{{TOKEN}}", token="sekrit"))
    db.commit()
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    ex.container = StubContainer()
    res = await ex.execute("run_shell", {
        "command": "curl -H 'Auth: {{TOKEN}}' http://example.com/api"})
    assert res["ok"] is True
    assert "substituted credentials: {{TOKEN}}" in res["note_creds"]
    kw = ex.container.calls[0][1]
    assert kw["command"] == "curl -H 'Auth: sekrit' http://example.com/api"
    assert kw["display_command"] == "curl -H 'Auth: {{TOKEN}}' http://example.com/api"


# ── adaptive timeout ──────────────────────────────────────────────────────────

def _ex_for_timeout(db):
    return ToolExecutor(db, 1, parse_scope("example.com"))


@pytest.mark.parametrize("command,expected", [
    ("nmap -sV example.com", 900),
    ("sudo nmap -p- example.com", 900),
    ("curl http://example.com/ffuf", 300),      # tool name in URL, not argv0
    ("echo hi | grep nmap", 300),               # nmap is argv1 not argv0
    ("/usr/bin/nuclei -u http://example.com", 900),  # path basename matched
    ("timeout 30 nmap example.com", 900),       # duration skipped → nmap found
    ("timeout 45s ffuf -u http://example.com", 900),  # suffixed duration too
    ("timeout 10 curl http://example.com", 300), # non-scan tool stays short
    ("curl -d 'a=1' http://example.com -p-", 900),  # scan FLAG anywhere
    ("nice -n 10 curl http://example.com", 300),
    ("curl http://example.com && nmap example.com", 900),  # chained segment
    ("echo test", 300),
])
def test_adaptive_timeout(db, command, expected):
    ex = _ex_for_timeout(db)
    assert ex._adaptive_timeout(command) == expected


# ── grep_output ───────────────────────────────────────────────────────────────

async def test_grep_output_regex_and_command_filter(db, no_async_db):
    from models.command_history import CommandHistory

    asn = _seed(db)
    db.add(CommandHistory(assessment_id=asn.id, command="nmap",
                          stdout="22/tcp open ssh\n80/tcp open http"))
    db.add(CommandHistory(assessment_id=asn.id, command="other",
                          stderr="error contacting host"))
    db.commit()
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))

    res = await ex.execute("grep_output", {"pattern": r"(\d+)/tcp open (\w+)"})
    assert res["ok"] is True and res["count"] == 2
    assert res["matches"][0]["line"] == "22/tcp open ssh"

    nmap_id = db.query(CommandHistory).filter_by(command="nmap").one().id
    res = await ex.execute("grep_output", {"pattern": "open", "command_id": nmap_id})
    assert res["count"] == 2
    res = await ex.execute("grep_output", {"pattern": "host"})
    assert res["count"] == 1  # stderr line matched too


async def test_grep_output_invalid_regex_falls_back_and_caps(db, no_async_db):
    from models.command_history import CommandHistory

    asn = _seed(db)
    for _ in range(3):
        db.add(CommandHistory(assessment_id=asn.id, command="x",
                              stdout="\n".join(f"line{n} [oops]" for n in range(40))))
    db.commit()
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    # Invalid regex → substring search instead of raising
    res = await ex.execute("grep_output", {"pattern": "[oops"})
    assert res["ok"] is True and res["count"] == 100  # hard cap at 100
    assert all("[oops]" in m["line"] for m in res["matches"])
    res = await ex.execute("grep_output", {"pattern": ""})
    assert res == {"ok": False, "error": "empty pattern"}


# ── simple recording tools ────────────────────────────────────────────────────

async def test_record_recon_and_finding_and_status(db, no_async_db):
    from models.card import Card
    from models.recon_data import ReconData

    asn = _seed(db)
    ex = _exec(db, asn)
    events = []

    async def rec(kind, data):
        events.append((kind, data))

    ex.on_event = rec

    res = await ex.execute("record_recon", {
        "data_type": "endpoint", "name": "/api/v1/users",
        "details": {"status": 200}})
    assert res["ok"] is True
    row = db.query(ReconData).one()
    assert row.data_type == "endpoint" and row.discovered_in_phase == "autonomous"
    assert row.details == {"status": 200}

    res = await ex.execute("record_finding", {
        "title": "SQLi", "severity": "HIGH",
        "technical_analysis": "union select", "proof": "dumped users"})
    assert res["ok"] is True
    card = db.query(Card).one()
    assert card.card_type == "finding" and card.status == "potential"
    assert card.severity == "HIGH" and card.technical_analysis == "union select"
    assert ex.findings == [card.id]  # later screenshots attach to it

    res = await ex.execute("status_update", {"summary": "Scan done"})
    assert res == {"ok": True}
    res = await ex.execute("status_update", {"summary": "  "})  # empty → no event
    assert [e[0] for e in events] == ["recon", "finding", "milestone"]


async def test_store_credential_placeholder_uniqueness(db, no_async_db):
    from models.credential import Credential

    asn = _seed(db)
    ex = _exec(db, asn)
    args = {"credential_type": "basic_auth", "name": "web admin login!",
            "username": "admin", "password": "admin"}
    r1 = await ex.execute("store_credential", args)
    r2 = await ex.execute("store_credential", args)
    assert r1["placeholder"] == "{{WEB_ADMIN_LOGIN}}"
    assert r2["placeholder"] == "{{WEB_ADMIN_LOGIN_1}}"
    assert r2["hint"] == "Reuse in commands as {{WEB_ADMIN_LOGIN_1}}."
    rows = db.query(Credential).order_by(Credential.id).all()
    assert [r.discovered_by for r in rows] == ["claude", "claude"]


# ── capture_screenshot ────────────────────────────────────────────────────────

@pytest.fixture()
def no_mirror(monkeypatch):
    monkeypatch.setattr("services.evidence_store.mirror_artifact",
                        lambda db, row: None)


async def test_screenshot_gates(db, no_async_db):
    asn = _seed(db)
    ex = _exec(db, asn)
    assert (await ex.execute("capture_screenshot", {}))["error"] == "url required"
    res = await ex.execute("capture_screenshot", {"url": "http://evil.com/x"})
    assert res["blocked"] == "out_of_scope" and "evil.com" in res["error"]
    assert ex.container.calls == []


async def test_screenshot_no_browser_and_failed_capture(db, no_async_db):
    asn = _seed(db)
    ex = _exec(db, asn)
    ex.container.next_log = StubLog(stdout="__NO_BROWSER__")
    res = await ex.execute("capture_screenshot", {"url": "http://example.com"})
    assert res["ok"] is False and "No headless browser" in res["error"]
    assert "chromium" in res["error"]

    ex.container.next_log = StubLog(stdout="__CAPTURE_FAILED__")
    res = await ex.execute("capture_screenshot", {"url": "http://example.com"})
    assert res["error"] == "Screenshot capture failed."
    ex.container.next_log = StubLog(stdout="")  # empty output
    assert (await ex.execute("capture_screenshot", {"url": "http://example.com"}))[
        "error"] == "Screenshot capture failed."


async def test_screenshot_success_and_bad_b64(db, no_async_db, no_mirror):
    import base64 as b64mod

    from models.artifact import Artifact

    asn = _seed(db)
    ex = _exec(db, asn)
    ex.container.next_log = StubLog(stdout=b64mod.b64encode(b"\x89PNG-fake").decode())
    res = await ex.execute("capture_screenshot", {
        "url": "http://example.com/app", "caption": "Login page"})
    assert res["ok"] is True and res["bytes"] == len(b"\x89PNG-fake")
    art = db.query(Artifact).one()
    assert art.kind == "screenshot" and art.data == b"\x89PNG-fake"
    assert art.caption == "Login page" and art.content_type == "image/png"
    # the chromium command quotes a sanitized URL
    cmd = ex.container.calls[0][1]["command"]
    assert "--headless=new" in cmd and '"http://example.com/app"' in cmd

    ex.container.next_log = StubLog(stdout="!!!not base64!!!")
    res = await ex.execute("capture_screenshot", {"url": "http://example.com"})
    assert res["error"] == "Could not decode screenshot."


# ── check_subdomain_takeover ──────────────────────────────────────────────────

def _takeover_result():
    return {
        "domain": "example.com", "wildcard": False, "subdomains_checked": 3,
        "summary": {"vulnerable": 1, "edge_case": 0},
        "results": [
            {"subdomain": "app.example.com", "verdict": "VULNERABLE",
             "service": "github", "confidence": "high", "evidence": "404 on repo",
             "dns_status": "NOERROR", "cname_chain": ["app.github.io"],
             "fingerprint": "fp", "cname_target": "app.github.io",
             "documentation": None},
            {"subdomain": "docs.example.com", "verdict": "SAFE", "service": "-",
             "confidence": "high", "evidence": "claimed", "dns_status": "NOERROR",
             "cname_chain": [], "fingerprint": "-", "cname_target": ""},
        ],
    }


async def test_takeover_gates(db, no_async_db):
    asn = _seed(db)
    ex = _exec(db, asn)
    assert (await ex.execute("check_subdomain_takeover", {}))["error"] == "domain required"
    res = await ex.execute("check_subdomain_takeover", {"domain": "evil.com"})
    assert res["blocked"] == "out_of_scope" and ex.container.calls == []


async def test_takeover_records_recon_and_finding(db, no_async_db, monkeypatch):
    from models.card import Card
    from models.recon_data import ReconData
    from services import takeover_service as tk

    seen = {}

    class FakeTakeover:
        async def scan(self, domain, subdomains=None):
            seen["domain"] = domain
            seen["subdomains"] = subdomains
            return _takeover_result()

    monkeypatch.setattr(tk, "TakeoverService", FakeTakeover)
    asn = _seed(db)
    ex = _exec(db, asn)
    res = await ex.execute("check_subdomain_takeover", {
        "domain": "example.com", "subdomains": ["app", "docs"]})
    assert res["ok"] is True and res["summary"] == {"vulnerable": 1, "edge_case": 0}
    assert res["subdomains_checked"] == 3
    assert seen == {"domain": "example.com", "subdomains": ["app", "docs"]}
    # compact view: only the 4 summary keys, capped
    assert set(res["results"][0]) == {"subdomain", "verdict", "service", "confidence"}

    recon = db.query(ReconData).all()
    assert len(recon) == 2  # every checked subdomain recorded
    card = db.query(Card).one()  # only the VULNERABLE one becomes a finding
    assert card.severity == "HIGH" and card.status == "potential"
    assert "app.example.com" in card.title and "github" in card.title
    assert "app.github.io" in card.proof


# ── record_poc ────────────────────────────────────────────────────────────────

async def test_record_poc_validation(db, no_async_db):
    asn = _seed(db)
    ex = _exec(db, asn)
    res = await ex.execute("record_poc", {"url": "ftp://example.com"})
    assert res["error"] == "valid http(s) url required"
    res = await ex.execute("record_poc", {"url": "http://evil.com"})
    assert res["blocked"] == "out_of_scope"
    res = await ex.execute("record_poc", {"url": "http://example.com",
                                          "actions": "not-a-list"})
    assert res["error"] == "actions must be a list"
    res = await ex.execute("record_poc", {"url": "http://example.com", "actions": [
        {"action": "goto", "url": "javascript:alert(1)"}]})
    assert "goto url invalid" in res["error"]
    res = await ex.execute("record_poc", {"url": "http://example.com", "actions": [
        {"action": "goto", "url": "http://evil.com"}]})
    assert res["blocked"] == "out_of_scope" and "goto host" in res["error"]
    assert ex.container.calls == []  # rejected before any container work


async def test_record_poc_action_normalization(db, no_async_db):
    import base64 as b64mod
    import json as jsonmod

    asn = _seed(db)
    ex = _exec(db, asn)
    ex.container.python_result = {"stdout": ""}  # failure path; inspect script cfg
    actions = [
        {"action": "goto", "url": "http://example.com/a"},
        {"action": "click", "selector": "#btn"},
        {"action": "fill", "selector": "#u", "value": "admin"},
        {"action": "press", "key": "Enter"},
        {"action": "wait", "ms": "250"},
        {"action": "wait_for", "selector": ".done"},
        {"action": "teleport"},          # unknown → dropped
        "garbage",                        # non-dict → dropped
    ] + [{"action": "click", "selector": "x"}] * 25  # over the 20 cap
    res = await ex.execute("record_poc", {"url": "http://example.com",
                                          "actions": actions})
    assert res["ok"] is False  # no __POC_B64__ → failure, but script was built
    kind, script, timeout = ex.container.calls[-1]
    assert kind == "python" and timeout == 150.0
    cfg_b64 = script.split('b64decode("', 1)[1].split('")', 1)[0]
    cfg = jsonmod.loads(b64mod.b64decode(cfg_b64))
    assert cfg["url"] == "http://example.com"
    assert cfg["viewport"] == {"width": 1280, "height": 800}
    kept = cfg["actions"]
    assert len(kept) == 18  # first 20 raw inputs, minus teleport + garbage
    assert kept[4] == {"action": "wait", "ms": 250}  # ms coerced to int


async def test_record_poc_failure_with_playwright_hint(db, no_async_db, no_mirror):
    asn = _seed(db)
    ex = _exec(db, asn)
    ex.container.python_result = {
        "stdout": "__POC_ERR__ ModuleNotFoundError: No module named 'playwright'"
                  " __POC_NOFILE__\n__POC_SHOT_B64__\n"}
    res = await ex.execute("record_poc", {"url": "http://example.com"})
    assert res["ok"] is False
    assert "Playwright/Chromium unavailable" in res["error"]
    assert "playwright install chromium" in res["error"]
    assert "screenshot_artifact_id" not in res  # no shot marker

    ex.container.python_result = {"stdout": "noise", "stderr": "boom"}
    res = await ex.execute("record_poc", {"url": "http://example.com"})
    assert "PoC recording failed: boom" in res["error"]


async def test_record_poc_success_video_and_frame(db, no_async_db, no_mirror):
    import base64 as b64mod

    from models.artifact import Artifact

    asn = _seed(db)
    ex = _exec(db, asn)
    video, frame = b"FAKEWEBM" * 10, b"PNGFRAME"
    ex.container.python_result = {"stdout":
        "__POC_ERR__ step click failed: nope; \n"
        + "__POC_B64__" + b64mod.b64encode(video).decode() + "\n"
        + "__POC_SHOT_B64__" + b64mod.b64encode(frame).decode() + "\n"}
    from models.card import Card

    card = Card(assessment_id=asn.id, card_type="finding", title="Reflected XSS",
                severity="HIGH")
    db.add(card)
    db.commit()
    db.refresh(card)
    ex.findings.append(card.id)  # attach evidence to the last recorded finding
    res = await ex.execute("record_poc", {
        "url": "http://example.com", "actions": [{"action": "click", "selector": "#x"}],
        "caption": "XSS replay"})
    assert res["ok"] is True and res["bytes"] == len(video) and res["steps"] == 1
    assert "non-fatal warning: step click failed" in res["note"]
    arts = db.query(Artifact).order_by(Artifact.id).all()
    vid, shot = arts[0], arts[-1]
    assert vid.kind == "video" and vid.data == video and vid.card_id == card.id
    assert vid.caption == "XSS replay" and vid.filename == "poc.webm"
    assert shot.kind == "screenshot" and shot.data == frame
    assert shot.caption == "XSS replay (final frame)"
    assert res["screenshot_artifact_id"] == shot.id


async def test_record_poc_oversized_video_rejected(db, no_async_db, no_mirror):
    import base64 as b64mod

    asn = _seed(db)
    ex = _exec(db, asn)
    big = b"\x00" * (ToolExecutor._POC_MAX_VIDEO_BYTES + 1)
    ex.container.python_result = {"stdout":
        "__POC_B64__" + b64mod.b64encode(big).decode() + "\n__POC_SHOT_B64__\n"}
    res = await ex.execute("record_poc", {"url": "http://example.com"})
    assert res["ok"] is False and "too large" in res["error"]


# ── _url_is_public (SSRF guard) ───────────────────────────────────────────────

def _resolve(monkeypatch, mapping):
    def fake_getaddrinfo(host, port, *a, **kw):
        if host in mapping:
            return [(2, 1, 6, "", (mapping[host], port))]
        import socket

        raise socket.gaierror(8, "unknown host")

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)


def test_url_is_public(db, monkeypatch):
    ok, host = ToolExecutor._url_is_public("https://example.com/page")
    assert (ok, host) == (True, "example.com")
    ok, err = ToolExecutor._url_is_public("ftp://example.com")
    assert ok is False and err == "only http/https URLs allowed"
    ok, err = ToolExecutor._url_is_public("not a url")
    assert ok is False


def test_url_is_public_blocks_private_and_unresolvable(db, monkeypatch):
    _resolve(monkeypatch, {"private.example": "10.1.2.3",
                           "meta.example": "169.254.169.254",
                           "pub.example": "93.184.216.34"})
    ok, err = ToolExecutor._url_is_public("http://private.example")
    assert ok is False and "non-public address (10.1.2.3)" in err
    ok, err = ToolExecutor._url_is_public("http://meta.example")
    assert ok is False and "169.254.169.254" in err
    ok, host = ToolExecutor._url_is_public("http://pub.example")
    assert (ok, host) == (True, "pub.example")
    ok, err = ToolExecutor._url_is_public("http://no-such.example")
    assert ok is False and "cannot resolve no-such.example" in err


# ── read_report ───────────────────────────────────────────────────────────────

class FakeStreamResp:
    def __init__(self, status_code=200, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = list(chunks)

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


class _StreamCtx:
    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *exc):
        return False


class FakeHTTPX:
    """httpx.AsyncClient stand-in with per-test canned behaviour."""
    created = 0
    get_result = None
    stream_resp = None
    raise_in_stream = False

    def __init__(self, **kw):
        FakeHTTPX.created += 1
        self.kwargs = kw
        self.gets = []
        self.streams = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        self.gets.append(url)
        return FakeHTTPX.get_result

    def stream(self, method, url):
        self.streams.append((method, url))
        return _StreamCtx(FakeHTTPX.stream_resp)


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    FakeHTTPX.created = 0
    FakeHTTPX.get_result = None
    FakeHTTPX.stream_resp = FakeStreamResp()
    FakeHTTPX.raise_in_stream = False
    monkeypatch.setattr("httpx.AsyncClient", FakeHTTPX)
    _resolve(monkeypatch, {"example.com": "93.184.216.34",
                           "hackerone.com": "199.232.1.1"})
    return FakeHTTPX


async def test_read_report_ssrf_guard_first(db, no_async_db):
    from pytest import MonkeyPatch

    mp = MonkeyPatch()
    try:
        _resolve(mp, {"example.com": "127.0.0.1"})
        ex = ToolExecutor(db, 1, parse_scope("example.com"))
        res = await ex._read_report({"url": "http://example.com/x"})
        assert res["ok"] is False and "non-public" in res["error"]
        assert FakeHTTPX.created == 0  # never constructed a client
    finally:
        mp.undo()


async def test_read_report_redirect_and_status(db, no_async_db):
    ex = ToolExecutor(db, 1, parse_scope("example.com"))
    FakeHTTPX.stream_resp = FakeStreamResp(status_code=302)
    res = await ex._read_report({"url": "http://example.com/x"})
    assert res["error"] == "redirect (302) not followed"
    FakeHTTPX.stream_resp = FakeStreamResp(status_code=404)
    res = await ex._read_report({"url": "http://example.com/x"})
    assert res["error"] == "HTTP 404"


async def test_read_report_size_caps(db, no_async_db, monkeypatch):
    monkeypatch.setattr(ToolExecutor, "_READ_REPORT_MAX_BYTES", 10)
    ex = ToolExecutor(db, 1, parse_scope("example.com"))
    FakeHTTPX.stream_resp = FakeStreamResp(headers={"content-length": "20"})
    res = await ex._read_report({"url": "http://example.com/x"})
    assert res["error"] == "response too large"
    # no content-length → bounded streaming read instead
    FakeHTTPX.stream_resp = FakeStreamResp(chunks=[b"0123456789", b"ABCDEFGH"])
    res = await ex._read_report({"url": "http://example.com/x"})
    assert res["ok"] is True and res["content"] == "0123456789"


async def test_read_report_strips_html(db, no_async_db):
    ex = ToolExecutor(db, 1, parse_scope("example.com"))
    body = (b"<html><nav>menu</nav><script>evil()</script>"
            b"<p>Hello &amp;   world</p><footer>by</footer></html>")
    FakeHTTPX.stream_resp = FakeStreamResp(chunks=[body])
    res = await ex._read_report({"url": "http://example.com/x"})
    assert res["ok"] is True and res["source"] == "web"
    assert res["content"] == "Hello world"


async def test_read_report_hackerone_json(db, no_async_db):
    class R:
        status_code = 200

        def json(self):
            return {"title": "Blind SQLi", "weakness": {"name": "SQL Injection"},
                    "bounty_amount": 1500, "currency": "USD",
                    "vulnerability_information": "steps to reproduce"}

    FakeHTTPX.get_result = R()
    ex = ToolExecutor(db, 1, parse_scope("example.com"))
    res = await ex._read_report({"url": "https://hackerone.com/reports/12345"})
    assert res["ok"] is True and res["source"] == "hackerone"
    assert res["content"].startswith("Title: Blind SQLi\nWeakness: SQL Injection")
    assert "Bounty: 1500 USD" in res["content"]
    assert "steps to reproduce" in res["content"]


# ── knowledge tools ───────────────────────────────────────────────────────────

def _seed_knowledge(db, asn):
    from models.knowledge_entry import KnowledgeEntry

    db.add(KnowledgeEntry(source="nvd", ext_id="CVE-2024-1111",
                          title="SQL injection in widget parser",
                          description="Parser builds queries by concatenation.",
                          severity="HIGH", cwe="CWE-89"))
    db.add(KnowledgeEntry(source="skill", ext_id="web_recon",
                          title="Web recon methodology", content="# Web recon",
                          references=["https://aida.local/skill"]))
    db.commit()


async def test_search_knowledge(db, no_async_db):
    asn = _seed(db)
    _seed_knowledge(db, asn)
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    res = await ex.execute("search_knowledge", {"query": "SQL injection"})
    assert res["ok"] is True and res["count"] >= 1
    hit = next(r for r in res["results"] if r["slug"] == "CVE-2024-1111")
    assert hit["source"] == "nvd" and hit["severity"] == "HIGH"
    assert hit["cwe"] == "CWE-89" and "concatenation" in hit["summary"]
    assert hit["references"] is None  # only skills/bugbounty carry references

    res = await ex.execute("search_knowledge", {"query": "recon"})
    hit = next(r for r in res["results"] if r["slug"] == "web_recon")
    assert hit["references"] == ["https://aida.local/skill"]
    assert "read_skill(slug)" in res["hint"]


async def test_read_skill(db, no_async_db, monkeypatch):
    asn = _seed(db)
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    monkeypatch.setattr("services.skills_loader.read_skill_file",
                        lambda slug, reference=None: f"# {slug}\nsteps")
    res = await ex.execute("read_skill", {"skill": "sqli"})
    assert res == {"ok": True, "skill": "sqli", "reference": None,
                   "content": "# sqli\nsteps"}
    res = await ex.execute("read_skill", {"skill": "sqli", "reference": "refs.md"})
    assert res["reference"] == "refs.md"


async def test_read_skill_db_fallback_and_fuzzy(db, no_async_db, monkeypatch):
    monkeypatch.setattr("services.skills_loader.read_skill_file",
                        lambda slug, reference=None: None)
    asn = _seed(db)
    _seed_knowledge(db, asn)
    ex = ToolExecutor(db, asn.id, parse_scope("example.com"))
    # exact ext_id match in the knowledge base
    res = await ex.execute("read_skill", {"skill": "web_recon"})
    assert res["ok"] is True
    assert res["content"].startswith("# Web recon methodology")
    # fuzzy: separators differ ("web-recon" vs "web_recon")
    res = await ex.execute("read_skill", {"skill": "WEB-recon"})
    assert res["ok"] is True and "# Web recon" in res["content"]
    # nowhere to be found
    res = await ex.execute("read_skill", {"skill": "nope"})
    assert res == {"ok": False, "error": "skill 'nope' not found"}
