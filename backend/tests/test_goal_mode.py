"""
Goal mode (Hermes "Ralph loop") — the agent runs until the task objective is
met, not until its first stop attempt:

  - an LLM judge reviews every stop candidate (plain text after acting, or an
    explicit finish()); CONTINUE → a steering message is injected and the run
    continues, DONE → the stop is accepted
  - judge failures fail OPEN (the stop is accepted — the judge is an
    accelerator, never a blocker)
  - consecutive CONTINUEs are capped (agent_goal_judge_max_cont) and the
    counter resets after real work
  - a capped run auto-continues from its checkpoint up to
    agent_max_auto_continuations times, then parks in needs_review
  - goal mode OFF keeps the legacy behavior byte-for-byte

All hermetic: scripted LLMs, the isolated test Postgres, no network/container.
Main-loop turns are told apart from judge/critic calls by the `tools` kwarg
(the judge and the critic chat WITHOUT tools).
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from models.ai_model_config import AIModelConfig
from models.assessment import Assessment
from models.platform_settings import PlatformSettings
from models.task import Task
from services.agent import agent_settings as agent_settings_mod
from services.agent import runtime as runtime_mod
from services.agent.runtime import TaskRuntime
from services.llm import LLMError
from services.task_service import TaskService


def _tc(name, args, id_="call_1"):
    return {"id": id_, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def _resp(tool_calls=None, content=None):
    return {"content": content, "tool_calls": tool_calls, "usage": {},
            "raw": {}, "latency_ms": 1}


def _judge(verdict, reason="objective not yet met"):
    return {"content": json.dumps({"verdict": verdict, "reason": reason}),
            "tool_calls": None, "usage": {}, "raw": {}, "latency_ms": 1}


class GoalFakeLLM:
    """Serves main-loop turns (chat WITH tools) from `script` and judge calls
    (chat WITHOUT tools — the critic uses the same shape) from `aux_script`.
    Any unexpected call raises, so a script can never silently mis-route."""

    def __init__(self, script, aux_script=()):
        self.script = list(script)
        self.aux = list(aux_script)
        self.main_calls = []      # list of message lists
        self.aux_calls = 0

    async def chat(self, messages, **kw):
        if kw.get("tools") is None:
            self.aux_calls += 1
            if not self.aux:
                raise AssertionError("unexpected judge/critic call — aux script empty")
            return self.aux.pop(0)
        self.main_calls.append(messages)
        if not self.script:
            raise AssertionError("unexpected main-loop call — script empty")
        return self.script.pop(0)


class JudgeDeadLLM(GoalFakeLLM):
    """The judge path itself raises (fail-open must accept the stop)."""

    async def chat(self, messages, **kw):
        if kw.get("tools") is None:
            self.aux_calls += 1
            raise LLMError("judge provider down (simulated)")
        return await super().chat(messages, **kw)


def _seed_model(db):
    row = AIModelConfig(name="goal-fake", provider="custom",
                        base_url="http://fake.local/v1", model="fake-1",
                        api_key_encrypted="enc::fake", enabled=True,
                        is_default=True)
    db.add(row)
    db.commit()
    return row


def _task(db, assessment, **kw):
    return TaskService(db).create(
        title=kw.pop("title", "goal-mode task"),
        authorized_scope="127.0.0.1", target="http://127.0.0.1:8080",
        execution_target="container", status="queued", orchestrate=False,
        source="api", assessment_id=assessment.id, **kw)


@pytest.fixture()
def patched_runtime_sessions(monkeypatch, runtime_sessions):
    monkeypatch.setattr(runtime_mod, "SessionLocal", runtime_sessions)
    return runtime_sessions


@pytest.fixture()
def agent_settings(monkeypatch, db, runtime_sessions):
    """Write agent_* settings visible to the code under test. Goal mode is ON
    by default (the key is absent after truncation → bool_setting default)."""
    monkeypatch.setattr(agent_settings_mod, "SessionLocal", runtime_sessions)

    def _set(key: str, value: str) -> None:
        row = db.query(PlatformSettings).filter(
            PlatformSettings.key == key).first()
        if row:
            row.value = value
        else:
            db.add(PlatformSettings(key=key, value=value, description="test"))
        db.commit()
        agent_settings_mod.invalidate_settings_cache()

    agent_settings_mod.invalidate_settings_cache()
    yield _set
    agent_settings_mod.invalidate_settings_cache()


def _install(monkeypatch, fake):
    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake)
    return fake


def _kinds(t):
    return [s.get("kind") for s in (t.meta or {}).get("log") or []]


def _assessment(db, name="goal-run"):
    row = Assessment(name=name, scope="127.0.0.1", status="active")
    db.add(row)
    db.commit()
    return row


# --- judge over plain-text stops ----------------------------------------------

async def test_judge_continue_then_done_plain_text(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Plain text after acting is only a PROPOSED stop: the judge says
    CONTINUE → a steering message is injected and the model keeps working;
    the next explicit finish() passes review and concludes the task."""
    assessment = _assessment(db)
    _seed_model(db)

    fake = _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "checked 1 endpoint"})]),
            _resp(content="Looks fine, I believe we are done here."),
            _resp(tool_calls=[_tc("finish", {"summary": "All 3 endpoints verified."})]),
        ],
        aux_script=[_judge("CONTINUE", "only 1 of 3 endpoints tested"),
                    _judge("DONE", "all endpoints verified")]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "All 3 endpoints verified."
    # The steering message reached the NEXT main-loop call.
    steering = [m for m in fake.main_calls[2]
                if m.get("role") == "user" and "GOAL REVIEW" in (m.get("content") or "")]
    assert steering and "objective" in steering[0]["content"].lower()
    assert "goal_continue" in _kinds(t)
    assert (t.meta or {}).get("goal_continues") == 1


async def test_finish_rejected_then_accepted(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """A premature finish() is rejected with a readable tool result (not
    quarantined — it is platform-generated); after real work the second
    finish() is accepted."""
    assessment = _assessment(db)
    _seed_model(db)

    fake = _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("finish", {"summary": "Stopping early."})]),
            _resp(tool_calls=[_tc("status_update", {"summary": "did the work"})]),
            _resp(tool_calls=[_tc("finish", {"summary": "Objective genuinely met."})]),
        ],
        aux_script=[_judge("CONTINUE", "nothing was actually tested"),
                    _judge("DONE")]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Objective genuinely met."
    # The rejection rode into the next turn as an UNQUARANTINED tool result.
    rejections = [m for m in fake.main_calls[1] if m.get("role") == "tool"
                  and "rejected_by_goal_review" in (m.get("content") or "")]
    assert rejections
    assert "UNTRUSTED" not in rejections[0]["content"]
    assert "goal_continue" in _kinds(t)


async def test_judge_error_fails_open(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Judge transport failure must never BLOCK a stop — fail open, log it."""
    assessment = _assessment(db)
    _seed_model(db)

    fake = _install(monkeypatch, JudgeDeadLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "worked"})]),
            _resp(content="Final report: everything checked."),
        ]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Final report: everything checked."
    assert "goal_judge_error" in _kinds(t)
    assert fake.aux_calls == 1


async def test_consecutive_continue_cap(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """agent_goal_judge_max_cont bounds CONSECUTIVE rejections: once spent, the
    next stop is accepted without even calling the judge."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_goal_judge_max_cont", "2")

    fake = _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "acted"})]),
            _resp(content="stop attempt one."),
            _resp(content="stop attempt two."),
            _resp(content="stop attempt three."),
        ],
        aux_script=[_judge("CONTINUE"), _judge("CONTINUE")]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "stop attempt three."
    assert fake.aux_calls == 2                    # third stop: no judge call
    assert (t.meta or {}).get("goal_continues") == 2


async def test_counter_resets_after_real_work(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Real tool work between stop attempts resets the consecutive counter —
    the nudge budget is per work streak, not per run."""
    assessment = _assessment(db)
    _seed_model(db)

    fake = _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "w1"})]),
            _resp(content="pause one."),
            _resp(tool_calls=[_tc("status_update", {"summary": "w2"})]),
            _resp(content="pause two."),
            _resp(tool_calls=[_tc("finish", {"summary": "Really done."})]),
        ],
        aux_script=[_judge("CONTINUE"), _judge("CONTINUE"), _judge("DONE")]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert fake.aux_calls == 3
    assert (t.meta or {}).get("goal_continues") == 1   # reset by work before DONE


# --- auto-continue past the step cap -------------------------------------------

async def test_auto_continue_on_cap(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """A capped run whose objective is unmet re-queues ITSELF (checkpoint
    resume, counter bumped); when the continuation budget is spent it finally
    parks in needs_review like before."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_max_steps", "2")
    agent_settings("agent_max_auto_continuations", "1")

    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "seg1 s1"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "seg1 s2"})]),
    ]))
    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "queued"                    # auto-continued, not parked
    assert (t.meta or {}).get("auto_continuations") == 1
    assert (t.meta or {}).get("resume") is True
    assert (t.meta or {}).get("checkpoint", {}).get("messages")
    assert "auto_continue" in _kinds(t)
    assert "auto-continuing" in (t.result_summary or "")

    # The runner picks the card up again → second segment, budget now spent.
    fake2 = _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "seg2 s1"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "seg2 s2"})]),
    ]))
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "needs_review"              # continuation budget spent
    assert "step budget reached" in (t.result_summary or "")
    assert fake2.main_calls                        # fresh window: 2 more steps ran
    assert len(fake2.main_calls) == 2


async def test_auto_continue_disabled(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """agent_max_auto_continuations=0 → legacy behavior: cap parks the task in
    needs_review immediately."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_max_steps", "2")
    agent_settings("agent_max_auto_continuations", "0")

    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "s1"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "s2"})]),
    ]))
    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "needs_review"
    assert "auto_continue" not in _kinds(t)
    assert not (t.meta or {}).get("auto_continuations")


# --- goal mode off: legacy behavior ---------------------------------------------

async def test_goal_mode_off_old_behavior(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Goal mode OFF → plain text after acting ends the run exactly as it
    always did, with zero judge calls."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_goal_mode", "false")

    fake = _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "acted"})]),
            _resp(content="Legacy final summary."),
        ]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Legacy final summary."
    assert fake.aux_calls == 0
    assert "goal_continue" not in _kinds(t)


# --- unlimited mode: the judge is the only stop authority --------------------------

async def test_unlimited_nudges_never_accept_a_stop(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """agent_goal_judge_max_cont=-1 → a stop attempt is NEVER accepted without
    the judge's DONE, no matter how many consecutive CONTINUEs pile up."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_goal_judge_max_cont", "-1")

    fake = _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "acted"})]),
            _resp(content="stop one."),
            _resp(content="stop two."),
            _resp(content="stop three."),
            _resp(tool_calls=[_tc("finish", {"summary": "Finally done."})]),
        ],
        aux_script=[_judge("CONTINUE"), _judge("CONTINUE"), _judge("CONTINUE"),
                    _judge("DONE")]))

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Finally done."
    # All THREE consecutive stops were judged (the old cap accepted the 3rd
    # unjudged), plus the finish verdict.
    assert fake.aux_calls == 4
    assert (t.meta or {}).get("goal_continues") == 3


async def test_unlimited_auto_continue_keeps_requeuing(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """agent_max_auto_continuations=-1 → every step-cap requeues the task with
    a fresh window; it never parks in needs_review for hitting the cap."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_max_steps", "2")
    agent_settings("agent_max_auto_continuations", "-1")

    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "s1"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "s2"})]),
    ]))
    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "queued"
    assert (t.meta or {}).get("auto_continuations") == 1
    assert "1/∞" in (t.result_summary or "")

    # Second segment: the default limit (2) would park here — unlimited requeues.
    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "s3"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "s4"})]),
    ]))
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "queued"                 # still going, not parked
    assert (t.meta or {}).get("auto_continuations") == 2
    assert "2/∞" in (t.result_summary or "")
    assert (t.meta or {}).get("steps") == 4     # global counter keeps climbing


# --- unlimited mode: platform gates are steered around, not fatal ------------------

async def test_infra_blocked_unlimited_requeues_with_steering(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Unlimited mode: a segment where scope/command-mode gates refused EVERY
    action does not terminally fail — it requeues with a [PLATFORM GATES]
    steering message injected into the checkpoint, so the next segment knows
    why nothing ran and adapts. Only the operator's Stop ends such a run."""
    assessment = Assessment(name="infra-unlim", scope="KZ SME program",
                            status="active")          # parses to NO targets
    db.add(assessment)
    db.commit()
    _seed_model(db)
    agent_settings("agent_max_steps", "1")
    agent_settings("agent_max_auto_continuations", "-1")

    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("run_shell",
                              {"command": "curl -s https://example.kz"})]),
    ]))
    task = TaskService(db).create(
        title="infra unlim", authorized_scope="KZ SME program", target=None,
        execution_target="container", status="queued", orchestrate=False,
        source="api", assessment_id=assessment.id)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "queued"                    # requeued, NOT failed
    meta = t.meta or {}
    assert meta.get("blocked_actions") == 1
    assert meta.get("executed_actions") == 0
    assert meta.get("auto_continuations") == 1
    assert meta.get("infra_blocked_continues") == 1
    assert "refused all 1 attempted actions" in (t.result_summary or "")
    assert "1/∞" in (t.result_summary or "")
    # The steering message rides inside the checkpoint for the next segment.
    msgs = meta.get("checkpoint", {}).get("messages") or []
    steer = [m for m in msgs if m.get("role") == "user"
             and "[PLATFORM GATES]" in (m.get("content") or "")]
    assert steer and "authorized scope" in steer[0]["content"]

    # Segment two: the FIRST thing the model sees is the steering note.
    fake2 = _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("finish", {"summary": "Adapted and done."})]),
    ], aux_script=[_judge("DONE")]))
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    seen = [m for m in fake2.main_calls[0]
            if m.get("role") == "user" and "[PLATFORM GATES]" in (m.get("content") or "")]
    assert seen


# --- the operator's hand beats every automatic path --------------------------------

async def test_operator_stop_during_final_steps_wins(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """A Stop/drag landing while the concluding steps run (critic/timeline)
    must NOT be overwritten by the conclusion — without the guard the
    auto-continue would flip the killed card back to 'queued' and the runner
    would resurrect it."""
    assessment = _assessment(db, "opstop")
    _seed_model(db)
    agent_settings("agent_max_steps", "1")
    agent_settings("agent_max_auto_continuations", "-1")

    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "acted"})]),
    ]))
    task = _task(db, assessment, title="opstop task")

    # The operator hits Stop exactly while TimelineService runs (i.e. after
    # the loop, before the conclusion writes): another session marks the card.
    from services.timeline_service import TimelineService

    def _stop_mid_conclude(self, assessment_id):
        s2 = runtime_mod.SessionLocal()
        try:
            row = s2.query(Task).filter(Task.id == task.id).one()
            row.status = "failed"
            row.result_summary = "⏹ Stopped by user."
            row.completed_at = datetime.utcnow()
            s2.commit()
        finally:
            s2.close()

    monkeypatch.setattr(TimelineService, "auto_generate", _stop_mid_conclude)

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "failed"                    # the operator's verdict
    assert t.result_summary == "⏹ Stopped by user."
    assert "auto_continue" not in _kinds(t)        # never resurrected to queued
    assert not (t.meta or {}).get("auto_continuations")


# --- per-segment step window -----------------------------------------------------

async def test_step_window_is_per_segment(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Each run segment gets a FRESH max_steps window (Hermes-style): a
    re-queued capped task runs another full window without anyone raising the
    cap, while `steps` keeps counting globally."""
    assessment = _assessment(db)
    _seed_model(db)
    agent_settings("agent_max_steps", "2")
    agent_settings("agent_max_auto_continuations", "0")

    _install(monkeypatch, GoalFakeLLM(script=[
        _resp(tool_calls=[_tc("status_update", {"summary": "s1"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "s2"})]),
    ]))
    task = _task(db, assessment)
    await TaskRuntime(task.id).run()
    db.expire_all()
    assert db.get(Task, task.id).status == "needs_review"

    # Operator drags the card back to Queued WITHOUT raising the cap.
    db.get(Task, task.id).status = "queued"
    db.commit()

    _install(monkeypatch, GoalFakeLLM(
        script=[
            _resp(tool_calls=[_tc("status_update", {"summary": "s3"})]),
            _resp(tool_calls=[_tc("finish", {"summary": "Window two finish."})]),
        ],
        aux_script=[_judge("DONE")]))
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Window two finish."
    assert (t.meta or {}).get("steps") == 4        # global counter: 2 + 2
