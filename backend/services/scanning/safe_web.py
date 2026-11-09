"""Fail-closed, bounded HTTP client and safe web baseline profile.

Only GET requests are issued. Redirects are rejected, every redirect-free
request is scope- and DNS-checked, responses are streamed to a byte cap, and
same-origin crawling has strict page/time limits.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html.parser import HTMLParser
import time
from typing import Optional
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from models.finding_snapshot import FindingSnapshot
from models.task import Task
from services.agent.scope import Scope, ScopeViolation, parse_scope
from services.finding_service import FindingService


@dataclass
class SafeResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int


class SafeHttpClient:
    def __init__(self, scope: Scope, *, timeout: float = 5.0,
                 max_response_bytes: int = 1_000_000):
        self.scope = scope
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    async def get(self, url: str) -> SafeResponse:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
            raise ScopeViolation("invalid_url")
        if self.scope.is_empty or not self.scope.host_in_scope(host):
            raise ScopeViolation(f"out_of_scope: {host}")
        allowed, reason = self.scope.check_resolved_host(host)
        if not allowed:
            raise ScopeViolation(f"{reason}: {host}")

        started = time.monotonic()
        chunks: list[bytes] = []
        total = 0
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False, trust_env=False,
            headers={"User-Agent": "AIDA-Safe-Web-Baseline/1.0",
                     "Accept": "text/html,application/xhtml+xml,application/json;q=0.5"},
        ) as client:
            async with client.stream("GET", url) as response:
                if 300 <= response.status_code < 400:
                    raise ScopeViolation(f"redirect denied ({response.status_code})")
                length = response.headers.get("content-length")
                if length and length.isdigit() and int(length) > self.max_response_bytes:
                    raise ValueError("response too large")
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.max_response_bytes:
                        raise ValueError("response too large")
                    chunks.append(chunk)
                return SafeResponse(
                    url=url, status_code=response.status_code,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=b"".join(chunks), elapsed_ms=int((time.monotonic() - started) * 1000),
                )


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and not href.lower().startswith(("javascript:", "data:", "mailto:", "tel:")):
            self.links.append(href)


class SafeWebBaseline:
    """Recurring, evidence-producing baseline for explicitly authorized web labs."""

    def __init__(self, db, task: Task, *, on_event=None,
                 rate_limit_seconds: Optional[float] = None,
                 max_pages: Optional[int] = None, max_response_bytes: Optional[int] = None,
                 timeout: Optional[float] = None):
        self.db = db
        self.task = task
        self.on_event = on_event
        configured_rate = (task.meta or {}).get("rate_limit_seconds", 60)
        self.rate_limit_seconds = configured_rate if rate_limit_seconds is None else rate_limit_seconds
        self.max_pages = max(1, min(int(max_pages if max_pages is not None
                                      else (task.meta or {}).get("max_pages", 8)), 25))
        self.max_response_bytes = max(1, min(int(
            max_response_bytes if max_response_bytes is not None
            else (task.meta or {}).get("max_response_bytes", 1_000_000)), 2_000_000))
        self.timeout = max(0.5, min(float(
            timeout if timeout is not None else (task.meta or {}).get("timeout_seconds", 5.0)), 15.0))
        self.findings = FindingService(db)

    async def _emit(self, kind: str, data: dict):
        if self.on_event:
            await self.on_event(kind, data)

    @staticmethod
    def _origin(url: str):
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme, (parsed.hostname or "").lower(), port

    def _same_origin(self, url: str) -> bool:
        try:
            return self._origin(url) == self._origin(self.task.target)
        except (ValueError, TypeError):
            return False

    async def _record(self, run_id: int, data: dict):
        result = self.findings.record(self.task.assessment_id, run_id, data)
        await self._emit("finding", {"id": result.card.id, "title": result.card.title,
                                    "severity": result.card.severity,
                                    "occurrence": result.occurrence})

    def _header_finding(self, response: SafeResponse, header: str):
        title = "Missing Content-Security-Policy" if header == "content-security-policy" else "Missing clickjacking protection"
        severity = "MEDIUM" if header == "content-security-policy" else "LOW"
        return {
            "title": title, "severity": severity, "status": "confirmed",
            "target_service": response.url,
            "technical_analysis": (
                "The HTML response has no Content-Security-Policy, leaving fewer browser-side "
                "mitigations for injected content." if header == "content-security-policy" else
                "The HTML response has neither X-Frame-Options nor a CSP frame-ancestors directive."),
            "proof": f"GET {response.url}\nHTTP {response.status_code}\n{header}: <absent>",
        }

    async def _analyze(self, response: SafeResponse):
        content_type = response.headers.get("content-type", "")
        text = response.body.decode("utf-8", "replace")
        if "html" in content_type.lower() or "<html" in text[:1000].lower():
            if not response.headers.get("content-security-policy"):
                await self._record(self.task.id, self._header_finding(response, "content-security-policy"))
            csp = response.headers.get("content-security-policy", "")
            if not response.headers.get("x-frame-options") and "frame-ancestors" not in csp.lower():
                await self._record(self.task.id, self._header_finding(response, "x-frame-options"))

        server = response.headers.get("server", "")
        if any(char.isdigit() for char in server):
            await self._record(self.task.id, {
                "title": "Server version disclosure", "severity": "INFO", "status": "confirmed",
                "target_service": response.url,
                "technical_analysis": "The HTTP Server response header discloses software/version information.",
                "proof": f"GET {response.url}\nHTTP {response.status_code}\nServer: {server[:200]}",
            })

        path = urlparse(response.url).path.lower()
        if response.status_code == 200 and (path == "/debug" or path.endswith("/debug")) and "debug" in text.lower():
            canary = "AIDA-E2E-CANARY" in text
            await self._record(self.task.id, {
                "title": "Exposed debug console", "severity": "HIGH" if canary else "MEDIUM",
                "status": "confirmed" if canary else "potential",
                "target_service": response.url,
                "technical_analysis": "An unauthenticated GET to a debug endpoint returned diagnostic content.",
                "proof": f"GET {response.url}\nHTTP {response.status_code}\n\n{text[:2000]}",
            })

    async def run(self) -> dict:
        started = time.monotonic()
        if not self.task.target:
            raise ScopeViolation("target_required")
        scope = parse_scope(self.task.authorized_scope)
        client = SafeHttpClient(scope, timeout=self.timeout,
                                max_response_bytes=self.max_response_bytes)
        queue = [self.task.target]
        queued = set(queue)
        visited: set[str] = set()
        errors: list[str] = []
        blocked = 0
        requests = 0

        while queue and len(visited) < self.max_pages:
            url = queue.pop(0)
            if url in visited or not self._same_origin(url):
                continue
            visited.add(url)
            if requests and self.rate_limit_seconds:
                await asyncio.sleep(float(self.rate_limit_seconds))
            await self._emit("http_request", {"method": "GET", "url": url,
                                              "request_no": requests + 1})
            try:
                response = await client.get(url)
                requests += 1
                await self._emit("http_response", {"url": url, "status": response.status_code,
                                                   "bytes": len(response.body),
                                                   "elapsed_ms": response.elapsed_ms})
                if response.status_code >= 500:
                    error = f"HTTP {response.status_code}; observation incomplete"
                    errors.append(error)
                    await self._emit("http_error", {"url": url, "status": response.status_code})
                    continue
                if response.status_code < 400:
                    await self._analyze(response)
                    parser = _Links()
                    parser.feed(response.body.decode("utf-8", "replace"))
                    for href in parser.links:
                        candidate = urldefrag(urljoin(url, href))[0]
                        if (candidate not in queued and self._same_origin(candidate)
                                and len(queued) < self.max_pages * 3):
                            queued.add(candidate)
                            queue.append(candidate)
            except ScopeViolation as exc:
                blocked += 1
                if not requests:
                    raise
                errors.append(str(exc)[:300])
                await self._emit("blocked", {"url": url, "error": str(exc)[:300]})
            except (httpx.HTTPError, ValueError) as exc:
                if not requests:
                    raise
                errors.append(str(exc)[:300])
                await self._emit("check_error", {"url": url, "error": str(exc)[:300]})

        complete = not errors
        diff = self.findings.finalize_run(self.task.assessment_id, self.task.id, complete=complete)
        current = self.db.query(FindingSnapshot).filter(FindingSnapshot.run_id == self.task.id).count()
        summary = {
            "profile": "safe_web_baseline", "pages": len(visited), "requests": requests,
            "findings": current, "blocked": blocked, "errors": errors[:20],
            "complete": complete, "partial": diff["partial"],
            "duration_seconds": round(time.monotonic() - started, 3),
            **diff["summary"],
        }
        await self._emit("run_diff", summary)
        return summary
