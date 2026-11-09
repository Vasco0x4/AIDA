"""
E3 resilience tests — the regression net for the agent-pool reliability layer:

  - worker-pool claim atomicity (no task runs twice)
  - crash recovery: orphaned 'running' tasks requeue, WITH the resume flag when
    a checkpoint exists; planned parents stay put
  - checkpoint/resume mid-task (the conversation continues, not restarts)
  - token budget guard (over-budget → needs_review, usage accounted)
  - step budget guard (agent_max_steps cap → needs_review, exact step count)
  - live Kanban steering: operator comments added mid-run / while paused are
    injected into the agent's conversation on the next step
  - model fallback chain (primary down → next model serves mid-task)
  - per-target rate-limit window
  - prompt-injection quarantine of tool output
  - evidence hash chain (link, verify, tamper detection, legacy skip)

All hermetic: scripted LLMs, the isolated test Postgres, no network/container.
"""
from __future__ import annotations

import hashlib
import json
import time

import pytest

from models.ai_model_config import AIModelConfig
from models.artifact import Artifact
from models.assessment import Assessment
from models.platform_settings import PlatformSettings
from models.task import Task
from models.task_comment import TaskComment
from services.agent import runtime as runtime_mod
from services.agent import runner as runner_mod
from services.agent import agent_settings as agent_settings_mod
from services.agent.runner import AgentRunner
from services.agent.runtime import TaskRuntime, quarantine
from services.evidence_chain import GENESIS, extend_chain, verify_chain
from services.llm import LLMError
from services.task_service import TaskService


def _tc(name, args, id_="call_1"):
    return {"id": id_, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def _resp(tool_calls=None, content=None, usage=None):
    return {"content": content, "tool_calls": tool_calls,
            "usage": usage or {}, "raw": {}, "latency_ms": 1}


class FakeLLM:
    """Scripted client; records every conversation it is handed."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def chat(self, messages, **kw):
        self.calls.append(messages)
        if not self.script:
            raise AssertionError("FakeLLM script exhausted — unexpected extra model call")
        return self.script.pop(0)


class DeadLLM:
    """Simulates an unreachable/rate-limited provider."""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, **kw):
        self.calls += 1
        raise LLMError("primary provider down (simulated)")


def _seed_model(db, name="e2e-fake", default=True):
    row = AIModelConfig(name=name, provider="custom",
                        base_url="http://fake.local/v1", model=name,
                        api_key_encrypted="enc::fake", enabled=True,
                        is_default=default)
    db.add(row)
    db.commit()
    return row


def _task(db, assessment, **kw):
    return TaskService(db).create(
        title=kw.pop("title", "resilience task"),
        authorized_scope="127.0.0.1", target="http://127.0.0.1:8080",
        execution_target="container", status="queued", orchestrate=False,
        source="api", assessment_id=assessment.id, **kw)


@pytest.fixture()
def patched_runtime_sessions(monkeypatch, runtime_sessions):
    """Point the runtime's module-level SessionLocal at the test database."""
    monkeypatch.setattr(runtime_mod, "SessionLocal", runtime_sessions)
    return runtime_sessions


@pytest.fixture()
def patched_runner_sessions(monkeypatch, runtime_sessions):
    """Point the runner's module-level SessionLocal at the test database."""
    monkeypatch.setattr(runner_mod, "SessionLocal", runtime_sessions)
    return runtime_sessions


@pytest.fixture()
def agent_settings(monkeypatch, db, runtime_sessions):
    """Write agent_* settings rows visible to the code under test (its TTL
    cache is cleared around every write and after the test)."""
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


@pytest.fixture(autouse=True)
def _goal_mode_off(agent_settings):
    """Goal mode ships default-ON; these legacy scripts assume stop attempts
    are accepted as-is. Goal-mode behavior has its own module
    (tests/test_goal_mode.py)."""
    agent_settings("agent_goal_mode", "false")


# --- quarantine ---------------------------------------------------------------

def test_quarantine_wraps_and_sanitizes():
    """Tool output enters the conversation delimited as untrusted data, with
    control characters stripped (ANSI/escape-injection hardening)."""
    payload = {"stdout": "HTTP/1.1 200 OK\n\x1b[31mRED\x1b[0m",
               "nested": {"x": "a\x00b"}, "items": ["ok", "b\x07ad"]}
    out = quarantine(payload)
    assert out.startswith("<<<UNTRUSTED TARGET-CONTROLLED DATA")
    assert "<<<END UNTRUSTED DATA>>>" in out
    for ctrl in ("\x1b", "\x00", "\x07"):
        assert ctrl not in out
    assert "HTTP/1.1 200 OK" in out          # the evidence itself survives
    assert "a?b" not in out and "ab" in out  # control chars removed, not ?-escaped


# --- model fallback chain -----------------------------------------------------

async def test_model_fallback_mid_task(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Primary model dies on every call → the fallback takes over mid-task,
    the switch is logged as a step, and usage is accounted per model."""
    assessment = Assessment(name="res-fallback", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    primary = _seed_model(db, "e2e-primary")
    fallback = _seed_model(db, "e2e-fallback", default=False)
    agent_settings("model_fallback_chain", json.dumps([fallback.id]))

    dead, serving = DeadLLM(), FakeLLM([
        _resp(tool_calls=[_tc("status_update", {"summary": "fallback online"})],
              usage={"prompt_tokens": 100, "completion_tokens": 50,
                     "total_tokens": 150}),
        _resp(tool_calls=[_tc("finish", {"summary": "Done via fallback."})],
              usage={"prompt_tokens": 80, "completion_tokens": 40,
                     "total_tokens": 120}),
    ])

    from services.ai_model_service import AIModelService
    monkeypatch.setattr(
        AIModelService, "build_client",
        lambda self, cfg: dead if cfg.id == primary.id else serving)

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Done via fallback."
    assert dead.calls == 2                    # primary retried each turn, then skipped

    usage = (t.meta or {}).get("usage") or {}
    assert usage["total"] == 270
    assert usage["calls"] == 2
    assert usage["by_model"] == {"custom/e2e-fallback": {"calls": 2, "total": 270}}
    assert (t.meta or {}).get("model") == "e2e-fallback (custom/e2e-fallback)"

    kinds = [s.get("kind") for s in (t.meta or {}).get("log") or []]
    assert kinds.count("model_fallback") == 2  # one per failed turn


# --- token budget -------------------------------------------------------------

async def test_token_budget_stops_task(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """Over-budget run stops mid-task → needs_review with a clear summary;
    usage is persisted for the audit."""
    assessment = Assessment(name="res-budget", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    _seed_model(db)

    fake = FakeLLM([
        _resp(tool_calls=[_tc("status_update", {"summary": "working…"})],
              usage={"prompt_tokens": 150, "completion_tokens": 50,
                     "total_tokens": 200}),
        # Second turn pushes the run over the 500-token budget mid-task
        # (after a tool round → a checkpoint exists to resume from).
        _resp(tool_calls=[_tc("status_update", {"summary": "still working…"})],
              usage={"prompt_tokens": 400, "completion_tokens": 200,
                     "total_tokens": 600}),
    ])
    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake)

    task = _task(db, assessment, token_budget=500)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "needs_review"         # partial by definition
    assert "Token budget exhausted (800 / 500 tokens)" in (t.result_summary or "")
    assert ((t.meta or {}).get("usage") or {}).get("total") == 800
    # The conversation is checkpointed: re-queue CONTINUES it instead of
    # restarting the phase from scratch.
    assert (t.meta or {}).get("resume") is True
    assert (t.meta or {}).get("checkpoint", {}).get("messages")

    kinds = [s.get("kind") for s in (t.meta or {}).get("log") or []]
    assert "budget_stopped" in kinds


# --- step budget ----------------------------------------------------------------

async def test_step_cap_checkpoints_and_continues_after_raise(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """`agent_max_steps` is a live platform setting (was a hard-coded 24 that
    silently truncated real phases). The cap is a backstop, not the goal: a
    model that never calls finish() stops at the cap → needs_review with the
    conversation CHECKPOINTED; raising the cap and re-queueing the task
    CONTINUES the same conversation until finish()."""
    assessment = Assessment(name="res-steps", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    _seed_model(db)
    agent_settings("agent_max_steps", "2")

    fake = FakeLLM([
        _resp(tool_calls=[_tc("status_update", {"summary": "step one"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "step two"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "must never run"})]),
    ])
    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake)

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "needs_review"          # capped = partial, not "done"
    assert "step budget reached" in (t.result_summary or "")
    assert "after 2 steps" in (t.result_summary or "")
    assert (t.meta or {}).get("steps") == 2
    assert len(fake.calls) == 2                # no extra model call past the cap
    # The conversation survives for continuation.
    assert (t.meta or {}).get("resume") is True
    cp = (t.meta or {}).get("checkpoint") or {}
    assert cp.get("steps") == 2 and cp.get("messages")

    # Operator raises the cap and drags the card back to Queued.
    agent_settings("agent_max_steps", "4")
    t.status = "queued"
    db.commit()

    fake2 = FakeLLM([
        _resp(tool_calls=[_tc("status_update", {"summary": "resumed work"})]),
        _resp(tool_calls=[_tc("finish", {"summary": "Goal reached."})]),
    ])
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake2)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"                  # ran until finish()
    assert t.result_summary == "Goal reached."
    assert (t.meta or {}).get("steps") == 4    # global counter continued 2→4
    assert not (t.meta or {}).get("resume")    # checkpoint consumed
    assert not (t.meta or {}).get("checkpoint")
    # The second run really CONTINUED the conversation (tool history present
    # in the first model call of round two), not a fresh prime.
    assert any(m.get("role") == "tool" for m in fake2.calls[0])

    kinds = [s.get("kind") for s in (t.meta or {}).get("log") or []]
    assert "resume" in kinds


# --- model error resumability -------------------------------------------------

async def test_model_error_with_checkpoint_parks_resumable(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """The whole chain is down after retries: with a saved checkpoint the task
    parks in needs_review flagged resume (NOT failed) — a later re-queue
    continues the conversation once the provider recovers."""
    assessment = Assessment(name="res-llmerr", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    _seed_model(db)

    class HalfDeadLLM:
        """First call serves a turn (checkpoint gets saved); then the
        provider dies on every subsequent call."""
        def __init__(self):
            self.calls = 0
        async def chat(self, messages, **kw):
            self.calls += 1
            if self.calls == 1:
                return _resp(tool_calls=[_tc("status_update",
                                             {"summary": "step one"})])
            raise LLMError("provider down mid-task (simulated)")

    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client",
                        lambda self, cfg: HalfDeadLLM())

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "needs_review"
    assert "Model error" in (t.result_summary or "")
    assert "checkpoint kept" in (t.result_summary or "")
    assert (t.meta or {}).get("resume") is True
    assert (t.meta or {}).get("checkpoint", {}).get("messages")


# --- checkpoint / resume ------------------------------------------------------

async def test_crash_resume_continues_from_checkpoint(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """A task flagged resume+checkpoint (crash recovery) continues its saved
    conversation — no fresh system prompt, step counter carries over, and the
    checkpoint is dropped once the run concludes."""
    assessment = Assessment(name="res-resume", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    _seed_model(db)

    checkpoint = {
        "messages": [
            {"role": "system", "content": "resume-sys-marker"},
            {"role": "assistant", "content": "recon already done"},
            {"role": "user", "content": "continue"},
        ],
        "steps": 3,
    }
    task = _task(db, assessment, meta={"resume": True, "checkpoint": checkpoint})

    fake = FakeLLM([
        _resp(tool_calls=[_tc("finish", {"summary": "Resumed OK."})]),
    ])
    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake)

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Resumed OK."
    assert (t.meta or {}).get("steps") == 4    # 3 saved + this one

    # Continued the SAVED conversation, not a fresh one.
    assert fake.calls[0][0]["content"] == "resume-sys-marker"
    assert any(m.get("content") == "recon already done" for m in fake.calls[0])

    steps = {s.get("kind"): s for s in (t.meta or {}).get("log") or []}
    assert "resume" in steps and steps["resume"].get("from_step") == 3

    # Stale checkpoint dropped on conclusion.
    assert "checkpoint" not in (t.meta or {})
    assert "resume" not in (t.meta or {})


# --- worker pool: claim atomicity + recovery + rate limit ---------------------

def test_claim_is_atomic(db, patched_runner_sessions):
    """The UPDATE…RETURNING claim wins exactly once: a second claim of the same
    task loses, and the task row is 'running' afterwards."""
    assessment = Assessment(name="res-claim", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    task = _task(db, assessment)

    r = AgentRunner()
    assert r._claim(task.id) is True
    db.expire_all()
    assert db.get(Task, task.id).status == "running"
    assert r._claim(task.id) is False          # someone else won; leave it alone


def test_recover_orphans_flags_resume(db, patched_runner_sessions):
    """Startup recovery: a stuck leaf goes back to queued (resume-flagged when a
    checkpoint exists); a planned parent stays running for the scheduler."""
    assessment = Assessment(name="res-orphans", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    with_cp = _task(db, assessment, title="with cp",
                    meta={"checkpoint": {"messages": [{"role": "system",
                                                       "content": "x"}], "steps": 2}})
    no_cp = _task(db, assessment, title="no cp")
    parent = _task(db, assessment, title="parent",
                   meta={"planned": True})
    for t in (with_cp, no_cp, parent):
        t.status = "running"
    db.commit()

    AgentRunner()._recover_orphans()

    db.expire_all()
    w, n, p = (db.get(Task, i.id) for i in (with_cp, no_cp, parent))
    assert w.status == "queued" and (w.meta or {}).get("resume") is True
    assert n.status == "queued" and not (n.meta or {}).get("resume")
    assert p.status == "running"               # finalized by the scheduler


def test_target_rate_limit_window():
    """Two agents never start on the same target inside the interval."""
    r = AgentRunner()
    assert r._target_ready(None, 60) is True       # no target → no limit
    assert r._target_ready("http://t", 0) is True  # disabled → no limit
    r._target_last["http://t"] = time.monotonic()
    assert r._target_ready("http://t", 60) is False
    r._target_last["http://t"] = time.monotonic() - 61
    assert r._target_ready("http://t", 60) is True


# --- evidence hash chain ------------------------------------------------------

def test_evidence_chain_link_verify_tamper(db):
    assessment = Assessment(name="res-chain", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()

    def artifact(data: bytes, link: bool = True) -> Artifact:
        row = Artifact(assessment_id=assessment.id, kind="file",
                       filename=f"{data.decode()}.bin",
                       content_type="application/octet-stream",
                       size_bytes=len(data), data=data)
        db.add(row)
        db.commit()
        db.refresh(row)
        if link:
            extend_chain(db, row)
        return row

    a1 = artifact(b"alpha")
    a2 = artifact(b"beta")
    a3 = artifact(b"legacy", link=False)      # pre-chain artifact, NULL hashes

    # Chain shape: genesis → a1 → a2, linked by hashes of prev + bytes.
    assert a1.hash_prev == GENESIS
    assert a2.hash_prev == a1.hash_self
    assert a1.hash_self == hashlib.sha256(GENESIS.encode() + b"alpha").hexdigest()
    assert a3.hash_self is None

    res = verify_chain(db, assessment.id)
    assert res == {"ok": True, "chained": 2, "legacy": 1, "broken_at": None}

    # Tampering with stored bytes is detected at the modified artifact.
    a2.data = b"tampered"
    db.commit()
    res = verify_chain(db, assessment.id)
    assert res["ok"] is False and res["broken_at"] == a2.id


# --- live Kanban steering (operator comments) ------------------------------------

class SteeringLLM(FakeLLM):
    """On the 2nd chat call, an operator drops a comment on the board."""

    def __init__(self, script, on_second_call):
        super().__init__(script)
        self._hook = on_second_call

    async def chat(self, messages, **kw):
        if len(self.calls) == 1:
            self._hook()
        return await super().chat(messages, **kw)


async def test_mid_run_operator_comment_steers_agent(
        db, patched_runtime_sessions, monkeypatch):
    """The board is a live control surface: a comment added WHILE the agent
    runs is injected into the conversation on the next step."""
    assessment = Assessment(name="res-steer", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    _seed_model(db)

    def _operator_comment():
        db.add(TaskComment(task_id=task.id, author="operator",
                           body="Focus on the registrar portal login."))
        db.commit()

    fake = SteeringLLM([
        _resp(tool_calls=[_tc("status_update", {"summary": "step one"})]),
        _resp(tool_calls=[_tc("status_update", {"summary": "step two"})]),
        _resp(tool_calls=[_tc("finish", {"summary": "Steered."})]),
    ], on_second_call=_operator_comment)
    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake)

    task = _task(db, assessment)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    # The 3rd model call carried the fresh comment as an instruction block.
    steering = [m for m in fake.calls[2]
                if m.get("role") == "user"
                and "NEW OPERATOR COMMENTS" in (m.get("content") or "")]
    assert steering and "registrar portal" in steering[0]["content"]
    assert len(steering) == 1                      # injected exactly once
    kinds = [s.get("kind") for s in (t.meta or {}).get("log") or []]
    assert "comment" in kinds


async def test_comments_added_while_paused_inject_on_resume(
        db, patched_runtime_sessions, agent_settings, monkeypatch):
    """A comment left while the task sat capped/stopped is injected when the
    run resumes from its checkpoint — steering survives the pause."""
    assessment = Assessment(name="res-steer2", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    _seed_model(db)
    agent_settings("agent_max_steps", "1")

    fake1 = FakeLLM([
        _resp(tool_calls=[_tc("status_update", {"summary": "only step"})]),
    ])
    from services.ai_model_service import AIModelService
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake1)
    task = _task(db, assessment)
    await TaskRuntime(task.id).run()
    db.expire_all()
    assert db.get(Task, task.id).status == "needs_review"   # capped at 1 step

    db.add(TaskComment(task_id=task.id, author="operator",
                       body="Now pivot to DNS zone transfers."))
    db.commit()
    db.get(Task, task.id).status = "queued"
    db.commit()

    agent_settings("agent_max_steps", "2")
    fake2 = FakeLLM([
        _resp(tool_calls=[_tc("finish", {"summary": "Resumed with steering."})]),
    ])
    monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake2)
    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Resumed with steering."
    steering = [m for m in fake2.calls[0]
                if m.get("role") == "user"
                and "NEW OPERATOR COMMENTS" in (m.get("content") or "")]
    assert steering and "DNS zone transfers" in steering[0]["content"]
    kinds = [s.get("kind") for s in (t.meta or {}).get("log") or []]
    assert "resume" in kinds and "comment" in kinds
