"""
E4 scheduler tests — cron parsing, next-run math and the engagement fire()
semantics: provenance tagging (meta.scheduled), run chaining for findings
diff, skip-if-active (never pile up), and the platform kill switch.

Hermetic: the workspace-provisioning AssessmentService is stubbed so no
container is ever touched.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from models.assessment import Assessment
from models.platform_settings import PlatformSettings
from models.scheduled_engagement import ScheduledEngagement
from models.task import Task
from services.scheduler import EngagementScheduler, next_run, validate_cron


# --- cron math ---------------------------------------------------------------

class TestCron:
    def test_valid_expressions(self):
        for expr in ("0 3 * * *", "*/5 * * * *", "0 3 * * mon", "0 3 1 * *",
                     "30 14 28 2 *", "0 */6 * * *"):
            assert validate_cron(expr) is True

    def test_invalid_expressions(self):
        for expr in ("", "   ", "not a cron", "0 3 * *", "99 * * * *",
                     "* * * * definitely-not-a-day"):
            assert validate_cron(expr) is False

    def test_next_run_daily(self):
        after = datetime(2026, 8, 18, 10, 0)  # a Tuesday
        assert next_run("0 3 * * *", after) == datetime(2026, 8, 19, 3, 0)

    def test_rejects_seconds_years_and_impossible_dates(self):
        for expr in ("* * * * * *", "0 3 * * * 0 2027", "0 3 30 2 *"):
            assert validate_cron(expr) is False

    def test_qyzylorda_daily_time(self):
        assert next_run("0 3 * * *", datetime(2026, 11, 8, 10), "Asia/Qyzylorda") == datetime(2026, 11, 8, 22)

    def test_next_run_is_strictly_after(self):
        # At the exact fire minute the NEXT occurrence is tomorrow's.
        at_fire = datetime(2026, 8, 18, 3, 0)
        assert next_run("0 3 * * *", at_fire) == datetime(2026, 8, 19, 3, 0)

    def test_next_run_weekly(self):
        after = datetime(2026, 8, 18, 10, 0)  # Tue → next Monday is the 24th
        assert next_run("0 3 * * mon", after) == datetime(2026, 8, 24, 3, 0)


# --- fire() ------------------------------------------------------------------

@pytest.mark.parametrize('enabled,next_at', [
    (False, datetime(2026, 8, 17, 3)), (True, datetime(2026, 8, 19, 3)),
])
async def test_due_fire_rechecks_schedule_after_lock(db, engagement, enabled, next_at):
    engagement.enabled = enabled
    engagement.next_run_at = next_at
    db.commit()
    result = await EngagementScheduler().fire(db, engagement, datetime(2026, 8, 18, 3), due_only=True)
    assert result is None
    assert db.query(Task).count() == 0

class StubAssessmentService:
    """Hermetic stand-in: creates the Assessment row without provisioning an
    Exegol workspace (which the real service does via Docker)."""

    def __init__(self, db):
        self.db = db

    async def create_assessment(self, data):
        row = Assessment(name=data.name, scope=data.scope,
                         objectives=data.objectives,
                         target_domains=data.target_domains)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row


@pytest.fixture()
def hermetic_assessments(monkeypatch):
    import services.assessment_service as asm
    monkeypatch.setattr(asm, "AssessmentService", StubAssessmentService)


@pytest.fixture()
def engagement(db):
    row = ScheduledEngagement(
        name="Weekly web audit", cron="0 3 * * mon",
        task_title="Recurring pentest — prod web", description="objectives",
        target="http://target.example.com",
        authorized_scope="target.example.com",
        enabled=True, orchestrate=True,
        next_run_at=datetime(2026, 8, 17, 3, 0))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


async def test_fire_creates_task_with_provenance(db, engagement,
                                                 hermetic_assessments):
    sched = EngagementScheduler()
    task = await sched.fire(db, engagement, datetime(2026, 8, 17, 3, 0))

    assert task is not None
    assert task.source == "schedule"
    assert task.status == "queued"
    assert task.title == "Recurring pentest — prod web"
    assert task.authorized_scope == "target.example.com"
    assert task.meta["scheduled"]["engagement_id"] == engagement.id
    assert task.meta["scheduled"]["run_no"] == 1

    assert engagement.run_count == 1
    assert engagement.last_task_id == task.id
    assert engagement.last_run_at == datetime(2026, 8, 17, 3, 0)
    assert engagement.next_run_at == datetime(2026, 8, 24, 3, 0)

    # Up-front assessment provisioned and linked (home for findings/diff).
    assert task.assessment_id is not None
    assert db.query(Assessment).count() == 1


async def test_second_run_chains_previous_assessment(db, engagement,
                                                     hermetic_assessments):
    sched = EngagementScheduler()
    first = await sched.fire(db, engagement, datetime(2026, 8, 17, 3, 0))
    first.status = "completed"  # done before the next cron slot fires
    db.commit()
    second = await sched.fire(db, engagement, datetime(2026, 8, 24, 3, 0))

    assert second is not None
    assert second.meta["scheduled"]["run_no"] == 2
    # The diff baseline for the recurring-audit FindingsDiff panel.
    assert second.meta["scheduled"]["previous_assessment_id"] == first.assessment_id
    assert engagement.run_count == 2


async def test_fire_skips_when_previous_run_still_active(db, engagement,
                                                         hermetic_assessments):
    sched = EngagementScheduler()
    first = await sched.fire(db, engagement, datetime(2026, 8, 17, 3, 0))
    first.status = "running"  # still going
    db.commit()

    result = await sched.fire(db, engagement, datetime(2026, 8, 24, 3, 0))

    # Never pile up: no new task, run counter untouched, schedule pushed on.
    assert result is None
    assert db.query(Task).count() == 1
    assert engagement.run_count == 1
    assert engagement.last_task_id == first.id
    assert engagement.next_run_at == datetime(2026, 8, 31, 3, 0)


async def test_fire_after_previous_completed_chains_no_assessment(db, engagement,
                                                                  hermetic_assessments):
    """A completed previous run is not 'active' — it only serves the chain."""
    sched = EngagementScheduler()
    first = await sched.fire(db, engagement, datetime(2026, 8, 17, 3, 0))
    first.status = "completed"
    db.commit()

    second = await sched.fire(db, engagement, datetime(2026, 8, 24, 3, 0))
    assert second is not None
    assert second.meta["scheduled"]["previous_assessment_id"] == first.assessment_id


def test_platform_kill_switch(db):
    sched = EngagementScheduler()
    assert sched._enabled(db) is True  # default: scheduler on

    db.add(PlatformSettings(key="scheduler_enabled", value="false"))
    db.commit()
    assert sched._enabled(db) is False

    db.query(PlatformSettings).filter(
        PlatformSettings.key == "scheduler_enabled").first().value = "true"
    db.commit()
    assert sched._enabled(db) is True
