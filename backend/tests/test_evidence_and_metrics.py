"""evidence_store (disk mirror) + metrics (Prometheus gauges).

The evidence mirror writes real files under tmp_path (EVIDENCE_DIR patched);
metrics reads task counts from the isolated test DB.
"""
from __future__ import annotations

import services.evidence_store as es
import services.metrics as metrics
from models.artifact import Artifact
from models.assessment import Assessment
from models.task import Task


# --- evidence_store ----------------------------------------------------------

def test_slug_sanitizes_and_blocks_parent_hop():
    assert es._slug("Web App 2024") == "Web_App_2024"
    assert es._slug("../../etc/passwd") == "etc_passwd"  # dots/slashes collapse, no ".."
    assert es._slug("...---___") == "item"  # nothing left → fallback
    assert es._slug("  spaced  ") == "spaced"


def _mk_artifact(db, asn, filename="shot.png", data=b"image-bytes"):
    a = Artifact(assessment_id=asn.id, kind="screenshot", filename=filename,
                 content_type="image/png", caption="cap", data=data)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_mirror_skipped_when_mount_absent(db, monkeypatch, tmp_path):
    monkeypatch.setattr(es, "EVIDENCE_DIR", str(tmp_path / "not-mounted"))
    asn = Assessment(name="no-mount", scope="127.0.0.1")
    db.add(asn)
    db.commit()
    art = _mk_artifact(db, asn)
    assert es.mirror_artifact(db, art) is None


def test_mirror_skipped_when_artifact_has_no_data(db, monkeypatch, tmp_path):
    monkeypatch.setattr(es, "EVIDENCE_DIR", str(tmp_path))
    asn = Assessment(name="empty-data", scope="127.0.0.1")
    db.add(asn)
    db.commit()
    art = _mk_artifact(db, asn, data=b"")  # column is NOT NULL; empty bytes allowed
    assert es.mirror_artifact(db, art) is None


def test_mirror_writes_file_and_links_hash_chain(db, monkeypatch, tmp_path):
    monkeypatch.setattr(es, "EVIDENCE_DIR", str(tmp_path))
    asn = Assessment(name="Engagement Name!", scope="127.0.0.1")
    db.add(asn)
    db.commit()
    art = _mk_artifact(db, asn, filename="proof shot.png")

    rel = es.mirror_artifact(db, art)
    assert rel == f"Engagement_Name-{asn.id}/{art.id:04d}-proof_shot.png"
    written = (tmp_path / rel).read_bytes()
    assert written == b"image-bytes"
    # The chain step ran too (extend_chain is called before the disk write).
    assert art.hash_self and len(art.hash_self) == 64

    # Second artifact chains onto the first and gets its own file.
    art2 = _mk_artifact(db, asn, filename="second.png", data=b"more")
    rel2 = es.mirror_artifact(db, art2)
    assert rel2 == f"Engagement_Name-{asn.id}/{art2.id:04d}-second.png"
    db.refresh(art2)
    assert art2.hash_prev == art.hash_self

    from services.evidence_chain import verify_chain
    assert verify_chain(db, asn.id)["ok"] is True


def test_mirror_handles_missing_assessment_row(db, monkeypatch, tmp_path):
    """The Assessment lookup misses (defensive branch) → generic folder name."""
    monkeypatch.setattr(es, "EVIDENCE_DIR", str(tmp_path))
    asn = Assessment(name="ghost", scope="127.0.0.1")
    db.add(asn)
    db.commit()
    art = _mk_artifact(db, asn)

    class OrphanSession:
        """Real session, except Assessment queries find nothing."""

        def query(self, model, *a, **kw):
            if model is Assessment:
                class _Q:
                    def filter(self, *a, **kw):
                        return self

                    def first(self):
                        return None
                return _Q()
            return db.query(model, *a, **kw)

        def __getattr__(self, item):
            return getattr(db, item)

    rel = es.mirror_artifact(OrphanSession(), art)
    assert rel == f"assessment-{asn.id}/{art.id:04d}-shot.png"


def test_mirror_failure_is_swallowed(db, monkeypatch, tmp_path):
    monkeypatch.setattr(es, "EVIDENCE_DIR", str(tmp_path))

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(es.os, "makedirs", boom)
    asn = Assessment(name="fail-write", scope="127.0.0.1")
    db.add(asn)
    db.commit()
    art = _mk_artifact(db, asn)
    assert es.mirror_artifact(db, art) is None  # never raises to the caller


# --- metrics -----------------------------------------------------------------

def _add_tasks(db, statuses):
    for i, st in enumerate(statuses):
        db.add(Task(title=f"t{i}", status=st))
    db.commit()


def test_render_exposes_counters_and_content_type(db, monkeypatch, runtime_sessions):
    monkeypatch.setattr("database.SessionLocal", runtime_sessions)
    _add_tasks(db, ["queued", "queued", "running", "done"])
    body, ctype = metrics.render()
    assert ctype.startswith("text/plain")
    text = body.decode()
    assert "aida_tasks_by_status" in text
    # Task gauges are computed from the DB on scrape.
    metrics.TASKS_BY_STATUS.labels(status="queued").set(0)  # reset before re-check
    metrics.collect_task_gauges()
    assert metrics.TASKS_BY_STATUS.labels(status="queued")._value.get() == 2.0


def test_nvd_cache_age_handles_postgres_timezone_aware_datetimes(
        db, monkeypatch, runtime_sessions):
    from datetime import datetime, timedelta, timezone
    from models.nvd import NVDDigestState

    monkeypatch.setattr("database.SessionLocal", runtime_sessions)
    db.add(NVDDigestState(
        id=1,
        last_success_at=datetime.now(timezone.utc) - timedelta(hours=2),
        item_count=3,
    ))
    db.commit()
    metrics.NVD_CACHE_AGE.set(-1)

    metrics.collect_task_gauges()

    assert 7000 <= metrics.NVD_CACHE_AGE._value.get() <= 7400
    assert metrics.NVD_CACHED_ITEMS._value.get() == 3


def test_collect_task_gauges_survives_query_failure(monkeypatch):
    """A DB error mid-query must never propagate to /metrics."""

    class BrokenSession:
        def query(self, *a, **kw):
            raise RuntimeError("db down")

        def close(self):
            pass

    monkeypatch.setattr("database.SessionLocal", lambda: BrokenSession())
    metrics.collect_task_gauges()  # must not raise


def test_llm_counters_are_scrapeable():
    metrics.LLM_CALLS.labels(provider="openai", model="gpt-test").inc()
    metrics.AGENT_STEPS.labels(kind="tool").inc()
    body, _ = metrics.render()
    text = body.decode()
    assert "aida_llm_calls_total" in text
    assert "aida_agent_steps_total" in text
