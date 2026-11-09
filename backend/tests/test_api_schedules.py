"""
Scheduled Engagements API — /api/schedules.

CRUD + cron/model validation, next_run_at recomputation on update, run-now
(scheduler.fire stubbed — nothing actually fires), and the run-history view
keyed off meta.scheduled.engagement_id.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from models.scheduled_engagement import ScheduledEngagement
from models.task import Task


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from slowapi import Limiter
    import main as main_mod
    monkeypatch.setattr(main_mod.app.state, "limiter",
                        Limiter(key_func=lambda r: "test", storage_uri="memory://"))


@pytest.fixture()
def schedule(db):
    from services.scheduler import next_run
    row = ScheduledEngagement(name="weekly-web", cron="0 3 * * mon",
                              task_title="Weekly web audit", target="example.com",
                              authorized_scope="example.com", enabled=True,
                              next_run_at=next_run("0 3 * * mon",
                                                   datetime.utcnow()))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _body(**over):
    body = {"name": "nightly", "cron": "15 2 * * *", "task_title": "Nightly scan"}
    body.update(over)
    return body


# ------------------------------------------------------------------ list/get
def test_schedules_require_auth(client):
    assert client.get("/api/schedules").status_code == 401


def test_preview_has_five_utc_occurrences_and_creates_no_work(client, db, admin_headers):
    response = client.get('/api/schedules/preview', params={'cron': '0 3 * * *', 'timezone': 'Asia/Qyzylorda'}, headers=admin_headers)
    assert response.status_code == 200
    occurrences = response.json()['occurrences']
    assert len(occurrences) == 5
    assert all(item.endswith('+00:00') for item in occurrences)
    assert all(datetime.fromisoformat(item).hour == 22 for item in occurrences)
    assert occurrences == sorted(occurrences)
    assert db.query(Task).count() == 0
    assert db.query(ScheduledEngagement).count() == 0


@pytest.mark.parametrize('params', [
    {'cron': '* * * * * *'}, {'cron': '0 3 30 2 *'},
    {'cron': '0 3 * * *', 'timezone': 'Unknown/Timezone'},
])
def test_preview_rejects_invalid_schedule(client, admin_headers, params):
    assert client.get('/api/schedules/preview', params=params, headers=admin_headers).status_code == 400


def test_list_orders_enabled_first_then_name(client, db, admin_headers):
    db.add(ScheduledEngagement(name="zz-active", cron="0 1 * * *",
                               task_title="t", enabled=True))
    db.add(ScheduledEngagement(name="aa-disabled", cron="0 1 * * *",
                               task_title="t", enabled=False))
    db.add(ScheduledEngagement(name="mm-active", cron="0 1 * * *",
                               task_title="t", enabled=True))
    db.commit()
    r = client.get("/api/schedules", headers=admin_headers)
    assert [s["name"] for s in r.json()] == \
        ["mm-active", "zz-active", "aa-disabled"]


def test_get_schedule_with_last_task_status(client, db, admin_headers, schedule):
    t = Task(title="last run", status="done", source="schedule")
    db.add(t)
    db.commit()
    schedule.last_task_id = t.id
    db.commit()
    r = client.get(f"/api/schedules/{schedule.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["last_task_status"] == "done"

    schedule.last_task_id = 424242  # pointing at a deleted task
    db.commit()
    assert client.get(f"/api/schedules/{schedule.id}",
                      headers=admin_headers).json()["last_task_status"] == "deleted"


def test_get_schedule_404(client, admin_headers):
    assert client.get("/api/schedules/31",
                      headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ create
def test_create_schedule(client, db, admin_headers):
    r = client.post("/api/schedules", headers=admin_headers, json=_body(
        description="nightly recon", priority="high", token_budget=5000))
    assert r.status_code == 201
    body = r.json()
    assert body["created_by"] == 1                # admin user id
    assert body["next_run_at"] is not None        # enabled → first fire computed
    row = db.query(ScheduledEngagement).one()
    assert row.run_count == 0
    assert row.orchestrate is True

    from services.scheduler import next_run
    assert body["next_run_at"].startswith(
        next_run("15 2 * * *", datetime.utcnow()).isoformat()[:10])


def test_create_schedule_disabled_has_no_next_run(client, db, admin_headers):
    r = client.post("/api/schedules", headers=admin_headers,
                    json=_body(enabled=False))
    assert r.status_code == 201
    assert r.json()["next_run_at"] is None


def test_create_schedule_bad_cron_400(client, admin_headers):
    for bad in ("nonsense", "* * * *", "0 0 0 0 0 0", ""):
        r = client.post("/api/schedules", headers=admin_headers,
                        json=_body(cron=bad))
        assert r.status_code == 400, bad
        assert "cron" in r.json()["detail"]


def test_create_schedule_unknown_model_400(client, admin_headers):
    r = client.post("/api/schedules", headers=admin_headers,
                    json=_body(model_config_id=99))
    assert r.status_code == 400
    assert "99" in r.json()["detail"]


def test_create_schedule_with_real_model(client, db, admin_headers):
    from models.ai_model_config import AIModelConfig
    m = AIModelConfig(name="sched-model", provider="custom",
                      base_url="http://x", model="m", enabled=True)
    db.add(m)
    db.commit()
    r = client.post("/api/schedules", headers=admin_headers,
                    json=_body(model_config_id=m.id))
    assert r.status_code == 201
    assert r.json()["model_config_id"] == m.id


def test_create_schedule_validation_422(client, admin_headers):
    assert client.post("/api/schedules", headers=admin_headers,
                       json=_body(name="")).status_code == 422
    assert client.post("/api/schedules", headers=admin_headers,
                       json={"cron": "0 1 * * *"}).status_code == 422


def test_create_schedule_requires_auditor(client, viewer_headers):
    assert client.post("/api/schedules", headers=viewer_headers,
                       json=_body()).status_code == 403


# ------------------------------------------------------------------ update
def test_update_schedule_fields(client, db, admin_headers, schedule):
    r = client.put(f"/api/schedules/{schedule.id}", headers=admin_headers,
                   json={"priority": "critical", "description": "retuned"})
    assert r.status_code == 200
    assert r.json()["priority"] == "critical"
    assert r.json()["description"] == "retuned"
    # shape unchanged → next_run_at untouched
    before = schedule.next_run_at
    assert r.json()["next_run_at"] == before.isoformat()


def test_update_schedule_recompute_on_cron_and_disable(client, db, admin_headers,
                                                       schedule):
    old_next = schedule.next_run_at
    r = client.put(f"/api/schedules/{schedule.id}", headers=admin_headers,
                   json={"cron": "0 5 * * fri"})
    assert r.status_code == 200
    assert r.json()["next_run_at"] != old_next.isoformat()

    r = client.put(f"/api/schedules/{schedule.id}", headers=admin_headers,
                   json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["next_run_at"] is None

    r = client.put(f"/api/schedules/{schedule.id}", headers=admin_headers,
                   json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["next_run_at"] is not None


def test_update_schedule_validation(client, admin_headers, schedule):
    assert client.put(f"/api/schedules/{schedule.id}", headers=admin_headers,
                      json={"cron": "bad"}).status_code == 400
    assert client.put(f"/api/schedules/{schedule.id}", headers=admin_headers,
                      json={"model_config_id": 71}).status_code == 400
    assert client.put("/api/schedules/77", headers=admin_headers,
                      json={"name": "x"}).status_code == 404


# ------------------------------------------------------------------ delete
def test_delete_schedule(client, db, admin_headers, schedule):
    assert client.delete(f"/api/schedules/{schedule.id}",
                         headers=admin_headers).status_code == 204
    assert db.query(ScheduledEngagement).count() == 0
    assert client.delete(f"/api/schedules/{schedule.id}",
                         headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ run now
def _stub_fire(monkeypatch, ret):
    """Patch EngagementScheduler.fire; when ret == 'create', build the Task on
    the request's own session (what the real fire() does)."""
    from services import scheduler as sched_mod
    calls = []

    async def _fake(self, db, eng, now):
        calls.append((eng.id, now))
        if ret != "create":
            return ret
        from services.task_service import TaskService
        return TaskService(db).create(
            title=eng.task_title, source="schedule", status="queued",
            meta={"scheduled": {"engagement_id": eng.id}})

    monkeypatch.setattr(type(sched_mod.scheduler), "fire", _fake)
    return calls


def test_run_now_returns_fired_task(client, db, admin_headers, monkeypatch,
                                    schedule):
    calls = _stub_fire(monkeypatch, "create")
    r = client.post(f"/api/schedules/{schedule.id}/run-now",
                    headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["source"] == "schedule"
    assert r.json()["meta"]["scheduled"]["engagement_id"] == schedule.id
    assert calls and calls[0][0] == schedule.id


def test_run_now_conflict_when_previous_run_active(client, db, admin_headers,
                                                   monkeypatch, schedule):
    _stub_fire(monkeypatch, None)
    r = client.post(f"/api/schedules/{schedule.id}/run-now",
                    headers=admin_headers)
    assert r.status_code == 409
    assert "still queued/running" in r.json()["detail"]


def test_run_now_404(client, admin_headers):
    assert client.post("/api/schedules/88/run-now",
                       headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ runs
def test_list_schedule_runs_filters_by_engagement(client, db, admin_headers,
                                                  schedule):
    db.add_all([
        Task(title="run 1", source="schedule",
             meta={"scheduled": {"engagement_id": schedule.id}}),
        Task(title="run 2", source="schedule",
             meta={"scheduled": {"engagement_id": schedule.id, "run_no": 2}}),
        Task(title="other engagement", source="schedule",
             meta={"scheduled": {"engagement_id": schedule.id + 5}}),
        Task(title="manual task", source="ui", meta={}),
    ])
    db.commit()
    r = client.get(f"/api/schedules/{schedule.id}/runs", headers=admin_headers)
    assert r.status_code == 200
    assert {t["title"] for t in r.json()} == {"run 1", "run 2"}


def test_list_schedule_runs_404(client, admin_headers):
    assert client.get("/api/schedules/89/runs",
                      headers=admin_headers).status_code == 404
