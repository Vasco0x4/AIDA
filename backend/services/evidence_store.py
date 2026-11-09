"""
Evidence disk mirror.

Artifacts (PoC videos, screenshots, submission reports) are stored as bytes in
the DB (so they embed into the exported report and need no external storage).
For operator convenience we ALSO mirror each one to a plain file on disk under
``EVIDENCE_DIR`` — laid out as ``<assessment-slug>-<id>/<artifact-id>-<name>`` —
so they can be opened/played/read directly from the filesystem.

Best-effort: if the evidence mount is absent or a write fails, the DB copy is
still authoritative and the caller is never disrupted.
"""
from __future__ import annotations

import os
import re

from sqlalchemy.orm import Session

from models.artifact import Artifact
from models.assessment import Assessment
from utils.logger import get_logger

logger = get_logger(__name__)

# Container path; bind-mounted to host ~/AIDA-dev/evidence via docker-compose.
EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", "/evidence")


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (s or "").strip())
    s = s.replace("..", "_")          # never allow a parent-dir hop
    return s.strip("._-") or "item"


def mirror_artifact(db: Session, artifact: Artifact) -> str | None:
    """Post-commit hook shared by EVERY artifact-creation site: link the
    artifact into the assessment's tamper-evidence hash chain, then write the
    bytes to disk. Returns the relative path under EVIDENCE_DIR (same on host
    and container), or None if skipped/failed."""
    from services.evidence_chain import extend_chain
    extend_chain(db, artifact)  # best-effort; independent of the mount below
    try:
        if not os.path.isdir(EVIDENCE_DIR):
            return None  # mount not present (e.g. prod without the volume) → skip
        if not artifact.data:
            return None
        asn = (db.query(Assessment)
               .filter(Assessment.id == artifact.assessment_id).first())
        folder_name = f"{_slug(asn.name) if asn else 'assessment'}-{artifact.assessment_id}"
        folder = os.path.join(EVIDENCE_DIR, folder_name)
        os.makedirs(folder, exist_ok=True)

        base, ext = os.path.splitext(artifact.filename or "artifact")
        ext = "." + _slug(ext.lstrip(".")) if ext.strip(".") else ""
        fname = f"{artifact.id:04d}-{_slug(base)}{ext}"
        rel = os.path.join(folder_name, fname)
        dest = os.path.join(EVIDENCE_DIR, rel)
        # Containment guard: the resolved path MUST stay under EVIDENCE_DIR.
        root = os.path.realpath(EVIDENCE_DIR)
        if os.path.commonpath([root, os.path.realpath(os.path.dirname(dest))]) != root:
            logger.warning("evidence mirror path escaped root; skipped",
                           artifact_id=getattr(artifact, "id", None))
            return None
        with open(dest, "wb") as f:
            f.write(artifact.data)
        return rel
    except Exception:
        logger.warning("evidence disk mirror failed", artifact_id=getattr(artifact, "id", None))
        return None
