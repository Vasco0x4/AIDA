"""
Background agent runner — the work pool that makes the platform autonomous.

E3: this used to be a single-flight loop (one task at a time). It is now a
pool of asyncio workers (up to MAX_WORKERS) that claim work ATOMICALLY —
`UPDATE tasks SET status='running' WHERE id=? AND status='queued' RETURNING id`
— so N workers never double-run a task, and concurrency is a setting
(`agent_max_concurrency`), not a code change.

Scheduling policy (unchanged from the single-flight era, now per-candidate):
in-progress audits advance first (children strictly in order), then planned
parents get finalized, then new top-level tasks are planned/executed.

Reliability features:
- per-target rate limit (`agent_target_min_interval`): two agents never start
  hammering the same target within N seconds;
- global kill switch `kill_all()`: cancels every running agent and marks the
  tasks failed — the operator's big red button;
- crash recovery: on startup, tasks stuck 'running' go back to 'queued'; if a
  runtime checkpoint exists it is flagged for RESUME (not restart-from-zero).
"""
from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import text

from database import SessionLocal
from models.task import Task, TaskDependency
from services.task_service import TaskService
from services.agent.agent_settings import get_setting, int_setting
from services.agent.runtime import TaskRuntime
from services.agent.planner import TaskPlanner
from utils.logger import get_logger
from services.metrics import TASK_RETRIES, WORKER_ACTIVE, TASK_ATTEMPTS, TASK_DURATION

logger = get_logger(__name__)

POLL_INTERVAL = 5.0  # seconds
MAX_WORKERS = 8      # hard cap; effective concurrency is the setting below
LEASE_SECONDS = 60
STALE_RECOVERY_INTERVAL = 15.0
MAX_JOB_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0
RETRY_BACKOFF_MAX = 30.0

# Priority ordering for pickup.
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class AgentRunner:
    def __init__(self):
        self._workers: list[asyncio.Task] = []
        self._stop = asyncio.Event()
        self._owner_id = f"runner-{uuid4()}"
        # task_id → unique lease token; heartbeats fence off recovered work.
        self._leases: dict[int, str] = {}
        # task_id → asyncio.Task of the running job (kill switch targets these).
        self._active: dict[int, asyncio.Task] = {}
        # target → monotonic time the last agent started working on it.
        self._target_last: dict[str, float] = {}
        self._last_stale_recovery = 0.0

    # --- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        if self._workers and any(not w.done() for w in self._workers):
            return
        self._recover_orphans()
        self._stop.clear()
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"aida-agent-worker-{i}")
            for i in range(MAX_WORKERS)
        ]
        logger.info("Agent worker pool started", workers=MAX_WORKERS)

    async def stop(self) -> None:
        self._stop.set()
        jobs = list(self._active.values())
        for t in self._workers + jobs:
            t.cancel()
        if self._workers or jobs:
            await asyncio.gather(*self._workers, *jobs, return_exceptions=True)
        logger.info("Agent worker pool stopped")

    async def kill_all(self) -> int:
        """Global kill switch: cancel every running agent NOW and mark the
        tasks failed. Returns how many agents were killed."""
        ids = list(self._active.keys())
        jobs = list(self._active.values())
        for j in jobs:
            j.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        # Sweep anything the (cancelled) runtime didn't manage to close out.
        db = SessionLocal()
        try:
            for tid in ids:
                row = db.execute(text(
                    "UPDATE tasks SET status='failed', "
                    "result_summary=COALESCE(result_summary,'') || "
                    "'⏹ Killed by operator (global kill switch).', "
                    "completed_at=NOW() "
                    "WHERE id=:i AND status='running' RETURNING id"),
                    {"i": tid}).first()
                db.commit()
                if row is not None:
                    from websocket.events import event_task_updated
                    from websocket.manager import manager
                    t = db.query(Task).filter(Task.id == tid).first()
                    if t:
                        from schemas.task import TaskResponse
                        await manager.broadcast(event_task_updated(
                            tid, TaskResponse.model_validate(t).model_dump(mode="json")))
        except Exception:
            db.rollback()
            logger.exception("kill-switch sweep failed")
        finally:
            db.close()
        if ids:
            logger.warning("Global kill switch used", killed=len(ids))
        return len(ids)

    async def cancel(self, task_id: int) -> bool:
        """Cancel one in-process job without changing its durable status."""
        job = self._active.get(task_id)
        if job is None or job.done():
            return False
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
        return True

    # --- recovery ----------------------------------------------------------------

    def _recover_orphans(self) -> None:
        """On startup, reclaim tasks stuck 'running' from a previous process/crash:
        a leaf/child goes back to 'queued' — flagged for RESUME when a runtime
        checkpoint exists; a planned parent stays 'running' (the scheduler
        finalizes it). Without this an interrupted run blocks its audit."""
        db = SessionLocal()
        try:
            stuck = db.query(Task).filter(Task.status == "running").all()
            n = 0
            for t in stuck:
                # A process-local asyncio job cannot survive a restart. Fence its
                # old lease even when a planned parent remains in running state.
                t.lease_owner = None
                t.lease_token = None
                t.heartbeat_at = None
                t.lease_expires_at = None
                if t.parent_task_id is not None or not (t.meta or {}).get("planned"):
                    meta = dict(t.meta or {})
                    if meta.get("checkpoint"):
                        meta["resume"] = True
                        t.meta = meta
                    t.status = "queued"
                    t.started_at = None
                    n += 1
            if n:
                db.commit()
                logger.info("Recovered orphaned running tasks", count=n)
        except Exception:
            db.rollback()
            logger.exception("orphan recovery failed")
        finally:
            db.close()

    def _recover_stale_leases(self) -> int:
        """Recover dead workers while this process remains alive.

        Live leases and legacy rows without a lease are deliberately untouched;
        startup-only _recover_orphans retains the legacy crash-recovery policy.
        """
        db = SessionLocal()
        try:
            stale = db.query(Task).filter(
                Task.status == "running",
                Task.lease_expires_at.isnot(None),
                Task.lease_expires_at <= datetime.utcnow(),
            ).all()
            tokens = [(t.id, t.lease_token) for t in stale]
        except Exception:
            db.rollback()
            logger.exception("stale lease scan failed")
            return 0
        finally:
            db.close()

        recovered = 0
        for task_id, token in tokens:
            db = SessionLocal()
            try:
                if TaskService(db).recover_stale(task_id, lease_token=token):
                    recovered += 1
            except Exception:
                db.rollback()
                logger.exception("stale lease recovery failed", task_id=task_id)
            finally:
                db.close()
        return recovered

    # --- scheduling -----------------------------------------------------------

    _TERMINAL = {"done", "failed", "needs_review"}

    def _candidates(self) -> list[tuple[str, int, Optional[str]]]:
        """Ordered (kind, task_id, target) candidates:
          - ("execute", id, target)  run a leaf/child or a plain task's agent loop
          - ("plan", id, None)       decompose a top-level orchestrate task
          - ("finalize", id, None)   close a planned parent whose children finished
        Ordering: in-progress audits advance (children strictly in order) before
        new audits are planned.
        """
        db = SessionLocal()
        try:
            tasks = db.query(Task).all()
            now = datetime.utcnow()
            by_id = {t.id: t for t in tasks}
            blocked = {
                edge.task_id for edge in db.query(TaskDependency).all()
                if edge.depends_on_id not in by_id
                or by_id[edge.depends_on_id].status != "done"
            }
            by_parent: dict = {}
            for t in tasks:
                by_parent.setdefault(t.parent_task_id, []).append(t)

            def prio(t):
                return (_PRIORITY_RANK.get(t.priority, 2), t.order_index, t.position, t.id)

            def retry_ready(t) -> bool:
                if (t.meta or {}).get("paused"):
                    return False
                value = (t.meta or {}).get("retry_not_before")
                if not value:
                    return True
                try:
                    return datetime.fromisoformat(value) <= now
                except (TypeError, ValueError):
                    return True

            out: list[tuple[str, int, Optional[str]]] = []

            # 1) Eligible children: earlier-order siblings all terminal.
            eligible_children = []
            for parent_id, children in by_parent.items():
                if parent_id is None:
                    continue
                sib = sorted(children, key=lambda t: t.order_index)
                for c in sib:
                    if c.status != "queued" or not retry_ready(c):
                        continue
                    earlier_blocking = any(
                        s.order_index < c.order_index and s.status not in self._TERMINAL
                        for s in sib
                    )
                    if not earlier_blocking:
                        eligible_children.append(c)
                        break  # only the next-in-order child per parent
            for c in sorted(eligible_children, key=prio):
                out.append(("execute", c.id, c.target))

            # 2) Finalize planned parents whose children are all terminal
            #    (all() of an empty list is True → a parent whose children were
            #    all deleted still gets finalized rather than hanging forever).
            for t in tasks:
                if t.parent_task_id is None and (t.meta or {}).get("planned") \
                        and t.status == "running":
                    kids = by_parent.get(t.id, [])
                    if all(k.status in self._TERMINAL for k in kids):
                        out.append(("finalize", t.id, None))

            # 3) New top-level work: plan orchestrate tasks, run plain tasks.
            top_queued = sorted(
                (t for t in tasks if t.parent_task_id is None
                 and t.status == "queued" and retry_ready(t)),
                key=prio)
            for t in top_queued:
                planned = (t.meta or {}).get("planned")
                if t.orchestrate and not planned:
                    out.append(("plan", t.id, None))
                elif t.orchestrate and planned:
                    # An already-planned audit dragged back to "queued" — never
                    # run the orchestrator itself as a leaf agent; return it to
                    # the orchestrating (running) state.
                    self._resume_planned_parent(t.id)
                else:
                    out.append(("execute", t.id, t.target))
            return [item for item in out
                    if item[0] == "finalize" or item[1] not in blocked]
        finally:
            db.close()

    def _resume_planned_parent(self, task_id: int) -> None:
        """Return a planned audit parent to the orchestrating 'running' state."""
        db = SessionLocal()
        try:
            t = db.query(Task).filter(Task.id == task_id).first()
            if t:
                t.status = "running"
                db.commit()
        finally:
            db.close()

    def _claim(self, task_id: int, lease_seconds: int = LEASE_SECONDS) -> bool:
        """Atomically flip a queued task to running and persist its lease."""
        db = SessionLocal()
        try:
            row = TaskService(db).claim(
                task_id, owner=self._owner_id, lease_seconds=lease_seconds)
            if row is None:
                return False
            self._leases[task_id] = row.lease_token
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    async def _heartbeat_loop(self, task_id: int, *, interval: float = 20.0,
                              lease_seconds: int = LEASE_SECONDS) -> None:
        """Renew a claimed task until its job finishes or its lease is fenced."""
        while not self._stop.is_set():
            token = self._leases.get(task_id)
            if token is None:
                return
            db = SessionLocal()
            try:
                if not TaskService(db).heartbeat(
                        task_id, lease_token=token, lease_seconds=lease_seconds):
                    job = self._active.get(task_id)
                    if job is not None and not job.done():
                        logger.warning("Cancelling job after lease fencing", task_id=task_id)
                        job.cancel()
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Heartbeat failed; cancelling job", task_id=task_id)
                job = self._active.get(task_id)
                if job is not None and not job.done():
                    job.cancel()
                return
            finally:
                db.close()
            await asyncio.sleep(interval)

    def _retry_crashed_job(self, task_id: int, error: Exception) -> Optional[float]:
        """Requeue a crashed job, or fail it once its retry budget is spent."""
        db = SessionLocal()
        try:
            service = TaskService(db)
            row = service.get(task_id)
            if row is None or row.status != "running":
                return None
            meta = dict(row.meta or {})
            retries = int(meta.get("retry_count", 0))
            meta["last_error"] = str(error)
            row.lease_owner = None
            row.lease_token = None
            row.heartbeat_at = None
            row.lease_expires_at = None
            if retries >= MAX_JOB_RETRIES:
                service.update(
                    task_id, status="failed", meta=meta,
                    result_summary=f"Agent crashed after {retries} retries: {error}")
                return None
            meta["retry_count"] = retries + 1
            delay = min(RETRY_BACKOFF_BASE * (2 ** retries), RETRY_BACKOFF_MAX)
            # ISO UTC is portable across runner processes and inspectable by operators.
            meta["retry_not_before"] = (
                datetime.utcnow() + timedelta(seconds=delay)).isoformat()
            service.update(task_id, status="queued", meta=meta)
            TASK_RETRIES.labels(trigger="crash").inc()
            return delay
        except Exception:
            db.rollback()
            logger.exception("could not retry crashed job", task_id=task_id)
            return None
        finally:
            db.close()

    def _target_ready(self, target: Optional[str], interval: float) -> bool:
        if not target or interval <= 0:
            return True
        last = self._target_last.get(target)
        return last is None or (time.monotonic() - last) >= interval

    # --- workers --------------------------------------------------------------

    def _enabled(self) -> bool:
        return get_setting("agent_runner_enabled", "true").lower() in \
            ("true", "1", "yes", "on")

    def _next_job(self) -> Optional[tuple[int, object]]:
        """Claim the best available candidate for this worker.
        Returns (task_id, awaitable) or None when there is nothing to do."""
        if not self._enabled():
            return None
        if len(self._active) >= int_setting("agent_max_concurrency", 2):
            return None
        interval = int_setting("agent_target_min_interval", 60)
        for kind, task_id, target in self._candidates():
            if kind == "execute":
                if not self._target_ready(target, interval):
                    continue
                if not self._claim(task_id):
                    continue
                self._target_last[target] = time.monotonic()
                return task_id, TaskRuntime(task_id).run()
            if kind == "plan":
                if not self._claim(task_id):
                    continue
                return task_id, TaskPlanner(task_id).run()
            # finalize: idempotent (finalize_parent re-checks status), no claim
            return task_id, TaskRuntime(task_id).finalize_parent()
        return None

    async def _worker(self, idx: int) -> None:
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if idx == 0 and now - self._last_stale_recovery >= STALE_RECOVERY_INTERVAL:
                    self._last_stale_recovery = now
                    self._recover_stale_leases()
                job = self._next_job()
                if job is not None:
                    task_id, awaitable = job
                    logger.info("Agent worker picked up job", worker=idx,
                                task_id=task_id)
                    t = asyncio.create_task(awaitable, name=f"aida-agent-job-{task_id}")
                    self._active[task_id] = t
                    WORKER_ACTIVE.inc()
                    attempt_started = time.monotonic()
                    heartbeat = asyncio.create_task(
                        self._heartbeat_loop(task_id),
                        name=f"aida-agent-heartbeat-{task_id}")
                    retry_delay = None
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass  # kill switch / shutdown — status handled there
                    except Exception as exc:
                        logger.exception("agent job crashed", task_id=task_id)
                        retry_delay = self._retry_crashed_job(task_id, exc)
                    else:
                        retry_delay = None
                    finally:
                        heartbeat.cancel()
                        await asyncio.gather(heartbeat, return_exceptions=True)
                        self._active.pop(task_id, None)
                        self._leases.pop(task_id, None)
                        WORKER_ACTIVE.dec()
                        TASK_DURATION.observe(time.monotonic() - attempt_started)
                        db = SessionLocal()
                        try:
                            task = db.get(Task, task_id)
                            if task:
                                TASK_ATTEMPTS.labels(status=task.status).inc()
                        finally:
                            db.close()
                    if retry_delay is not None:
                        try:
                            await asyncio.wait_for(self._stop.wait(), timeout=retry_delay)
                        except asyncio.TimeoutError:
                            pass
                    continue  # immediately look for more work
            except Exception:
                logger.exception("agent worker loop error", worker=idx)
            # Idle wait (interruptible, jittered so workers don't stampede).
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=POLL_INTERVAL + random.uniform(0, 2.0))
            except asyncio.TimeoutError:
                pass

    @property
    def active_count(self) -> int:
        return len(self._active)


# Module-level singleton.
runner = AgentRunner()
