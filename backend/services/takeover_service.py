"""
Subdomain Takeover checker — implements the can-i-take-over-xyz methodology.

Given a target domain: enumerate subdomains, then for each one resolve its DNS
CNAME chain + terminal state and (when it resolves / dangles) fetch HTTP/HTTPS,
and match against the canonical fingerprint dataset to emit a verdict:

    VULNERABLE | EDGE_CASE | NOT_VULNERABLE | NONE   (+ confidence + evidence)

Correctness rules (from the design + adversarial review) that we uphold:
- Fingerprints are HTML-entity-decoded then compiled as case-insensitive regex
  (literal fallback); `fingerprint == "NXDOMAIN"` is a DNS sentinel, never grepped.
- Service identity comes from LABEL-BOUNDARY cname matching (never substring, so
  `s3.amazonaws.com.evil.com` can't spoof it) + an infra-domain map for the 48/76
  entries whose cname list is empty.
- Two-signal minimum for VULNERABLE: entry.vulnerable AND status=='Vulnerable'
  AND positive service identity AND an "unclaimed" proof (specific fingerprint OR
  a dangling third-party NXDOMAIN) AND not a wildcard artifact AND not "claimed"
  (a live/configured resource → NONE, never VULNERABLE).
- Status ceiling: Edge case can never become VULNERABLE; Not vulnerable is at most
  informational.
NOTE: dangling-NS delegation takeovers (rows 10-12 of the spec) are a separate
mechanism, left as a follow-up; this covers the CNAME + fingerprint + NXDOMAIN
paths, which are the large majority of real takeovers.

All DNS/HTTP work runs in the pentest container (dig/curl/subfinder) so it uses
the same network path (incl. VPN) as the rest of the platform.
"""
from __future__ import annotations

import asyncio
import functools
import html
import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from services.container_service import ContainerService
from utils.logger import get_logger

logger = get_logger(__name__)

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "subdomain_takeover_fingerprints.json")

# Recover service identity when the dataset cname list is empty (48/76 entries).
# Label-boundary matched. Extend freely.
INFRA_MAP = {
    "herokuapp.com": "Heroku", "herokudns.com": "Heroku", "herokussl.com": "Heroku",
    "github.io": "Github", "github.map.fastly.net": "Github",
    "myshopify.com": "Shopify",
    "ghost.io": "Ghost",
    "azurewebsites.net": "Microsoft Azure", "cloudapp.net": "Microsoft Azure",
    "cloudapp.azure.com": "Microsoft Azure", "trafficmanager.net": "Microsoft Azure",
    "blob.core.windows.net": "Microsoft Azure", "azureedge.net": "Microsoft Azure",
    "azure-api.net": "Microsoft Azure", "azurecontainer.io": "Microsoft Azure",
    "elb.amazonaws.com": "AWS/Load Balancer (ELB)",
    "s3.amazonaws.com": "AWS/S3", "s3-website": "AWS/S3",
    "bitbucket.io": "Bitbucket",
    "fastly.net": "Fastly", "netlify.app": "Netlify", "netlify.com": "Netlify",
    "readthedocs.io": "Readthedocs", "surge.sh": "Surge.sh",
    "ngrok.io": "Ngrok", "wordpress.com": "Wordpress", "pantheonsite.io": "Pantheon",
    "zendesk.com": "Zendesk", "unbouncepages.com": "Unbounce",
    "wpengine.com": "WP Engine", "cargocollective.com": "Cargo Collective",
    "helpscoutdocs.com": "Help Scout", "helpjuice.com": "Help Juice",
}
# Infra keys that are fragments, not full domains → matched as substrings.
_INFRA_FRAGMENTS = {"s3-website"}

_MAX_SUBDOMAINS = 2000
_CONCURRENCY = 12
_BODY_CAP = 60000


@dataclass
class Fingerprint:
    service: str
    status: str            # Vulnerable | Not vulnerable | Edge case
    vulnerable: bool
    nxdomain: bool
    http_status: Optional[int]
    cnames: list           # normalized base domains
    raw_fp: str
    regex: Optional[re.Pattern]
    literal: Optional[str]
    over_match: bool        # fingerprint that leans on a bare '.'/quantifier
    documentation: str = ""


def _decode(s: str) -> str:
    return html.unescape(s or "")


def _norm(host: str) -> str:
    return (host or "").strip().rstrip(".").lower()


def _compile_fp(raw: str):
    """Decode HTML entities, compile as regex, else regex-escaped literal."""
    if not raw:
        return None, None, False
    decoded = _decode(raw)
    # Heuristic for the over-match guard: a plain phrase whose only "regex" is a
    # trailing '.' (e.g. "Sorry, this shop is currently unavailable.").
    stripped = decoded.rstrip(".")
    over_match = ("|" not in decoded and "\\" not in decoded
                  and not re.search(r"[\[\](){}^$*+?]", stripped)
                  and decoded.endswith("."))
    try:
        rx = re.compile(decoded, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        return rx, None, over_match
    except re.error:
        return None, re.escape(decoded), over_match


@functools.lru_cache(maxsize=1)
def load_fingerprints() -> list:
    with open(_DATA, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for e in data:
        raw = e.get("fingerprint") or ""
        is_nx = (raw.strip().upper() == "NXDOMAIN") or e.get("nxdomain")
        rx, lit, over = (None, None, False) if raw.strip().upper() == "NXDOMAIN" else _compile_fp(raw)
        out.append(Fingerprint(
            service=e["service"], status=e["status"], vulnerable=bool(e["vulnerable"]),
            nxdomain=bool(is_nx), http_status=e.get("http_status"),
            cnames=[_norm(c) for c in (e.get("cname") or [])],
            raw_fp=raw, regex=rx, literal=lit, over_match=over,
            documentation=e.get("documentation") or "",
        ))
    return out


def _base_match(host: str, base: str) -> bool:
    """Label-boundary match — host == base or host endswith '.'+base."""
    host, base = _norm(host), _norm(base)
    return bool(base) and (host == base or host.endswith("." + base))


@dataclass
class DnsResult:
    cname_chain: list = field(default_factory=list)   # ordered targets
    resolves: bool = False                            # has terminal A/AAAA
    status: str = "UNKNOWN"                           # NOERROR/NXDOMAIN/SERVFAIL/...
    a_records: list = field(default_factory=list)


class TakeoverService:
    def __init__(self):
        self.container = ContainerService()
        self.fps = load_fingerprints()

    # ---- container helpers -------------------------------------------------
    async def _exec(self, cmd: str) -> str:
        try:
            res = await self.container.execute_container_command(command=cmd)
            return (res.get("stdout") or "") if isinstance(res, dict) else ""
        except Exception as e:
            logger.warning("takeover exec failed", error=str(e))
            return ""

    async def _dns(self, host: str) -> DnsResult:
        host = _norm(host)
        out = await self._exec(
            f"dig +tries=2 +time=3 {host} +noall +answer; echo '==='; "
            f"dig +tries=2 +time=3 {host} +noall +comments 2>/dev/null | grep -o 'status: [A-Z]*' | head -1")
        answer, _, comments = out.partition("===")
        r = DnsResult()
        for line in answer.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                rtype, rdata = parts[3], parts[4]
                if rtype == "CNAME":
                    r.cname_chain.append(_norm(rdata))
                elif rtype in ("A", "AAAA"):
                    r.a_records.append(rdata.rstrip("."))
        r.resolves = len(r.a_records) > 0
        m = re.search(r"status:\s*([A-Z]+)", comments)
        r.status = m.group(1) if m else ("NOERROR" if r.resolves else "NXDOMAIN")
        return r

    async def _http_bodies(self, host: str) -> list:
        """Fetch http+https body of host (Host/SNI = host, tolerate TLS errors).

        The HTTP status code is captured on stdout INDEPENDENTLY of the body
        (which is written to a temp file and size-capped), so a body larger than
        _BODY_CAP can never truncate/lose the status marker.
        """
        import uuid as _uuid
        host = _norm(host)
        bodies = []
        for scheme in ("https", "http"):
            tmp = f"/tmp/aida_tk_{_uuid.uuid4().hex}.body"
            out = await self._exec(
                f"code=$(curl -sk -m 12 -L --max-redirs 3 -A 'Mozilla/5.0 AIDA' "
                f"-o '{tmp}' -w '%{{http_code}}' '{scheme}://{host}/' 2>/dev/null); "
                f"echo \"$code\"; head -c {_BODY_CAP} '{tmp}' 2>/dev/null; rm -f '{tmp}'")
            code, _, body = out.partition("\n")
            code = code.strip() or "0"
            if body or code not in ("0", ""):
                bodies.append({"scheme": scheme, "code": code, "body": _decode(body)[:_BODY_CAP]})
        return bodies

    # ---- matching / verdict -----------------------------------------------
    def _attribute(self, dns: DnsResult, apex: str):
        """Identify candidate services via cname base match + infra map.
        Returns list of (Fingerprint, matched_hop, via)."""
        hits = []
        for fp in self.fps:
            for base in fp.cnames:
                for hop in dns.cname_chain:
                    if _base_match(hop, base):
                        hits.append((fp, hop, "cname"))
                        break
        # Infra-map re-anchor (for empty-cname services). Use LABEL-BOUNDARY
        # matching (same anti-spoof guarantee as cname matching); only a small
        # set of non-domain fragment keys (e.g. "s3-website") match as substrings.
        matched_services = {h[0].service for h in hits}
        for hop in dns.cname_chain:
            for infra, service in INFRA_MAP.items():
                is_fragment = infra in _INFRA_FRAGMENTS
                if (is_fragment and infra in hop) or (not is_fragment and _base_match(hop, infra)):
                    if service not in matched_services:
                        fp = next((f for f in self.fps if f.service == service), None)
                        if fp:
                            hits.append((fp, hop, "infra"))
                            matched_services.add(service)
        return hits

    def _fp_matches(self, fp: Fingerprint, bodies: list):
        for b in bodies:
            text = b["body"]
            if fp.regex and fp.regex.search(text):
                return b
            if fp.literal and fp.literal.replace("\\", "") and \
                    re.search(fp.literal, text, re.IGNORECASE):
                return b
        return None

    def _off_domain(self, dns: DnsResult, apex: str) -> bool:
        apex = _norm(apex)
        return any(not _base_match(hop, apex) for hop in dns.cname_chain)

    @staticmethod
    def _resolves_internal(dns: DnsResult) -> bool:
        """True if any terminal A/AAAA is a private/reserved/loopback/metadata IP —
        we never send server-side HTTP there (SSRF-to-internal guard)."""
        import ipaddress
        for ip in dns.a_records:
            try:
                addr = ipaddress.ip_address(ip.strip())
            except ValueError:
                continue
            if (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
                return True
            if str(addr) == "169.254.169.254":  # cloud metadata
                return True
        return False

    def verdict(self, sub: str, dns: DnsResult, bodies: list, apex: str,
                wildcard_sig: Optional[str]) -> Optional[dict]:
        """Apply the decision table. Returns a result dict or None (=NONE)."""
        # Wildcard suppression: if this sub looks identical to the catch-all
        # baseline AND has no off-domain CNAME of its own, it's an artifact.
        if wildcard_sig and not self._off_domain(dns):
            sig = self._body_sig(bodies)
            if sig and sig == wildcard_sig:
                return None

        candidates = self._attribute(dns, apex)
        # Candidacy gate: need an off-domain CNAME (to a known service) at least.
        if not candidates:
            return None

        best = None
        for fp, hop, via in candidates:
            # --- NXDOMAIN-type entry (Azure/ELB shape) ---
            if fp.nxdomain:
                # dangling: a CNAME exists but the chain does not resolve.
                if dns.cname_chain and not dns.resolves and dns.status in ("NXDOMAIN", "SERVFAIL"):
                    if fp.vulnerable and fp.status == "Vulnerable":
                        v = ("VULNERABLE", "high")
                    elif fp.status == "Not vulnerable":
                        v = ("NOT_VULNERABLE", "medium")
                    else:
                        v = ("EDGE_CASE", "low")
                    best = self._pick(best, (fp, hop, via, v, "dangling CNAME → NXDOMAIN"))
                continue
            # --- HTTP-fingerprint entry ---
            matched = self._fp_matches(fp, bodies)
            if not matched:
                # G2 claimed override: identity matches a vulnerable base but the
                # unclaimed fingerprint is absent and it serves content → NONE.
                continue
            # over-match guard: bare-'.' literal alone can't be sole VULNERABLE signal
            if fp.over_match and via != "cname":
                v = ("EDGE_CASE", "low")
            elif fp.vulnerable and fp.status == "Vulnerable":
                conf = "high" if via == "cname" else "medium"
                v = ("VULNERABLE", conf)
            elif fp.status == "Edge case":
                v = ("EDGE_CASE", "medium")
            elif fp.status == "Not vulnerable":
                v = ("NOT_VULNERABLE", "medium")
            else:
                v = ("EDGE_CASE", "low")
            ev = f"fingerprint matched in {matched['scheme']} body (HTTP {matched['code']})"
            best = self._pick(best, (fp, hop, via, v, ev))

        if not best:
            return None
        fp, hop, via, (verdict, conf), evidence = best
        return {
            "subdomain": sub, "verdict": verdict, "confidence": conf,
            "service": fp.service, "cname_target": hop, "via": via,
            "dns_status": dns.status, "cname_chain": dns.cname_chain,
            "evidence": evidence, "documentation": fp.documentation,
            "fingerprint": fp.raw_fp,
        }

    @staticmethod
    def _pick(cur, cand):
        rank = {"VULNERABLE": 3, "EDGE_CASE": 2, "NOT_VULNERABLE": 1}
        if cur is None:
            return cand
        return cand if rank.get(cand[3][0], 0) > rank.get(cur[3][0], 0) else cur

    @staticmethod
    def _body_sig(bodies: list) -> Optional[str]:
        if not bodies:
            return None
        b = bodies[0]
        return f"{b['code']}:{len(b['body'])}"

    # ---- top-level scan ----------------------------------------------------
    async def _wildcard_baseline(self, apex: str) -> Optional[str]:
        sigs = []
        for seed in ("zzq7x9nope", "aida-nx-4k2p"):
            rand = f"{seed}{abs(hash(seed)) % 9999}.{apex}"
            dns = await self._dns(rand)
            if dns.resolves:
                bodies = await self._http_bodies(rand)
                sigs.append(self._body_sig(bodies))
        if len(sigs) == 2 and sigs[0] and sigs[0] == sigs[1]:
            return sigs[0]
        return None

    async def enumerate_subdomains(self, apex: str) -> list:
        out = await self._exec(
            f"subfinder -d {apex} -silent 2>/dev/null | head -n {_MAX_SUBDOMAINS}")
        subs = [_norm(line) for line in out.splitlines() if line.strip() and apex in line]
        return sorted(set(subs))

    async def scan(self, domain: str, subdomains: Optional[list] = None,
                   on_progress=None) -> dict:
        """Scan a domain concurrently. on_progress(event) is awaited after each
        subdomain with {checked, total, result} so callers can stream progress."""
        apex = _norm(domain)
        wildcard = await self._wildcard_baseline(apex)
        subs = [_norm(s) for s in subdomains] if subdomains else await self.enumerate_subdomains(apex)
        subs = sorted(set(s for s in subs if s and (s == apex or s.endswith("." + apex))))[:_MAX_SUBDOMAINS]

        total = len(subs)
        results = []
        counter = {"n": 0}
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def check_one(sub):
            async with sem:
                try:
                    dns = await self._dns(sub)
                    off = self._off_domain(dns, apex)
                    # SSRF guard: never send server-side HTTP to an internal IP.
                    fetch = (off or dns.resolves) and not self._resolves_internal(dns)
                    bodies = await self._http_bodies(sub) if fetch else []
                    v = self.verdict(sub, dns, bodies, apex, wildcard)
                except Exception as e:
                    logger.warning("takeover check failed", sub=sub, error=str(e))
                    v = None
                counter["n"] += 1
                if v:
                    results.append(v)
                if on_progress:
                    await on_progress({"checked": counter["n"], "total": total, "result": v})
                return v

        await asyncio.gather(*(check_one(s) for s in subs), return_exceptions=True)

        order = {"VULNERABLE": 0, "EDGE_CASE": 1, "NOT_VULNERABLE": 2}
        results.sort(key=lambda r: order.get(r["verdict"], 9))
        return {
            "domain": apex, "wildcard": bool(wildcard),
            "subdomains_checked": total,
            "results": results,
            "summary": {
                "vulnerable": sum(1 for r in results if r["verdict"] == "VULNERABLE"),
                "edge_case": sum(1 for r in results if r["verdict"] == "EDGE_CASE"),
                "not_vulnerable": sum(1 for r in results if r["verdict"] == "NOT_VULNERABLE"),
            },
        }
