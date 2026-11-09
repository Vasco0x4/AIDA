"""
PII / secret redaction for anything that leaves the operational path —
audit-log details and log lines in particular.

Design notes:
- Applied to audit details and logs, NEVER to operational evidence (findings,
  recon data, command output are stored purposefully — redacting them would
  destroy the platform's purpose).
- Conservative by design: high-precision patterns only. A pattern that fires
  on ordinary text is worse than one that misses an exotic format.
"""
from __future__ import annotations

import re
from typing import Any

# --- secret-shaped tokens -----------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # JWTs (header.payload.signature)
    (re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'),
     '***REDACTED_JWT***'),
    # Bearer tokens regardless of shape
    (re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}'), 'Bearer ***REDACTED***'),
    # OpenAI-style / AIDA / GitHub / Slack / AWS keys
    (re.compile(r'\bsk-[A-Za-z0-9_\-]{16,}'), '***REDACTED_KEY***'),
    (re.compile(r'\baida_sk_[A-Za-z0-9_\-]{8,}'), '***REDACTED_KEY***'),
    (re.compile(r'\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|xox[bap]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16})'),
     '***REDACTED_KEY***'),
    # Zhipu/GLM-style credentials: 32 hex + '.' + ~16 alnum
    (re.compile(r'\b[0-9a-f]{32}\.[A-Za-z0-9]{12,20}\b'), '***REDACTED_KEY***'),
    # PEM private key blocks
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.|\n)*?-----END [A-Z ]*PRIVATE KEY-----'),
     '***REDACTED_PRIVATE_KEY***'),
]

# --- PII patterns --------------------------------------------------------------

_EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b')
_SSN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
# Candidate card numbers: 13-19 digits with optional single separators.
_CC_CANDIDATE = re.compile(r'\b(?:\d[ -]?){13,19}\b')


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def redact_text(value: str) -> str:
    """Mask secrets and PII in a string (best-effort, conservative)."""
    for pattern, repl in _SECRET_PATTERNS:
        value = pattern.sub(repl, value)
    # Emails: keep the domain, mask the local part.
    value = _EMAIL.sub(lambda m: f'***@{m.group(1)}', value)
    value = _SSN.sub('***-**-****', value)
    # Cards: Luhn-validated candidates only, keep last 4.
    def _card(m: re.Match) -> str:
        raw = m.group(0)
        digits = re.sub(r'\D', '', raw)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return f'****-****-****-{digits[-4:]}'
        return raw
    value = _CC_CANDIDATE.sub(_card, value)
    return value


def redact_obj(obj: Any, _depth: int = 0) -> Any:
    """Recursively redact strings inside dicts/lists (depth-capped)."""
    if _depth > 6:
        return '***MAX_DEPTH***'
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v, _depth + 1) for v in obj]
    return obj
