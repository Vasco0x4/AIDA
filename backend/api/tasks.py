"""
Task API — Kanban board + autonomous work queue.

CRUD + a /move endpoint for drag-and-drop, plus /board for the grouped view.
Mutations broadcast over WebSocket so any open board updates live.

Safety: host execution_target is accepted but flagged; the agent runner (later)
enforces the opt-in and the authorized_scope invariant at run time.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from models.task import Task, TASK_COLUMNS
from models.platform_settings import PlatformSettings
from pydantic import BaseModel, Field
from schemas.task import (
    TaskCreate, TaskUpdate, TaskMove, TaskResponse, BoardResponse, BoardColumn,
    TaskDependenciesUpdate, TaskEventResponse,
)
from services.task_service import OptimisticLockError, TaskService
from services.audit_service import record as audit
from websocket.manager import manager
from websocket.events import (
    event_task_created, event_task_updated, event_task_deleted, event_task_moved,
)
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _resp(row: Task) -> dict:
    return TaskResponse.model_validate(row).model_dump(mode="json")


def _current_user_id(request: Request) -> Optional[int]:
    user = getattr(request.state, "user", None)
    return getattr(user, "id", None) if user else None


@router.get("/columns")
def list_columns():
    """The ordered Kanban columns (workflow stages)."""
    return {"columns": list(TASK_COLUMNS)}


class RunnerState(BaseModel):
    enabled: bool


class RunnerConfig(BaseModel):
    """E3 reliability knobs (AgentOps). Mirrored in Settings → Agents."""
    max_concurrency: int = Field(2, ge=1, le=8)
    target_min_interval: int = Field(60, ge=0, description=(
        "Minimum seconds between two agents starting on the SAME target"))
    max_steps: int = Field(500, ge=1, le=1_000_000, description=(
        "Per-task step budget — runaway backstop; agents run until finish(). "
        "Raise to run goal-mode engagements with effectively no cap"))
    token_budget: int = Field(0, ge=0, description=(
        "Default per-task token budget (prompt+completion); 0 = unlimited"))
    fallback_chain: list[int] = Field(default_factory=list, description=(
        "AIModelConfig ids tried, in order, when the primary model fails"))
    goal_mode: bool = Field(True, description=(
        "Goal mode: an LLM judge reviews premature stops and capped runs "
        "auto-continue until the task objective is met"))
    max_auto_continuations: int = Field(2, ge=-1, le=10, description=(
        "Automatic requeues past the step cap before the task parks in "
        "needs_review (-1 = unlimited: requeue until the objective is met)"))
    goal_judge_max_cont: int = Field(3, ge=-1, le=10, description=(
        "Consecutive judge-CONTINUE nudges before a stop attempt is accepted "
        "(-1 = never accept a judge-rejected stop; only DONE ends the run)"))


class RunnerStatus(BaseModel):
    enabled: bool
    active: int
    config: RunnerConfig


def _runner_enabled(db: Session) -> bool:
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == "agent_runner_enabled"
    ).first()
    return (row.value if row else "true").lower() in ("true", "1", "yes", "on")


def _setting_bool(db: Session, key: str, default: bool) -> bool:
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == key).first()
    return (row.value if row else ("true" if default else "false")).lower() in (
        "true", "1", "yes", "on")


def _set_setting(db: Session, key: str, value: str, description: str) -> None:
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSettings(key=key, value=value, description=description))
    db.commit()


def _runner_config(db: Session) -> RunnerConfig:
    import json as _json

    from services.agent.runner import MAX_WORKERS

    def _int(key: str, default: int) -> int:
        row = db.query(PlatformSettings).filter(
            PlatformSettings.key == key).first()
        try:
            return int(row.value) if row else default
        except (TypeError, ValueError):
            return default

    try:
        chain = _json.loads(_setting_value(db, "model_fallback_chain") or "[]")
        chain = [i for i in chain if isinstance(i, int)]
    except Exception:
        chain = []
    return RunnerConfig(
        max_concurrency=min(_int("agent_max_concurrency", 2), MAX_WORKERS),
        target_min_interval=_int("agent_target_min_interval", 60),
        max_steps=_int("agent_max_steps", 500),
        token_budget=_int("agent_token_budget", 0),
        fallback_chain=chain,
        goal_mode=_setting_bool(db, "agent_goal_mode", True),
        max_auto_continuations=_int("agent_max_auto_continuations", 2),
        goal_judge_max_cont=_int("agent_goal_judge_max_cont", 3),
    )


def _setting_value(db: Session, key: str):
    row = db.query(PlatformSettings).filter(
        PlatformSettings.key == key).first()
    return row.value if row else None


@router.get("/runner", response_model=RunnerStatus)
def get_runner_state(db: Session = Depends(get_db)):
    """Runner pool status: paused/running, in-flight agents, reliability config."""
    from services.agent.runner import runner
    return RunnerStatus(enabled=_runner_enabled(db), active=runner.active_count,
                        config=_runner_config(db))


@router.put("/runner", response_model=RunnerState)
def set_runner_state(body: RunnerState, request: Request, db: Session = Depends(get_db)):
    """Pause/resume the autonomous runner without a restart."""
    _set_setting(db, "agent_runner_enabled", "true" if body.enabled else "false",
                 "Autonomous agent runner: pick up queued tasks")
    from services.agent.agent_settings import invalidate_settings_cache
    invalidate_settings_cache()
    audit(db, action="runner.updated", request=request,
          detail={"enabled": body.enabled})
    return RunnerState(enabled=body.enabled)


@router.put("/runner/config", response_model=RunnerConfig)
def set_runner_config(body: RunnerConfig, request: Request,
                      db: Session = Depends(get_db)):
    """Update the agent pool reliability config (concurrency, rate limit,
    budget, model fallback chain). Applies immediately."""
    import json as _json
    from models.ai_model_config import AIModelConfig
    from services.agent.agent_settings import invalidate_settings_cache

    # The fallback chain must reference real, usable model configs.
    chain = body.fallback_chain
    valid = {i for (i,) in db.query(AIModelConfig.id).all()} if chain else set()
    unknown = [i for i in chain if i not in valid]
    if unknown:
        raise HTTPException(400, f"Unknown AIModelConfig ids in fallback chain: "
                                 f"{unknown}")

    _set_setting(db, "agent_max_concurrency", str(body.max_concurrency),
                 "Agent pool: max concurrent agents")
    _set_setting(db, "agent_target_min_interval", str(body.target_min_interval),
                 "Agent pool: min seconds between agents on the same target")
    _set_setting(db, "agent_max_steps", str(body.max_steps),
                 "Agent pool: per-task step budget (runaway backstop)")
    _set_setting(db, "agent_token_budget", str(body.token_budget),
                 "Agent pool: default per-task token budget (0 = unlimited)")
    _set_setting(db, "agent_goal_mode",
                 "true" if body.goal_mode else "false",
                 "Agent pool: goal mode (judge premature stops, auto-continue caps)")
    _set_setting(db, "agent_max_auto_continuations", str(body.max_auto_continuations),
                 "Agent pool: automatic requeues past the step cap")
    _set_setting(db, "agent_goal_judge_max_cont", str(body.goal_judge_max_cont),
                 "Agent pool: consecutive goal-judge CONTINUEs before accepting a stop")
    _set_setting(db, "model_fallback_chain", _json.dumps(chain),
                 "Agent pool: fallback AIModelConfig ids, in order")
    invalidate_settings_cache()
    audit(db, action="runner.config_updated", request=request,
          detail=body.model_dump())
    return body


@router.post("/runner/kill")
async def kill_running_agents(request: Request, db: Session = Depends(get_db)):
    """GLOBAL KILL SWITCH: cancel every running agent now and mark its task
    failed. Returns how many were killed."""
    from services.agent.runner import runner
    killed = await runner.kill_all()
    audit(db, action="runner.kill_switch", request=request,
          detail={"killed": killed})
    return {"killed": killed}


@router.get("/board", response_model=BoardResponse)
async def get_board(db: Session = Depends(get_db)):
    """Tasks grouped by column for the board view."""
    service = TaskService(db)
    grouped = service.board()
    columns = [
        BoardColumn(key=col, tasks=[TaskResponse.model_validate(t) for t in grouped.get(col, [])])
        for col in TASK_COLUMNS
    ]
    return BoardResponse(columns=columns)


@router.get("", response_model=List[TaskResponse])
async def list_tasks(status: Optional[str] = None, db: Session = Depends(get_db)):
    service = TaskService(db)
    return service.list_tasks(status=status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    service = TaskService(db)
    row = service.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, request: Request, db: Session = Depends(get_db)):
    service = TaskService(db)
    try:
        row = service.create(created_by=_current_user_id(request), **body.model_dump())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    # Provision the Assessment up-front (top-level tasks only) so findings have a
    # home immediately and it shows in Assessments — instead of being created
    # lazily when the agent first runs. Best-effort: if it fails (e.g. container
    # down) the runtime/planner still create it on pickup.
    if not row.parent_task_id and not row.assessment_id:
        try:
            from services.assessment_service import AssessmentService
            from services.agent.runtime import _safe_name
            from schemas.assessment import AssessmentCreate
            assessment = await AssessmentService(db).create_assessment(AssessmentCreate(
                name=_safe_name(row),
                scope=row.authorized_scope,
                objectives=row.description,
                target_domains=[row.target] if row.target else None,
            ))
            row.assessment_id = assessment.id
            db.commit()
            db.refresh(row)
        except Exception as e:
            # A failed INSERT/COMMIT leaves SQLAlchemy in pending-rollback and
            # expires the already-persisted task. Recover that session before
            # logging or auditing so best-effort provisioning cannot turn a
            # successfully created task into a 500 response.
            db.rollback()
            db.refresh(row)
            logger.warning("Up-front assessment creation failed (will retry on run)",
                           task_id=row.id, error=str(e))

    audit(db, action="task.created", request=request, resource_type="task",
          resource_id=row.id, detail={"title": row.title, "status": row.status})
    await manager.broadcast(event_task_created(_resp(row)))
    return row


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, body: TaskUpdate, request: Request,
                       db: Session = Depends(get_db)):
    service = TaskService(db)
    try:
        row = service.update(task_id, **body.model_dump(exclude_unset=True))
    except OptimisticLockError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    audit(db, action="task.updated", request=request, resource_type="task",
          resource_id=task_id, detail={"fields": sorted(body.model_dump(exclude_unset=True))})
    await manager.broadcast(event_task_updated(task_id, _resp(row)))
    return row


@router.post("/{task_id}/move", response_model=TaskResponse)
async def move_task(task_id: int, body: TaskMove, request: Request,
                      db: Session = Depends(get_db)):
    # "running" is owned by the agent runner: a task dropped there manually
    # would sit forever (nothing executes it; orphan recovery only fires at
    # startup). Re-route to "queued" so the runner picks it up immediately.
    if body.status == "running":
        body.status = "queued"
    service = TaskService(db)
    try:
        row = service.move(
            task_id, body.status, body.position,
            expected_version=body.expected_version)
    except OptimisticLockError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    audit(db, action="task.moved", request=request, resource_type="task",
          resource_id=task_id, detail={"status": row.status, "position": row.position})
    await manager.broadcast(event_task_moved(task_id, row.status, row.position))
    return row


@router.put("/{task_id}/dependencies", response_model=TaskResponse)
async def set_dependencies(task_id: int, body: TaskDependenciesUpdate,
                           db: Session = Depends(get_db)):
    service = TaskService(db)
    try:
        row = service.set_dependencies(
            task_id, body.dependency_ids, expected_version=body.expected_version)
    except OptimisticLockError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    await manager.broadcast(event_task_updated(task_id, _resp(row)))
    return row


@router.get("/{task_id}/events", response_model=list[TaskEventResponse])
def task_events(task_id: int, limit: int = Query(default=200, ge=1, le=1000),
                before_id: Optional[int] = Query(default=None, ge=1),
                db: Session = Depends(get_db)):
    service = TaskService(db)
    if not service.get(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return service.list_events(task_id, limit=limit, before_id=before_id)


@router.post("/{task_id}/recover", response_model=TaskResponse)
async def recover_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """Fence a stuck worker and explicitly return its task to the queue."""
    service = TaskService(db)
    if not service.get(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    row = service.recover(task_id)
    if not row:
        raise HTTPException(status_code=409, detail="Only running tasks can be recovered")
    audit(db, action="task.recovered", request=request, resource_type="task",
          resource_id=task_id)
    await manager.broadcast(event_task_updated(task_id, _resp(row)))
    return row


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """Explicitly retry failed/reviewed work; never silently loops forever."""
    service = TaskService(db)
    if not service.get(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    row = service.retry(task_id)
    if not row:
        raise HTTPException(
            status_code=409,
            detail="Only failed, needs_review, or done tasks can be retried")
    audit(db, action="task.retried", request=request, resource_type="task",
          resource_id=task_id)
    await manager.broadcast(event_task_updated(task_id, _resp(row)))
    return row


@router.post("/{task_id}/stop", response_model=TaskResponse)
async def stop_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """Hard-stop a task: kill any scan processes in the pentest container and
    mark the task (and its running children, if a parent) as failed/stopped."""
    service = TaskService(db)
    row = service.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    from services.agent.runner import runner
    await runner.cancel(task_id)

    # Kill leftover scan processes in the sandbox (single-flight → safe).
    try:
        from services.container_service import ContainerService
        kill = ("pkill -9 -f 'nmap|masscan|ffuf|gobuster|feroxbuster|nuclei|nikto|"
                "sqlmap|hydra|medusa|wfuzz|dirsearch|dirb|wpscan|chromium|amass|"
                "subfinder' 2>/dev/null; true")
        await ContainerService().execute_container_command(command=kill)
    except Exception as e:
        logger.warning("stop: could not kill container processes", error=str(e))

    from datetime import datetime as _dt
    stopped = []
    targets = [row] + (db.query(Task).filter(
        Task.parent_task_id == row.id,
        Task.status.in_(["running", "queued"])).all() if not row.parent_task_id else [])
    for t in targets:
        if t.status not in ("done", "failed", "needs_review"):
            t.status = "failed"
            t.result_summary = "⏹ Stopped by user."
            t.completed_at = _dt.utcnow()
            stopped.append(t.id)
    db.commit()
    db.refresh(row)
    audit(db, action="task.stopped", request=request, resource_type="task",
          resource_id=task_id, detail={"stopped_ids": stopped})
    for tid in stopped:
        await manager.broadcast(event_task_updated(tid, {"id": tid, "status": "failed"}))
    return row


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    service = TaskService(db)
    if not service.delete(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    audit(db, action="task.deleted", request=request, resource_type="task", resource_id=task_id)
    await manager.broadcast(event_task_deleted(task_id))
