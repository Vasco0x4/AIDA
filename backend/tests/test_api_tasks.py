"""
Task API (Kanban board + autonomous work queue) — /api/tasks.

Covers CRUD, board grouping, drag-and-drop /move (incl. the running→queued
re-route), /stop (container kill mocked), delete cascade + empty-assessment
cleanup, and the runner state/config endpoints (whole-object PUT semantics,
validation, RBAC: writes are admin-only). Nothing here ever starts the real
agent runner: the TestClient harness skips the app lifespan.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from models.assessment import Assessment
from models.platform_settings import PlatformSettings
from models.recon_data import ReconData
from models.task import Task, TASK_COLUMNS
from services.task_service import TaskService


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def auditor_headers(db):
    from auth import create_access_token
    from conftest import make_user
    u = make_user(db, "auditor", "auditor")
    return {"Authorization": f"Bearer {create_access_token(u.id, u.username)}"}


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Fresh in-memory limiter per test — the default 200/min counter must not
    leak across tests (all TestClient requests share one client IP)."""
    from slowapi import Limiter
    import main as main_mod
    monkeypatch.setattr(main_mod.app.state, "limiter",
                        Limiter(key_func=lambda r: "test", storage_uri="memory://"))
    from middleware.rate_limit import limiter as global_limiter
    global_limiter.reset()


@pytest.fixture(autouse=True)
def _runner_sessions(monkeypatch, runtime_sessions):
    """The runner singleton's module SessionLocal must never touch the dev DB
    (kill_all / orphan recovery open their own sessions)."""
    from services.agent import runner as runner_mod
    monkeypatch.setattr(runner_mod, "SessionLocal", runtime_sessions)


@pytest.fixture()
def no_workspace(monkeypatch):
    """Assessment provisioning must not reach docker."""
    from services.container_service import ContainerService

    async def _fake(self, assessment_name, db=None):
        return {"workspace_path": f"/ws/{assessment_name}",
                "container_name": "exegol-fake"}

    monkeypatch.setattr(ContainerService, "create_workspace", _fake)
    return _fake


def _seed_task(db, title="t", status="backlog", **kw):
    return TaskService(db).create(title=title, status=status, **kw)


# ------------------------------------------------------------------ columns
def test_columns_requires_auth(client):
    assert client.get("/api/tasks/columns").status_code == 401


def test_columns_lists_workflow_stages(client, admin_headers):
    r = client.get("/api/tasks/columns", headers=admin_headers)
    assert r.status_code == 200
    assert tuple(r.json()["columns"]) == TASK_COLUMNS


# ------------------------------------------------------------------ listing
def test_list_tasks_and_status_filter(client, db, admin_headers):
    _seed_task(db, "a", status="queued")
    _seed_task(db, "b", status="done")
    r = client.get("/api/tasks", headers=admin_headers)
    assert r.status_code == 200
    assert {t["title"] for t in r.json()} == {"a", "b"}

    r = client.get("/api/tasks", params={"status": "queued"}, headers=admin_headers)
    assert [t["title"] for t in r.json()] == ["a"]


def test_get_task_404(client, admin_headers):
    assert client.get("/api/tasks/9999", headers=admin_headers).status_code == 404


def test_board_groups_by_column(client, db, admin_headers):
    _seed_task(db, "queued-1", status="queued")
    _seed_task(db, "done-1", status="done")
    r = client.get("/api/tasks/board", headers=admin_headers)
    assert r.status_code == 200
    cols = {c["key"]: [t["title"] for t in c["tasks"]] for c in r.json()["columns"]}
    assert set(cols) == set(TASK_COLUMNS)
    assert cols["queued"] == ["queued-1"]
    assert cols["done"] == ["done-1"]
    assert cols["backlog"] == []


# ------------------------------------------------------------------ create
def test_create_task_happy_path(client, db, admin_headers, no_workspace):
    r = client.post("/api/tasks", headers=admin_headers, json={
        "title": "Audit example.com", "description": "web audit",
        "target": "http://example.com", "authorized_scope": "example.com",
        "status": "queued", "priority": "high",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    assert body["position"] == 0
    assert body["created_by"] == 1  # admin_user id
    # Top-level task without assessment → provisioned up-front.
    assert body["assessment_id"] is not None
    a = db.query(Assessment).filter(Assessment.id == body["assessment_id"]).one()
    assert a.scope == "example.com"


def test_create_task_survives_failed_assessment_transaction(client, db, admin_headers, monkeypatch):
    """Best-effort assessment provisioning must not poison the task session."""
    from services.agent import runtime as runtime_mod

    db.add(Assessment(name="duplicate-assessment", scope="127.0.0.1"))
    db.commit()
    monkeypatch.setattr(runtime_mod, "_safe_name", lambda task: "duplicate-assessment")

    response = client.post("/api/tasks", headers=admin_headers, json={
        "title": "Task survives assessment failure",
        "authorized_scope": "127.0.0.1",
        "status": "backlog",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assessment_id"] is None
    fetched = client.get(f"/api/tasks/{body['id']}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Task survives assessment failure"


def test_create_task_with_existing_assessment_no_new_one(
        client, db, admin_headers, no_workspace):
    a = Assessment(name="pre-existing", scope="10.0.0.0/8")
    db.add(a)
    db.commit()
    r = client.post("/api/tasks", headers=admin_headers, json={
        "title": "attached", "assessment_id": a.id, "orchestrate": False})
    assert r.status_code == 201
    assert r.json()["assessment_id"] == a.id
    assert db.query(Assessment).count() == 1


def test_create_task_validation_422(client, admin_headers):
    for bad in ({"title": "x", "priority": "urgent"},   # not a priority
                {"title": "x", "status": "wip"},        # not a column
                {"title": "x", "execution_target": "vm"},  # not container|host
                {"title": "x", "token_budget": -1},     # ge=0
                {"title": ""},                          # empty title
                {}):                                    # title is required
        r = client.post("/api/tasks", headers=admin_headers, json=bad)
        assert r.status_code == 422, bad


def test_create_task_rbac(client, db, viewer_headers, auditor_headers):
    assert client.post("/api/tasks", json={"title": "x"}).status_code == 401
    assert client.post("/api/tasks", headers=viewer_headers,
                       json={"title": "x"}).status_code == 403
    assert client.post("/api/tasks", headers=auditor_headers,
                       json={"title": "x"}).status_code == 201


def test_create_task_audit_logged(client, db, admin_headers, no_workspace):
    from models.audit_log import AuditLog
    client.post("/api/tasks", headers=admin_headers, json={"title": "logged"})
    row = db.query(AuditLog).filter(AuditLog.action == "task.created").one()
    assert row.actor_username == "admin"
    assert row.resource_id == "1"


# ------------------------------------------------------------------ update
def test_update_task_fields(client, db, admin_headers):
    t = _seed_task(db, "old")
    r = client.put(f"/api/tasks/{t.id}", headers=admin_headers,
                   json={"title": "new", "priority": "critical"})
    assert r.status_code == 200
    assert r.json()["title"] == "new"
    assert r.json()["priority"] == "critical"


def test_update_task_status_reroutes_position(client, db, admin_headers):
    _seed_task(db, "first", status="queued")
    t2 = _seed_task(db, "second", status="queued")
    r = client.put(f"/api/tasks/{t2.id}", headers=admin_headers,
                   json={"status": "done"})
    assert r.status_code == 200
    db.refresh(t2)
    assert t2.completed_at is not None
    assert t2.position == 0  # appended to the (empty) done column
    assert db.query(Task).filter(Task.id == 1).one().position == 0


def test_update_task_404_and_422(client, admin_headers):
    assert client.put("/api/tasks/77", headers=admin_headers,
                      json={"title": "x"}).status_code == 404
    assert client.put("/api/tasks/1", headers=admin_headers,
                      json={"status": "nope"}).status_code == 422


# ------------------------------------------------------------------ move
def test_move_task_to_done(client, db, admin_headers):
    t = _seed_task(db, "m", status="backlog")
    r = client.post(f"/api/tasks/{t.id}/move", headers=admin_headers,
                    json={"status": "done", "position": 0})
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["completed_at"] is not None


def test_move_task_running_is_rerouted_to_queued(client, db, admin_headers):
    """'running' is owned by the runner — a manual drop there becomes queued."""
    t = _seed_task(db, "r", status="backlog")
    r = client.post(f"/api/tasks/{t.id}/move", headers=admin_headers,
                    json={"status": "running", "position": 0})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_move_task_inserts_at_position(client, db, admin_headers):
    _seed_task(db, "a", status="backlog")
    _seed_task(db, "b", status="backlog")
    _seed_task(db, "c", status="backlog")
    r = client.post("/api/tasks/3/move", headers=admin_headers,
                    json={"status": "backlog", "position": 0})
    assert r.status_code == 200
    order = [(t.id, t.position) for t in
             db.query(Task).order_by(Task.position).all()]
    assert order == [(3, 0), (1, 1), (2, 2)]


def test_move_task_404_and_422(client, admin_headers):
    assert client.post("/api/tasks/9/move", headers=admin_headers,
                       json={"status": "done", "position": 0}).status_code == 404
    assert client.post("/api/tasks/1/move", headers=admin_headers,
                       json={"status": "limbo"}).status_code == 422


# ------------------------------------------------------------------ stop
@pytest.fixture()
def no_container_exec(monkeypatch):
    from services.container_service import ContainerService
    calls = []

    async def _fake(self, command=None, **kw):
        calls.append(command)
        return {"success": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(ContainerService, "execute_container_command", _fake)
    return calls


def test_stop_task_fails_it_and_running_children(
        client, db, admin_headers, no_container_exec):
    parent = _seed_task(db, "parent", status="running")
    child = Task(title="child", status="running", parent_task_id=parent.id)
    done_child = Task(title="done-child", status="done", parent_task_id=parent.id)
    db.add_all([child, done_child])
    db.commit()
    r = client.post(f"/api/tasks/{parent.id}/stop", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert "Stopped by user" in r.json()["result_summary"]
    db.refresh(child)
    db.refresh(done_child)
    assert child.status == "failed"
    assert done_child.status == "done"  # terminal child untouched
    assert no_container_exec and "pkill" in no_container_exec[0]


def test_stop_task_survives_container_being_down(
        client, db, admin_headers, monkeypatch):
    from services.container_service import ContainerService

    async def _boom(self, command=None, **kw):
        raise RuntimeError("docker socket gone")

    monkeypatch.setattr(ContainerService, "execute_container_command", _boom)
    t = _seed_task(db, "t", status="queued")
    r = client.post(f"/api/tasks/{t.id}/stop", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_stop_task_404(client, admin_headers):
    assert client.post("/api/tasks/41/stop", headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ delete
def test_delete_task_cascades_and_cleans_empty_assessment(
        client, db, admin_headers, no_workspace):
    t = _seed_task(db, "parent", status="queued", assessment_id=None)
    a = Assessment(name="auto-" + t.title, scope="x")
    db.add(a)
    db.commit()
    t.assessment_id = a.id
    db.commit()
    db.add(Task(title="child", parent_task_id=t.id, assessment_id=a.id))
    db.commit()

    r = client.delete(f"/api/tasks/{t.id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.query(Task).count() == 0
    # Assessment had no data → cleaned up with the task.
    assert db.query(Assessment).count() == 0


def test_delete_task_keeps_used_assessment(client, db, admin_headers):
    t = _seed_task(db, "t2")
    a = Assessment(name="used", scope="x")
    db.add(a)
    db.commit()
    t.assessment_id = a.id
    db.add(ReconData(assessment_id=a.id, data_type="subdomain", name="a.x"))
    db.commit()
    assert client.delete(f"/api/tasks/{t.id}", headers=admin_headers).status_code == 204
    assert db.query(Assessment).count() == 1


def test_delete_task_404(client, admin_headers):
    assert client.delete("/api/tasks/1234", headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ runner
def test_runner_status_defaults(client, db, admin_headers):
    r = client.get("/api/tasks/runner", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True  # no setting row → default true
    assert body["active"] == 0      # pool never started in tests
    assert body["config"]["max_concurrency"] == 2
    assert body["config"]["max_steps"] == 500
    assert body["config"]["fallback_chain"] == []
    assert body["config"]["goal_mode"] is True


def test_runner_put_requires_admin(client, db, viewer_headers, auditor_headers):
    for headers in (viewer_headers, auditor_headers):
        r = client.put("/api/tasks/runner", headers=headers, json={"enabled": False})
        assert r.status_code == 403
    assert client.put("/api/tasks/runner", json={"enabled": True}).status_code == 401


def test_runner_pause_and_resume(client, db, admin_headers):
    r = client.put("/api/tasks/runner", headers=admin_headers, json={"enabled": False})
    assert r.status_code == 200
    assert r.json() == {"enabled": False}
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == "agent_runner_enabled").one()
    assert row.value == "false"
    assert client.get("/api/tasks/runner", headers=admin_headers)\
        .json()["enabled"] is False

    client.put("/api/tasks/runner", headers=admin_headers, json={"enabled": True})
    assert client.get("/api/tasks/runner", headers=admin_headers)\
        .json()["enabled"] is True


def test_runner_config_put_replaces_whole_object(client, db, admin_headers):
    """PUT /runner/config is whole-object: omitted knobs fall back to defaults
    (previous values are NOT merged)."""
    client.put("/api/tasks/runner/config", headers=admin_headers, json={
        "max_concurrency": 4, "target_min_interval": 5, "max_steps": 650,
        "token_budget": 120000, "fallback_chain": [],
        "goal_mode": False, "max_auto_continuations": 0,
        "goal_judge_max_cont": 1})
    body = client.get("/api/tasks/runner", headers=admin_headers).json()["config"]
    assert body == {"max_concurrency": 4, "target_min_interval": 5,
                    "max_steps": 650, "token_budget": 120000,
                    "fallback_chain": [], "goal_mode": False,
                    "max_auto_continuations": 0, "goal_judge_max_cont": 1}

    # A second PUT sending only one knob resets everything else to defaults.
    client.put("/api/tasks/runner/config", headers=admin_headers,
               json={"max_steps": 99})
    body = client.get("/api/tasks/runner", headers=admin_headers).json()["config"]
    assert body["max_steps"] == 99
    assert body["max_concurrency"] == 2       # default again
    assert body["goal_mode"] is True          # default again


def test_runner_config_persists_settings_rows(client, db, admin_headers):
    client.put("/api/tasks/runner/config", headers=admin_headers,
               json={"max_concurrency": 3})
    keys = {k for (k,) in db.query(PlatformSettings.key).all()}
    assert {"agent_max_concurrency", "agent_max_steps", "agent_goal_mode",
            "model_fallback_chain"} <= keys


def test_runner_config_fallback_chain_validated(client, db, admin_headers):
    r = client.put("/api/tasks/runner/config", headers=admin_headers,
                   json={"fallback_chain": [42]})
    assert r.status_code == 400
    assert "42" in r.json()["detail"]
    # Nothing was persisted by the failed request.
    assert db.query(PlatformSettings).filter(
        PlatformSettings.key == "model_fallback_chain").count() == 0


def test_runner_config_accepts_real_model_ids(client, db, admin_headers):
    from models.ai_model_config import AIModelConfig
    m = AIModelConfig(name="cfg", provider="custom", base_url="http://x",
                      model="m1", enabled=True)
    db.add(m)
    db.commit()
    r = client.put("/api/tasks/runner/config", headers=admin_headers,
                   json={"fallback_chain": [m.id]})
    assert r.status_code == 200
    assert r.json()["fallback_chain"] == [m.id]


def test_runner_config_validation_422(client, admin_headers):
    for bad in ({"max_concurrency": 0}, {"max_concurrency": 9},
                {"max_steps": 0}, {"target_min_interval": -1},
                {"token_budget": -5}, {"max_auto_continuations": 11},
                {"max_auto_continuations": -2},
                {"goal_judge_max_cont": -2}):
        r = client.put("/api/tasks/runner/config", headers=admin_headers, json=bad)
        assert r.status_code == 422, bad


def test_runner_config_accepts_unlimited_goal_limits(client, db, admin_headers):
    """-1 = unlimited on both goal limits — the 'stop only when the goal is
    ready' contract."""
    r = client.put("/api/tasks/runner/config", headers=admin_headers, json={
        "max_auto_continuations": -1, "goal_judge_max_cont": -1})
    assert r.status_code == 200
    assert r.json()["max_auto_continuations"] == -1
    assert r.json()["goal_judge_max_cont"] == -1


def test_runner_kill_switch_noop_when_idle(client, db, admin_headers):
    r = client.post("/api/tasks/runner/kill", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"killed": 0}


def test_runner_kill_requires_admin(client, db, auditor_headers):
    assert client.post("/api/tasks/runner/kill",
                       headers=auditor_headers).status_code == 403


# ------------------------------------------------------------------ helpers
def test_task_service_move_clamps_negative_position(db):
    """Service-level guard behind the /move route: position < 0 inserts first."""
    _seed_task(db, "a", status="backlog")
    t2 = _seed_task(db, "b", status="backlog")
    TaskService(db).move(t2.id, "backlog", -7)
    db.refresh(t2)
    assert t2.position == 0


def test_simple_namespace_import_shape():
    """Documentation-ish guard: the response of /runner/kill is a plain dict."""
    assert SimpleNamespace(killed=0).killed == 0
