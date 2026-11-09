"""Recurring scans are Scan Runs inside one existing Assessment.

Tasks remain the durable run/lease/event implementation. A schedule selects the
Assessment once; every fire adds a Task with run provenance, never a new
Assessment. These tests intentionally exercise the production behavior rather
than a parallel reporting model.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from models.assessment import Assessment
from models.scheduled_engagement import ScheduledEngagement
from models.task import Task
from services.scheduler import EngagementScheduler


@pytest.fixture()
def existing_assessment(db):
    row = Assessment(name="Recurring customer portal", scope="127.0.0.1")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def recurring_engagement(db, existing_assessment):
    row = ScheduledEngagement(
        name="Portal every night",
        cron="0 3 * * *",
        task_title="Safe portal baseline",
        description="Re-run non-destructive checks",
        target="http://127.0.0.1:3000",
        authorized_scope="127.0.0.1",
        enabled=True,
        orchestrate=False,
        next_run_at=datetime(2026, 8, 17, 3, 0),
    )
    # Kept as a plain attribute here so the regression test fails against the
    # old model instead of erroring during fixture setup.
    row.assessment_id = existing_assessment.id
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class FailOnAssessmentCreate:
    """The scheduler must not provision another Assessment for later runs."""

    def __init__(self, db):
        self.db = db

    async def create_assessment(self, data):  # pragma: no cover - failure path
        raise AssertionError("A recurring Scan Run must reuse its Assessment")


async def test_repeated_runs_reuse_one_assessment(
    db, recurring_engagement, existing_assessment, monkeypatch,
):
    import services.assessment_service as assessments
    monkeypatch.setattr(assessments, "AssessmentService", FailOnAssessmentCreate)
    scheduler = EngagementScheduler()

    first = await scheduler.fire(db, recurring_engagement, datetime(2026, 8, 17, 3, 0))
    assert first is not None
    assert first.assessment_id == existing_assessment.id
    first.status = "done"
    db.commit()

    second = await scheduler.fire(db, recurring_engagement, datetime(2026, 8, 18, 3, 0))
    assert second is not None
    assert second.assessment_id == existing_assessment.id
    assert second.id != first.id
    assert second.meta["scheduled"]["run_no"] == 2
    assert second.meta["scheduled"]["previous_task_id"] == first.id
    assert second.meta["scheduled"]["previous_assessment_id"] == existing_assessment.id
    assert db.query(Assessment).count() == 1
    assert db.query(Task).filter(Task.assessment_id == existing_assessment.id).count() == 2


async def test_same_assessment_active_run_blocks_other_schedule(
    db, recurring_engagement, existing_assessment, monkeypatch,
):
    import services.assessment_service as assessments
    monkeypatch.setattr(assessments, "AssessmentService", FailOnAssessmentCreate)
    scheduler = EngagementScheduler()
    first = await scheduler.fire(db, recurring_engagement, datetime(2026, 8, 17, 3, 0))
    first.status = "running"
    db.commit()

    other = ScheduledEngagement(
        name="Same Assessment manual template", cron="*/5 * * * *",
        task_title="Must not overlap", target="http://127.0.0.1:3000",
        authorized_scope="127.0.0.1", enabled=True, orchestrate=False,
    )
    other.assessment_id = existing_assessment.id
    db.add(other)
    db.commit()

    assert await scheduler.fire(db, other, datetime(2026, 8, 17, 3, 5)) is None
    assert db.query(Task).filter(Task.assessment_id == existing_assessment.id).count() == 1


def test_non_utc_cron_is_stored_as_utc():
    from services.scheduler import next_run

    # 09:00 in New York is 13:00 UTC during daylight saving time.
    value = next_run("0 9 * * *", datetime(2026, 8, 17, 0, 0), "America/New_York")
    assert value == datetime(2026, 8, 17, 13, 0)


def test_schedule_api_persists_assessment_and_safe_policy(
    client, admin_headers, existing_assessment,
):
    response = client.post("/api/schedules", headers=admin_headers, json={
        "name": "Authorized local lab",
        "cron": "0 9 * * *",
        "timezone": "America/New_York",
        "task_title": "Safe web baseline",
        "target": "http://127.0.0.1:3000",
        "authorized_scope": "http://127.0.0.1:3000",
        "assessment_id": existing_assessment.id,
        "scan_profile": "safe_web_baseline",
        "orchestrate": False,
        "rate_limit_seconds": 2,
        "authorization_confirmed": True,
        "authorization_reference": "Local isolated lab owned by test runner",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assessment_id"] == existing_assessment.id
    assert body["scan_profile"] == "safe_web_baseline"
    assert body["timezone"] == "America/New_York"
    assert body["rate_limit_seconds"] == 2

    duplicate = client.post("/api/schedules", headers=admin_headers, json={
        "name": "authorized LOCAL lab", "cron": "0 9 * * *", "task_title": "Duplicate",
    })
    assert duplicate.status_code == 409


def test_safe_schedule_requires_authorization_reference(
    client, admin_headers, existing_assessment,
):
    response = client.post("/api/schedules", headers=admin_headers, json={
        "name": "Unconfirmed lab", "cron": "0 9 * * *", "task_title": "Denied",
        "target": "http://127.0.0.1:3000", "authorized_scope": "127.0.0.1",
        "assessment_id": existing_assessment.id, "scan_profile": "safe_web_baseline",
        "authorization_confirmed": False,
    })
    assert response.status_code == 400
    assert "Confirm authorization" in response.json()["detail"]
