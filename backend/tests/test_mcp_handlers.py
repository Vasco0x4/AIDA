"""
MCP tool handlers (mcp/modules/mcp_handlers.py) + scan output parsers.

The handlers format TextContent replies over an `mcp_service` that talks to the
backend over HTTP. Everything here is hermetic: a FakeMcpService whose
http_client serves canned responses, no network, no containers.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# The MCP server imports these modules FLAT (sys.path gets mcp/modules added —
# see aida_mcp_server.py), so the tests import them the same way.
_MODULES_DIR = Path(__file__).resolve().parent.parent / "mcp" / "modules"
if str(_MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULES_DIR))

import mcp_handlers  # noqa: E402
from scan_parsers import (  # noqa: E402
    parse_generic_output,
    parse_nmap_output,
    parse_nuclei_output,
    parse_scan_output,
    parse_subdomain_output,
)


# --- fakes -------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, json_data=None, error_text=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.error_text = error_text or f"HTTP {status_code} error"

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(self.error_text)


class FakeHTTPClient:
    """Routes (method, url-substring) → response or callable(params/json)."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls: list[tuple] = []

    def _route(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, frag), handler in self.routes.items():
            if m == method and frag in url:
                return handler(kw) if callable(handler) else handler
        return FakeResponse(404, None, error_text=f"no route for {method} {url}")

    async def get(self, url, params=None, **kw):
        return self._route("GET", url, params=params, **kw)

    async def post(self, url, json=None, **kw):
        return self._route("POST", url, json=json, **kw)

    async def patch(self, url, json=None, **kw):
        return self._route("PATCH", url, json=json, **kw)

    async def delete(self, url, **kw):
        return self._route("DELETE", url, **kw)


class FakeMcpService:
    """Stands in for AidaMCPService — just the surface handlers touch."""

    def __init__(self, http_routes=None):
        self.backend_url = "http://backend.test"
        self.http_client = FakeHTTPClient(http_routes)
        self.current_assessment_id = None
        self.current_assessment_name = None
        self.current_container = None
        self.initialize_calls = 0
        self.cards_added: list[dict] = []
        self.recon_added: list[dict] = []

    async def initialize(self):
        self.initialize_calls += 1

    async def get_assessment_by_name(self, name):
        return None

    async def get_assessment_full_data(self, assessment_id):
        return {"assessment": {}, "sections": [], "cards": [], "recon_data": []}

    async def add_card(self, assessment_id, **card):
        self.cards_added.append(card)
        return {"id": 101, **card}

    async def add_recon_data(self, assessment_id, **entry):
        self.recon_added.append(entry)
        return {"id": 55, **entry}

    async def get_command_history_limit(self):
        return 10

    async def get_output_max_length(self):
        return 5000

    async def get_python_exec_output_max_length(self):
        return 5000

    async def get_http_request_output_max_length(self):
        return 5000

    async def check_tool_availability(self, tool):
        return True


def _text(result):
    assert len(result) == 1
    return result[0].text


@pytest.fixture()
def no_sleep(monkeypatch):
    """Approval polls sleep 2s each — collapse them for tests."""
    async def _fast(_seconds):
        return None
    monkeypatch.setattr(asyncio, "sleep", _fast)


# --- scan_parsers -------------------------------------------------------------------

NMAP_SAMPLE = """Starting Nmap 7.94
Nmap scan report for 10.0.0.5
Host is up (0.001s latency).
22/tcp   open  ssh
80/tcp   open  http
443/tcp  open  https
Service Info: OS: Linux
"""


def test_parse_nmap_open_ports_and_services():
    out = parse_nmap_output(NMAP_SAMPLE, {})
    assert "Nmap Scan Results" in out
    assert "Open Ports (3)" in out
    assert "22/tcp   open  ssh" in out
    assert "Services Detected" in out
    assert "OS: Linux" in out


def test_parse_nmap_no_open_ports():
    out = parse_nmap_output("nothing here\n", {})
    assert "No open ports found." in out


def test_parse_nmap_caps_ports_at_15():
    stdout = "\n".join(f"{p}/tcp  open  svc{p}" for p in range(10000, 10020))
    out = parse_nmap_output(stdout, {})
    assert "Open Ports (20)" in out
    assert "... and 5 more ports" in out


def test_parse_scan_output_dispatch():
    result = {"stdout": NMAP_SAMPLE, "success": True}
    assert "Nmap Scan Results" in parse_scan_output("nmap -sV target", result)
    assert "Gobuster" in parse_scan_output("gobuster dir -u x", {"stdout": "", "success": True})
    assert "Nikto" in parse_scan_output("nikto -h x", {"stdout": "", "success": True})
    assert "Nuclei" in parse_scan_output("nuclei -u x", {"stdout": "", "success": True})
    assert "Subdomain" in parse_scan_output("subfinder -d x", {"stdout": "a.x\nb.x\n", "success": True})
    assert "Subdomain" in parse_scan_output("amass enum -d x", {"stdout": "a.x\n", "success": True})
    assert "Command completed (no output)" in parse_scan_output("whoami", {"stdout": "", "success": True})


def test_parse_nuclei_severity_buckets():
    stdout = (
        "[critical] CVE-1 a\n[high] CVE-2 b\n[medium] CVE-3 c\n"
        "[low] CVE-4 d\n[info] CVE-5 e\n[high] CVE-6 f\n"
    )
    out = parse_nuclei_output(stdout, {})
    assert "CRITICAL (1)" in out
    assert "HIGH (2)" in out
    assert "MEDIUM (1)" in out
    assert "Total findings: 6" in out


def test_parse_subdomain_output_filters_and_caps():
    stdout = "\n".join([f"sub{i}.example.com" for i in range(25)] + ["", "no-dot-line"])
    out = parse_subdomain_output(stdout, {})
    assert "Found 25 subdomains" in out
    assert "... and 5 more" in out
    assert "no-dot-line" not in out
    assert "No subdomains found." in parse_subdomain_output("", {})


def test_parse_generic_output_branches():
    long = "x" * 20
    out = parse_generic_output(long, {"success": True}, max_length=10)
    assert out.count("x") == 10
    assert "showing 10/20 chars" in out

    assert parse_generic_output("abc", {"success": True}, max_length=-1).count("x") == 0
    assert "abc" in parse_generic_output("abc", {"success": True}, max_length=-1)

    assert "binary file matches" in parse_generic_output(
        "", {"success": True, "stderr": "grep: binary file matches"})[:80]

    assert "Command completed (no output)" in parse_generic_output("", {"success": True})

    assert "ERROR: boom" in parse_generic_output("", {"success": False, "stderr": "boom"})
    assert "ERROR: Unknown error" in parse_generic_output("", {"success": False})


def test_parse_gobuster_status_groups():
    stdout = "/admin (Status: 200)\n/login (Status: 301)\n/secret (Status: 403)\n"
    out = parse_scan_output("gobuster dir -u http://x", {"stdout": stdout, "success": True})
    assert "Status 200 (1)" in out and "/admin" in out
    assert "Redirects (1)" in out and "/login" in out
    assert "Forbidden (1)" in out and "/secret" in out
    assert "No paths found." in parse_scan_output(
        "gobuster dir -u http://x", {"stdout": "nothing", "success": True})


def test_parse_nikto_findings():
    stdout = ("+ OSVDB-1: something\n+ CVE-2024-1: other\n- plain line\n"
              "+ INFO line without marker\n")
    out = parse_scan_output("nikto -h x", {"stdout": stdout, "success": True})
    assert "Potential Issues (2)" in out
    assert "OSVDB-1" in out and "CVE-2024-1" in out
    assert "No major issues found." in parse_scan_output(
        "nikto -h x", {"stdout": "+ harmless\n", "success": True})


# --- dispatcher ----------------------------------------------------------------------

async def test_dispatch_unknown_tool():
    out = _text(await mcp_handlers.handle_tool_call("nope", {}, FakeMcpService()))
    assert "Unknown tool: `nope`" in out


async def test_dispatch_wraps_handler_exceptions():
    class Exploding(FakeMcpService):
        async def initialize(self):
            raise RuntimeError("boom at init")

    out = _text(await mcp_handlers.handle_tool_call("list_cards", {}, Exploding()))
    assert out.startswith("Error:")


async def test_dispatch_initializes_service():
    svc = FakeMcpService()
    await mcp_handlers.handle_tool_call(
        "list_cards", {}, svc)  # no assessment → early return text
    assert svc.initialize_calls == 1


# --- _await_command_approval ----------------------------------------------------------

def _approval_service(poll_responses, create_response=None):
    routes = {
        ("POST", "/pending-commands/create"):
            create_response if create_response is not None
            else FakeResponse(200, {"id": 9}),
    }
    poll_iter = list(poll_responses)

    def _poll(kw):
        return poll_iter.pop(0) if poll_iter else FakeResponse(200, {"status": "pending"})

    routes[("GET", "/pending-commands/9")] = _poll
    return FakeMcpService(routes)


async def test_approval_create_failure_is_error(no_sleep):
    svc = _approval_service([], FakeResponse(500, None, error_text="backend down"))
    status, payload = await mcp_handlers._await_command_approval(
        svc, command="nmap x", phase="1", matched_keywords=[], timeout_seconds=5)
    assert status == "error"
    assert "backend down" in payload


async def test_approval_invalid_id_is_error(no_sleep):
    svc = _approval_service([], FakeResponse(200, {}))
    status, payload = await mcp_handlers._await_command_approval(
        svc, command="x", phase=None, matched_keywords=[], timeout_seconds=5)
    assert status == "error" and payload == "invalid approval request"


async def test_approval_approved_returns_execution_result(no_sleep):
    svc = _approval_service([
        FakeResponse(200, {"status": "executed", "execution_result": {"stdout": "ok"}}),
    ])
    status, payload = await mcp_handlers._await_command_approval(
        svc, command="x", phase="2", matched_keywords=["nmap"], timeout_seconds=5)
    assert status == "approved"
    assert payload == {"stdout": "ok"}
    create = [c for c in svc.http_client.calls if c[0] == "POST"][0]
    assert create[2]["json"]["command"] == "x"
    assert create[2]["json"]["matched_keywords"] == ["nmap"]


async def test_approval_rejected_and_timeout(no_sleep):
    svc = _approval_service([FakeResponse(200, {"status": "rejected"})])
    status, payload = await mcp_handlers._await_command_approval(
        svc, command="x", phase=None, matched_keywords=[], timeout_seconds=5)
    assert (status, payload) == ("rejected", None)

    # deadline already elapsed → immediate timeout, no polls
    svc2 = _approval_service([FakeResponse(200, {"status": "executed"})])
    status, payload = await mcp_handlers._await_command_approval(
        svc2, command="x", phase=None, matched_keywords=[], timeout_seconds=0)
    assert (status, payload) == ("timeout", None)


async def test_approval_backend_unreachable_stops_early(no_sleep):
    svc = _approval_service([FakeResponse(500, None, error_text="down")] * 5)
    status, payload = await mcp_handlers._await_command_approval(
        svc, command="x", phase=None, matched_keywords=[], timeout_seconds=60)
    assert status == "error"
    assert "unreachable" in payload


# --- assessment handlers -------------------------------------------------------------

async def test_load_assessment_not_found():
    out = _text(await mcp_handlers.handle_tool_call(
        "load_assessment", {"name": "ghost"}, FakeMcpService()))
    assert "not found" in out
    assert "USER must create it" in out


async def test_load_assessment_skip_data():
    svc = FakeMcpService()
    svc.get_assessment_by_name = _async_value({"id": 7, "name": "acme"})
    out = _text(await mcp_handlers.handle_tool_call(
        "load_assessment", {"name": "acme", "skip_data": True}, svc))
    assert "loaded successfully" in out
    assert svc.current_assessment_id == 7
    assert svc.current_assessment_name == "acme"


def _async_value(value):
    async def _fn(*a, **kw):
        return value
    return _fn


async def test_load_assessment_full_data():
    full = {
        "assessment": {
            "id": 7, "name": "acme", "client_name": "ACME Ltd",
            "environment": "prod", "scope": "*.acme.test", "limitations": "no DoS",
            "target_domains": ["acme.test"], "ip_scopes": ["10.0.0.0/8"],
        },
        "sections": [
            {"section_type": "phase_1", "content": "did recon"},
            {"section_type": "phase_9", "content": "weird phase"},
        ],
        "cards": [
            {"id": 1, "card_type": "finding", "title": "SQLi", "severity": "HIGH",
             "status": "confirmed", "cvss_score": 8.1, "target_service": "web",
             "technical_analysis": "analysis", "proof": "proof", "notes": "n",
             "context": "c", "created_at": "2026-01-01"},
            {"id": 2, "card_type": "finding", "title": "FP", "severity": "LOW",
             "status": "false_positive"},
            {"id": 3, "card_type": "observation", "title": "Old TLS", "notes": "note"},
            {"id": 4, "card_type": "info", "title": "Host info", "context": "ctx"},
        ],
        "recon_data": [
            {"data_type": "endpoint", "name": "/api"},
            {"data_type": "subdomain", "name": "a.acme.test"},
            {"data_type": "custom_thing", "name": "weird"},
        ],
    }

    class S(FakeMcpService):
        def __init__(self):
            super().__init__()
            self.current_assessment_id = 7

    svc = S()
    svc.get_assessment_by_name = _async_value({"id": 7, "name": "acme"})
    svc.get_assessment_full_data = _async_value(full)
    # command history + credentials come over http
    svc.http_client.routes[("GET", "/commands")] = FakeResponse(
        200, [{"command": "nmap -sV x", "stdout": "out", "stderr": ""}])
    svc.http_client.routes[("GET", "/credentials")] = FakeResponse(200, {
        "credentials": [
            {"name": "api", "credential_type": "api_key", "placeholder": "API_KEY",
             "token": "tok", "service": "svc", "target": "t", "notes": "n"},
            {"name": "ssh", "credential_type": "ssh", "placeholder": "SSH",
             "username": "root", "password": "pw"},
        ]})

    out = _text(await mcp_handlers.handle_tool_call(
        "load_assessment", {"name": "acme"}, svc))

    assert "Assessment Loaded: acme" in out
    assert "ACME Ltd" in out and "*.acme.test" in out
    assert "Phase 1 - Reconnaissance" in out and "did recon" in out
    assert "Findings (1 total)" in out          # false positive filtered out
    assert "HIGH (1)" in out and "SQLi" in out and "8.1" in out
    assert "Observations (1 total)" in out and "Old TLS" in out
    assert "Info Cards (1 total)" in out
    assert "**Endpoints (1):** /api" in out
    assert "**Subdomains (1):** a.acme.test" in out
    assert "**Custom things (1):** weird" in out
    assert "Recent Commands (1" in out and "nmap -sV x" in out
    assert "Credentials (2 available)" in out
    assert "API_KEY" in out and "Value: `tok`" in out
    assert "Username: `root`" in out and "Password: `pw`" in out
    assert "Ready to begin assessment work!" in out


async def test_load_assessment_empty_everything():
    class S(FakeMcpService):
        def __init__(self):
            super().__init__()
            self.current_assessment_id = 7

    svc = S()
    svc.get_assessment_by_name = _async_value({"id": 7, "name": "empty"})
    svc.get_assessment_full_data = _async_value({
        "assessment": {"id": 7, "name": "empty"},
        "sections": [], "cards": [], "recon_data": []})
    svc.get_command_history_limit = _async_value(0)  # disabled → skipped
    svc.http_client.routes[("GET", "/credentials")] = FakeResponse(
        200, {"credentials": []})

    out = _text(await mcp_handlers.handle_tool_call(
        "load_assessment", {"name": "empty"}, svc))
    assert "No credentials configured yet" in out
    assert "Recent Commands" not in out


async def test_create_assessment_requires_name():
    out = _text(await mcp_handlers.handle_tool_call(
        "create_assessment", {"name": "   "}, FakeMcpService()))
    assert "name is required" in out


async def test_create_assessment_success_and_autoload():
    svc = FakeMcpService()
    svc.http_client.routes[("POST", "/assessments")] = FakeResponse(200, {
        "id": 12, "name": "newco", "status": "active", "category": "web",
        "environment": "prod", "container_name": "exa-newco",
        "workspace_path": "/workspace/newco", "scope": "*.newco.test",
        "target_domains": ["newco.test"], "ip_scopes": ["10.1.0.0/16"],
        "limitations": "none", "objectives": "find bugs", "client_name": "NC"})

    out = _text(await mcp_handlers.handle_tool_call("create_assessment", {
        "name": "newco", "client_name": "NC", "scope": "*.newco.test",
        "unknown_field": "dropped",
    }, svc))

    assert "Created and Loaded: newco" in out
    assert svc.current_assessment_id == 12
    sent = [c for c in svc.http_client.calls if c[0] == "POST"][0][2]["json"]
    assert sent == {"name": "newco", "client_name": "NC", "scope": "*.newco.test"}


async def test_create_assessment_bad_request():
    svc = FakeMcpService()
    svc.http_client.routes[("POST", "/assessments")] = FakeResponse(
        400, {"detail": "name already used"})
    out = _text(await mcp_handlers.handle_tool_call(
        "create_assessment", {"name": "dup"}, svc))
    assert "Error: name already used" in out


async def test_list_assessments_formats_rows():
    svc = FakeMcpService()
    svc.http_client.routes[("GET", "/assessments")] = lambda kw: FakeResponse(200, [
        {"name": "one", "status": "active", "category": "web", "client_name": "C1"},
        {"name": "two", "status": "completed"},
    ])
    out = _text(await mcp_handlers.handle_tool_call("list_assessments", {}, svc))
    assert "Assessments (2)" in out
    assert "● **one** [web] — active | Client: C1" in out
    assert "✓ **two** — completed" in out
    params = [c for c in svc.http_client.calls if c[0] == "GET"][0][2]["params"]
    assert params == {"limit": 50}


async def test_list_assessments_empty_and_filtered():
    svc = FakeMcpService()
    svc.http_client.routes[("GET", "/assessments")] = FakeResponse(200, [])
    out = _text(await mcp_handlers.handle_tool_call(
        "list_assessments", {"status": "archived"}, svc))
    assert "No assessments found with status 'archived'." in out


# --- cards handlers -------------------------------------------------------------------

async def test_cards_require_loaded_assessment():
    for tool in ("add_card", "list_cards", "update_card", "delete_card"):
        out = _text(await mcp_handlers.handle_tool_call(tool, {}, FakeMcpService()))
        assert "No assessment loaded" in out


async def test_add_card_finding_with_cvss_vector():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    out = _text(await mcp_handlers.handle_tool_call("add_card", {
        "card_type": "finding", "title": "RCE",
        "cvss_vector": "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H",
    }, svc))
    assert "Finding added: RCE" in out and "[ID: 101]" in out
    card = svc.cards_added[0]
    assert card["cvss_score"] is not None
    assert card["severity"] in ("CRITICAL", "HIGH")
    assert card["status"] == "confirmed"           # default for findings


async def test_add_card_finding_requires_severity_or_vector():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    out = _text(await mcp_handlers.handle_tool_call("add_card", {
        "card_type": "finding", "title": "no-sev"}, svc))
    assert "require either cvss_vector or severity" in out
    assert svc.cards_added == []


async def test_add_card_observation_and_info():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    out = _text(await mcp_handlers.handle_tool_call("add_card", {
        "card_type": "observation", "title": "obs", "notes": "n"}, svc))
    assert "Observation added: obs" in out
    out = _text(await mcp_handlers.handle_tool_call("add_card", {
        "card_type": "info", "title": "inf", "context": "c"}, svc))
    assert "Info added: inf" in out
    assert svc.cards_added[0] == {"card_type": "observation", "title": "obs", "notes": "n"}
    assert svc.cards_added[1] == {"card_type": "info", "title": "inf", "context": "c"}


async def test_list_cards_filters_and_formats():
    full = {"cards": [
        {"id": 1, "card_type": "finding", "title": "SQLi", "severity": "HIGH",
         "status": "confirmed", "target_service": "web",
         "technical_analysis": "x" * 150},
        {"id": 2, "card_type": "finding", "title": "FP", "status": "false_positive"},
        {"id": 3, "card_type": "observation", "title": "obs", "notes": "short note"},
    ]}
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.get_assessment_full_data = _async_value(full)

    out = _text(await mcp_handlers.handle_tool_call("list_cards", {}, svc))
    assert "Cards (2)" in out                    # false positive hidden
    assert "[FINDING] [HIGH] SQLi" in out
    assert "x" * 100 + "..." in out              # long preview truncated
    assert "[OBSERVATION] obs" in out

    out = _text(await mcp_handlers.handle_tool_call(
        "list_cards", {"card_type": "observation"}, svc))
    assert "Cards (1)" in out

    out = _text(await mcp_handlers.handle_tool_call(
        "list_cards", {"severity": "HIGH"}, svc))
    assert "Cards (1)" in out

    out = _text(await mcp_handlers.handle_tool_call(
        "list_cards", {"limit": 0}, svc))
    assert "No cards found" in out


async def test_update_card_sends_only_provided_fields():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("PATCH", "/cards/3")] = FakeResponse(200, {})

    out = _text(await mcp_handlers.handle_tool_call("update_card", {
        "card_id": 3, "status": "false_positive", "notes": "not exploitable"}, svc))
    assert "Card 3 updated successfully" in out
    sent = [c for c in svc.http_client.calls if c[0] == "PATCH"][0][2]["json"]
    assert sent == {"status": "false_positive", "notes": "not exploitable"}

    out = _text(await mcp_handlers.handle_tool_call(
        "update_card", {"card_id": 3}, svc))
    assert "No fields to update" in out


async def test_update_card_recovers_cvss_from_vector():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("PATCH", "/cards/4")] = FakeResponse(200, {})
    await mcp_handlers.handle_tool_call("update_card", {
        "card_id": 4,
        "cvss_vector": "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H",
    }, svc)
    sent = [c for c in svc.http_client.calls if c[0] == "PATCH"][0][2]["json"]
    assert sent["cvss_score"] > 0
    assert sent["severity"] in ("CRITICAL", "HIGH")


async def test_delete_card():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("DELETE", "/cards/5")] = FakeResponse(200, {})
    out = _text(await mcp_handlers.handle_tool_call(
        "delete_card", {"card_id": 5}, svc))
    assert "Card 5 deleted successfully" in out


# --- ASVS handlers -------------------------------------------------------------------

async def test_asvs_tools_require_loaded_assessment():
    for tool in ("list_asvs_requirements", "get_asvs_summary", "update_asvs_requirement"):
        out = _text(await mcp_handlers.handle_tool_call(tool, {}, FakeMcpService()))
        assert "No assessment loaded" in out


async def test_list_asvs_requirements_groups_by_section():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.list_asvs_requirements = _async_value([
        {"req_id": "1.1.1", "section_id": "1.1", "section_name": "Docs",
         "level": 1, "status": "PASS", "description": "d1", "test_type": "t",
         "guidance": "g", "suggested_command": "cmd1", "analysis": "a1"},
        {"req_id": "1.1.2", "section_id": "1.1", "section_name": "Docs",
         "level": 2, "status": "NOT_TESTED", "description": "d2"},
        {"req_id": "2.1.1", "section_id": "2.1", "section_name": "Auth",
         "level": 1, "status": "FAIL", "description": "d3"},
    ])
    out = _text(await mcp_handlers.handle_tool_call("list_asvs_requirements", {}, svc))
    assert "ASVS requirements (3)" in out
    assert out.count("### 1.1 Docs") == 1        # section header printed once
    assert "**1.1.1** [L1] [PASS] d1" in out
    assert "Suggested command: `cmd1`" in out
    assert "### 2.1 Auth" in out
    # no-match branch
    svc.list_asvs_requirements = _async_value([])
    out = _text(await mcp_handlers.handle_tool_call("list_asvs_requirements", {}, svc))
    assert "No ASVS requirements match" in out


async def test_get_asvs_summary_formats_coverage():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.get_asvs_summary = _async_value({
        "asvs_version": "4.0.3", "asvs_level": 2, "total": 100, "tested": 40,
        "coverage_pct": 40,
        "by_status": {"PASS": 30, "FAIL": 10, "NA": 5, "NOT_TESTED": 55},
        "by_chapter": [
            {"chapter_id": "V1", "chapter_name": "Architecture", "total": 10,
             "tested": 5, "by_status": {"FAIL": 2, "NOT_TESTED": 5}},
        ],
    })
    out = _text(await mcp_handlers.handle_tool_call("get_asvs_summary", {}, svc))
    assert "v4.0.3" in out and "target L2" in out
    assert "Tested: 40 (40%)" in out
    assert "PASS 30 · FAIL 10" in out
    assert "V1 Architecture: 5/10 tested (FAIL 2, NOT_TESTED 5)" in out


async def test_update_asvs_requirement_payload_and_reply():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.update_asvs_requirement = _async_value(
        {"status": "FAIL", "cvss_score": 9.3, "severity": "CRITICAL"})

    out = _text(await mcp_handlers.handle_tool_call("update_asvs_requirement", {
        "req_id": "2.4.1", "status": "fail", "analysis": "broken",
        "cvss_vector": "CVSS:4.0/AV:N/AC:H/AT:N/PR:L/UI:N/VC:H/VI:L/VA:L/SC:L/SI:L/SA:L",
    }, svc))
    assert "ASVS 2.4.1 → FAIL — CVSS 9.3 (CRITICAL)" in out


async def test_update_asvs_requirement_captures_call():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    calls = []
    async def _capture(**kw):
        calls.append(kw)
        return {"status": "PASS"}
    svc.update_asvs_requirement = _capture

    out = _text(await mcp_handlers.handle_tool_call("update_asvs_requirement", {
        "req_id": "1.2.3", "status": "pass", "evidence": "ev", "command_used": "cu",
    }, svc))
    assert "ASVS 1.2.3 → PASS" in out
    assert calls == [{"assessment_id": 7, "req_id": "1.2.3",
                      "status": "pass", "evidence": "ev", "command_used": "cu"}]


# --- recon handlers ------------------------------------------------------------------

async def test_recon_tools_require_loaded_assessment():
    for tool in ("add_recon_data", "list_recon"):
        out = _text(await mcp_handlers.handle_tool_call(tool, {}, FakeMcpService()))
        assert "No assessment loaded" in out


async def test_add_recon_data_single_and_batch():
    svc = FakeMcpService()
    svc.current_assessment_id = 7

    out = _text(await mcp_handlers.handle_tool_call("add_recon_data", {
        "data_type": "endpoint", "name": "/api", "details": "json api",
        "discovered_in_phase": "1"}, svc))
    assert "Recon data added: endpoint -> /api [ID: 55]" in out

    svc.http_client.routes[("POST", "/recon/batch")] = FakeResponse(200, {
        "created_count": 3, "summary": {"subdomain": 2, "endpoint": 1}})
    out = _text(await mcp_handlers.handle_tool_call("add_recon_data", {
        "entries": [{"data_type": "subdomain", "name": "a.x"},
                    {"data_type": "subdomain", "name": "b.x"},
                    {"data_type": "endpoint", "name": "/api"}]}, svc))
    assert "Added 3 recon entries: 2 subdomain(s), 1 endpoint(s)" in out

    out = _text(await mcp_handlers.handle_tool_call(
        "add_recon_data", {"entries": []}, svc))
    assert "No entries provided." in out

    svc.http_client.routes[("POST", "/recon/batch")] = FakeResponse(
        500, None, error_text="boom")
    out = _text(await mcp_handlers.handle_tool_call(
        "add_recon_data", {"entries": [{"data_type": "x", "name": "y"}]}, svc))
    assert "Error adding batch recon data" in out


async def test_list_recon_filters_and_formats():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.get_assessment_full_data = _async_value({"recon_data": [
        {"id": 1, "data_type": "endpoint", "name": "/api",
         "discovered_in_phase": "1", "details": "d"},
        {"id": 2, "data_type": "subdomain", "name": "a.x",
         "discovered_in_phase": "2"},
    ]})
    out = _text(await mcp_handlers.handle_tool_call("list_recon", {}, svc))
    assert "Reconnaissance Data (2)" in out
    assert "**ID: 1** | [endpoint] /api" in out
    assert "Details: d" in out

    out = _text(await mcp_handlers.handle_tool_call(
        "list_recon", {"data_type": "subdomain"}, svc))
    assert "Reconnaissance Data (1)" in out

    out = _text(await mcp_handlers.handle_tool_call("list_recon", {"limit": 0}, svc))
    assert "No recon data found." in out


# --- execute / python_exec / http_request ---------------------------------------------

def _exec_service(mode="open", filters=None, exec_result=None, http_rules=None,
                  exec_error=None):
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("GET", "/command-settings")] = FakeResponse(200, {
        "execution_mode": mode,
        "filter_keywords": filters or [],
        "timeout_seconds": 5,
        "http_method_rules": http_rules or {},
    })
    if exec_error is not None:
        svc.http_client.routes[("POST", "/commands/")] = exec_error
    elif exec_result is not None:
        svc.http_client.routes[("POST", "/commands/")] = FakeResponse(200, exec_result)
    return svc


async def test_execute_requires_assessment_and_open_mode(no_sleep):
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, FakeMcpService()))
    assert "No assessment loaded" in out

    svc = _exec_service(exec_result={"success": True, "stdout": "hello\n"})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "hello" in out
    sent = [c for c in svc.http_client.calls if c[0] == "POST"][0][2]["json"]
    assert sent == {"command": "ls", "phase": None}


async def test_execute_settings_unavailable_defaults_open(no_sleep):
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("GET", "/command-settings")] = FakeResponse(
        500, None, error_text="settings down")
    svc.http_client.routes[("POST", "/commands/")] = FakeResponse(
        200, {"success": True, "stdout": "ran"})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "ran" in out


async def test_execute_open_mode_failure_and_timeout(no_sleep):
    svc = _exec_service(exec_result={
        "success": False, "returncode": 2, "stdout": "partial", "stderr": "oops"})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "exit code 2" in out and "partial" in out and "oops" in out

    svc = _exec_service(exec_result={
        "success": False, "returncode": 1, "stdout": "", "stderr": "only-err"})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "ERROR: only-err" in out

    svc = _exec_service(exec_result={"success": False, "returncode": 3,
                                     "stdout": "", "stderr": ""})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "exit code 3" in out

    svc = _exec_service(exec_result={"status": "timeout", "execution_time": 42})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "slow"}, svc))
    assert "Timeout (42s exceeded)" in out
    assert "pausing until you provide the output" in out


async def test_execute_filter_mode_triggers_approval(no_sleep):
    # filter keyword hit → approval → approved with result
    svc = _exec_service(mode="filter", filters=["nmap"])
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "executed", "execution_result": {"stdout": "scan ok",
                                                         "success": True}})

    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "nmap -sV target"}, svc))
    assert "scan ok" in out
    create = [c for c in svc.http_client.calls
              if c[0] == "POST" and "pending-commands/create" in c[1]][0]
    assert create[2]["json"]["matched_keywords"] == ["nmap"]
    # the direct execute endpoint must NOT have been called
    assert not [c for c in svc.http_client.calls if "execute-with-credentials" in c[1]]


async def test_execute_closed_mode_rejected_and_timeout(no_sleep):
    svc = _exec_service(mode="closed")
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "rejected"})

    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "Command rejected by user" in out

    svc2 = _exec_service(mode="closed")
    svc2.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc2.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "pending"})
    # timeout_seconds=0 in settings? no — settings say 5; force fast timeout:
    svc2.http_client.routes[("GET", "/command-settings")] = FakeResponse(200, {
        "execution_mode": "closed", "filter_keywords": [], "timeout_seconds": 0})
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc2))
    assert "approval timed out after 0s" in out


async def test_execute_approval_create_failure_blocks(no_sleep):
    svc = _exec_service(mode="closed")
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        500, None, error_text="cannot create")
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "ls"}, svc))
    assert "blocked - failed to create approval request" in out
    assert "NOT executed" in out


async def test_execute_placeholder_error_gets_hint(no_sleep):
    svc = _exec_service(exec_error=FakeResponse(
        404, None, error_text="404 Client Error: Placeholder {{KEY}} not found"))
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "curl -H {{KEY}}"}, svc))
    assert "credentials_list" in out

    svc = _exec_service(exec_error=FakeResponse(
        500, None, error_text="500 boom"))
    out = _text(await mcp_handlers.handle_tool_call(
        "execute", {"command": "x"}, svc))
    assert "ERROR executing command: 500 boom" in out


# --- python_exec ----------------------------------------------------------------------

async def test_python_exec_validation(no_sleep):
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "print(1)"}, FakeMcpService()))
    assert "No assessment loaded" in out

    svc = FakeMcpService()
    svc.current_assessment_id = 7
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "   "}, svc))
    assert "No code provided." in out


async def test_python_exec_open_mode_success_and_failure(no_sleep):
    svc = _exec_service()
    svc.http_client.routes[("POST", "/commands/python-exec")] = FakeResponse(
        200, {"success": True, "stdout": "42"})
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "print(21*2)", "phase": "2"}, svc))
    assert "42" in out
    sent = [c for c in svc.http_client.calls
            if "python-exec" in c[1]][0][2]["json"]
    assert sent == {"code": "print(21*2)", "phase": "2"}

    svc2 = _exec_service()
    svc2.http_client.routes[("POST", "/commands/python-exec")] = FakeResponse(
        200, {"success": True, "stdout": ""})
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "pass"}, svc2))
    assert "no output" in out.lower()

    svc3 = _exec_service()
    svc3.http_client.routes[("POST", "/commands/python-exec")] = FakeResponse(
        200, {"success": False, "returncode": 1, "stdout": "", "stderr": "SyntaxError"})
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "bad("}, svc3))
    assert "**Python error:**" in out
    assert "SyntaxError" in out

    svc4 = _exec_service()
    svc4.http_client.routes[("POST", "/commands/python-exec")] = FakeResponse(
        200, {"status": "timeout", "execution_time": 60})
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "while True: pass"}, svc4))
    assert "Timeout (60s exceeded)" in out


async def test_python_exec_filter_mode_keyword_in_code(no_sleep):
    svc = _exec_service(mode="filter", filters=["os.system"])
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "executed", "execution_result": {
            "stdout": "shell out", "success": True}})

    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "import os\nos.system('id')"}, svc))
    assert "shell out" in out
    create = [c for c in svc.http_client.calls
              if c[0] == "POST" and "pending-commands/create" in c[1]][0]
    assert create[2]["json"]["command_type"] == "python"
    assert not [c for c in svc.http_client.calls if "python-exec" in c[1]]


async def test_python_exec_rejected_by_user(no_sleep):
    svc = _exec_service(mode="closed")
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "rejected"})
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "x=1"}, svc))
    assert "python_exec rejected by user." in out


async def test_python_exec_transport_error(no_sleep):
    svc = _exec_service(exec_error=FakeResponse(500, None, error_text="500 nope"))
    svc.http_client.routes[("POST", "/commands/python-exec")] = FakeResponse(
        500, None, error_text="500 nope")
    out = _text(await mcp_handlers.handle_tool_call(
        "python_exec", {"code": "x"}, svc))
    assert "ERROR executing Python: 500 nope" in out


# --- http_request ----------------------------------------------------------------------

async def test_http_request_validation(no_sleep):
    out = _text(await mcp_handlers.handle_tool_call(
        "http_request", {"url": "http://x"}, FakeMcpService()))
    assert "No assessment loaded" in out

    svc = FakeMcpService()
    svc.current_assessment_id = 7
    out = _text(await mcp_handlers.handle_tool_call(
        "http_request", {"url": "  "}, svc))
    assert "No URL provided." in out


async def test_http_request_open_mode_payload_building(no_sleep):
    svc = _exec_service()
    svc.http_client.routes[("POST", "/commands/http-request")] = FakeResponse(
        200, {"success": True, "stdout": "HTTP/1.1 200 OK"})

    out = _text(await mcp_handlers.handle_tool_call("http_request", {
        "url": "http://t.local/api", "method": "post",
        "headers": {"X-A": "1"}, "params": {"q": "1"}, "data": "raw",
        "cookies": {"s": "v"}, "auth": ("u", "p"), "proxy": "http://p",
        "json": {"k": "v"}, "timeout": 10, "follow_redirects": False,
        "verify_ssl": False, "phase": "1",
    }, svc))
    assert "200 OK" in out
    sent = [c for c in svc.http_client.calls
            if "http-request" in c[1]][0][2]["json"]
    assert sent == {
        "url": "http://t.local/api", "method": "POST", "phase": "1",
        "headers": {"X-A": "1"}, "params": {"q": "1"}, "data": "raw",
        "cookies": {"s": "v"}, "auth": ("u", "p"), "proxy": "http://p",
        "json_body": {"k": "v"}, "timeout": 10,
        "follow_redirects": False, "verify_ssl": False,
    }


async def test_http_request_method_rules_override_mode(no_sleep):
    # explicit require_approval for POST overrides open mode
    svc = _exec_service(mode="open", http_rules={"POST": "require_approval"})
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "executed", "execution_result": {"stdout": "posted",
                                                         "success": True}})
    out = _text(await mcp_handlers.handle_tool_call("http_request", {
        "url": "http://t.local", "method": "POST"}, svc))
    assert "posted" in out
    create = [c for c in svc.http_client.calls
              if c[0] == "POST" and "pending-commands/create" in c[1]][0]
    assert create[2]["json"]["command_type"] == "http"
    assert create[2]["json"]["matched_keywords"] == ["HTTP POST"]

    # auto_approve for DELETE overrides closed mode
    svc2 = _exec_service(mode="closed", http_rules={"DELETE": "auto_approve"})
    svc2.http_client.routes[("POST", "/commands/http-request")] = FakeResponse(
        200, {"success": True, "stdout": "deleted"})
    out = _text(await mcp_handlers.handle_tool_call("http_request", {
        "url": "http://t.local/1", "method": "DELETE"}, svc2))
    assert "deleted" in out


async def test_http_request_failure_paths(no_sleep):
    svc = _exec_service()
    svc.http_client.routes[("POST", "/commands/http-request")] = FakeResponse(
        200, {"status": "timeout", "execution_time": 30})
    out = _text(await mcp_handlers.handle_tool_call("http_request", {
        "url": "http://slow.local"}, svc))
    assert "Timeout (30s exceeded)" in out

    svc2 = _exec_service()
    svc2.http_client.routes[("POST", "/commands/http-request")] = FakeResponse(
        200, {"success": True, "stdout": ""})
    out = _text(await mcp_handlers.handle_tool_call("http_request", {
        "url": "http://t.local"}, svc2))
    assert "no output" in out.lower()

    svc3 = _exec_service()
    svc3.http_client.routes[("POST", "/commands/http-request")] = FakeResponse(
        200, {"success": False, "returncode": 7, "stdout": "", "stderr": "conn refused"})
    out = _text(await mcp_handlers.handle_tool_call("http_request", {
        "url": "http://refused.local"}, svc3))
    assert "**HTTP error:**" in out and "conn refused" in out


# --- pentest tool wrappers -------------------------------------------------------------

def _scan_service(svc_result=None, available=True):
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.current_container = "exa-test"
    svc.check_tool_availability = _async_value(available)
    if svc_result is not None:
        svc.http_client.routes[("POST", "/commands/")] = FakeResponse(200, svc_result)
    return svc


async def test_scan_requires_container():
    out = _text(await mcp_handlers.handle_tool_call(
        "scan", {"type": "nmap_quick", "target": "x"}, FakeMcpService()))
    assert "No container selected" in out


async def test_scan_builds_expected_commands(no_sleep):
    cases = [
        ({"type": "nmap_quick", "target": "10.0.0.1", "ports": "22,80"},
         "nmap -sV -p 22,80 10.0.0.1"),
        ({"type": "nmap_quick", "target": "10.0.0.1"},
         "nmap -sV -F 10.0.0.1"),
        ({"type": "nmap_full", "target": "10.0.0.1"},
         "nmap -sS -sV -O -T4 -p- 10.0.0.1"),
        ({"type": "nmap_full", "target": "10.0.0.1", "ports": "443"},
         "nmap -sS -sV -O -T4 -p 443 10.0.0.1"),
        ({"type": "nmap_vuln", "target": "10.0.0.1", "ports": "80"},
         "nmap -sV --script=vuln -p 80 10.0.0.1"),
        ({"type": "gobuster", "target": "t.local", "wordlist": "medium",
          "extensions": "php,html", "threads": 20},
         "gobuster dir -u http://t.local -w /usr/share/dirbuster/directory-list-2.3-medium.txt"
         " -t 20 -x php,html"),
        ({"type": "ffuf", "target": "t.local/FUZZ"},
         "ffuf -u http://t.local/FUZZ -w /usr/share/dirb/wordlists/common.txt -t 10"),
        ({"type": "dirb", "target": "t.local", "extensions": "php"},
         "dirb http://t.local /usr/share/dirb/wordlists/common.txt -X .php"),
        ({"type": "nikto", "target": "t.local", "extra_flags": "-ssl"},
         "nikto -h t.local -ssl"),
    ]
    for args, expected_command in cases:
        svc = _scan_service({"success": True, "stdout": "ok"})
        await mcp_handlers.handle_tool_call("scan", args, svc)
        sent = [c for c in svc.http_client.calls
                if c[0] == "POST" and "execute-with-credentials" in c[1]][0]
        assert sent[2]["json"]["command"] == expected_command, args["type"]


async def test_scan_routes_through_approval_not_direct_exec():
    """A scan in closed mode must pass the approval gate (legacy direct-exec
    bypass was the reason scans now route through _handle_execute)."""
    svc = _scan_service()
    svc.http_client.routes[("GET", "/command-settings")] = FakeResponse(200, {
        "execution_mode": "closed", "filter_keywords": [], "timeout_seconds": 5})
    svc.http_client.routes[("POST", "/pending-commands/create")] = FakeResponse(
        200, {"id": 9})
    svc.http_client.routes[("GET", "/pending-commands/9")] = FakeResponse(
        200, {"status": "rejected"})

    out = _text(await mcp_handlers.handle_tool_call(
        "scan", {"type": "nmap_quick", "target": "10.0.0.1"}, svc))
    assert "Command rejected by user" in out
    assert not [c for c in svc.http_client.calls
                if "execute-with-credentials" in c[1]]


async def test_scan_unknown_type_and_missing_tool(no_sleep):
    svc = _scan_service()
    out = _text(await mcp_handlers.handle_tool_call(
        "scan", {"type": "nessus", "target": "x"}, svc))
    assert "Unknown scan type: nessus" in out

    svc2 = _scan_service(available=False)
    out = _text(await mcp_handlers.handle_tool_call(
        "scan", {"type": "nmap_quick", "target": "x"}, svc2))
    assert "Tool `nmap` not available in container." in out


async def test_subdomain_enum_formats_methods():
    svc = FakeMcpService()
    svc.subdomain_enumeration = _async_value({
        "success": True,
        "results": [
            {"command": "subfinder -d x", "success": True, "output": "a.x\nb.x",
             "error": None},
            {"command": "amass enum -d x", "success": False, "output": "",
             "error": "no keys"},
        ],
    })
    out = _text(await mcp_handlers.handle_tool_call(
        "subdomain_enum", {"domain": "x"}, svc))
    assert "Subdomain Enumeration for `x`" in out
    assert "**Method 1:** `subfinder`" in out
    assert "a.x" in out
    assert "Error: no keys" in out

    svc.subdomain_enumeration = _async_value({"success": False, "error": "no dns"})
    out = _text(await mcp_handlers.handle_tool_call(
        "subdomain_enum", {"domain": "x"}, svc))
    assert "Error: no dns" in out


async def test_ssl_analysis_and_tech_detection():
    svc = FakeMcpService()
    svc.ssl_analysis = _async_value({
        "success": True,
        "results": [
            {"command": "openssl x509 -noout -subject", "success": True,
             "output": "CN=acme", "error": None},
            {"command": "openssl s_client -bad", "success": False,
             "output": "", "error": "handshake fail"},
        ],
    })
    out = _text(await mcp_handlers.handle_tool_call(
        "ssl_analysis", {"target": "t:443"}, svc))
    assert "SSL Analysis for `t:443`" in out
    assert "Subject:**" in out and "CN=acme" in out
    assert "Error in openssl s_client -bad: handshake fail" in out

    svc.tech_stack_detection = _async_value({
        "success": True,
        "results": [
            {"command": "whatweb http://x", "success": True,
             "output": "nginx[1.2]", "error": None},
            {"command": "wappalyzer http://x", "success": False,
             "output": "", "error": "not installed"},
        ],
    })
    out = _text(await mcp_handlers.handle_tool_call(
        "tech_detection", {"url": "http://x"}, svc))
    assert "Technology Detection for `http://x`" in out
    assert "**WHATWEB:**" in out
    assert "Error with wappalyzer" in out


# --- credentials handlers ----------------------------------------------------------------

async def test_credentials_require_loaded_assessment():
    for tool in ("credentials_add", "credentials_list"):
        out = _text(await mcp_handlers.handle_tool_call(tool, {}, FakeMcpService()))
        assert "No assessment loaded" in out


async def test_credentials_add_generates_placeholder():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("POST", "/credentials")] = FakeResponse(200, {})

    out = _text(await mcp_handlers.handle_tool_call("credentials_add", {
        "credential_type": "bearer_token", "name": "My API! Token",
        "token": "abc123", "service": "api", "target": "t.local"}, svc))
    assert "Credential added: **My API! Token**" in out
    assert "`{{BEARER_TOKEN_MY_API_TOKEN}}`" in out
    sent = [c for c in svc.http_client.calls if c[0] == "POST"][0][2]["json"]
    assert sent["placeholder"] == "{{BEARER_TOKEN_MY_API_TOKEN}}"
    assert sent["discovered_by"] == "claude"
    assert sent["token"] == "abc123"


async def test_credentials_add_conflict_message():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("POST", "/credentials")] = FakeResponse(
        409, None, error_text="409 placeholder already exists")

    out = _text(await mcp_handlers.handle_tool_call("credentials_add", {
        "credential_type": "api_key", "name": "k", "placeholder": "K"}, svc))
    assert "Placeholder 'K' already exists" in out

    svc.http_client.routes[("POST", "/credentials")] = FakeResponse(
        500, None, error_text="500 boom")
    out = _text(await mcp_handlers.handle_tool_call("credentials_add", {
        "credential_type": "api_key", "name": "k", "placeholder": "K2"}, svc))
    assert "Error adding credential: 500 boom" in out


async def test_credentials_list_formats_and_filters():
    svc = FakeMcpService()
    svc.current_assessment_id = 7
    svc.http_client.routes[("GET", "/credentials")] = FakeResponse(200, {
        "total": 2,
        "by_type": {"bearer_token": 1, "cookie": 1},
        "credentials": [
            {"name": "api", "credential_type": "bearer_token",
             "placeholder": "API", "target": "t", "service": "s",
             "notes": "n" * 100, "created_at": "2026-01-01"},
            {"name": "sess", "credential_type": "cookie", "placeholder": "SESS"},
        ],
    })
    out = _text(await mcp_handlers.handle_tool_call("credentials_list", {}, svc))
    assert "Available Credentials (2)" in out
    assert "- bearer_token: 1" in out
    assert "Placeholder: `API`" in out
    assert "n" * 80 + "..." in out

    # type filter goes into the URL query
    await mcp_handlers.handle_tool_call(
        "credentials_list", {"credential_type": "cookie"}, svc)
    get = [c for c in svc.http_client.calls if c[0] == "GET"][-1]
    assert "credential_type=cookie" in get[1]

    svc.http_client.routes[("GET", "/credentials")] = FakeResponse(200, {
        "total": 0, "credentials": []})
    out = _text(await mcp_handlers.handle_tool_call("credentials_list", {}, svc))
    assert "No credentials found" in out

    svc.http_client.routes[("GET", "/credentials")] = FakeResponse(
        500, None, error_text="500 boom")
    out = _text(await mcp_handlers.handle_tool_call("credentials_list", {}, svc))
    assert "Error listing credentials" in out
