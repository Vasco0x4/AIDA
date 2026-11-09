"""
Task planner — services/agent/planner.py.

Extends tests/test_planner_parse.py (which covers the common _parse_plan
shapes) with the remaining parse branches, the phase→model routing map
parser, and the full TaskPlanner.run() flow against the test DB: default-plan
decomposition when no model is configured (no LLM, no docker — workspace
creation stubbed), assessment failure handling, invalid-phase fallback, and
per-phase model routing.
"""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.platform_settings import PlatformSettings
from models.task import Task

from services.agent.planner import TaskPlanner, _DEFAULT_PLAN


@pytest.fixture(autouse=True)
def _planner_sessions(monkeypatch, runtime_sessions):
    import services.agent.planner as planner_mod
    monkeypatch.setattr(planner_mod, "SessionLocal", runtime_sessions)


@pytest.fixture(autouse=True)
def _workspace(monkeypatch):
    """AssessmentService.create_assessment touches docker (workspace folder) —
    stub the container boundary; the assessment row itself is still real."""
    from services.container_service import ContainerService

    async def _fake_ws(self, assessment_name, db=None):
        return {"workspace_path": f"/ws/{assessment_name}",
                "container_name": "exegol-test"}

    monkeypatch.setattr(ContainerService, "create_workspace", _fake_ws)


@pytest.fixture()
def audit(db):
    row = Task(title="Web audit of example.com", orchestrate=True,
               status="queued", target="example.com",
               authorized_scope="example.com",
               description="Full audit of the login flow")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ============================================================ _parse_plan gaps
def test_parse_plan_skips_non_dict_entries():
    plan = TaskPlanner._parse_plan(
        '{"subtasks": ["just a string", 42, {"title": "Real"}]}')
    assert plan == [{"phase": "recon", "title": "Real", "description": ""}]


def test_parse_plan_non_list_subtasks():
    assert TaskPlanner._parse_plan('{"subtasks": 5}') == []
    assert TaskPlanner._parse_plan('{"subtasks": "recon then exploit"}') == []


def test_parse_plan_invalid_json_between_braces():
    assert TaskPlanner._parse_plan("sure { this is } not json") == []
    assert TaskPlanner._parse_plan("}{") == []


def test_parse_plan_empty_subtasks():
    assert TaskPlanner._parse_plan('{"subtasks": []}') == []
    assert TaskPlanner._parse_plan("{}") == []


# ========================================================= _phase_model_map
def _map_setting(db, value):
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == "phase_model_map").first()
    if row:
        row.value = value
    else:
        db.add(PlatformSettings(key="phase_model_map", value=value))
    db.commit()


def test_phase_model_map_absent_or_empty(db):
    assert TaskPlanner._phase_model_map(db) == {}
    _map_setting(db, "")
    assert TaskPlanner._phase_model_map(db) == {}


def test_phase_model_map_invalid_json_or_non_dict(db):
    _map_setting(db, "not json {")
    assert TaskPlanner._phase_model_map(db) == {}
    _map_setting(db, '[1, 2, 3]')
    assert TaskPlanner._phase_model_map(db) == {}


def test_phase_model_map_filters_and_coerces(db):
    _map_setting(db, '{"recon": 3, "enumeration": "5", '
                     '"exploitation": 0, "reporting": "junk", '
                     '"post_exploitation": null}')
    assert TaskPlanner._phase_model_map(db) == {"recon": 3, "enumeration": 5}


# ==================================================================== run()
async def test_run_unknown_task_is_a_noop(db):
    await TaskPlanner(424242).run()
    assert db.query(Task).count() == 0


async def test_run_default_plan_without_model(db, runtime_sessions, audit):
    """No AIModelConfig → no LLM call: the audit is decomposed into the
    default 4-phase plan with ordered children and a planned parent."""
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        parent = s.query(Task).filter(Task.id == audit.id).one()
        assert parent.status == "running"
        assert parent.started_at is not None
        assert parent.meta["planned"] is True
        assert parent.meta["plan_size"] == 4
        assert "Planned 4 sub-tasks" in parent.result_summary

        kids = (s.query(Task).filter(Task.parent_task_id == audit.id)
                .order_by(Task.order_index).all())
        assert [k.phase for k in kids] == \
            ["recon", "enumeration", "exploitation", "reporting"]
        assert [k.order_index for k in kids] == [0, 1, 2, 3]
        assert all(k.status == "queued" for k in kids)
        assert all(k.orchestrate is False for k in kids)
        assert all(k.assessment_id == parent.assessment_id for k in kids)
        assert all(k.target == "example.com" for k in kids)
        assert all(k.model_config_id is None for k in kids)
        assert parent.meta["subtask_ids"] == [k.id for k in kids]

        assessment = s.query(Assessment).one()
        assert assessment.scope == "example.com"
        assert assessment.workspace_path == f"/ws/{assessment.name}"
    finally:
        s.close()


async def test_run_keeps_existing_assessment(db, runtime_sessions, audit,
                                             monkeypatch):
    from services.assessment_service import AssessmentService
    a = Assessment(name="pre-existing", scope="example.com")
    db.add(a)
    db.commit()
    audit.assessment_id = a.id
    db.commit()

    async def _must_not_create(self, data):
        raise AssertionError("assessment already set — must not re-create")

    monkeypatch.setattr(AssessmentService, "create_assessment",
                        _must_not_create)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        assert s.query(Assessment).count() == 1     # only the seeded one
        kids = s.query(Task).filter(Task.parent_task_id == audit.id).all()
        assert len(kids) == len(_DEFAULT_PLAN)
        assert all(k.assessment_id == a.id for k in kids)
    finally:
        s.close()


async def test_run_assessment_failure_fails_the_task(db, runtime_sessions,
                                                     audit, monkeypatch):
    from services.assessment_service import AssessmentService

    async def _boom(self, data):
        raise RuntimeError("docker daemon unreachable")

    monkeypatch.setattr(AssessmentService, "create_assessment", _boom)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        parent = s.query(Task).filter(Task.id == audit.id).one()
        assert parent.status == "failed"
        assert "Planner could not create assessment" in parent.result_summary
        assert "docker daemon unreachable" in parent.result_summary
        # no half-planned children were created
        assert s.query(Task).filter(Task.parent_task_id == audit.id).count() == 0
    finally:
        s.close()


async def test_run_maps_unknown_phases_to_recon(db, runtime_sessions, audit,
                                                monkeypatch):
    async def _custom(self, db, task):
        return [{"phase": "bogus_phase", "title": "Weird"},
                {"phase": "post_exploitation", "title": "Post"}]

    monkeypatch.setattr(TaskPlanner, "_make_plan", _custom)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        kids = (s.query(Task).filter(Task.parent_task_id == audit.id)
                .order_by(Task.order_index).all())
        assert [k.phase for k in kids] == ["recon", "post_exploitation"]
    finally:
        s.close()


async def test_run_routes_phase_models(db, runtime_sessions, audit):
    from models.ai_model_config import AIModelConfig
    cheap = AIModelConfig(name="cheap-local", provider="custom",
                          base_url="http://x", model="m1", enabled=True)
    strong = AIModelConfig(name="strong", provider="custom",
                           base_url="http://x", model="m2", enabled=True)
    db.add_all([cheap, strong])
    db.commit()
    db.add(PlatformSettings(
        key="phase_model_map",
        value='{"recon": %d, "reporting": %d}' % (cheap.id, strong.id)))
    db.commit()
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        kids = (s.query(Task).filter(Task.parent_task_id == audit.id)
                .order_by(Task.order_index).all())
        models = {k.phase: k.model_config_id for k in kids}
        assert models["recon"] == cheap.id
        assert models["reporting"] == strong.id
        assert models["enumeration"] is None      # unmapped → parent's (None)
        assert models["exploitation"] is None
    finally:
        s.close()


async def test_run_crash_marks_task_failed(db, runtime_sessions, audit,
                                           monkeypatch):
    from services.agent import planner as planner_mod

    async def _boom(*a, **kw):
        raise RuntimeError("websocket exploded")

    monkeypatch.setattr(planner_mod.manager, "broadcast", _boom)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        parent = s.query(Task).filter(Task.id == audit.id).one()
        assert parent.status == "failed"
        assert "Planner error" in parent.result_summary
        assert "websocket exploded" in parent.result_summary
    finally:
        s.close()


# ================================================================= _make_plan
def _stub_llm(monkeypatch, chat):
    """An enabled model config exists, but the HTTP client is a stub — no
    network, no decryption."""
    from types import SimpleNamespace
    from services.ai_model_service import AIModelService
    from models.ai_model_config import AIModelConfig

    def _fake_build(self, row):
        return SimpleNamespace(chat=chat)

    monkeypatch.setattr(AIModelService, "build_client", _fake_build)
    return AIModelConfig


async def _seed_model(db):
    from models.ai_model_config import AIModelConfig
    cfg = AIModelConfig(name="planner-llm", provider="custom",
                        base_url="http://llm.internal", model="plan-v1",
                        api_key_encrypted="opaque", enabled=True)
    db.add(cfg)
    db.commit()
    return cfg


async def test_make_plan_uses_model_plan(db, runtime_sessions, audit,
                                         monkeypatch):
    await _seed_model(db)

    async def chat(messages, **kw):
        return {"content": 'Thought hard.\n{"subtasks": ['
                '{"phase": "recon", "title": "Model recon step",'
                ' "description": "custom"}]}'}

    _stub_llm(monkeypatch, chat)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        kids = s.query(Task).filter(Task.parent_task_id == audit.id).all()
        assert [k.title for k in kids] == ["Model recon step"]
        assert kids[0].description == "custom"
    finally:
        s.close()


async def test_make_plan_falls_back_on_unparseable_reply(db, runtime_sessions,
                                                          audit, monkeypatch):
    await _seed_model(db)

    async def chat(messages, **kw):
        return {"content": "sorry, no JSON here {"}

    _stub_llm(monkeypatch, chat)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        kids = s.query(Task).filter(Task.parent_task_id == audit.id).all()
        assert [k.phase for k in kids] == \
            [step["phase"] for step in _DEFAULT_PLAN]
    finally:
        s.close()


async def test_make_plan_falls_back_on_llm_error(db, runtime_sessions, audit,
                                                 monkeypatch):
    from services.llm import LLMError
    await _seed_model(db)

    async def chat(messages, **kw):
        raise LLMError("provider 503")

    _stub_llm(monkeypatch, chat)
    await TaskPlanner(audit.id).run()

    s = runtime_sessions()
    try:
        kids = s.query(Task).filter(Task.parent_task_id == audit.id).all()
        assert len(kids) == len(_DEFAULT_PLAN)
    finally:
        s.close()
