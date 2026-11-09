"""Regression coverage for durable, lease-based Kanban execution."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import asyncio
import threading
import time

import pytest

from models.task import Task
from services.task_service import TaskService
from services.agent.runner import AgentRunner


@pytest.fixture(autouse=True)
def _runner_sessions(monkeypatch, runtime_sessions):
    import services.agent.runner as runner_mod
    monkeypatch.setattr(runner_mod, "SessionLocal", runtime_sessions)


def _task(service: TaskService, title="work", status="queued", **fields) -> Task:
    return service.create(title=title, status=status, source="api",
                          authorized_scope="127.0.0.1", orchestrate=False, **fields)


def test_optimistic_version_rejects_stale_update(db):
    service = TaskService(db)
    row = _task(service)

    updated = service.update(row.id, title="first writer", expected_version=1)
    assert updated.version == 2

    with pytest.raises(ValueError, match="version"):
        service.update(row.id, title="stale writer", expected_version=1)
    db.expire_all()
    assert db.get(Task, row.id).title == "first writer"


def test_explicit_dependencies_gate_scheduling_until_done(db):
    service = TaskService(db)
    prerequisite = _task(service, "prerequisite")
    dependent = _task(service, "dependent", dependency_ids=[prerequisite.id])
    runner = AgentRunner()

    assert dependent.dependency_ids == [prerequisite.id]
    assert runner._candidates() == [("execute", prerequisite.id, None)]

    service.update(prerequisite.id, status="done")
    db.expire_all()
    assert ("execute", dependent.id, None) in runner._candidates()


def test_dependency_cycles_are_rejected(db):
    service = TaskService(db)
    first = _task(service, "first")
    second = _task(service, "second")
    service.set_dependencies(second.id, [first.id])

    with pytest.raises(ValueError, match="cycle"):
        service.set_dependencies(first.id, [second.id])
    with pytest.raises(ValueError, match="cycle"):
        service.set_dependencies(first.id, [first.id])


def test_concurrent_claim_has_one_winner_and_durable_lease(db, runtime_sessions):
    row = _task(TaskService(db))
    barrier = threading.Barrier(2)

    def claim(owner):
        session = runtime_sessions()
        try:
            barrier.wait(timeout=5)
            claimed = TaskService(session).claim(row.id, owner=owner, lease_seconds=30)
            return owner, claimed.lease_token if claimed else None
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))

    winners = [result for result in results if result[1]]
    assert len(winners) == 1
    db.expire_all()
    claimed = db.get(Task, row.id)
    assert claimed.status == "running"
    assert claimed.lease_owner == winners[0][0]
    assert claimed.assignee == winners[0][0]
    assert claimed.lease_token == winners[0][1]
    assert claimed.heartbeat_at is not None
    assert claimed.lease_expires_at is not None
    assert TaskService(db).claim(row.id, owner="late-worker") is None


def test_runner_claim_uses_durable_lease(db):
    row = _task(TaskService(db))
    runner = AgentRunner()

    assert runner._claim(row.id) is True
    db.expire_all()
    claimed = db.get(Task, row.id)
    assert claimed.lease_owner == runner._owner_id
    assert claimed.lease_token == runner._leases[row.id]


def test_heartbeat_protects_live_lease_and_expired_lease_recovers(db):
    service = TaskService(db)
    row = _task(service)
    claimed = service.claim(row.id, owner="worker", lease_seconds=30)
    runner = AgentRunner()

    assert service.heartbeat(row.id, lease_token=claimed.lease_token,
                             lease_seconds=60) is True
    assert service.heartbeat(row.id, lease_token="wrong-token") is False
    assert runner._recover_stale_leases() == 0

    # Simulate a dead worker without restarting the runner process.
    db.expire_all()
    stale = db.get(Task, row.id)
    stale.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    assert runner._recover_stale_leases() == 1
    db.expire_all()
    recovered = db.get(Task, row.id)
    assert recovered.status == "queued"
    assert recovered.lease_owner is None
    assert recovered.lease_token is None
    assert recovered.lease_expires_at is None


async def test_runner_heartbeat_loop_extends_active_lease(db):
    row = _task(TaskService(db))
    runner = AgentRunner()
    assert runner._claim(row.id, lease_seconds=1)

    heartbeat = asyncio.create_task(runner._heartbeat_loop(
        row.id, interval=0.01, lease_seconds=60))
    await asyncio.sleep(0.04)
    heartbeat.cancel()
    with pytest.raises(asyncio.CancelledError):
        await heartbeat

    db.expire_all()
    assert db.get(Task, row.id).lease_expires_at > (
        datetime.utcnow() + timedelta(seconds=30))


async def test_worker_heartbeat_keeps_long_job_lease_alive(db, monkeypatch):
    row = _task(TaskService(db))
    runner = AgentRunner()
    claimed = False
    observed = {}

    async def job():
        await asyncio.sleep(0.04)
        db.expire_all()
        current = db.get(Task, row.id)
        observed["heartbeat_at"] = current.heartbeat_at
        observed["lease_expires_at"] = current.lease_expires_at
        TaskService(db).update(row.id, status="done")

    def next_job():
        nonlocal claimed
        if claimed:
            return None
        claimed = True
        assert runner._claim(row.id, lease_seconds=1)
        return row.id, job()

    monkeypatch.setattr(runner, "_next_job", next_job)
    worker = asyncio.create_task(runner._worker(0))
    await asyncio.sleep(0.08)
    runner._stop.set()
    await asyncio.wait_for(worker, timeout=1)

    assert observed["lease_expires_at"] > datetime.utcnow() + timedelta(seconds=30)
    assert observed["heartbeat_at"] is not None
    assert runner.active_count == 0


async def test_worker_periodically_recovers_newly_stale_lease(db, monkeypatch):
    service = TaskService(db)
    row = _task(service)
    claimed = service.claim(row.id, owner="dead-worker", lease_seconds=60)
    assert claimed is not None
    runner = AgentRunner()

    import services.agent.runner as runner_mod
    monkeypatch.setattr(runner_mod, "POLL_INTERVAL", 0.005)
    monkeypatch.setattr(runner_mod, "STALE_RECOVERY_INTERVAL", 0.01, raising=False)
    monkeypatch.setattr(runner_mod.random, "uniform", lambda _a, _b: 0)
    monkeypatch.setattr(runner, "_next_job", lambda: None)

    worker = asyncio.create_task(runner._worker(0))
    await asyncio.sleep(0.015)
    db.expire_all()
    stale = db.get(Task, row.id)
    stale.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    await asyncio.sleep(0.04)
    runner._stop.set()
    await asyncio.wait_for(worker, timeout=1)

    db.expire_all()
    assert db.get(Task, row.id).status == "queued"


async def test_worker_retries_crashed_job_with_backoff(db, runtime_sessions, monkeypatch):
    service = TaskService(db)
    row = _task(service)
    runner = AgentRunner()
    attempts = []

    import services.agent.runner as runner_mod
    monkeypatch.setattr(runner_mod, "POLL_INTERVAL", 0.005)
    monkeypatch.setattr(runner_mod, "STALE_RECOVERY_INTERVAL", 3600)
    monkeypatch.setattr(runner_mod, "RETRY_BACKOFF_BASE", 0.01, raising=False)
    monkeypatch.setattr(runner_mod.random, "uniform", lambda _a, _b: 0)

    async def job():
        attempts.append(time.monotonic())
        if len(attempts) < 3:
            raise RuntimeError("transient crash")
        session = runtime_sessions()
        try:
            TaskService(session).update(row.id, status="done")
        finally:
            session.close()

    def next_job():
        db.expire_all()
        if db.get(Task, row.id).status != "queued":
            return None
        assert runner._claim(row.id)
        return row.id, job()

    monkeypatch.setattr(runner, "_next_job", next_job)
    worker = asyncio.create_task(runner._worker(0))
    await asyncio.sleep(0.15)
    runner._stop.set()
    await asyncio.wait_for(worker, timeout=1)

    assert len(attempts) == 3
    assert attempts[1] - attempts[0] >= 0.008
    assert attempts[2] - attempts[1] >= 0.016
    db.expire_all()
    completed = db.get(Task, row.id)
    assert completed.status == "done"
    assert completed.meta["retry_count"] == 2


def test_crashed_job_fails_after_retry_budget_and_clears_lease(db):
    service = TaskService(db)
    row = _task(service)
    claimed = service.claim(row.id, owner="worker")
    assert claimed is not None
    meta = dict(claimed.meta or {})
    meta["retry_count"] = 3
    service.update(row.id, meta=meta)

    assert AgentRunner()._retry_crashed_job(row.id, RuntimeError("permanent")) is None
    db.expire_all()
    failed = db.get(Task, row.id)
    assert failed.status == "failed"
    assert failed.meta["last_error"] == "permanent"
    assert failed.lease_token is None
    assert failed.completed_at is not None


def test_task_creation_records_durable_event(db):
    from models.task import TaskEvent

    row = _task(TaskService(db), title="evented")
    events = db.query(TaskEvent).filter(TaskEvent.task_id == row.id).all()
    assert len(events) == 1
    assert events[0].event_type == "created"
    assert events[0].payload["status"] == "queued"
    assert events[0].created_at is not None


def test_claim_records_durable_event(db):
    from models.task import TaskEvent

    service = TaskService(db)
    row = _task(service)
    claimed = service.claim(row.id, owner="worker-a", lease_seconds=30)
    assert claimed is not None
    event = db.query(TaskEvent).filter(
        TaskEvent.task_id == row.id, TaskEvent.event_type == "claimed").one()
    assert event.payload == {"owner": "worker-a", "lease_seconds": 30}


def test_manual_recovery_requeues_running_task_and_records_event(db):
    from models.task import TaskEvent

    service = TaskService(db)
    row = _task(service)
    claimed = service.claim(row.id, owner="stuck-worker")
    assert claimed is not None
    claimed_version = claimed.version

    recovered = service.recover(row.id, expected_version=claimed.version)
    assert recovered is not None
    assert recovered.status == "queued"
    assert recovered.lease_token is None
    assert recovered.version == claimed_version + 1
    event = db.query(TaskEvent).filter(
        TaskEvent.task_id == row.id, TaskEvent.event_type == "recovered").one()
    assert event.payload["manual"] is True


def test_retry_backoff_is_visible_to_every_worker(db):
    service = TaskService(db)
    row = _task(service)
    assert service.claim(row.id, owner="worker") is not None
    runner = AgentRunner()

    delay = runner._retry_crashed_job(row.id, RuntimeError("transient"))

    assert delay is not None
    db.expire_all()
    queued = db.get(Task, row.id)
    assert queued.status == "queued"
    assert datetime.fromisoformat(queued.meta["retry_not_before"]) > datetime.utcnow()
    assert runner._candidates() == []

    meta = dict(queued.meta)
    meta["retry_not_before"] = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    queued.meta = meta
    db.commit()
    db.expire_all()
    assert ("execute", row.id, None) in runner._candidates()


def test_startup_recovery_fences_process_local_leases(db):
    service = TaskService(db)
    row = _task(service)
    claimed = service.claim(row.id, owner="old-process")
    assert claimed is not None

    AgentRunner()._recover_orphans()

    db.expire_all()
    recovered = db.get(Task, row.id)
    assert recovered.status == "queued"
    assert recovered.lease_owner is None
    assert recovered.lease_token is None
    assert recovered.heartbeat_at is None
    assert recovered.lease_expires_at is None
