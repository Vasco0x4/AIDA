"""
Compliance registry + finding classification (E4).

Maps findings to the three frameworks enterprise report buyers ask for:

  - OWASP Top 10 (2021)
  - PCI DSS v4.0
  - NIST CSF 2.0

Classification is keyword-driven (title + technical analysis), which is honest
v1 automation: it errs toward leaving a finding UNMAPPED rather than inventing
a mapping. Anything it misses can be set manually — ``Card.compliance_refs``
overrides the automatic classification per framework (``{"owasp": ["A03:2021"]}``
forces A03 and suppresses the classifier's guess for OWASP).

Used by the report generator (framework appendix per report template) and
GET /assessments/{id}/compliance.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from models.card import Card

# Each item: code → {title, patterns (regex, case-insensitive, searched over
# title + technical analysis)}.
FRAMEWORKS: dict[str, dict] = {
    "owasp": {
        "name": "OWASP Top 10 (2021)",
        "items": {
            "A01:2021": {"title": "Broken Access Control", "patterns": [
                r"\bidor\b", r"broken access control", r"unauthorized (access|data)",
                r"privilege escalation", r"\bbola\b", r"\bbfla\b",
                r"path traversal", r"directory traversal", r"\bmass assignment\b"]},
            "A02:2021": {"title": "Cryptographic Failures", "patterns": [
                r"\bssl\b|\btls\b", r"weak cipher", r"cleartext", r"plain-?text",
                r"weak hash", r"\bmd5\b|\bsha-?1\b", r"sensitive data",
                r"credit card", r"\bpan\b", r"missing encryption"]},
            "A03:2021": {"title": "Injection", "patterns": [
                r"sql injection", r"nosql injection", r"command injection",
                r"\bxss\b", r"cross-?site scripting", r"\bssti\b", r"\bxpath\b",
                r"\bxxe\b", r"header injection", r"expression injection"]},
            "A04:2021": {"title": "Insecure Design", "patterns": [
                r"business logic", r"insecure design", r"race condition",
                r"lack of rate limit", r"missing rate limit", r"workflow bypass"]},
            "A05:2021": {"title": "Security Misconfiguration", "patterns": [
                r"misconfig", r"default credential", r"directory listing",
                r"debug mode", r"security header", r"\bcors\b",
                r"admin (panel|interface).{0,30}(expos|open|unauth)",
                r"verbose error", r"backup file", r"source disclosure"]},
            "A06:2021": {"title": "Vulnerable and Outdated Components", "patterns": [
                r"outdated", r"unpatched", r"vulnerable (version|component|software)",
                r"\bcve-\d{4}-\d{4,}\b", r"obsolete (software|version)"]},
            "A07:2021": {"title": "Identification and Authentication Failures", "patterns": [
                r"authenticat", r"brute[- ]forc", r"credential stuffing",
                r"\bsession\b", r"\bjwt\b", r"weak password", r"password policy",
                r"\bmfa\b|\botp\b|\b2fa\b", r"account lockout", r"user enumeration"]},
            "A08:2021": {"title": "Software and Data Integrity Failures", "patterns": [
                r"deserializ", r"unsigned (update|firmware|package)",
                r"supply chain", r"integrity check"]},
            "A09:2021": {"title": "Security Logging and Monitoring Failures", "patterns": [
                r"\blogging\b", r"missing (logs|logging|monitoring)", r"\bmonitoring\b",
                r"audit log", r"no alerting"]},
            "A10:2021": {"title": "Server-Side Request Forgery (SSRF)", "patterns": [
                r"\bssrf\b", r"server[- ]side request forgery"]},
        },
    },
    "pci": {
        "name": "PCI DSS v4.0",
        "items": {
            "1.2.1": {"title": "Network security controls configured and maintained",
                      "patterns": [r"firewall", r"network segmentation", r"exposed (service|port)"]},
            "2.2.4": {"title": "Insecure services / misconfiguration removed",
                      "patterns": [r"misconfig", r"default credential", r"directory listing",
                                   r"debug mode", r"unnecessary service"]},
            "3.3.1": {"title": "Stored cardholder data masked / unreadable",
                      "patterns": [r"credit card", r"\bpan\b", r"cardholder",
                                   r"plain-?text password", r"weak hash"]},
            "3.5.1": {"title": "Cryptographic key protection",
                      "patterns": [r"hardcoded (key|secret)", r"exposed (key|secret|token)"]},
            "4.2.1": {"title": "Strong cryptography in transmission",
                      "patterns": [r"\bssl ?3\b", r"tls ?1\.?[01]\b", r"weak tls",
                                   r"weak cipher", r"cleartext transmission",
                                   r"plaintext http"]},
            "6.2.4": {"title": "Insecure components remediated",
                      "patterns": [r"outdated", r"unpatched", r"vulnerable (version|component|software)",
                                   r"\bcve-\d{4}-\d{4,}\b"]},
            "6.5.1": {"title": "Injection flaws prevented in software",
                      "patterns": [r"injection", r"\bxss\b", r"cross-?site scripting", r"\bssti\b"]},
            "7.2.1": {"title": "Access restricted to job need (least privilege)",
                      "patterns": [r"\bidor\b", r"broken access control", r"privilege escalation",
                                   r"unauthorized (access|data)", r"path traversal"]},
            "8.3.5": {"title": "Authentication strength (no brute force / lockout)",
                      "patterns": [r"brute[- ]forc", r"weak password", r"default credential",
                                   r"user enumeration", r"account lockout"]},
            "8.4.2": {"title": "MFA for access to cardholder data",
                      "patterns": [r"\bmfa\b|\botp\b|\b2fa\b"]},
            "10.2.1": {"title": "Security events logged and monitored",
                       "patterns": [r"\blogging\b", r"missing (logs|logging|monitoring)",
                                    r"audit log"]},
        },
    },
    "nist": {
        "name": "NIST CSF 2.0",
        "items": {
            "ID.RA-01": {"title": "Weaknesses in assets identified", "patterns": [
                r"\bcve-\d{4}-\d{4,}\b", r"outdated", r"unpatched",
                r"vulnerable (version|component|software)"]},
            "PR.AA-01": {"title": "Identities and credentials managed", "patterns": [
                r"authenticat", r"weak password", r"default credential", r"user enumeration",
                r"hardcoded (key|secret)"]},
            "PR.AA-03": {"title": "Access to assets limited (least privilege)", "patterns": [
                r"\bidor\b", r"broken access control", r"privilege escalation",
                r"unauthorized (access|data)", r"path traversal", r"\bbola\b"]},
            "PR.AA-05": {"title": "Access permissions / sessions managed", "patterns": [
                r"\bsession\b", r"\bjwt\b", r"token", r"\bmfa\b|\botp\b|\b2fa\b"]},
            "PR.DS-01": {"title": "Data-at-rest protected", "patterns": [
                r"plain-?text", r"weak hash", r"cleartext", r"sensitive data",
                r"credit card", r"missing encryption"]},
            "PR.DS-02": {"title": "Data-in-transit protected", "patterns": [
                r"\bssl\b|\btls\b", r"weak cipher", r"plaintext http"]},
            "PR.PS-01": {"title": "Configuration management enforced", "patterns": [
                r"misconfig", r"directory listing", r"debug mode", r"security header",
                r"\bcors\b", r"verbose error"]},
            "PR.PS-02": {"title": "Software maintained / replaced", "patterns": [
                r"outdated", r"unpatched", r"\bcve-\d{4}-\d{4,}\b"]},
            "DE.CM-01": {"title": "Networks monitored to detect events", "patterns": [
                r"\blogging\b", r"missing (logs|logging|monitoring)", r"audit log",
                r"no alerting"]},
            "DE.CM-06": {"title": "External service activities monitored", "patterns": [
                r"brute[- ]forc", r"credential stuffing"]},
        },
    },
}

# Pre-compiled pattern cache (module load time is fine — a few dozen regexes).
_COMPILED: dict[str, list[tuple[str, str, re.Pattern]]] = {}
for fw, spec in FRAMEWORKS.items():
    _COMPILED[fw] = [
        (code, item["title"], re.compile("|".join(item["patterns"]), re.IGNORECASE))
        for code, item in spec["items"].items()
    ]

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def classify_finding(card: Card) -> dict[str, list[dict]]:
    """Automatic framework mapping for one finding: framework → matched items.
    Manual ``card.compliance_refs`` overrides the automatic result per
    framework (present → replace, absent → auto)."""
    text = f"{card.title or ''}\n{card.technical_analysis or ''}"
    manual = card.compliance_refs if isinstance(card.compliance_refs, dict) else {}
    out: dict[str, list[dict]] = {}
    for fw, entries in _COMPILED.items():
        refs = manual.get(fw)
        if refs is not None:
            items = [{"code": c, "title": FRAMEWORKS[fw]["items"].get(
                c, {}).get("title", "")} for c in refs]
        else:
            items = [{"code": code, "title": title}
                     for code, title, rx in entries if rx.search(text)]
        if items:
            out[fw] = items
    return out


def map_assessment(db: Session, assessment_id: int,
                   framework: Optional[str] = None) -> dict:
    """Full mapping for a report: framework → code → findings. When
    ``framework`` is given only that one is computed."""
    if framework is not None and framework not in FRAMEWORKS:
        raise ValueError(f"Unknown framework {framework!r} "
                         f"(expected one of {sorted(FRAMEWORKS)})")
    findings = (db.query(Card)
                .filter(Card.assessment_id == assessment_id,
                        Card.card_type == "finding",
                        Card.status != "false_positive")
                .all())
    findings.sort(key=lambda c: (_SEVERITY_ORDER.get(c.severity or "INFO", 9), c.id))

    def _card(f: Card) -> dict:
        return {"id": f.id, "title": f.title, "severity": f.severity,
                "status": f.status, "target_service": f.target_service}

    result: dict = {}
    for fw in ([framework] if framework else list(FRAMEWORKS)):
        mapping: dict[str, dict] = {}
        for f in findings:
            for item in classify_finding(f).get(fw, []):
                slot = mapping.setdefault(item["code"],
                                          {"title": item["title"], "findings": []})
                slot["findings"].append(_card(f))
        result[fw] = {
            "name": FRAMEWORKS[fw]["name"],
            "controls": dict(sorted(mapping.items())),
            "mapped_findings": sum(len(v["findings"]) for v in mapping.values()),
            "unmapped_findings": len(findings) - sum(
                1 for f in findings if classify_finding(f).get(fw)),
        }
    return result
