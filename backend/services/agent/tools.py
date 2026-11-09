"""
Agent tool surface (OpenAI function-calling schema) + executor.

The autonomous runtime exposes a SMALL, safe tool set to the model and maps each
call to the platform's existing internal services — no HTTP round-trip through
the app's own API. Every network-touching action passes the scope gate, and
free-form shell honors the existing command-execution mode (open/filter/closed),
so autonomy never bypasses the human-configured brakes.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any, Optional, Callable, Awaitable

from database import AsyncSessionLocal, SessionLocal
from models.card import Card
from models.recon_data import ReconData
from models.artifact import Artifact
from models.pending_command import PendingCommand
from services.container_service import ContainerService
from services.agent.scope import Scope
from services.agent.agent_settings import get_setting, int_setting
from api.pending_commands import get_command_settings
from utils.exploit_classify import classify_exploit_risk
from utils.logger import get_logger

logger = get_logger(__name__)


# OpenAI-compatible tool schemas presented to the model.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command in the isolated pentest container against "
                "an IN-SCOPE target. Use standard tools (nmap, curl, ffuf, "
                "nuclei, httpx, sqlmap, etc.). Only targets inside the authorized "
                "scope are permitted; out-of-scope hosts are rejected."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The exact shell command."},
                    "purpose": {"type": "string", "description": "Why you are running it (one line)."},
                },
                "required": ["command", "purpose"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "status_update",
            "description": (
                "Post a SHORT human-readable progress update after a key milestone "
                "(finished a scan, identified services, confirmed/ruled out a vector, "
                "got a shell). One or two sentences, plain language — this is what the "
                "user watches. Do NOT call it for every command; only real milestones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "e.g. 'Port scan done: 21/ftp, 80/http, 111/rpc open. FTP allows anonymous login.'"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_output",
            "description": (
                "Search the FULL stored output of previously-run commands (which may have been "
                "truncated in the tool result) for a pattern — like grep. Use when a scan's "
                "output was long and you need specific lines (open ports, a version, a path)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Substring or regex to search for."},
                    "command_id": {"type": "integer", "description": "Optional: restrict to one command's output; omit to search recent commands."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_credential",
            "description": (
                "Store a credential you discovered (found in output, cracked, default login) so "
                "later commands can reuse it via its {{PLACEHOLDER}}. Enables attack chains "
                "(e.g. FTP creds → reuse on SMB/SSH)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "credential_type": {"type": "string", "enum": ["bearer_token", "cookie", "basic_auth", "api_key", "ssh", "custom"]},
                    "name": {"type": "string", "description": "Descriptive name, e.g. 'FTP anonymous' or 'websvc SSH'."},
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                    "token": {"type": "string"},
                    "service": {"type": "string", "description": "e.g. 'FTP', 'SSH', 'HTTP'."},
                    "target": {"type": "string", "description": "Host/URL it works on."},
                },
                "required": ["credential_type", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_subdomain_takeover",
            "description": (
                "Enumerate a domain's subdomains and check each for SUBDOMAIN TAKEOVER "
                "using the can-i-take-over-xyz fingerprint set (S3, Azure, Heroku, GitHub "
                "Pages, Shopify, Ghost, etc.). Returns per-subdomain verdicts "
                "(VULNERABLE/EDGE_CASE/NOT_VULNERABLE) and records findings. In-scope only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Apex/root domain to scan, e.g. example.com."},
                    "subdomains": {"type": "array", "items": {"type": "string"},
                                   "description": "Optional: pre-discovered subdomains to check instead of enumerating."},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_recon",
            "description": "Save a reconnaissance finding (endpoint, service, subdomain, technology, vulnerability).",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_type": {"type": "string", "enum": ["endpoint", "service", "subdomain", "technology", "vulnerability"]},
                    "name": {"type": "string"},
                    "details": {"type": "object", "description": "Free-form structured details."},
                },
                "required": ["data_type", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_finding",
            "description": "Record a confirmed or potential security finding as a report card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]},
                    "technical_analysis": {"type": "string", "description": "What it is and why it matters."},
                    "proof": {"type": "string", "description": "PoC: exact command(s) + observed evidence."},
                    "target_service": {"type": "string"},
                },
                "required": ["title", "severity", "technical_analysis"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_report",
            "description": (
                "Fetch and read the FULL text of a public disclosed bug-bounty report / "
                "writeup by URL (e.g. one returned by search_knowledge). Use to study exactly "
                "how a technique was exploited before replicating it. HackerOne reports are read "
                "via their JSON; blog/writeup pages are fetched and stripped to text."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The report/writeup URL."}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screenshot",
            "description": (
                "Capture a headless-browser screenshot of an IN-SCOPE URL and save "
                "it as evidence attached to the report. Use to document a finding "
                "(e.g. an XSS firing, an exposed page)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The in-scope URL to screenshot."},
                    "caption": {"type": "string", "description": "Short evidence caption."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_poc",
            "description": (
                "Record a short SCREEN-CAPTURE VIDEO (WebM) of a headless browser "
                "reproducing a finding against an IN-SCOPE URL, and save it as "
                "evidence on the report. Give the starting url and an ordered list "
                "of browser actions to perform (navigate, click, fill a field, "
                "press a key, wait). Use this to produce a reproducible visual PoC "
                "(e.g. an IDOR, an auth bypass, a stored-XSS trigger). Keep it short "
                "(a handful of steps)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The in-scope URL to open first."},
                    "caption": {"type": "string", "description": "Short evidence caption describing what the video proves."},
                    "actions": {
                        "type": "array",
                        "description": "Ordered browser steps. Each item is one of: "
                                       "{\"action\":\"goto\",\"url\":\"<in-scope url>\"}, "
                                       "{\"action\":\"click\",\"selector\":\"<css>\"}, "
                                       "{\"action\":\"fill\",\"selector\":\"<css>\",\"value\":\"<text>\"}, "
                                       "{\"action\":\"press\",\"key\":\"Enter\",\"selector\":\"<css optional>\"}, "
                                       "{\"action\":\"wait\",\"ms\":1000}, "
                                       "{\"action\":\"wait_for\",\"selector\":\"<css>\"}.",
                        "items": {"type": "object"},
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Search the offensive-security knowledge base — a curated SKILL library "
                "(pentest methodology, web/CVE exploitation, Active Directory, privesc, "
                "post-exploitation, cloud, API, OSINT, reporting, safe-testing doctrine, …) "
                "plus ingested CVEs. Use it FIRST to find the right skill(s) for the target "
                "tech or vulnerability class, then read_skill() the most relevant one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords, tech/product name, CWE/CVE id, or attack class."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": (
                "Read the FULL text of a skill (its SKILL.md methodology) or one of its "
                "reference files, by slug. Use after search_knowledge to load the detailed "
                "playbook for the current phase/target (e.g. slug 'web-cve-exploitation', "
                "'active-directory-attack-paths', 'privilege-escalation', 'security-reporting'). "
                "Always consult 'safe-testing-doctrine' before active testing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "Skill slug, e.g. 'web-cve-exploitation'."},
                    "reference": {"type": "string", "description": "Optional reference filename within the skill (e.g. 'java-rce.md'). Omit for the main SKILL.md."},
                },
                "required": ["skill"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "Conclude the task with a concise summary of what was tested and "
                "found. Call it ONLY when the phase objective is genuinely achieved "
                "and verified, or every safe in-scope avenue has been exhausted — a "
                "premature finish() is rejected by the platform's goal review and "
                "you will be told to continue working."),
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


class ToolExecutor:
    """Executes model tool calls against internal services, with safety gates."""

    def __init__(
        self,
        db,                       # sync Session
        assessment_id: int,
        scope: Scope,
        *,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        task_id: Optional[int] = None,
    ):
        self.db = db
        self.assessment_id = assessment_id
        self.scope = scope
        self.container = ContainerService()
        self.on_event = on_event
        self.task_id = task_id
        self.findings: list[int] = []
        self.blocked_actions: int = 0
        # Commands that actually RAN in the container (vs. refused by the
        # scope/mode/approval gates). The runtime uses blocked>0 ∧ ran==0 to
        # conclude "infrastructure-blocked" instead of a hollow "done".
        self.executed_actions: int = 0

    async def _emit(self, kind: str, data: dict) -> None:
        if self.on_event:
            try:
                await self.on_event(kind, data)
            except Exception:  # never let telemetry break the run
                pass

    async def execute(self, name: str, args: dict) -> dict:
        handler = {
            "run_shell": self._run_shell,
            "record_recon": self._record_recon,
            "record_finding": self._record_finding,
            "search_knowledge": self._search_knowledge,
            "capture_screenshot": self._capture_screenshot,
            "record_poc": self._record_poc,
            "status_update": self._status_update,
            "read_skill": self._read_skill,
            "grep_output": self._grep_output,
            "store_credential": self._store_credential,
            "check_subdomain_takeover": self._check_subdomain_takeover,
            "read_report": self._read_report,
        }.get(name)
        if not handler:
            return {"ok": False, "error": f"unknown tool '{name}'"}
        try:
            return await handler(args)
        except Exception as e:
            logger.warning("tool execution failed", tool=name, error=str(e))
            return {"ok": False, "error": str(e)}

    # --- tools -------------------------------------------------------------

    async def _request_exploit_approval(self, command: str, reason: str) -> dict:
        """E4 PoC approval chain: park the agent on a high-risk PendingCommand
        and poll for the human decision. An approved command is EXECUTED by the
        approve endpoint (same as UI-issued approvals), so its result and audit
        trail are identical to a manual run."""
        timeout = int_setting("exploit_approval_timeout", 600)
        row = PendingCommand(
            assessment_id=self.assessment_id,
            command=command,
            phase="autonomous",
            command_type="shell",
            matched_keywords=[f"exploit:{reason}"],
            status="pending",
            timeout_seconds=timeout,
            risk_level="high",
            risk_reason=reason,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        try:
            from websocket.manager import manager
            await manager.broadcast({
                "type": "command_pending_approval",
                "data": {
                    "id": row.id,
                    "assessment_id": self.assessment_id,
                    "command": command,
                    "matched_keywords": row.matched_keywords,
                    "risk_level": "high",
                    "risk_reason": reason,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "timeout_seconds": timeout,
                },
            })
        except Exception:  # broadcast is best-effort
            pass
        await self._emit("approval_requested", {
            "command": command, "reason": reason, "timeout": timeout})

        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            db = SessionLocal()
            try:
                cur = db.query(PendingCommand).filter(
                    PendingCommand.id == row.id).first()
                if cur is not None and cur.status != "pending":
                    if cur.status == "executed":
                        er = cur.execution_result or {}
                        await self._emit("approval_resolved", {
                            "command": command, "decision": "approved"})
                        return {
                            "ok": bool(er.get("success")),
                            "approved": True,
                            "returncode": er.get("returncode"),
                            "stdout": (er.get("stdout") or "")[:6000],
                            "stderr": (er.get("stderr") or "")[:2000],
                        }
                    self.blocked_actions += 1
                    await self._emit("approval_resolved", {
                        "command": command, "decision": cur.status})
                    return {
                        "ok": False,
                        "blocked": f"approval_{cur.status}",
                        "error": f"Human {cur.status} this exploit-class command"
                                 f" ({reason})."
                                 + (f" Reason: {cur.rejection_reason}"
                                    if cur.rejection_reason else ""),
                    }
            finally:
                db.close()
        self.blocked_actions += 1
        return {"ok": False, "blocked": "approval_timeout",
                "error": f"No human approved the exploit-class command ({reason}) "
                         f"within {timeout}s; it was not executed."}

    async def _run_shell(self, args: dict) -> dict:
        command = (args.get("command") or "").strip()
        if not command:
            return {"ok": False, "error": "empty command"}

        # 1) Scope gate (hard).
        if self.scope.is_empty:
            self.blocked_actions += 1
            hint = (f" authorized_scope was '{self.scope.raw[:120]}' but none of it "
                    "parsed into domains/IPs/CIDRs — use forms like "
                    "*.example.com, 10.0.0.0/24 or a TLD grant (.kz)."
                    if (self.scope.raw or "").strip() else "")
            return {"ok": False, "blocked": "no_scope",
                    "error": "No authorized scope on this task; refusing to run." + hint}
        allowed, offending = self.scope.check_command(command)
        if not allowed:
            self.blocked_actions += 1
            await self._emit("blocked", {"command": command, "out_of_scope": offending})
            return {"ok": False, "blocked": "out_of_scope",
                    "error": f"Out-of-scope target(s): {', '.join(offending)}. Refused."}

        # 2) Command-mode gate (honor the human-configured brakes).
        settings = get_command_settings(self.db)
        mode = settings.get("execution_mode", "filter")
        if mode == "closed":
            self.blocked_actions += 1
            return {"ok": False, "blocked": "mode_closed",
                    "error": "Command mode is 'closed'; a human must run this from the UI."}
        if mode == "filter":
            import re as _re
            kws = [k.lower() for k in settings.get("filter_keywords", [])]
            # Word-boundary match: a bare substring test would make the
            # keyword "rm" fire on "perform" and "dd" on "hidden".
            if any(_re.search(rf"\b{_re.escape(k)}\b", command.lower())
                   for k in kws):
                self.blocked_actions += 1
                return {"ok": False, "blocked": "filter_match",
                        "error": "Command matches a filter keyword requiring human approval; skipped in autonomous mode."}

        # 2b) E4 PoC approval chain: exploit-class commands (sqlmap, hydra,
        # impacket, metasploit, reverse shells, …) need a HUMAN even in open
        # mode. The agent parks until the approval is decided (an admin signs
        # off when exploit_admin_approval is on) or the approval times out.
        risk, reason = classify_exploit_risk(command)
        if risk == "high" and get_setting("exploit_approval", "on").lower() in (
                "on", "true", "1", "yes"):
            return await self._request_exploit_approval(command, reason)

        # 3) Substitute stored credentials ({{PLACEHOLDER}} → secret) and pick an
        #    adaptive timeout (long scans need more than the default).
        run_command, used_creds = self._substitute_credentials(command)
        timeout = self._adaptive_timeout(command)

        await self._emit("run_shell", {"command": command, "purpose": args.get("purpose")})
        async with AsyncSessionLocal() as adb:
            log = await self.container.execute_and_log_command(
                assessment_id=self.assessment_id,
                command=run_command,
                phase="autonomous",
                db=adb,
                timeout=timeout,
                # Persist/broadcast the placeholder form, never the real secret.
                display_command=command if used_creds else None,
            )
        self.executed_actions += 1
        full_out = log.stdout or ""
        stdout = full_out[:6000]
        stderr = (log.stderr or "")[:2000]
        truncated = len(full_out) > 6000
        result = {"ok": bool(log.success), "returncode": log.returncode,
                  "stdout": stdout, "stderr": stderr, "command_id": log.id}
        if truncated:
            result["note"] = (f"stdout truncated to 6000 of {len(full_out)} chars — "
                              f"use grep_output(pattern) to search the full output.")
        if used_creds:
            result["note_creds"] = f"substituted credentials: {', '.join(used_creds)}"
        await self._emit("shell_result", {"command": command, "returncode": log.returncode,
                                           "success": bool(log.success)})
        return result

    # --- run_shell helpers -------------------------------------------------
    _SCAN_TOOLS = {"nmap", "masscan", "ffuf", "gobuster", "feroxbuster", "nuclei",
                   "nikto", "sqlmap", "wpscan", "dirb", "hydra", "subfinder", "amass",
                   "medusa", "wfuzz", "dirsearch"}
    _SCAN_FLAGS = ("-p-", "--top-ports")

    def _adaptive_timeout(self, command: str) -> int:
        """Long scans get a bigger timeout. Only the COMMAND WORD (argv0) of each
        pipeline/chain segment is matched — so a URL, path, or flag *value* that
        happens to contain a tool name (e.g. `curl http://x/nmap`) can't
        false-trigger the long timeout."""
        import re as _re
        # Split into segments on pipes / chaining / redirection / subshells.
        segments = _re.split(r"(?:\|\||\||&&|&|;|\bthen\b|\bdo\b|\$\(|`|\()", command)
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            # First bare word of the segment = the program being invoked. Skip
            # a leading `sudo`/`time`/env-assignment prefix to reach the real
            # one. `timeout` is itself followed by a DURATION (`timeout 600 …`,
            # `timeout 30s …`) — swallow that too, else the number is mistaken
            # for argv0 and the wrapped scan tool never gets its long timeout.
            after_timeout = False
            for tok in seg.split():
                if "=" in tok and not tok.startswith("-"):
                    continue  # VAR=val env prefix
                if tok in ("sudo", "time", "nice", "nohup", "env", "stdbuf"):
                    continue
                if tok == "timeout":
                    after_timeout = True
                    continue
                if after_timeout:
                    after_timeout = False
                    if tok[:1].isdigit():
                        continue  # the duration argument, not the program
                argv0 = tok.rsplit("/", 1)[-1].lower()
                if argv0 in self._SCAN_TOOLS:
                    return 900
                break  # only inspect argv0 of this segment
        if any(f in command.split() for f in self._SCAN_FLAGS):
            return 900
        return 300

    def _substitute_credentials(self, command: str):
        """Replace {{PLACEHOLDER}} tokens with stored credential secrets."""
        if "{{" not in command:
            return command, []
        from models.credential import Credential
        creds = self.db.query(Credential).filter(
            Credential.assessment_id == self.assessment_id).all()
        used = []
        out = command
        for c in creds:
            ph = c.placeholder
            if not ph or ph not in out:
                continue
            # Pick the right secret form for the credential type.
            if c.credential_type == "basic_auth" and c.username and c.password:
                secret = f"{c.username}:{c.password}"
            else:
                secret = c.token or c.password or c.cookie_value or c.username or ""
            if secret:
                out = out.replace(ph, secret)
                used.append(ph)
        return out, used

    async def _grep_output(self, args: dict) -> dict:
        import re as _re
        from models.command_history import CommandHistory
        pattern = args.get("pattern") or ""
        if not pattern:
            return {"ok": False, "error": "empty pattern"}
        try:
            rx = _re.compile(pattern, _re.I)
        except _re.error:
            rx = None  # fall back to substring

        q = self.db.query(CommandHistory).filter(
            CommandHistory.assessment_id == self.assessment_id)
        cmd_id = args.get("command_id")
        if cmd_id:
            q = q.filter(CommandHistory.id == cmd_id)
        rows = q.order_by(CommandHistory.id.desc()).limit(30).all()

        matches = []
        for r in rows:
            for stream in ((r.stdout or ""), (r.stderr or "")):
                for line in stream.splitlines():
                    hit = rx.search(line) if rx else (pattern.lower() in line.lower())
                    if hit:
                        matches.append({"command_id": r.id, "line": line[:300]})
                        if len(matches) >= 100:
                            break
                if len(matches) >= 100:
                    break
            if len(matches) >= 100:
                break
        return {"ok": True, "count": len(matches), "matches": matches}

    async def _check_subdomain_takeover(self, args: dict) -> dict:
        domain = (args.get("domain") or "").strip()
        if not domain:
            return {"ok": False, "error": "domain required"}
        # Scope gate on the domain.
        if self.scope.is_empty or not self.scope.host_in_scope(domain):
            self.blocked_actions += 1
            return {"ok": False, "blocked": "out_of_scope",
                    "error": f"'{domain}' is out of scope. Refused."}
        await self._emit("milestone", {"text": f"Subdomain-takeover scan on {domain}…"})
        from services.takeover_service import TakeoverService
        result = await TakeoverService().scan(domain, subdomains=args.get("subdomains"))

        # Record findings (recon + cards) into the assessment.
        for r in result["results"]:
            self.db.add(ReconData(
                assessment_id=self.assessment_id, data_type="subdomain",
                name=r["subdomain"], discovered_in_phase="autonomous",
                details={"takeover_verdict": r["verdict"], "service": r["service"]}))
            if r["verdict"] in ("VULNERABLE", "EDGE_CASE"):
                card = Card(
                    assessment_id=self.assessment_id, card_type="finding",
                    title=f"Subdomain takeover ({r['service']}): {r['subdomain']}",
                    severity="HIGH" if r["verdict"] == "VULNERABLE" else "MEDIUM",
                    status="potential" if r["verdict"] == "VULNERABLE" else "untested",
                    target_service=r["service"],
                    technical_analysis=(f"`{r['subdomain']}` → **{r['service']}** "
                                        f"(CNAME `{r.get('cname_target')}`), appears unclaimed. "
                                        f"Verdict {r['verdict']} ({r['confidence']}). {r['evidence']}."),
                    proof=(f"DNS {r['dns_status']}; CNAME chain: {', '.join(r['cname_chain']) or '-'}\n"
                           f"Fingerprint: {r['fingerprint']}\nRef: {r.get('documentation') or 'can-i-take-over-xyz'}"))
                self.db.add(card)
        self.db.commit()
        s = result["summary"]
        await self._emit("milestone", {"text":
            f"Takeover scan: {s['vulnerable']} vulnerable, {s['edge_case']} edge, "
            f"{result['subdomains_checked']} subdomains checked."})
        # Return a compact view (cap results in the tool result).
        return {"ok": True, "domain": result["domain"], "wildcard": result["wildcard"],
                "subdomains_checked": result["subdomains_checked"], "summary": s,
                "results": [{k: r[k] for k in ("subdomain", "verdict", "service", "confidence")}
                            for r in result["results"][:40]]}

    async def _store_credential(self, args: dict) -> dict:
        from models.credential import Credential
        import re as _re
        name = args.get("name", "credential")
        base = _re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:24] or "CRED"
        placeholder = "{{" + base + "}}"
        # Ensure placeholder uniqueness.
        n = 1
        while self.db.query(Credential).filter(
                Credential.assessment_id == self.assessment_id,
                Credential.placeholder == placeholder).first():
            placeholder = "{{" + base + f"_{n}" + "}}"
            n += 1
        row = Credential(
            assessment_id=self.assessment_id,
            credential_type=args.get("credential_type", "custom"),
            name=name, placeholder=placeholder,
            username=args.get("username"), password=args.get("password"),
            token=args.get("token"), service=args.get("service"),
            target=args.get("target"), discovered_by="claude",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        await self._emit("milestone", {"text": f"Stored credential '{name}' ({placeholder})"})
        return {"ok": True, "credential_id": row.id, "placeholder": placeholder,
                "hint": f"Reuse in commands as {placeholder}."}

    async def _record_recon(self, args: dict) -> dict:
        row = ReconData(
            assessment_id=self.assessment_id,
            data_type=args.get("data_type", "endpoint"),
            name=args.get("name", ""),
            details=args.get("details") or {},
            discovered_in_phase="autonomous",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        await self._emit("recon", {"id": row.id, "name": row.name, "data_type": row.data_type})
        return {"ok": True, "recon_id": row.id}

    async def _capture_screenshot(self, args: dict) -> dict:
        url = (args.get("url") or "").strip()
        if not url:
            return {"ok": False, "error": "url required"}
        # Scope gate on the URL host.
        host = url.split("://", 1)[-1].split("/", 1)[0]
        if self.scope.is_empty or not self.scope.host_in_scope(host):
            self.blocked_actions += 1
            return {"ok": False, "blocked": "out_of_scope",
                    "error": f"URL host '{host}' is out of scope. Refused."}

        safe_url = url.replace('"', "").replace("'", "").replace("`", "").replace("$", "")
        capture = (
            'BROWSER=$(command -v chromium || command -v chromium-browser); '
            'if [ -z "$BROWSER" ]; then echo __NO_BROWSER__; else '
            '"$BROWSER" --headless=new --no-sandbox --disable-gpu --hide-scrollbars '
            '--screenshot=/tmp/_aida_shot.png --window-size=1280,900 '
            f'"{safe_url}" >/dev/null 2>&1; '
            'base64 -w0 /tmp/_aida_shot.png 2>/dev/null || echo __CAPTURE_FAILED__; fi'
        )
        async with AsyncSessionLocal() as adb:
            log = await self.container.execute_and_log_command(
                assessment_id=self.assessment_id, command=capture,
                phase="autonomous", db=adb,
            )
        out = (log.stdout or "").strip()
        if "__NO_BROWSER__" in out:
            return {"ok": False, "error": "No headless browser in the container "
                    "(rebuild the pentest image with chromium to enable screenshots)."}
        if "__CAPTURE_FAILED__" in out or not out:
            return {"ok": False, "error": "Screenshot capture failed."}
        try:
            data = base64.b64decode(out)
        except Exception:
            return {"ok": False, "error": "Could not decode screenshot."}

        row = Artifact(
            assessment_id=self.assessment_id,
            card_id=self.findings[-1] if self.findings else None,
            kind="screenshot",
            filename="screenshot.png",
            content_type="image/png",
            caption=args.get("caption") or f"Screenshot of {url}",
            size_bytes=len(data),
            data=data,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        from services.evidence_store import mirror_artifact
        mirror_artifact(self.db, row)  # also write to disk (~/AIDA-dev/evidence)
        await self._emit("screenshot", {"artifact_id": row.id, "url": url})
        return {"ok": True, "artifact_id": row.id, "bytes": len(data)}

    _POC_MAX_ACTIONS = 20
    _POC_MAX_VIDEO_BYTES = 12_000_000

    @staticmethod
    def _host_of(url: str) -> str:
        return url.split("://", 1)[-1].split("/", 1)[0]

    async def _record_poc(self, args: dict) -> dict:
        """Record a short headless-browser WebM video reproducing a finding, and
        store it as an evidence artifact. All navigation targets are scope-gated."""
        url = (args.get("url") or "").strip()
        if not url.startswith("http"):
            return {"ok": False, "error": "valid http(s) url required"}
        if self.scope.is_empty or not self.scope.host_in_scope(self._host_of(url)):
            self.blocked_actions += 1
            return {"ok": False, "blocked": "out_of_scope",
                    "error": f"URL host '{self._host_of(url)}' is out of scope. Refused."}

        raw_actions = args.get("actions") or []
        if not isinstance(raw_actions, list):
            return {"ok": False, "error": "actions must be a list"}
        actions = []
        for a in raw_actions[:self._POC_MAX_ACTIONS]:
            if not isinstance(a, dict):
                continue
            act = (a.get("action") or "").lower()
            if act == "goto":
                g = (a.get("url") or "").strip()
                if not g.startswith("http"):
                    return {"ok": False, "error": f"goto url invalid: {g}"}
                if not self.scope.host_in_scope(self._host_of(g)):
                    self.blocked_actions += 1
                    return {"ok": False, "blocked": "out_of_scope",
                            "error": f"goto host '{self._host_of(g)}' is out of scope. Refused."}
                actions.append({"action": "goto", "url": g})
            elif act == "click":
                actions.append({"action": "click", "selector": a.get("selector", "")})
            elif act == "fill":
                actions.append({"action": "fill", "selector": a.get("selector", ""),
                                "value": str(a.get("value", ""))})
            elif act == "press":
                actions.append({"action": "press", "selector": a.get("selector"),
                                "key": a.get("key", "Enter")})
            elif act == "wait":
                try:
                    ms = int(a.get("ms", 1000))
                except (TypeError, ValueError):
                    ms = 1000
                actions.append({"action": "wait", "ms": ms})
            elif act == "wait_for":
                actions.append({"action": "wait_for", "selector": a.get("selector", "")})

        vp = {"width": 1280, "height": 800}
        cfg = {"url": url, "actions": actions, "viewport": vp}
        cfg_b64 = base64.b64encode(json.dumps(cfg).encode()).decode()
        script = self._POC_SCRIPT.replace("__CFG_B64__", cfg_b64)

        await self._emit("record_poc", {"url": url, "steps": len(actions)})
        # Ensure the active pentest container is selected, then run Playwright there.
        async with AsyncSessionLocal() as adb:
            try:
                await self.container._resolve_active_container(adb)
            except Exception:
                pass
        res = await self.container.execute_python_stdin(script, timeout=150.0)
        out = res.get("stdout") or ""

        err = ""
        if "__POC_ERR__" in out:
            err = out.split("__POC_ERR__", 1)[1].split("__POC_", 1)[0].strip()
        card_for_poc = self.findings[-1] if self.findings else None
        if "__POC_B64__" not in out:
            detail = err or (res.get("stderr") or "")[:400] or "no video produced"
            if "No module named 'playwright'" in detail or "Executable doesn't exist" in detail:
                detail = ("Playwright/Chromium unavailable in the pentest container. "
                          "Rebuild the image with `playwright install chromium`.")
            # The video failed, but a final-frame screenshot may still have been
            # captured — keep it as evidence rather than discarding it.
            shot_id = await self._persist_poc_screenshot(out, card_for_poc, url, args.get("caption"))
            fail = {"ok": False, "error": f"PoC recording failed: {detail}"}
            if shot_id:
                fail["screenshot_artifact_id"] = shot_id
                fail["note"] = "video failed, but a screenshot was saved as evidence."
            return fail
        b64 = out.split("__POC_B64__", 1)[1].strip().split()[0]
        try:
            data = base64.b64decode(b64)
        except Exception:
            return {"ok": False, "error": "could not decode PoC video"}
        if not data:
            return {"ok": False, "error": "empty PoC video"}
        if len(data) > self._POC_MAX_VIDEO_BYTES:
            return {"ok": False, "error": f"PoC video too large ({len(data)} bytes); "
                    "shorten the steps."}

        row = Artifact(
            assessment_id=self.assessment_id,
            card_id=self.findings[-1] if self.findings else None,
            kind="video",
            filename="poc.webm",
            content_type="video/webm",
            caption=args.get("caption") or f"PoC video of {url}",
            size_bytes=len(data),
            data=data,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        from services.evidence_store import mirror_artifact
        mirror_artifact(self.db, row)  # also write to disk (~/AIDA-dev/evidence)
        await self._emit("poc_video", {"artifact_id": row.id, "url": url, "bytes": len(data)})
        result = {"ok": True, "artifact_id": row.id, "bytes": len(data), "steps": len(actions)}

        # Also persist the final-frame screenshot (a still that CAN embed into a
        # PDF report, unlike the video). Best-effort — never fail the PoC on this.
        shot_id = await self._persist_poc_screenshot(out, row.card_id, url, args.get("caption"))
        if shot_id:
            result["screenshot_artifact_id"] = shot_id
        if err:
            result["note"] = f"completed with a non-fatal warning: {err[:200]}"
        return result

    async def _persist_poc_screenshot(self, out: str, card_id, url: str, caption):
        """Decode the recorder's final-frame screenshot marker and save it as a
        screenshot artifact (embeddable in a PDF, unlike the video). Best-effort:
        returns the artifact id or None; never raises."""
        try:
            if "__POC_SHOT_B64__" not in out:
                return None
            tail = out.split("__POC_SHOT_B64__", 1)[1].strip().split()
            shot_b64 = tail[0] if tail else ""
            if not shot_b64:
                return None
            shot = base64.b64decode(shot_b64)
            if not shot:
                return None
            srow = Artifact(
                assessment_id=self.assessment_id, card_id=card_id,
                kind="screenshot", filename="poc-frame.png", content_type="image/png",
                caption=(caption or f"PoC of {url}") + " (final frame)",
                size_bytes=len(shot), data=shot)
            self.db.add(srow)
            self.db.commit()
            self.db.refresh(srow)
            from services.evidence_store import mirror_artifact
            mirror_artifact(self.db, srow)
            return srow.id
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    # Playwright recorder run inside the pentest container (config injected as b64).
    _POC_SCRIPT = r'''
import os, glob, base64, json, traceback
_CFG = json.loads(base64.b64decode("__CFG_B64__").decode())
url, actions, vp = _CFG["url"], _CFG["actions"], _CFG["viewport"]
os.makedirs("/tmp/aida_poc", exist_ok=True)
for _f in glob.glob("/tmp/aida_poc/*.webm"):
    try: os.remove(_f)
    except Exception: pass
err = ""
_shot_b64 = ""
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        launch_args = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        try:
            browser = p.chromium.launch(headless=True, args=launch_args)
        except Exception:
            browser = p.chromium.launch(headless=True, executable_path="/usr/local/bin/chromium", args=launch_args)
        ctx = browser.new_context(record_video_dir="/tmp/aida_poc", record_video_size=vp,
                                  viewport=vp, ignore_https_errors=True)
        ctx.set_default_timeout(15000)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())   # auto-accept alert()-style XSS PoCs
        page.goto(url, wait_until="load")
        page.wait_for_timeout(700)
        for a in actions:
            act = a.get("action")
            try:
                if act == "goto":
                    page.goto(a["url"], wait_until="load")
                elif act == "click":
                    page.click(a["selector"])
                elif act == "fill":
                    page.fill(a["selector"], a.get("value", ""))
                elif act == "press":
                    if a.get("selector"):
                        page.press(a["selector"], a.get("key", "Enter"))
                    else:
                        page.keyboard.press(a.get("key", "Enter"))
                elif act == "wait":
                    page.wait_for_timeout(min(int(a.get("ms", 1000)), 10000))
                elif act == "wait_for":
                    page.wait_for_selector(a["selector"])
            except Exception as _e:
                err += f"step {act} failed: {_e}; "
            page.wait_for_timeout(400)
        page.wait_for_timeout(800)
        # Final-frame screenshot — embeddable still evidence for PDF reports.
        try:
            _shot_b64 = base64.b64encode(page.screenshot(full_page=False)).decode()
        except Exception:
            _shot_b64 = ""
        ctx.close(); browser.close()
except Exception:
    err += traceback.format_exc()
print("__POC_ERR__", err[:1500])
_files = glob.glob("/tmp/aida_poc/*.webm")
if _files:
    _data = open(_files[0], "rb").read()
    print("__POC_B64__" + base64.b64encode(_data).decode())
else:
    print("__POC_NOFILE__")
print("__POC_SHOT_B64__" + _shot_b64)
'''

    async def _status_update(self, args: dict) -> dict:
        summary = (args.get("summary") or "").strip()
        if summary:
            await self._emit("milestone", {"text": summary})
        return {"ok": True}

    _READ_REPORT_MAX_BYTES = 2_000_000

    @staticmethod
    def _url_is_public(url: str):
        """Validate scheme http(s) and that the host does NOT resolve to a
        private/internal IP (SSRF guard). Returns (ok, host_or_error)."""
        import socket
        import ipaddress
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False, "only http/https URLs allowed"
        host = p.hostname
        try:
            infos = socket.getaddrinfo(host, None)
        except Exception:
            return False, f"cannot resolve {host}"
        for info in infos:
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_reserved or addr.is_multicast or addr.is_unspecified
                    or str(addr) == "169.254.169.254"):
                return False, f"{host} resolves to a non-public address ({ip})"
        return True, host

    async def _read_report(self, args: dict) -> dict:
        import re as _re
        import httpx
        url = (args.get("url") or "").strip()
        ok, info = self._url_is_public(url)
        if not ok:
            return {"ok": False, "error": info}

        m = _re.match(r"https?://hackerone\.com/reports/(\d+)", url)
        cap = self._READ_REPORT_MAX_BYTES
        try:
            # Do NOT auto-follow redirects (a redirect could target an internal
            # host, bypassing the pre-resolve SSRF check).
            async with httpx.AsyncClient(timeout=25, follow_redirects=False,
                                         headers={"User-Agent": "Mozilla/5.0 AIDA"}) as client:
                if m:
                    r = await client.get(f"https://hackerone.com/reports/{m.group(1)}.json")
                    if r.status_code == 200:
                        try:
                            d = r.json()
                        except ValueError:
                            d = {}
                        if d:
                            text = (f"Title: {d.get('title','')}\n"
                                    f"Weakness: {(d.get('weakness') or {}).get('name','')}\n"
                                    f"Bounty: {d.get('bounty_amount') or ''} {d.get('currency') or ''}\n\n"
                                    f"{d.get('vulnerability_information') or ''}")
                            return {"ok": True, "url": url, "source": "hackerone",
                                    "content": text[:14000]}
                # Bounded streaming read so a huge page can't blow memory/stall.
                async with client.stream("GET", url) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        return {"ok": False, "error": f"redirect ({resp.status_code}) not followed"}
                    if resp.status_code >= 400:
                        return {"ok": False, "error": f"HTTP {resp.status_code}"}
                    clen = resp.headers.get("content-length")
                    if clen and clen.isdigit() and int(clen) > cap:
                        return {"ok": False, "error": "response too large"}
                    chunks, total = [], 0
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total > cap:
                            break
                    raw = b"".join(chunks)[:cap]
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"fetch failed: {e}"}
        html_text = raw.decode("utf-8", "ignore")
        html_text = _re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html_text)
        text = _re.sub(r"(?s)<[^>]+>", " ", html_text)
        text = _re.sub(r"&[a-z#0-9]+;", " ", text)
        text = _re.sub(r"[ \t]+", " ", _re.sub(r"\n\s*\n\s*", "\n\n", text)).strip()
        return {"ok": True, "url": url, "source": "web", "content": text[:14000]}

    async def _search_knowledge(self, args: dict) -> dict:
        from services.knowledge_service import KnowledgeService
        query = (args.get("query") or "").strip()
        rows = KnowledgeService(self.db).search(query=query, limit=8)
        results = [{
            "source": r.source, "slug": r.ext_id, "title": r.title,
            "severity": r.severity, "cwe": r.cwe,
            "summary": (r.description or r.content or "")[:300],
            "references": (r.references or []) if r.source in ("skill", "bugbounty") else None,
        } for r in rows]
        return {"ok": True, "count": len(results), "results": results,
                "hint": "Use read_skill(slug) to load the full methodology."}

    async def _read_skill(self, args: dict) -> dict:
        from services.skills_loader import read_skill_file
        slug = (args.get("skill") or "").strip()
        reference = (args.get("reference") or "").strip() or None
        text = read_skill_file(slug, reference)
        if not text and not reference:
            # search_knowledge returns ext_id slugs for ALL sources; playbooks
            # and KB entries exist only in the DB, not under /skills. Resolve
            # the slug there so a searched slug is always readable.
            from models.knowledge_entry import KnowledgeEntry
            row = (self.db.query(KnowledgeEntry)
                   .filter(KnowledgeEntry.ext_id == slug).first())
            if row is None:
                # Fuzzy: the model often drops/alters separators ("web-recon"
                # → "web_recon", "recon_web"). Compare on a light id-only
                # projection — the KB can hold tens of thousands of rows.
                import re as _re
                norm = _re.sub(r"[^a-z0-9]", "", slug.lower())
                if norm:
                    ids = self.db.query(KnowledgeEntry.id, KnowledgeEntry.ext_id).all()
                    match = next((i for i, ext in ids
                                  if _re.sub(r"[^a-z0-9]", "", (ext or "").lower()) == norm),
                                 None)
                    if match is not None:
                        row = self.db.query(KnowledgeEntry).get(match)
            if row is not None:
                text = row.content or row.description or ""
                if row.title:
                    text = f"# {row.title}\n\n{text}"
        if not text:
            return {"ok": False, "error": f"skill '{slug}'"
                    f"{'/' + reference if reference else ''} not found"}
        return {"ok": True, "skill": slug, "reference": reference,
                "content": text[:14000]}

    async def _record_finding(self, args: dict) -> dict:
        from services.finding_service import FindingService
        result = FindingService(self.db).record(
            self.assessment_id, self.task_id, {**args, "status": "potential"})
        row = result.card
        self.findings.append(row.id)
        await self._emit("finding", {"id": row.id, "title": row.title,
                                    "severity": row.severity, "occurrence": result.occurrence})
        return {"ok": True, "card_id": row.id, "occurrence": result.occurrence,
                "fingerprint": row.fingerprint}
