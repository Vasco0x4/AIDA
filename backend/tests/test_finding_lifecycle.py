"""Stable finding identity, idempotent ingest, and run-over-run diffs."""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.card import Card
from models.finding_snapshot import FindingSnapshot
from models.task import Task
from services.finding_service import FindingService


@pytest.fixture()
def assessment(db):
    row = Assessment(name="Finding lifecycle", scope="127.0.0.1")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_run(db, assessment, title):
    row = Task(title=title, status="running", assessment_id=assessment.id,
               authorized_scope=assessment.scope, orchestrate=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def finding(title="Missing Content-Security-Policy", target="http://127.0.0.1:3000",
            proof="Header absent", severity="MEDIUM"):
    return {
        "title": title, "target_service": target, "severity": severity,
        "status": "confirmed", "technical_analysis": "Browser defenses are reduced.",
        "proof": proof,
    }


def test_repeated_ingest_is_idempotent_and_preserves_evidence(db, assessment):
    first_run = make_run(db, assessment, "run 1")
    second_run = make_run(db, assessment, "run 2")
    service = FindingService(db)

    first = service.record(assessment.id, first_run.id, finding(proof="run one evidence"))
    replay = service.record(assessment.id, first_run.id, finding(proof="retried same observation"))
    assert replay.card.id == first.card.id
    assert replay.occurrence == "idempotent"
    assert db.query(Card).count() == 1
    assert db.query(FindingSnapshot).count() == 1

    second = service.record(assessment.id, second_run.id, finding(
        severity="LOW", proof="run two independent evidence"))
    assert second.card.id == first.card.id
    assert second.occurrence == "recurring"
    assert db.query(Card).count() == 1
    assert second.card.seen_count == 2
    assert second.card.first_seen_run_id == first_run.id
    assert second.card.last_seen_run_id == second_run.id
    assert "run one evidence" in second.card.proof
    assert "run two independent evidence" in second.card.proof
    # A scan observation must not reset a human triage decision.
    assert second.card.status == "confirmed"
    assert db.query(FindingSnapshot).count() == 2


def test_diff_reports_new_recurring_remediated_and_reopened(db, assessment):
    run1 = make_run(db, assessment, "run 1")
    run2 = make_run(db, assessment, "run 2")
    run3 = make_run(db, assessment, "run 3")
    service = FindingService(db)
    a = finding(title="Exposed debug console", target="http://127.0.0.1:3000/debug")
    b = finding(title="Missing Content-Security-Policy", target="http://127.0.0.1:3000")
    c = finding(title="Server version disclosure", target="http://127.0.0.1:3000")

    service.record(assessment.id, run1.id, a)
    service.record(assessment.id, run1.id, b)
    service.finalize_run(assessment.id, run1.id)

    service.record(assessment.id, run2.id, b)
    service.record(assessment.id, run2.id, c)
    diff2 = service.finalize_run(assessment.id, run2.id)
    assert [item["title"] for item in diff2["new"]] == [c["title"]]
    assert [item["title"] for item in diff2["recurring"]] == [b["title"]]
    assert [item["title"] for item in diff2["remediated"]] == [a["title"]]
    assert db.query(Card).count() == 3
    remediated = db.query(Card).filter(Card.title == a["title"]).one()
    assert remediated.lifecycle_status == "remediated"

    service.record(assessment.id, run3.id, a)
    service.record(assessment.id, run3.id, b)
    service.record(assessment.id, run3.id, c)
    diff3 = service.finalize_run(assessment.id, run3.id)
    assert [item["title"] for item in diff3["reopened"]] == [a["title"]]
    assert remediated.lifecycle_status == "reopened"
    assert db.query(Card).count() == 3


def test_fingerprint_excludes_mutable_evidence_and_severity():
    left = FindingService.fingerprint(finding(severity="HIGH", proof="first"))
    right = FindingService.fingerprint(finding(severity="LOW", proof="second"))
    changed_target = FindingService.fingerprint(finding(target="http://127.0.0.1:3000/other"))
    assert left == right
    assert len(left) == 64
    assert changed_target != left
