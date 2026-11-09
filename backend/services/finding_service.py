"""Idempotent finding ingest and consecutive Scan Run diffs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.card import Card
from models.finding_snapshot import FindingSnapshot
from models.task import Task

_SEVERITIES = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_MAX_OBSERVATION = 50_000
_MAX_CARD_EVIDENCE = 200_000


@dataclass
class IngestResult:
    card: Card
    snapshot: Optional[FindingSnapshot]
    occurrence: str


class FindingService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _norm(value) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().casefold())

    @classmethod
    def fingerprint(cls, data: dict) -> str:
        """Stable identity excludes severity, evidence, status and run metadata."""
        identity = "\x1f".join((
            cls._norm(data.get("vulnerability_type") or data.get("title")),
            cls._norm(data.get("target_service") or data.get("asset_url")).rstrip("/"),
            cls._norm(data.get("cwe")),
        ))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def record(self, assessment_id: int, run_id: Optional[int], data: dict) -> IngestResult:
        title = str(data.get("title") or "Untitled finding").strip()[:255]
        target = (str(data.get("target_service") or data.get("asset_url") or "").strip()[:255] or None)
        proof = str(data.get("proof") or "")[:_MAX_OBSERVATION] or None
        analysis = str(data.get("technical_analysis") or "")[:_MAX_OBSERVATION] or None
        severity = str(data.get("severity") or "INFO").upper()
        if severity not in _SEVERITIES:
            severity = "INFO"
        fingerprint = self.fingerprint({**data, "title": title, "target_service": target})

        if run_id is not None:
            run = self.db.get(Task, run_id)
            if run is None or run.assessment_id != assessment_id:
                raise ValueError("Scan Run does not belong to this Assessment")

        # A transaction-scoped advisory lock prevents two workers from creating
        # competing canonical cards for the same Assessment+fingerprint.
        self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                        {"key": f"{assessment_id}:{fingerprint}"})
        if run_id is not None:
            existing_snapshot = self.db.query(FindingSnapshot).filter(
                FindingSnapshot.run_id == run_id,
                FindingSnapshot.fingerprint == fingerprint,
            ).first()
            if existing_snapshot is not None:
                return IngestResult(self.db.get(Card, existing_snapshot.card_id),
                                    existing_snapshot, "idempotent")

        card = self.db.query(Card).filter(
            Card.assessment_id == assessment_id,
            Card.fingerprint == fingerprint,
        ).with_for_update().first()
        if card is None:
            # Adopt a pre-fingerprint legacy card rather than discarding its
            # triage and evidence. The normalized comparison is bounded by the
            # Assessment and exact title/target values.
            candidates = self.db.query(Card).filter(
                Card.assessment_id == assessment_id, Card.card_type == "finding",
                Card.fingerprint.is_(None),
            ).order_by(Card.id).all()
            card = next((row for row in candidates
                         if self._norm(row.title) == self._norm(title)
                         and self._norm(row.target_service).rstrip("/") == self._norm(target).rstrip("/")), None)

        now = datetime.utcnow()
        if card is None:
            card = Card(
                assessment_id=assessment_id, card_type="finding", title=title,
                target_service=target, severity=severity,
                status=str(data.get("status") or "potential"),
                technical_analysis=analysis, proof=proof, fingerprint=fingerprint,
                lifecycle_status="new", first_seen_run_id=run_id,
                last_seen_run_id=run_id, last_seen_at=now, seen_count=1,
            )
            self.db.add(card)
            self.db.flush()
            occurrence = "new"
        else:
            occurrence = "reopened" if card.lifecycle_status == "remediated" else "recurring"
            card.fingerprint = fingerprint
            card.lifecycle_status = occurrence
            card.last_seen_run_id = run_id or card.last_seen_run_id
            card.last_seen_at = now
            card.seen_count = int(card.seen_count or 0) + 1
            if _SEVERITIES[severity] > _SEVERITIES.get((card.severity or "INFO").upper(), 0):
                card.severity = severity
            # Preserve triage and prior evidence; add a bounded observation log.
            if proof and proof not in (card.proof or ""):
                marker = f"\n\n--- Observed again in Scan Run #{run_id or 'legacy'} ---\n"
                card.proof = ((card.proof or "") + marker + proof)[-_MAX_CARD_EVIDENCE:]

        snapshot = None
        if run_id is not None:
            snapshot = FindingSnapshot(
                assessment_id=assessment_id, run_id=run_id, card_id=card.id,
                fingerprint=fingerprint, title=title, target_service=target,
                severity=severity, triage_status=card.status,
                lifecycle_status=occurrence, technical_analysis=analysis, proof=proof,
            )
            self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(card)
        if snapshot is not None:
            self.db.refresh(snapshot)
        return IngestResult(card, snapshot, occurrence)

    @staticmethod
    def _item(card: Card, fingerprint: str) -> dict:
        return {
            "card_id": card.id, "fingerprint": fingerprint, "title": card.title,
            "target_service": card.target_service, "severity": card.severity,
            "triage_status": card.status, "lifecycle_status": card.lifecycle_status,
            "first_seen_run_id": card.first_seen_run_id,
            "last_seen_run_id": card.last_seen_run_id,
        }

    def finalize_run(self, assessment_id: int, run_id: int, *, complete: bool = True) -> dict:
        current_rows = self.db.query(FindingSnapshot).filter(
            FindingSnapshot.assessment_id == assessment_id,
            FindingSnapshot.run_id == run_id,
        ).order_by(FindingSnapshot.id).all()
        previous_id = self.db.query(FindingSnapshot.run_id).filter(
            FindingSnapshot.assessment_id == assessment_id,
            FindingSnapshot.run_id < run_id,
        ).order_by(FindingSnapshot.run_id.desc()).first()
        previous_id = previous_id[0] if previous_id else None
        previous_rows = self.db.query(FindingSnapshot).filter(
            FindingSnapshot.run_id == previous_id).all() if previous_id else []
        current = {row.fingerprint: row for row in current_rows}
        previous = {row.fingerprint: row for row in previous_rows}
        card_ids = {row.card_id for row in current_rows + previous_rows}
        cards = {row.id: row for row in self.db.query(Card).filter(Card.id.in_(card_ids)).all()} if card_ids else {}

        diff = {"previous_run_id": previous_id, "current_run_id": run_id, "partial": not complete,
                "new": [], "recurring": [], "remediated": [], "reopened": []}
        for fingerprint, snapshot in current.items():
            card = cards[snapshot.card_id]
            if fingerprint not in previous:
                category = ("reopened" if card.lifecycle_status == "reopened"
                            else "new" if card.first_seen_run_id == run_id else "recurring")
            else:
                category = "reopened" if card.lifecycle_status == "reopened" else "recurring"
            card.lifecycle_status = category if category != "new" else "new"
            diff[category].append(self._item(card, fingerprint))
        for fingerprint, snapshot in previous.items():
            if fingerprint in current or not complete:
                continue
            card = cards[snapshot.card_id]
            card.lifecycle_status = "remediated"
            diff["remediated"].append(self._item(card, fingerprint))
        for values in diff.values():
            if isinstance(values, list):
                values.sort(key=lambda item: (item["title"], item["target_service"] or ""))
        diff["summary"] = {key: len(diff[key]) for key in ("new", "recurring", "remediated", "reopened")}

        run = self.db.get(Task, run_id)
        if run is not None:
            run.meta = {**(run.meta or {}), "finding_diff": diff}
        self.db.commit()
        return diff
