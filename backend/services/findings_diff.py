"""
Findings diff between two audits (E4) — the recurring-audit payoff.

Classifies findings of a NEW assessment against an OLD baseline:

  - new         — present now, absent before (regression / newly introduced)
  - fixed       — present before, absent now (remediated)
  - persistent  — present in both, with severity/status change flags

Findings are matched by (normalized title, normalized target_service) — the
identity a pentester gives a finding across audit rounds. False positives are
excluded from both sides: they are noise the reviewer already dismissed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.assessment import Assessment
from models.card import Card

_WS = re.compile(r"\s+")


def _norm(value: Optional[str]) -> str:
    return _WS.sub(" ", (value or "").strip().lower())


def _key(card: Card) -> tuple[str, str]:
    return (_norm(card.title), _norm(card.target_service))


def _card_out(card: Card) -> dict:
    return {
        "id": card.id,
        "title": card.title,
        "severity": card.severity,
        "status": card.status,
        "target_service": card.target_service,
        "cvss_score": card.cvss_score,
        "created_at": card.created_at.isoformat() if card.created_at else None,
    }


def _load_findings(db: Session, assessment_id: int) -> list[Card]:
    return (
        db.query(Card)
        .filter(Card.assessment_id == assessment_id,
                Card.card_type == "finding",
                # Reviewer-dismissed findings never drive regression decisions.
                Card.status != "false_positive")
        .order_by(Card.id)
        .all()
    )


def _assessment_out(a: Optional[Assessment]) -> Optional[dict]:
    if not a:
        return None
    return {"id": a.id, "name": a.name, "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None}


def diff_assessments(db: Session, old_id: int, new_id: int) -> dict:
    """Diff the findings of ``new_id`` (current audit) against ``old_id``
    (baseline). Both assessments must exist — the API layer 404s otherwise."""
    old = db.query(Assessment).filter(Assessment.id == old_id).first()
    new = db.query(Assessment).filter(Assessment.id == new_id).first()

    old_findings = _load_findings(db, old_id)
    new_findings = _load_findings(db, new_id)
    old_keys = {_key(f) for f in old_findings}
    new_keys = {_key(f) for f in new_findings}

    fresh = [f for f in new_findings if _key(f) not in old_keys]
    fixed = [f for f in old_findings if _key(f) not in new_keys]

    old_by_key = {_key(f): f for f in old_findings}
    persistent = []
    for f in new_findings:
        prior = old_by_key.get(_key(f))
        if prior is None:
            continue
        persistent.append({
            "old": _card_out(prior),
            "new": _card_out(f),
            "severity_changed": (prior.severity or "INFO") != (f.severity or "INFO"),
            "old_severity": prior.severity,
            "new_severity": f.severity,
            "status_changed": (prior.status or "") != (f.status or ""),
        })

    def _sev_rank(sev) -> int:
        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        return order.get((sev or "INFO").upper(), 9)

    fresh.sort(key=lambda c: _sev_rank(c.severity))
    fixed.sort(key=lambda c: _sev_rank(c.severity))
    persistent.sort(key=lambda p: _sev_rank(p["new"]["severity"]))

    return {
        "old_assessment": _assessment_out(old),
        "new_assessment": _assessment_out(new),
        "generated_at": datetime.utcnow().isoformat(),
        "new": [_card_out(f) for f in fresh],
        "fixed": [_card_out(f) for f in fixed],
        "persistent": persistent,
        "summary": {
            "total_old": len(old_findings),
            "total_new": len(new_findings),
            "new": len(fresh),
            "fixed": len(fixed),
            "persistent": len(persistent),
            "severity_changed": sum(1 for p in persistent if p["severity_changed"]),
        },
    }
