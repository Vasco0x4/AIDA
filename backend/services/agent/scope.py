"""
Authorization-scope enforcement — a hard safety gate for the autonomous agent.

A task's ``authorized_scope`` is free text listing what the agent MAY touch
(domains, wildcard domains, IPs, CIDRs), optionally with exclusions. Before any
network-touching action, the runtime extracts candidate targets and checks each
against the scope. No scope → nothing is in scope (the agent refuses to act).

This is best-effort but meaningful: structured tools (http_probe, targeted
scans) carry an explicit target we can check precisely; free-form shell commands
are scanned for host/URL/IP tokens and every extracted target must be in scope.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


_HOST_RE = re.compile(
    r"\b(?:https?://)?"
    r"(?P<host>(?:[a-zA-Z0-9_-]+\.)+[a-zA-Z]{2,}|(?:\d{1,3}\.){3}\d{1,3})"
    r"(?::\d+)?\b"
)

# Tokens that look like hosts but are local/harmless; never blocked or required.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class ScopeViolation(ValueError):
    """A network action was denied by explicit authorization policy."""

# Common file extensions: a bare token like "wordlist.txt" or "out.json" matches
# the host regex but is a filename, not a target. Skip these during extraction so
# the scope gate doesn't block legitimate commands (wordlists, output files).
_FILE_EXTS = {
    "txt", "json", "xml", "html", "htm", "csv", "tsv", "js", "ts", "py", "sh",
    "conf", "cfg", "ini", "log", "yaml", "yml", "md", "png", "jpg", "jpeg",
    "gif", "svg", "pdf", "zip", "tar", "gz", "tgz", "bz2", "7z", "db", "sql",
    "pem", "key", "crt", "cer", "pcap", "bin", "dat", "list", "lst", "dic",
    "php", "asp", "aspx", "jsp", "bak", "old", "tmp", "out", "env",
    # Common source/build files an exploit-writing agent references as bare args.
    # NOTE: deliberately EXCLUDES real ccTLDs (rs=Serbia, pl=Poland, ml=Mali, …)
    # so an out-of-scope host on those TLDs still fails closed and gets checked.
    "go", "rb", "ex", "exs", "kt", "hs", "clj", "cljs", "scala", "swift", "lua",
    "jl", "dart", "jsx", "tsx", "vue", "toml", "lock", "mod", "gradle", "cmake",
    "c", "cc", "cpp", "h", "hpp", "java", "cs", "rc",
}


def _looks_like_file(host: str) -> bool:
    """True if the token is almost certainly a filename, not a hostname."""
    if "." not in host:
        return False
    return host.rsplit(".", 1)[-1] in _FILE_EXTS


# JS/DOM globals that begin a property-access chain in an XSS/JS payload
# (document.domain, window.location, String.fromCharCode, navigator.userAgent).
# These match the host regex but are CODE, not network targets — recognise them
# by their leading identifier so we can skip them. Everything NOT in this set (or
# the file-ext set) is FAIL-CLOSED: still checked against scope, so an
# out-of-scope host on any TLD (evil.top, data.leak.club) is never silently let
# through.
_JS_GLOBALS = {
    "document", "window", "self", "top", "parent", "globalthis", "navigator",
    "location", "console", "history", "screen", "frames", "this",
    "string", "number", "object", "array", "math", "json", "boolean", "symbol",
    "promise", "regexp", "date", "map", "set", "weakmap", "weakset", "function",
    "eval", "atob", "btoa", "settimeout", "setinterval", "fetch",
    "xmlhttprequest", "localstorage", "sessionstorage", "element", "node",
}


def _looks_like_code(host: str) -> bool:
    """True if a dotted token is a JS/DOM property access (document.domain,
    String.fromCharCode) rather than a hostname — its leading label is a JS
    global. Fail-closed: unknown dotted tokens are NOT treated as code."""
    if "." not in host:
        return False
    return host.split(".", 1)[0] in _JS_GLOBALS


def _norm_host(token: str) -> str:
    token = token.strip().lower()
    if "://" in token:
        token = urlparse(token).hostname or token
    token = token.split("/")[0].split(":")[0]
    return token.rstrip(".")


@dataclass
class Scope:
    domains: set[str] = field(default_factory=set)        # exact + wildcard bases
    wildcards: set[str] = field(default_factory=set)      # base domains for *.x
    tlds: set[str] = field(default_factory=set)           # whole-TLD scopes (.kz)
    ips: set[str] = field(default_factory=set)
    cidrs: list[ipaddress._BaseNetwork] = field(default_factory=list)
    exclusions: set[str] = field(default_factory=set)     # excluded hosts (raw)
    excluded_wildcards: set[str] = field(default_factory=set)
    excluded_tlds: set[str] = field(default_factory=set)  # excluded TLDs (.gov)
    raw: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.domains or self.wildcards or self.tlds
                    or self.ips or self.cidrs)

    def host_in_scope(self, host: str) -> bool:
        host = _norm_host(host)
        if not host:
            return False
        if host in self.exclusions:
            return False
        if any(host == base or host.endswith("." + base)
               for base in self.excluded_wildcards):
            return False
        if any(host.endswith("." + t) for t in self.excluded_tlds):
            return False
        # Whole-TLD scope: any host under the TLD (.kz → shop.example.kz).
        if any(host.endswith("." + t) for t in self.tlds):
            return True
        # IP / CIDR
        try:
            ip = ipaddress.ip_address(host)
            if str(ip) in self.ips:
                return True
            for net in self.cidrs:
                if ip in net:
                    return True
            return False
        except ValueError:
            pass
        # "localhost" is only an alias for an explicitly authorized loopback;
        # it is never an implicit bypass.
        if host == "localhost" and "127.0.0.1" in self.ips:
            return True
        # Exact domain
        if host in self.domains:
            return True
        # Wildcard: host is the base or a subdomain of a wildcard base
        for base in self.wildcards:
            if host == base or host.endswith("." + base):
                return True
        return False

    def check_command(self, command: str) -> tuple[bool, list[str]]:
        """Return (allowed, out_of_scope_hosts) for a free-form shell command."""
        offending = []
        for m in _HOST_RE.finditer(command):
            raw = m.group(0)
            host = _norm_host(m.group("host"))

            # For a schemeless token, skip only what we're CONFIDENT isn't a
            # network target: known filenames (wordlist.txt, main.go) and JS/DOM
            # payload tokens (document.domain, String.fromCharCode). Everything
            # else — including unknown/uncommon TLDs — is checked against scope
            # (fail closed), so an out-of-scope host is never silently allowed.
            # A token carrying an explicit scheme (http://…) is always a target.
            if "://" not in raw:
                if _looks_like_file(host) or _looks_like_code(host):
                    continue
            if not self.host_in_scope(host):
                offending.append(host)
        return (len(offending) == 0, sorted(set(offending)))

    def check_resolved_host(self, host: str, expected_addresses=None, *, resolver=None):
        """Check host authorization and pin/validate every DNS answer.

        Private, loopback, link-local and other special-use answers are denied
        for domain grants unless that exact IP/CIDR was independently granted.
        This prevents an in-scope hostname from rebounding to metadata or an
        internal service. Local labs remain supported by explicit IP/CIDR scope.
        """
        import socket

        host = _norm_host(host)
        if not self.host_in_scope(host):
            return False, "out_of_scope"
        if resolver is None:
            def resolver(hostname):
                return [ipaddress.ip_address(item[4][0])
                        for item in socket.getaddrinfo(hostname, None)]
        try:
            answers = list(resolver(host))
        except (OSError, ValueError):
            return False, "dns_error"
        if not answers:
            return False, "dns_error"
        expected = {str(ipaddress.ip_address(str(v))) for v in (expected_addresses or [])}
        for value in answers:
            addr = value if isinstance(value, ipaddress._BaseAddress) else ipaddress.ip_address(str(value))
            explicitly_allowed = str(addr) in self.ips or any(addr in net for net in self.cidrs)
            special = (addr.is_private or addr.is_loopback or addr.is_link_local
                       or addr.is_reserved or addr.is_multicast or addr.is_unspecified)
            if expected and str(addr) not in expected and not explicitly_allowed:
                return False, "dns_rebinding"
            if special and not explicitly_allowed:
                return False, "dns_rebinding"
        return True, None


# Whole-TLD scope forms: ".kz", "*.kz", "all .kz domains". The host regex
# requires a label before the dot, so these otherwise parse to an EMPTY
# scope — silently disarming the agent ("no scope → nothing is in scope")
# while the operator believes a whole-TLD bug-bounty program is covered.
# The TLD grant must be delimited on both sides — ".example.com" must NOT
# grant the pseudo-TLD "example", only the real host match below applies.
_TLD_FORM_RE = re.compile(
    r"(?:^|[\s*'\"(])\*?\.([a-z]{2,24})\.?(?=$|[\s,;)\]}'\"])", re.I)


def parse_scope(text: str | None) -> Scope:
    """Parse free-text authorized_scope into a structured Scope."""
    scope = Scope(raw=text or "")
    if not text:
        return scope

    # Split on commas/newlines/semicolons; tolerate "exclude:"/"-" prefixes.
    tokens = re.split(r"[,\n;]+", text)
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue

        excluded = False
        low = tok.lower()
        if low.startswith(("exclude", "exclusion", "!", "-")):
            excluded = True
            tok = re.sub(r"(?i)^(exclude[d]?|exclusion|!|-)\s*[:=]?\s*", "", tok).strip()

        # Whole-TLD forms first: explicit ".tld" / "*.tld" mentions (with or
        # without surrounding prose). Requires the leading dot/star so a bare
        # prose word is never mistaken for a TLD grant.
        for tld in set(m.lower() for m in _TLD_FORM_RE.findall(tok)):
            (scope.excluded_tlds if excluded else scope.tlds).add(tld)

        # Pull the first host-like / cidr-like token out of the phrase.
        cidr_m = re.search(r"(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}", tok)
        if cidr_m:
            try:
                scope.cidrs.append(ipaddress.ip_network(cidr_m.group(0), strict=False))
                continue
            except ValueError:
                pass

        host_m = _HOST_RE.search(tok)
        if not host_m:
            continue
        host = _norm_host(host_m.group("host"))
        raw_host = host_m.group("host").lower()

        if excluded:
            if raw_host.startswith("*.") or "*." in tok or "subdomain" in low:
                scope.excluded_wildcards.add(host[2:] if host.startswith("*.") else host)
            else:
                scope.exclusions.add(host)
            continue

        # Wildcard forms: "*.example.com" or "all subdomains of example.com"
        if raw_host.startswith("*.") or "*." in tok or "subdomain" in low or tok.strip().startswith("."):
            base = host[2:] if host.startswith("*.") else host
            scope.wildcards.add(base)
            scope.domains.add(base)  # base itself is also in scope
        else:
            try:
                ipaddress.ip_address(host)
                scope.ips.add(host)
            except ValueError:
                scope.domains.add(host)
    return scope
