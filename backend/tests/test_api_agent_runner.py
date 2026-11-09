"""
Agent runner pool — services/agent/runner.py.

Scheduling policy (_candidates ordering, blocked siblings, planned-parent
finalize/resume), atomic claiming, per-target rate limiting, the settings-driven
gates in _next_job, crash recovery, and the global kill switch. The runner is
NEVER started here — no worker loops, no TaskRuntime.run() awaits; only the
pure scheduling/DB helpers run against the test database.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from models.platform_settings import PlatformSettings
from models.task import Task

from services.agent.runner import AgentRunner


@pytest.fixture(autouse=True)
def _runner_sessions(monkeypatch, runtime_sessions):
    """Both the runner and the settings cache open SessionLocal() directly."""
    import services.agent.runner as runner_mod
    import services.agent.agent_settings as settings_mod
    monkeypatch.setattr(runner_mod, "SessionLocal", runtime_sessions)
    monkeypatch.setattr(settings_mod, "SessionLocal", runtime_sessions)
    settings_mod.invalidate_settings_cache()
    yield
    settings_mod.invalidate_settings_cache()


@pytest.fixture()
def r():
    """A FRESH runner (never the module singleton, never started)."""
    return AgentRunner()


def _task(db, **kw):
    row = Task(
        title=kw.pop("title", "t"),
        status=kw.pop("status", "queued"),
        priority=kw.pop("priority", "medium"),
        target=kw.pop("target", None),
        orchestrate=kw.pop("orchestrate", False),
        order_index=kw.pop("order_index", 0),
        position=kw.pop("position", 0),
        parent_task_id=kw.pop("parent_task_id", None),
        meta=kw.pop("meta", {}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _planned_parent(db, status="running", **kw):
    kw.setdefault("title", "audit")
    return _task(db, orchestrate=True, status=status,
                 meta={"planned": True}, **kw)


def _setting(db, key, value):
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSettings(key=key, value=value))
    db.commit()


# ==================================================================== _candidates
def test_candidates_advances_only_next_child_in_order(db, r):
    parent = _planned_parent(db)
    _task(db, title="c1", parent_task_id=parent.id, order_index=0,
          position=0, status="done")
    c2 = _task(db, title="c2", parent_task_id=parent.id, order_index=1,
               position=1, target="example.com")
    _task(db, title="c3", parent_task_id=parent.id, order_index=2,
          position=2)

    assert r._candidates() == [("execute", c2.id, "example.com")]


def test_candidates_child_blocked_by_running_sibling(db, r):
    parent = _planned_parent(db)
    _task(db, title="c1", parent_task_id=parent.id, order_index=0,
          status="running")
    _task(db, title="c2", parent_task_id=parent.id, order_index=1)

    assert r._candidates() == []


def test_candidates_orders_children_by_priority(db, r):
    p1 = _planned_parent(db, title="audit-low")
    p2 = _planned_parent(db, title="audit-critical")
    late = _task(db, title="late", parent_task_id=p1.id, order_index=0,
                 position=0, priority="low")
    hot = _task(db, title="hot", parent_task_id=p2.id, order_index=0,
                position=0, priority="critical")

    kinds = r._candidates()
    assert kinds[0] == ("execute", hot.id, None)
    assert kinds[1] == ("execute", late.id, None)


def test_candidates_finalizes_planned_parent_when_children_terminal(db, r):
    parent = _planned_parent(db)
    _task(db, title="c1", parent_task_id=parent.id, order_index=0,
          status="done")
    _task(db, title="c2", parent_task_id=parent.id, order_index=1,
          status="failed")

    assert r._candidates() == [("finalize", parent.id, None)]


def test_candidates_finalizes_planned_parent_with_no_children(db, r):
    parent = _planned_parent(db)
    assert r._candidates() == [("finalize", parent.id, None)]


def test_candidates_waits_while_child_still_active(db, r):
    parent = _planned_parent(db)
    _task(db, title="c1", parent_task_id=parent.id, order_index=0,
          status="running")

    assert r._candidates() == []


def test_candidates_children_advance_before_new_audits(db, r):
    parent = _planned_parent(db)
    _task(db, title="c1", parent_task_id=parent.id, order_index=0,
          status="done")
    c2 = _task(db, title="c2", parent_task_id=parent.id, order_index=1,
               position=1)
    fresh = _task(db, title="new audit", orchestrate=True)

    assert r._candidates() == [("execute", c2.id, None),
                               ("plan", fresh.id, None)]


def test_candidates_plans_new_orchestrate_and_executes_plain(db, r):
    orch = _task(db, title="audit", orchestrate=True)
    plain = _task(db, title="one-shot", target="example.com")

    assert r._candidates() == [("plan", orch.id, None),
                               ("execute", plain.id, "example.com")]


def test_candidates_ignores_terminal_and_backlog(db, r):
    _task(db, title="done", status="done")
    _task(db, title="failed", status="failed")
    _task(db, title="review", status="needs_review")
    _task(db, title="backlog", status="backlog")

    assert r._candidates() == []


def test_candidates_resumes_planned_parent_dragged_back_to_queued(db, r):
    """A planned audit dragged to 'queued' must return to 'running', never be
    planned (or executed as a leaf) again."""
    parent = _planned_parent(db, status="queued")

    # Not planned again, not executed as a leaf: this tick only flips the row.
    assert r._candidates() == []
    db.expire_all()
    s = db.query(Task).filter(Task.id == parent.id).one()
    assert s.status == "running"
    # and the next tick now sees it as an orchestrating parent to finalize
    assert r._candidates() == [("finalize", parent.id, None)]


# ======================================================================== _claim
def test_claim_flips_queued_atomically(db, r):
    t = _task(db)
    assert r._claim(t.id) is True
    db.refresh(t)
    assert t.status == "running"
    assert t.started_at is not None


def test_claim_loses_race_for_running_task(db, r):
    t = _task(db, status="running")
    assert r._claim(t.id) is False


def test_claim_nonexistent(db, r):
    assert r._claim(424242) is False


# =================================================================== _target_ready
def test_target_ready_matrix(r):
    assert r._target_ready(None, 60) is True
    assert r._target_ready("t", 0) is True
    assert r._target_ready("fresh-target", 60) is True
    r._target_last["t"] = time.monotonic()
    assert r._target_ready("t", 60) is False
    r._target_last["t"] = time.monotonic() - 61
    assert r._target_ready("t", 60) is True


# ======================================================================= _enabled
def test_enabled_default_and_off(db, r):
    assert r._enabled() is True          # unset → default "true"
    _setting(db, "agent_runner_enabled", "false")
    from services.agent.agent_settings import invalidate_settings_cache
    invalidate_settings_cache()
    assert r._enabled() is False
    _setting(db, "agent_runner_enabled", "OFF")
    invalidate_settings_cache()
    assert r._enabled() is False


# ====================================================================== _next_job
def test_next_job_none_when_disabled(db, r):
    _setting(db, "agent_runner_enabled", "false")
    from services.agent.agent_settings import invalidate_settings_cache
    invalidate_settings_cache()
    _task(db)
    assert r._next_job() is None


def test_next_job_none_at_concurrency_cap(db, r):
    _task(db)
    _task(db, title="second")
    r._active[1] = object()          # only the count matters on this path
    r._active[2] = object()
    assert r._next_job() is None


def test_next_job_claims_execute_candidate(db, r):
    t = _task(db, target="example.com")
    job = r._next_job()
    assert job is not None
    task_id, awaitable = job
    assert task_id == t.id
    awaitable.close()                    # never actually run the agent
    db.refresh(t)
    assert t.status == "running"
    assert "example.com" in r._target_last


def test_next_job_skips_rate_limited_target(db, r):
    hot = _task(db, title="hot", target="hot.example.com")
    cold = _task(db, title="cold", target="cold.example.com",
                 position=1)
    r._target_last["hot.example.com"] = time.monotonic()   # just started

    task_id, awaitable = r._next_job()
    awaitable.close()
    assert task_id == cold.id            # hot skipped, cold claimed
    db.refresh(hot)
    db.refresh(cold)
    assert hot.status == "queued"
    assert cold.status == "running"


def test_next_job_plan_and_finalize_candidates(db, r):
    orch = _task(db, title="audit", orchestrate=True)
    task_id, awaitable = r._next_job()
    awaitable.close()
    assert task_id == orch.id
    db.refresh(orch)
    assert orch.status == "running"      # planning claims the task

    parent = _planned_parent(db)
    _task(db, title="c1", parent_task_id=parent.id, order_index=0,
          status="done")
    task_id, awaitable = r._next_job()
    awaitable.close()
    assert task_id == parent.id
    db.refresh(parent)
    assert parent.status == "running"    # finalize does NOT claim


def test_active_count(r):
    assert r.active_count == 0
    r._active[7] = object()
    assert r.active_count == 1


# ================================================================== kill switch
async def test_kill_all_cancels_job_and_fails_task(db, r):
    t = _task(db, status="running")
    job = asyncio.ensure_future(asyncio.sleep(3600))
    r._active[t.id] = job

    killed = await r.kill_all()
    assert killed == 1
    assert job.cancelled()
    db.refresh(t)
    assert t.status == "failed"
    assert "Killed by operator" in t.result_summary
    assert t.completed_at is not None


async def test_kill_all_with_nothing_active_sweeps_nothing(db, r):
    t = _task(db, status="running")      # running row but no tracked job
    assert await r.kill_all() == 0
    db.refresh(t)
    assert t.status == "running"         # untouched — sweep only covers _active


# ===================================================================== recovery
def test_recover_orphans_requeues_with_resume_flag(db, r):
    _task(db, status="running", meta={"checkpoint": {"step": 3}})
    _task(db, title="no-checkpoint", status="running", meta={})
    _task(db, title="plain-top", status="running", orchestrate=False)
    parent = _planned_parent(db)         # orchestrating parent stays running

    r._recover_orphans()

    s = db.query(Task).filter(Task.title == "t").one()          # leaf
    assert s.status == "queued"
    assert s.meta["resume"] is True
    assert s.started_at is None
    nc = db.query(Task).filter(Task.title == "no-checkpoint").one()
    assert nc.status == "queued"
    assert "resume" not in (nc.meta or {})
    plain = db.query(Task).filter(Task.title == "plain-top").one()
    assert plain.status == "queued"
    db.refresh(parent)
    assert parent.status == "running"


def test_recover_orphans_survives_db_error(monkeypatch, r):
    import services.agent.runner as runner_mod

    class _Boom:
        def query(self, *a, **kw):
            raise RuntimeError("db gone")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runner_mod, "SessionLocal", _Boom)
    r._recover_orphans()                 # must not raise


# ============================================================ error resilience
def test_claim_returns_false_on_db_error(monkeypatch, r):
    import services.agent.runner as runner_mod

    class _BoomSession:
        def execute(self, *a, **kw):
            raise RuntimeError("connection lost")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runner_mod, "SessionLocal", _BoomSession)
    assert r._claim(1) is False


async def test_kill_all_survives_sweep_error(monkeypatch, r):
    import services.agent.runner as runner_mod

    class _BoomSession:
        def execute(self, *a, **kw):
            raise RuntimeError("connection lost")

        def rollback(self):
            pass

        def close(self):
            pass

    job = asyncio.ensure_future(asyncio.sleep(60))
    r._active[9] = job
    monkeypatch.setattr(runner_mod, "SessionLocal", _BoomSession)
    assert await r.kill_all() == 1       # killed count comes from _active
    assert job.cancelled()


async def test_stop_cancels_tracked_jobs(db, r):
    job = asyncio.ensure_future(asyncio.sleep(3600))
    r._active[4] = job
    await r.stop()
    assert job.cancelled()
    assert r._stop.is_set()


# ======================================================== claim-race continues
def test_next_job_skips_unclaimable_candidates(db, r, monkeypatch):
    """A candidate that loses the claim race (row moved) is skipped and the
    pool tries the next one — synthetic candidate list, real _claim calls."""
    real = _task(db, target="example.com")
    monkeypatch.setattr(r, "_candidates", lambda: [
        ("execute", 424242, "gone.example.com"),   # already gone → claim fails
        ("execute", real.id, "example.com")])
    task_id, awaitable = r._next_job()
    awaitable.close()
    assert task_id == real.id

    orch = _task(db, title="audit", orchestrate=True)
    monkeypatch.setattr(r, "_candidates", lambda: [
        ("plan", 424243, None),                    # vanished parent
        ("plan", orch.id, None)])
    task_id, awaitable = r._next_job()
    awaitable.close()
    assert task_id == orch.id

    monkeypatch.setattr(r, "_candidates", lambda: [("execute", 424244, None)])
    assert r._next_job() is None                   # nothing claimable → idle
