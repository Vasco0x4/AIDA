"""
End-to-end agent runtime test with a scripted (mock) LLM — no network, no
docker, no real model. This is the regression net for the agent loop itself:

  plan→act→observe cycle, tool execution against the DB, milestone persistence,
  the empty-response nudge path (reasoning models), finding verification
  (critic), and the final needs_review/done transition.

The assessment is inserted directly via the ORM (bypassing the workspace
creation that needs the container), so the whole run is hermetic and CI-safe.
"""

from __future__ import annotations

import json

import pytest

from models.assessment import Assessment
from models.ai_model_config import AIModelConfig
from models.card import Card
from models.task import Task
from services.agent import runtime as runtime_mod
from services.agent.runtime import TaskRuntime
from services.task_service import TaskService


def _tc(name, args, id_="call_1"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _resp(tool_calls=None, content=None):
    return {"content": content, "tool_calls": tool_calls, "usage": {}, "raw": {}, "latency_ms": 1}


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def chat(self, messages, **kw):
        self.calls.append(messages)
        if not self.script:
            raise AssertionError("FakeLLM script exhausted — runtime made an unexpected extra call")
        return self.script.pop(0)


@pytest.fixture()
def seed_model(db):
    """A default AIModelConfig row (build_client is patched, key value unused)."""
    row = AIModelConfig(
        name="e2e-fake",
        provider="custom",
        base_url="http://fake.local/v1",
        model="fake-1",
        api_key_encrypted="enc::fake",
        enabled=True,
        is_default=True,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def install_fake_llm(monkeypatch):
    def _install(script):
        fake = FakeLLM(script)
        from services.ai_model_service import AIModelService

        monkeypatch.setattr(AIModelService, "build_client", lambda self, cfg: fake)
        return fake

    return _install


@pytest.fixture()
def patched_runtime_sessions(monkeypatch, runtime_sessions):
    """Point the runtime's module-level SessionLocal at the test database."""
    monkeypatch.setattr(runtime_mod, "SessionLocal", runtime_sessions)
    return runtime_sessions


@pytest.fixture(autouse=True)
def _goal_mode_off(monkeypatch, db, runtime_sessions):
    """Goal mode is default-ON in production and would insert judge calls at
    every scripted stop below; pin it off so the legacy scripts stay hermetic.
    Goal-mode behavior has its own module (tests/test_goal_mode.py)."""
    from models.platform_settings import PlatformSettings
    from services.agent import agent_settings as agent_settings_mod

    monkeypatch.setattr(agent_settings_mod, "SessionLocal", runtime_sessions)
    row = db.query(PlatformSettings).filter(PlatformSettings.key == "agent_goal_mode").first()
    if row:
        row.value = "false"
    else:
        db.add(PlatformSettings(key="agent_goal_mode", value="false", description="test"))
    db.commit()
    agent_settings_mod.invalidate_settings_cache()
    yield
    agent_settings_mod.invalidate_settings_cache()


async def test_full_agent_cycle_to_needs_review(
    db, runtime_sessions, patched_runtime_sessions, seed_model, install_fake_llm
):
    assessment = Assessment(name="e2e-hermetic-a", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()

    task = TaskService(db).create(
        title="e2e agent run",
        authorized_scope="127.0.0.1",
        target="http://127.0.0.1:8080",
        execution_target="container",
        status="queued",
        orchestrate=False,
        source="api",
        assessment_id=assessment.id,
    )

    fake = install_fake_llm(
        [
            _resp(tool_calls=[_tc("status_update", {"summary": "Recon done: 3 endpoints found"})]),
            _resp(
                tool_calls=[
                    _tc(
                        "record_finding",
                        {
                            "title": "Reflected XSS in /search",
                            "severity": "HIGH",
                            "technical_analysis": "q parameter echoed without encoding",
                            "proof": "curl 'http://127.0.0.1:8080/search?q=<script>alert(1)</script>'",
                        },
                    )
                ]
            ),
            # Reasoning-model starvation: neither content nor tool calls → nudge.
            _resp(content="", tool_calls=None),
            _resp(tool_calls=[_tc("finish", {"summary": "One reflected XSS found and proven."})]),
            # Critic pass for the recorded finding.
            _resp(content='{"verdict":"confirmed","reason":"PoC reproduces the reflection"}'),
        ]
    )

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "needs_review"  # findings → human triage
    assert t.result_summary == "One reflected XSS found and proven."
    meta = t.meta or {}
    assert meta.get("findings") == 1
    assert meta.get("steps") >= 3

    milestones = [m.get("text", "") for m in (meta.get("milestones") or [])]
    assert any("Recon done" in m for m in milestones)

    card = db.query(Card).filter(Card.assessment_id == assessment.id).first()
    assert card is not None
    assert card.title == "Reflected XSS in /search"
    assert card.status == "confirmed"  # critic verdict applied
    assert "PoC reproduces" in (card.notes or "")

    # The nudge path ran: 4 loop calls + 1 critic call.
    assert len(fake.calls) == 5


async def test_agent_without_findings_ends_done(db, patched_runtime_sessions, seed_model, install_fake_llm):
    assessment = Assessment(name="e2e-hermetic-b", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    task = TaskService(db).create(
        title="e2e clean run",
        authorized_scope="127.0.0.1",
        execution_target="container",
        status="queued",
        orchestrate=False,
        source="api",
        assessment_id=assessment.id,
    )

    install_fake_llm(
        [
            _resp(tool_calls=[_tc("status_update", {"summary": "Nothing reachable"})]),
            _resp(tool_calls=[_tc("finish", {"summary": "No issues found."})]),
        ]
    )

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "No issues found."
    assert (t.meta or {}).get("findings") == 0


async def test_no_model_config_fails_task(db, patched_runtime_sessions, install_fake_llm):
    """No AIModelConfig rows at all → task must fail with a clear reason,
    not hang in 'running'."""
    assessment = Assessment(name="e2e-hermetic-c", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    task = TaskService(db).create(
        title="e2e no-model",
        authorized_scope="127.0.0.1",
        execution_target="container",
        status="queued",
        orchestrate=False,
        source="api",
        assessment_id=assessment.id,
    )

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "failed"
    assert "No AI model configured" in (t.result_summary or "")


async def test_unrelated_agent_task_does_not_remediate_existing_findings(
    db, patched_runtime_sessions, seed_model, install_fake_llm
):
    from services.finding_service import FindingService

    assessment = Assessment(name="QA unrelated task", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    previous = TaskService(db).create(
        title="Prior baseline",
        authorized_scope="127.0.0.1",
        assessment_id=assessment.id,
        status="done",
        orchestrate=False,
    )
    service = FindingService(db)
    observed = service.record(
        assessment.id,
        previous.id,
        {
            "title": "Existing finding",
            "target_service": "http://127.0.0.1/debug",
            "severity": "HIGH",
            "proof": "Synthetic prior evidence",
            "status": "confirmed",
        },
    )
    service.finalize_run(assessment.id, previous.id)
    task = TaskService(db).create(
        title="Local coding check",
        authorized_scope="127.0.0.1",
        assessment_id=assessment.id,
        status="queued",
        orchestrate=False,
    )
    first = _resp(tool_calls=[_tc("status_update", {"summary": "Checked the supplied code"})])
    first["reasoning_content"] = "Synthetic provider reasoning"
    fake = install_fake_llm([first, _resp(tool_calls=[_tc("finish", {"summary": "Coding check complete"})])])
    await TaskRuntime(task.id).run()
    db.expire_all()
    assert db.get(Card, observed.card.id).lifecycle_status != "remediated"
    diff = db.get(Task, task.id).meta["finding_diff"]
    assert diff["partial"] and diff["summary"]["remediated"] == 0
    assert any(m.get("reasoning_content") == "Synthetic provider reasoning" for m in fake.calls[1])


async def test_plan_only_first_turn_is_nudged_not_finished(db, patched_runtime_sessions, seed_model, install_fake_llm):
    """Regression (GLM 5.3): the model emits its PLAN as plain text and stops,
    without any tool call. That must NOT end the task 'done' at step 1 — the
    runtime nudges once and the agent continues to act."""
    assessment = Assessment(name="e2e-hermetic-d", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    task = TaskService(db).create(
        title="e2e plan-nudge",
        authorized_scope="127.0.0.1",
        execution_target="container",
        status="queued",
        orchestrate=False,
        source="api",
        assessment_id=assessment.id,
    )

    fake = install_fake_llm(
        [
            _resp(content="## Plan\n1. enumerate\n2. verify"),  # text only!
            _resp(tool_calls=[_tc("status_update", {"summary": "Acting now"})]),
            _resp(tool_calls=[_tc("finish", {"summary": "Ran the plan."})]),
        ]
    )

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"
    assert t.result_summary == "Ran the plan."  # not the plan text
    assert (t.meta or {}).get("steps", 0) >= 3  # it kept going
    # The nudge actually reached the model as a user message.
    nudged = [
        m for call in fake.calls for m in call if m.get("role") == "user" and "Plan noted" in (m.get("content") or "")
    ]
    assert nudged


async def test_fully_blocked_run_fails_as_infra_blocked(db, patched_runtime_sessions, seed_model, install_fake_llm):
    """Regression (QazNet): scope text that parses to nothing + every command
    refused → the run must close 'failed' with an explicit reason, not a
    hollow 'done' with zero findings."""
    assessment = Assessment(name="e2e-hermetic-e", scope="KZ SME program", status="active")
    db.add(assessment)
    db.commit()
    task = TaskService(db).create(
        title="e2e infra-blocked",
        authorized_scope="KZ SME program",  # parses empty
        execution_target="container",
        status="queued",
        orchestrate=False,
        source="api",
        assessment_id=assessment.id,
    )

    install_fake_llm(
        [
            _resp(tool_calls=[_tc("run_shell", {"command": "curl -s https://example.kz"})]),
            _resp(tool_calls=[_tc("finish", {"summary": "Every command refused."})]),
        ]
    )

    await TaskRuntime(task.id).run()

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "failed"
    assert "Infrastructure-blocked" in (t.result_summary or "")
    meta = t.meta or {}
    assert meta.get("blocked_actions") == 1
    assert meta.get("executed_actions") == 0
    # The config error is visible in the step log.
    assert any(s.get("kind") == "scope_parse_failed" for s in (meta.get("log") or []))


async def test_read_skill_resolves_kb_slugs_from_database(db, patched_runtime_sessions, seed_model, install_fake_llm):
    """search_knowledge returns ext_id slugs for ALL sources, but only skills
    live under /skills on disk. read_skill must fall back to the knowledge
    entries table so playbook slugs are readable."""
    from models.knowledge_entry import KnowledgeEntry

    db.add(
        KnowledgeEntry(
            source="playbook",
            ext_id="web-recon-methodology",
            title="Web Recon Methodology",
            content="Phase 1: asset inventory. Phase 2: content discovery.",
        )
    )
    db.commit()

    assessment = Assessment(name="e2e-hermetic-f", scope="127.0.0.1", status="active")
    db.add(assessment)
    db.commit()
    task = TaskService(db).create(
        title="e2e read-skill",
        authorized_scope="127.0.0.1",
        execution_target="container",
        status="queued",
        orchestrate=False,
        source="api",
        assessment_id=assessment.id,
    )

    fake = install_fake_llm(
        [
            _resp(tool_calls=[_tc("read_skill", {"skill": "web-recon-methodology"})]),
            _resp(tool_calls=[_tc("finish", {"summary": "Methodology loaded."})]),
        ]
    )

    await TaskRuntime(task.id).run()

    # The tool result reached the model with the playbook's content.
    tool_msgs = [m for call in fake.calls for m in call if m.get("role") == "tool"]
    assert tool_msgs and "asset inventory" in tool_msgs[0]["content"]

    db.expire_all()
    t = db.get(Task, task.id)
    assert t.status == "done"


class TestRepairToolPairing:
    """Checkpoint slicing can cut between an assistant tool_calls turn and
    its tool replies — GLM rejects that with 400/1214 'messages parameter
    is illegal' (observed live: a resumed vuln-testing task died on the
    first call). The repairer must make any transcript pair-consistent."""

    @staticmethod
    def _tc(id_):
        return {"id": id_, "type": "function", "function": {"name": "run_shell", "arguments": "{}"}}

    def _valid(self, msgs):
        """Every assistant tool_call id has a following tool reply; every
        tool reply has a preceding assistant tool_calls parent."""
        pending = set()
        for m in msgs:
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    pending.add(tc["id"])
            elif m["role"] == "tool":
                assert m["tool_call_id"] in pending, "orphan tool message"
                pending.discard(m["tool_call_id"])
            else:
                assert not pending, "role message inside a tool exchange"
        assert not pending, "tool_calls without replies"

    def test_slice_orphans_are_repaired(self):
        from services.agent.runtime import _repair_tool_pairing

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [self._tc("a"), self._tc("b")]},
            {"role": "tool", "tool_call_id": "a", "content": "out-a"},
            {"role": "tool", "tool_call_id": "b", "content": "out-b"},
            {"role": "assistant", "content": "next", "tool_calls": [self._tc("c")]},
            {"role": "tool", "tool_call_id": "c", "content": "out-c"},
        ]
        # Slice like the checkpoint does: starts mid-exchange (orphan 'a').
        cut = msgs[3:]
        assert cut[0]["role"] == "tool"  # precondition: broken input
        repaired = _repair_tool_pairing(cut)
        self._valid(repaired)
        # Both orphaned replies ('a', 'b') are dropped with their sliced-away
        # parent; the intact exchange (assistant 'next' → tool 'c') survives
        # verbatim, no synthetic noise.
        assert [m["role"] for m in repaired] == ["assistant", "tool"]
        assert repaired[0]["content"] == "next"
        assert repaired[1]["content"] == "out-c"

    def test_unsatisfied_calls_get_synthetic_replies(self):
        from services.agent.runtime import _repair_tool_pairing

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "", "tool_calls": [self._tc("x")]},
            {"role": "user", "content": "next instruction"},
        ]
        repaired = _repair_tool_pairing(msgs)
        self._valid(repaired)
        synth = [m for m in repaired if m["role"] == "tool"]
        assert len(synth) == 1 and synth[0]["tool_call_id"] == "x"

    def test_trailing_tool_calls_flushed_at_end(self):
        from services.agent.runtime import _repair_tool_pairing

        msgs = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [self._tc("y")]},
        ]
        repaired = _repair_tool_pairing(msgs)
        self._valid(repaired)
        assert repaired[-1]["role"] == "tool"

    def test_intact_transcript_unchanged(self):
        from services.agent.runtime import _repair_tool_pairing

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "hi"},
        ]
        assert _repair_tool_pairing(msgs) == msgs
