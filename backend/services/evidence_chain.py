"""
Evidence hash chain (E3) — tamper-evidence for everything an agent records.

Per assessment, artifacts are linked like a blockchain: each artifact's
``hash_self = sha256(prev_hash || artifact_bytes)`` where ``prev_hash`` is the
previous chained artifact's ``hash_self`` (all zeros for the first). Any later
modification of stored bytes — or deletion of an artifact — breaks the chain
and is reported by ``verify_chain``.

Concurrency: two agents finishing artifacts for the same assessment at once
must not fork the chain, so the link step takes a Postgres advisory lock on
the assessment id (transaction-scoped, auto-released).

Legacy artifacts created before the chain existed have NULL hashes; they are
skipped by verification, not treated as a break.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.artifact import Artifact
from utils.logger import get_logger

logger = get_logger(__name__)

GENESIS = "0" * 64


def _hash(prev_hex: str, data: bytes) -> str:
    return hashlib.sha256(prev_hex.encode() + data).hexdigest()


def extend_chain(db: Session, artifact: Artifact) -> Artifact | None:
    """Link ``artifact`` (already committed, bytes loaded) into its assessment's
    chain. Best-effort: never raises — an unlinked artifact just shows up as
    legacy in verification."""
    try:
        # Row is committed; (re)load bytes if the instance lost them.
        data = artifact.data
        if data is None:
            row = db.query(Artifact.data).filter(Artifact.id == artifact.id).first()
            if not row or row[0] is None:
                return None
            data = row[0]

        db.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                   {"key": int(artifact.assessment_id)})
        prev = (db.query(Artifact.hash_self)
                .filter(Artifact.assessment_id == artifact.assessment_id,
                        Artifact.hash_self.isnot(None),
                        Artifact.id != artifact.id)
                .order_by(Artifact.id.desc()).first())
        prev_hex = prev[0] if prev else GENESIS

        artifact.hash_prev = prev_hex
        artifact.hash_self = _hash(prev_hex, bytes(data))
        db.commit()
        return artifact
    except Exception as e:  # pragma: no cover - never break artifact saving
        db.rollback()
        logger.warning("evidence chain link failed", artifact_id=artifact.id,
                       error=str(e))
        return None


def verify_chain(db: Session, assessment_id: int) -> dict:
    """Walk the assessment's chained artifacts (by id) and recompute hashes.

    Returns {ok, chained, legacy, broken_at} — ``broken_at`` is the first
    artifact whose recomputed hash differs (tampered bytes, or a preceding
    artifact was deleted)."""
    rows = (db.query(Artifact)
            .filter(Artifact.assessment_id == assessment_id)
            .order_by(Artifact.id).all())
    chained = [r for r in rows if r.hash_self]
    legacy = len(rows) - len(chained)

    expect_prev = GENESIS
    for r in chained:
        if r.hash_prev != expect_prev or _hash(r.hash_prev, bytes(r.data)) != r.hash_self:
            return {"ok": False, "chained": len(chained), "legacy": legacy,
                    "broken_at": r.id}
        expect_prev = r.hash_self
    return {"ok": True, "chained": len(chained), "legacy": legacy,
            "broken_at": None}
