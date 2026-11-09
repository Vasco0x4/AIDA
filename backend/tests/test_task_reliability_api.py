"""API regressions for reliable, operator-controlled Kanban execution."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from models.task import TaskEvent
from services.task_service import TaskService


@pytest.fixture(autouse=True)
def _isolated_runner(monkeypatch, runtime_sessions):
    from services.agent import runner as runner_mod
    monkeypatch.setattr(runner_mod, "SessionLocal", runtime_sessions)


def _task(db, title="reliable", status="queued", **fields):
    return TaskService(db).create(title=title, status=status, **fields)


def test_task_response_exposes_version_and_dependencies_but_not_lease_token(
        client, db, admin_headers):
    prerequisite = _task(db, "prerequisite")
    dependent = _task(db, "dependent", dependency_ids=[prerequisite.id])

    response = client.get(f"/api/tasks/{dependent.id}", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["dependency_ids"] == [prerequisite.id]
    assert "lease_token" not in body


def test_stale_update_and_move_return_conflict_without_overwriting(
        client, db, admin_headers):
    row = _task(db)
    original_version = row.version

    update = client.put(
        f"/api/tasks/{row.id}", headers=admin_headers,
        json={"title": "stale", "expected_version": original_version + 10})
    move = client.post(
        f"/api/tasks/{row.id}/move", headers=admin_headers,
        json={"status": "done", "position": 0,
              "expected_version": original_version + 10})

    assert update.status_code == 409
    assert move.status_code == 409
    db.expire_all()
    current = TaskService(db).get(row.id)
    assert current.title == "reliable"
    assert current.status == "queued"
    assert current.version == original_version


def test_dependency_update_rejects_cycles_and_unknown_tasks(
        client, db, admin_headers):
    first = _task(db, "first")
    second = _task(db, "second")
    assert client.put(
        f"/api/tasks/{second.id}/dependencies", headers=admin_headers,
        json={"dependency_ids": [first.id]}).status_code == 200

    cycle = client.put(
        f"/api/tasks/{first.id}/dependencies", headers=admin_headers,
        json={"dependency_ids": [second.id]})
    unknown = client.put(
        f"/api/tasks/{first.id}/dependencies", headers=admin_headers,
        json={"dependency_ids": [99999]})

    assert cycle.status_code == 422
    assert unknown.status_code == 422


def test_events_are_returned_in_stable_order_with_a_bounded_limit(
        client, db, admin_headers):
    row = _task(db)
    TaskService(db).update(row.id, title="updated")

    response = client.get(
        f"/api/tasks/{row.id}/events", headers=admin_headers,
        params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["event_type"] == "updated"
    assert client.get(
        f"/api/tasks/{row.id}/events", headers=admin_headers,
        params={"limit": 0}).status_code == 422


def test_events_support_stable_cursor_pagination(client, db, admin_headers):
    row = _task(db)
    TaskService(db).update(row.id, title="second")
    TaskService(db).update(row.id, title="third")

    latest = client.get(
        f"/api/tasks/{row.id}/events", headers=admin_headers,
        params={"limit": 2})
    assert latest.status_code == 200
    latest_ids = [event["id"] for event in latest.json()]
    assert len(latest_ids) == 2

    previous = client.get(
        f"/api/tasks/{row.id}/events", headers=admin_headers,
        params={"limit": 2, "before_id": latest_ids[0]})
    assert previous.status_code == 200
    assert [event["event_type"] for event in previous.json()] == ["created"]
    assert max(event["id"] for event in previous.json()) < latest_ids[0]
    assert client.get(
        f"/api/tasks/{row.id}/events", headers=admin_headers,
        params={"before_id": 0}).status_code == 422


def test_manual_recovery_and_retry_requeue_with_operator_events(
        client, db, admin_headers):
    service = TaskService(db)
    row = _task(db)
    claimed = service.claim(row.id, owner="dead-worker")
    assert claimed is not None
    db.expire_all()
    stale = service.get(row.id)
    stale.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    recovered = client.post(f"/api/tasks/{row.id}/recover", headers=admin_headers)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "queued"
    assert recovered.json()["lease_owner"] is None

    db.expire_all()  # the API committed through its own session
    TaskService(db).update(row.id, status="failed", result_summary="boom")
    retried = client.post(f"/api/tasks/{row.id}/retry", headers=admin_headers)
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["completed_at"] is None
    event_types = [event.event_type for event in db.query(TaskEvent).filter(
        TaskEvent.task_id == row.id).order_by(TaskEvent.id)]
    assert "recovered" in event_types
    assert "retried" in event_types


def test_recovery_rejects_task_that_is_not_running(client, db, admin_headers):
    row = _task(db, status="backlog")
    response = client.post(f"/api/tasks/{row.id}/recover", headers=admin_headers)
    assert response.status_code == 409
