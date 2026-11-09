"""
Task planner / orchestrator.

When a top-level "audit" task is picked up, the planner reads its description +
authorized scope + the available skills (playbooks) and decomposes it into an
ORDERED list of specialized sub-tasks (one per phase/role: recon → enumeration →
exploitation → post-exploitation → reporting). Sub-tasks share the parent's
assessment and run sequentially (enforced by the single-flight runner + order).

If the model is unavailable or returns junk, a sensible default plan is used so
the audit still proceeds.
"""
from __future__ import annotations

import json
from datetime import datetime

from database import SessionLocal
from models.task import Task, TASK_PHASES, PHASE_ROLE
from schemas.assessment import AssessmentCreate
from services.assessment_service import AssessmentService
from services.ai_model_service import AIModelService
from services.knowledge_service import KnowledgeService
from services.agent.runtime import _safe_name
from services.llm import LLMError
from websocket.manager import manager
from websocket.events import create_event, EventType, event_task_created, event_task_updated
from schemas.task import TaskResponse
from utils.logger import get_logger

logger = get_logger(__name__)

# The default decomposition when the model can't be reached.
_DEFAULT_PLAN = [
    {"phase": "recon", "title": "Reconnaissance & asset discovery",
     "description": "Enumerate subdomains, live hosts, ports, services and tech stack in scope."},
    {"phase": "enumeration", "title": "Content & endpoint enumeration",
     "description": "Discover endpoints, parameters, auth flows and APIs; fingerprint versions."},
    {"phase": "exploitation", "title": "Vulnerability testing",
     "description": "Test discovered surface for injection, auth, access-control, SSRF, XSS with safe PoCs."},
    {"phase": "reporting", "title": "Consolidate findings",
     "description": "Review findings, confirm PoCs, capture evidence, and summarize the kill chain."},
]


def _default_plan(task: Task) -> list[dict]:
    """Default plan annotated with the operator's instructions.

    The canned phases are engagement-agnostic; without this the operator's
    objective ("what to look for", engagement constraints) silently evaporates
    when the model plan fails, and every phase agent works from generic text.
    """
    brief = (task.description or "").strip()
    if not brief:
        return [dict(s) for s in _DEFAULT_PLAN]
    brief = brief[:4000]
    out = []
    for step in _DEFAULT_PLAN:
        out.append({
            **step,
            "description": (
                f"{step['description']}\n\n"
                "OPERATOR'S BRIEF FOR THE WHOLE ENGAGEMENT (authoritative — tailor "
                "this phase's work to it, honor every constraint stated there):\n"
                f"{brief}"
            ),
        })
    return out


class TaskPlanner:
    def __init__(self, task_id: int):
        self.task_id = task_id

    async def _emit(self, kind: str, data: dict) -> None:
        await manager.broadcast(create_event(
            EventType.AGENT_STEP, {"task_id": self.task_id, "kind": kind, **data}
        ))

    async def run(self) -> None:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == self.task_id).first()
            if not task:
                return

            # Ensure a shared assessment for the whole audit.
            if not task.assessment_id:
                try:
                    svc = AssessmentService(db)
                    assessment = await svc.create_assessment(AssessmentCreate(
                        name=_safe_name(task),
                        scope=task.authorized_scope,
                        objectives=task.description,
                        target_domains=[task.target] if task.target else None,
                    ))
                    task.assessment_id = assessment.id
                    db.commit()
                except Exception as e:
                    task.status = "failed"
                    task.result_summary = f"Planner could not create assessment: {e}"
                    db.commit()
                    return

            task.status = "running"
            task.started_at = task.started_at or datetime.utcnow()
            db.commit()
            await self._emit("plan_start", {"title": task.title})

            plan = await self._make_plan(db, task)

            # Optional per-phase model routing: platform setting `phase_model_map`
            # is a JSON object {"recon": <model_config_id>, ...}. Cheap/local models
            # for light phases, a strong model for exploitation, etc.
            phase_model = self._phase_model_map(db)

            # Create all child tasks AND mark the parent planned in ONE
            # transaction, so a failure can't leave orphaned queued children
            # attached to a non-planned parent.
            created = []
            for i, step in enumerate(plan):
                phase = step.get("phase") if step.get("phase") in TASK_PHASES else "recon"
                child = Task(
                    parent_task_id=task.id,
                    assessment_id=task.assessment_id,
                    title=step.get("title") or f"{phase} phase",
                    description=step.get("description"),
                    target=task.target,
                    authorized_scope=task.authorized_scope,
                    status="queued",
                    position=i,
                    order_index=i,
                    phase=phase,
                    role=PHASE_ROLE.get(phase, "Agent"),
                    priority=task.priority,
                    execution_target=task.execution_target,
                    model_config_id=phase_model.get(phase, task.model_config_id),
                    orchestrate=False,          # children are leaves
                    source=task.source,
                    created_by=task.created_by,
                    meta={},
                )
                db.add(child)
                created.append(child)

            task.meta = {**(task.meta or {}), "planned": True, "plan_size": len(created)}
            task.result_summary = f"Planned {len(created)} sub-tasks; executing in order."
            db.commit()
            for c in created:
                db.refresh(c)
            task.meta = {**task.meta, "subtask_ids": [c.id for c in created]}
            db.commit()

            for i, child in enumerate(created):
                await manager.broadcast(event_task_created(
                    TaskResponse.model_validate(child).model_dump(mode="json")))
                await self._emit("subtask_created", {
                    "child_id": child.id, "phase": child.phase, "role": child.role,
                    "order": i, "title": child.title})
            await manager.broadcast(event_task_updated(
                task.id, TaskResponse.model_validate(task).model_dump(mode="json")))
            await self._emit("plan_done", {"subtasks": len(created)})
        except Exception as e:
            logger.exception("planner crashed", task_id=self.task_id)
            try:
                task = db.query(Task).filter(Task.id == self.task_id).first()
                if task:
                    task.status = "failed"
                    task.result_summary = f"Planner error: {e}"
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    @staticmethod
    def _phase_model_map(db) -> dict:
        """Read the optional phase→model_config_id routing map from settings."""
        import json as _json
        from models.platform_settings import PlatformSettings
        row = db.query(PlatformSettings).filter(
            PlatformSettings.key == "phase_model_map").first()
        if not row or not row.value:
            return {}
        try:
            m = _json.loads(row.value)
        except Exception:
            return {}
        out = {}
        for k, v in (m.items() if isinstance(m, dict) else []):
            try:
                if v:
                    out[k] = int(v)
            except (ValueError, TypeError):
                continue
        return out

    async def _make_plan(self, db, task: Task) -> list[dict]:
        """Ask the model to decompose the audit; fall back to the default plan."""
        ai = AIModelService(db)
        cfg = ai.get(task.model_config_id) if task.model_config_id else ai.get_default()
        if not cfg or not cfg.api_key_encrypted:
            logger.warning("planner: no model configured — using default plan",
                           task_id=task.id)
            await self._emit("plan_note", {"note": "no model — using default plan"})
            return _default_plan(task)

        # Give the planner the catalog of available skills so it plans like the
        # engagement-orchestrator: route the target to the right skill chain.
        skills = KnowledgeService(db).search(source="skill", limit=40)
        skills_txt = "\n".join(f"- {s.ext_id}: {(s.description or s.title)[:140]}" for s in skills)

        sys = (
            "You are the lead planner (engagement orchestrator) of an AUTHORIZED, scoped "
            "penetration test. Given the target and objective, decompose the engagement into "
            "an ORDERED chain of specialized sub-tasks — one dedicated agent per phase — that a "
            "professional team would run, executed strictly in sequence (recon first, reporting "
            "last). Route by target type to the RIGHT phases and note which skills each phase "
            "should load. Use ONLY these phases: recon, enumeration, exploitation, "
            "post_exploitation, reporting. Stay strictly within the authorized scope, and every "
            "phase inherits safe-testing-doctrine (no DoS, no destruction, scope-only, "
            "least-intrusive PoC).\n\n"
            "Available skills the agents can load (slug: what it covers):\n" + (skills_txt or "(none)") +
            "\n\nWrite each sub-task's description as concrete, actionable guidance for that "
            "phase's agent: what to enumerate/test, which skills to read_skill(), and what a "
            "'done' looks like. Tailor to the target and objective — don't emit a generic template."
        )
        from services.agent.context import build_task_context
        ctx = build_task_context(db, task)
        ctx_block = f"\nADDITIONAL CONTEXT (user comments + attached files):\n{ctx}\n" if ctx else ""
        user = (
            f"AUDIT: {task.title}\n"
            f"TARGET: {task.target or '(none)'}\n"
            f"SCOPE: {task.authorized_scope or '(none)'}\n"
            f"INSTRUCTIONS/WHAT TO LOOK FOR:\n{task.description or '(none)'}\n"
            f"{ctx_block}\n"
            "Return ONLY a JSON object of the form:\n"
            '{"subtasks":[{"phase":"recon","title":"...","description":"what this agent should do"}]}\n'
            "Order the subtasks by execution sequence. 3-6 subtasks."
        )
        try:
            client = ai.build_client(cfg)
            params = cfg.params or {}
            resp = await client.chat(
                [{"role": "system", "content": sys}, {"role": "user", "content": user}],
                temperature=params.get("temperature", 0.2),
                # The plan JSON alone runs 1-2k tokens; reasoning models also
                # spend budget on hidden reasoning before it — 1200 truncated
                # every reasoning-model plan to the generic fallback, and 3072
                # still starved glm-5.3 to an EMPTY content (observed live:
                # completion 2918/3072, content ""). 8192 leaves reasoning
                # headroom without paying for unused budget.
                max_tokens=params.get("max_tokens", 8192),
            )
            content = resp.get("content") or ""
            if not content.strip():
                finish = ""
                try:
                    finish = (((resp.get("raw") or {}).get("choices") or [{}])[0]
                              .get("finish_reason"))
                except Exception:
                    pass
                logger.warning("planner: model returned EMPTY content",
                               task_id=task.id, finish_reason=finish,
                               usage=resp.get("usage"))
            plan = self._parse_plan(content)
            if plan:
                return plan
            # A model refusal arrives as prose (no JSON) — log enough of it to
            # see WHY the engagement fell back to the canned plan.
            logger.warning("planner: model plan unparseable — using default",
                           task_id=task.id, reply_head=content[:300])
            await self._emit("plan_note", {"note": "model plan unparseable — using default"})
        except LLMError as e:
            logger.warning("planner: model error — using default",
                           task_id=task.id, error=str(e))
            await self._emit("plan_note", {"note": f"model error ({e}) — using default"})
        return _default_plan(task)

    @staticmethod
    def _parse_plan(content: str) -> list[dict]:
        # Extract the first JSON object from the reply.
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(content[start:end + 1])
            subs = data.get("subtasks") or data.get("tasks") or []
            out = []
            for s in subs:
                if isinstance(s, dict) and s.get("title"):
                    out.append({"phase": s.get("phase", "recon"),
                                "title": s.get("title"),
                                "description": s.get("description", "")})
            return out
        except Exception:
            return []
