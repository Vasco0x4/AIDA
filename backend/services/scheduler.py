"""
Engagement scheduler — cron-triggered recurring audits (E4).

A ScheduledEngagement is a task template plus a cron expression (UTC). When
``next_run_at`` comes due — and the engagement's previous run is no longer
queued/running — the scheduler enqueues a Task exactly like a user would from
the Board, tagged with provenance in ``meta.scheduled`` (engagement id, run
number, previous assessment id) so recurring audits can be diffed
(findings_diff) and traced.

Deliberately boring: one asyncio loop, one DB session per tick, fire-and-forget
task creation (the E3 agent pool does the actual work). All times are naive
UTC, matching the rest of the platform.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from database import SessionLocal
from models.platform_settings import PlatformSettings
from models.scheduled_engagement import ScheduledEngagement
from models.task import Task
from services.task_service import TaskService
from utils.logger import get_logger

logger = get_logger(__name__)

TICK_SECONDS = 30.0

_ACTIVE_STATES = ("queued", "running")


def validate_cron(expr: str) -> bool:
    """True when ``expr`` is a valid standard 5-field cron expression."""
    try:
        if len((expr or "").split()) != 5:
            return False
        croniter((expr or "").strip()).get_next(datetime)
        return True
    except (ValueError, TypeError):
        return False


def validate_timezone(name: str) -> bool:
    try:
        ZoneInfo(name or "UTC")
        return True
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False


def next_run(cron: str, after: datetime, timezone_name: str = "UTC") -> datetime:
    """Next fire strictly after ``after``, returned as naive UTC.

    Cron is evaluated in the operator's timezone so local-wall-clock schedules
    behave correctly across DST transitions.
    """
    if (timezone_name or "UTC").upper() == "UTC":
        return croniter(cron.strip(), after).get_next(datetime)
    tz = ZoneInfo(timezone_name)
    aware = after.replace(tzinfo=dt_timezone.utc).astimezone(tz)
    local_next = croniter(cron.strip(), aware).get_next(datetime)
    return local_next.astimezone(dt_timezone.utc).replace(tzinfo=None)


class EngagementScheduler:
    def __init__(self) -> None:
        self._loop_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    # --- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop.clear()
        self._loop_task = asyncio.create_task(
            self._loop(), name="aida-engagement-scheduler")
        logger.info("Engagement scheduler started")

    async def stop(self) -> None:
        self._stop.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
            self._loop_task = None
        logger.info("Engagement scheduler stopped")

    def _enabled(self, db) -> bool:
        row = db.query(PlatformSettings).filter(
            PlatformSettings.key == "scheduler_enabled").first()
        return (row.value if row else "true").lower() in ("true", "1", "yes", "on")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("engagement scheduler tick failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=TICK_SECONDS + random.uniform(0, 5.0))
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        db = SessionLocal()
        try:
            if not self._enabled(db):
                return
            now = datetime.utcnow()
            due = db.query(ScheduledEngagement).filter(
                ScheduledEngagement.enabled.is_(True),
                ScheduledEngagement.next_run_at <= now,
            ).all()
            for eng in due:
                try:
                    await self.fire(db, eng, now, due_only=True)
                except Exception:
                    db.rollback()
                    logger.exception("scheduled engagement failed to fire",
                                     engagement_id=eng.id)
        finally:
            db.close()

    # --- firing ----------------------------------------------------------------

    async def fire(self, db, eng: ScheduledEngagement,
                   now: datetime, *, due_only: bool = False) -> Optional[Task]:
        """Enqueue one run of ``eng``. Returns the created Task, or None when
        skipped because the previous run is still active."""
        # Serialize due ticks and Run now across workers. Task creation and
        # engagement advancement commit together, closing the manual/cron race.
        eng = (db.query(ScheduledEngagement)
               .filter(ScheduledEngagement.id == eng.id)
               .populate_existing().with_for_update().first())
        if eng is None:
            db.rollback()
            return None
        # Recheck after taking the lock: another worker may have advanced the
        # cursor, or an operator may have disabled this schedule since the tick.
        if due_only and (not eng.enabled or eng.next_run_at is None or eng.next_run_at > now):
            db.commit()
            return None
        prev: Optional[Task] = None
        if eng.last_task_id:
            prev = db.query(Task).filter(Task.id == eng.last_task_id).first()
        if prev is not None and prev.status in _ACTIVE_STATES:
            # Never pile up: push the schedule forward and log the skip.
            logger.info(
                "scheduled engagement skipped — previous run still active",
                engagement_id=eng.id, last_task_id=prev.id, status=prev.status)
            eng.next_run_at = next_run(eng.cron, now, eng.timezone)
            db.commit()
            return None

        assessment_id = getattr(eng, "assessment_id", None)
        if assessment_id:
            active = (db.query(Task)
                      .filter(Task.assessment_id == assessment_id,
                              Task.status.in_(_ACTIVE_STATES))
                      .first())
            if active is not None:
                eng.next_run_at = next_run(eng.cron, now, eng.timezone)
                db.commit()
                logger.info("scan run skipped — Assessment already active",
                            engagement_id=eng.id, task_id=active.id)
                return None

        run_no = eng.run_count + 1
        # Recover cleanly if a process died after creating a run but before
        # persisting the schedule cursor.
        existing = (db.query(Task)
                    .filter(Task.source == "schedule",
                            Task.meta["scheduled"]["engagement_id"].as_string() == str(eng.id),
                            Task.meta["scheduled"]["run_no"].as_string() == str(run_no))
                    .first())
        if existing is not None:
            eng.last_task_id = existing.id
            eng.last_run_at = existing.created_at or now
            eng.run_count = run_no
            eng.next_run_at = next_run(eng.cron, now, eng.timezone)
            db.commit()
            return existing

        meta = {"scheduled": {"engagement_id": eng.id, "run_no": run_no},
                "scan_profile": eng.scan_profile,
                "rate_limit_seconds": eng.rate_limit_seconds}
        if getattr(eng, "scan_profile_id", None):
            from models.scan_profile import ScanProfile
            profile = db.get(ScanProfile, eng.scan_profile_id)
            if profile is not None:
                # Immutable policy snapshot: later template edits cannot change
                # what an already-created run was authorized to do.
                meta.update(scan_profile=profile.kind,
                            scan_profile_id=profile.id,
                            rate_limit_seconds=profile.rate_limit_seconds,
                            max_pages=profile.max_pages,
                            max_response_bytes=profile.max_response_bytes,
                            timeout_seconds=profile.timeout_seconds)
        if prev is not None and prev.assessment_id:
            # Chain recurring audits so findings can be diffed run-over-run.
            meta["scheduled"]["previous_assessment_id"] = prev.assessment_id
        if prev is not None:
            meta["scheduled"]["previous_task_id"] = prev.id

        task = TaskService(db).create(
            created_by=eng.created_by,
            title=eng.task_title,
            description=eng.description,
            target=eng.target,
            authorized_scope=eng.authorized_scope,
            priority=eng.priority,
            execution_target="container",
            model_config_id=eng.model_config_id,
            token_budget=eng.token_budget,
            status="queued",
            source="schedule",
            orchestrate=eng.orchestrate,
            assessment_id=assessment_id,
            meta=meta,
            _commit=False,
        )

        # Provision the Assessment up-front (mirrors POST /tasks) so findings
        # have a home immediately. Best-effort: the runtime re-creates it on
        # pickup when this fails (e.g. container down).
        try:
            if assessment_id:
                raise _AssessmentAlreadySelected()
            from schemas.assessment import AssessmentCreate
            from services.assessment_service import AssessmentService
            from services.agent.runtime import _safe_name
            assessment = await AssessmentService(db).create_assessment(
                AssessmentCreate(
                    name=_safe_name(task),
                    scope=task.authorized_scope,
                    objectives=task.description,
                    target_domains=[task.target] if task.target else None,
                ))
            task.assessment_id = assessment.id
            eng.assessment_id = assessment.id
        except _AssessmentAlreadySelected:
            pass
        except Exception as e:
            logger.warning("up-front assessment creation failed (will retry on run)",
                           task_id=task.id, error=str(e))

        eng.last_run_at = now
        eng.last_task_id = task.id
        eng.run_count += 1
        eng.next_run_at = next_run(eng.cron, now, eng.timezone)
        eng.last_error = None
        db.commit()
        db.refresh(task)

        try:
            from schemas.task import TaskResponse
            from websocket.events import event_task_created
            from websocket.manager import manager
            await manager.broadcast(event_task_created(
                TaskResponse.model_validate(task).model_dump(mode="json")))
        except Exception:
            pass

        logger.info("scheduled engagement fired", engagement_id=eng.id,
                    task_id=task.id, run_no=eng.run_count)
        return task


# Module-level singleton, wired in main.py lifespan.
scheduler = EngagementScheduler()


class _AssessmentAlreadySelected(Exception):
    """Internal control flow: selected Assessments need no provisioning."""
