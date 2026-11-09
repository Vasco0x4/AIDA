"""
Scheduled Engagements API — cron-triggered recurring audits (E4).

CRUD plus a manual run-now trigger and a run history view. Cron expressions
are standard 5-field, interpreted in UTC.
"""
from datetime import datetime, timezone as utc_timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.scheduled_engagement import ScheduledEngagement
from models.task import Task
from schemas.task import TaskResponse
from services.audit_service import record as audit
from services.scheduler import next_run, validate_cron, validate_timezone

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    cron: str = Field(..., max_length=64)
    task_title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    target: Optional[str] = Field(None, max_length=512)
    authorized_scope: Optional[str] = None
    priority: str = "medium"
    model_config_id: Optional[int] = None
    orchestrate: bool = True
    token_budget: Optional[int] = Field(None, ge=0)
    enabled: bool = True
    assessment_id: Optional[int] = None
    timezone: str = "UTC"
    scan_profile: str = "autonomous"
    scan_profile_id: Optional[int] = None
    rate_limit_seconds: int = Field(60, ge=1, le=3600)
    max_concurrency: int = Field(1, ge=1, le=1)
    authorization_reference: Optional[str] = None
    authorization_confirmed: bool = False


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    cron: Optional[str] = Field(None, max_length=64)
    task_title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    target: Optional[str] = Field(None, max_length=512)
    authorized_scope: Optional[str] = None
    priority: Optional[str] = None
    model_config_id: Optional[int] = None
    orchestrate: Optional[bool] = None
    token_budget: Optional[int] = Field(None, ge=0)
    enabled: Optional[bool] = None
    assessment_id: Optional[int] = None
    timezone: Optional[str] = None
    scan_profile: Optional[str] = None
    scan_profile_id: Optional[int] = None
    rate_limit_seconds: Optional[int] = Field(None, ge=1, le=3600)
    max_concurrency: Optional[int] = Field(None, ge=1, le=1)
    authorization_reference: Optional[str] = None
    authorization_confirmed: Optional[bool] = None


class ScheduleResponse(BaseModel):
    id: int
    name: str
    cron: str
    enabled: bool
    task_title: str
    description: Optional[str]
    target: Optional[str]
    authorized_scope: Optional[str]
    priority: str
    model_config_id: Optional[int]
    orchestrate: bool
    token_budget: Optional[int]
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_task_id: Optional[int]
    last_task_status: Optional[str] = None
    run_count: int
    created_by: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    assessment_id: Optional[int]
    timezone: str
    scan_profile: str
    scan_profile_id: Optional[int]
    rate_limit_seconds: int
    max_concurrency: int
    authorization_reference: Optional[str]
    authorization_confirmed: bool
    last_error: Optional[str]

    class Config:
        from_attributes = True


def _validate(db: Session, cron: Optional[str],
              model_config_id: Optional[int], *, assessment_id: Optional[int] = None,
              timezone: Optional[str] = None, scan_profile: Optional[str] = None,
              scan_profile_id: Optional[int] = None,
              authorized_scope: Optional[str] = None,
              authorization_reference: Optional[str] = None,
              authorization_confirmed: bool = False) -> None:
    if cron is not None and not validate_cron(cron):
        raise HTTPException(
            400, f"Invalid cron expression: {cron!r} "
                 "(expected 5 fields, e.g. '0 3 * * mon' — UTC)")
    if model_config_id is not None:
        from models.ai_model_config import AIModelConfig
        if not db.query(AIModelConfig).filter(
                AIModelConfig.id == model_config_id).first():
            raise HTTPException(400, f"Unknown model_config_id {model_config_id}")
    if assessment_id is not None:
        from models.assessment import Assessment
        if not db.get(Assessment, assessment_id):
            raise HTTPException(400, f"Unknown assessment_id {assessment_id}")
    if timezone is not None and not validate_timezone(timezone):
        raise HTTPException(400, f"Unknown timezone: {timezone}")
    if scan_profile is not None and scan_profile not in ("autonomous", "safe_web_baseline"):
        raise HTTPException(400, "scan_profile must be autonomous or safe_web_baseline")
    if scan_profile_id is not None:
        from models.scan_profile import ScanProfile
        profile = db.get(ScanProfile, scan_profile_id)
        if profile is None or not profile.enabled:
            raise HTTPException(400, f"Unknown or disabled scan_profile_id {scan_profile_id}")
        if scan_profile is not None and profile.kind != scan_profile:
            raise HTTPException(400, "scan_profile must match the saved Scan Profile kind")
    if authorized_scope:
        from services.agent.scope import parse_scope
        if parse_scope(authorized_scope).is_empty:
            raise HTTPException(400, "authorized_scope contains no valid domains, URLs, IPs or CIDRs")
    if scan_profile == "safe_web_baseline":
        if not assessment_id:
            raise HTTPException(400, "Select an existing Assessment for recurring Scan Runs")
        if not authorized_scope or not authorized_scope.strip():
            raise HTTPException(400, "authorized_scope is required")
        if not authorization_confirmed or not (authorization_reference or "").strip():
            raise HTTPException(
                400, "Confirm authorization and provide its policy/reference before scheduling")


def _resp(db: Session, row: ScheduledEngagement) -> ScheduleResponse:
    out = ScheduleResponse.model_validate(row).model_dump(mode="json")
    if row.last_task_id:
        t = db.query(Task.status).filter(Task.id == row.last_task_id).first()
        out["last_task_status"] = t[0] if t else "deleted"
    return ScheduleResponse(**out)


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(db: Session = Depends(get_db)):
    rows = db.query(ScheduledEngagement).order_by(
        ScheduledEngagement.enabled.desc(), ScheduledEngagement.name).all()
    ids = {row.last_task_id for row in rows if row.last_task_id}
    statuses = dict(db.query(Task.id, Task.status).filter(Task.id.in_(ids)).all()) if ids else {}
    result = []
    for row in rows:
        out = ScheduleResponse.model_validate(row)
        if row.last_task_id:
            out.last_task_status = statuses.get(row.last_task_id, "deleted")
        result.append(out)
    return result


@router.get("/preview")
def preview_schedule(cron: str = Query(..., max_length=64), timezone: str = "UTC"):
    """Preview five occurrences without creating or executing a task."""
    if not validate_cron(cron):
        raise HTTPException(400, "Use a five-field cron expression, for example 0 3 * * mon")
    if not validate_timezone(timezone):
        raise HTTPException(400, "Unknown IANA timezone")
    cursor = datetime.utcnow()
    occurrences = []
    try:
        for _ in range(5):
            cursor = next_run(cron, cursor, timezone)
            occurrences.append(cursor.replace(tzinfo=utc_timezone.utc).isoformat())
    except (ValueError, OverflowError):
        raise HTTPException(400, "This expression has no reachable run date")
    return {"timezone": timezone, "occurrences": occurrences}


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(body: ScheduleCreate, request: Request,
                          db: Session = Depends(get_db)):
    _validate(db, body.cron, body.model_config_id, assessment_id=body.assessment_id,
              timezone=body.timezone, scan_profile=body.scan_profile,
              scan_profile_id=body.scan_profile_id,
              authorized_scope=body.authorized_scope,
              authorization_reference=body.authorization_reference,
              authorization_confirmed=body.authorization_confirmed)
    from sqlalchemy import func
    duplicate = db.query(ScheduledEngagement).filter(
        func.lower(ScheduledEngagement.name) == body.name.strip().lower()).first()
    if duplicate:
        raise HTTPException(409, "A schedule with this name already exists")
    user = getattr(request.state, "user", None)
    row = ScheduledEngagement(
        **body.model_dump(),
        created_by=getattr(user, "id", None),
        next_run_at=next_run(body.cron, datetime.utcnow(), body.timezone) if body.enabled else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, action="schedule.created", request=request,
          resource_type="scheduled_engagement", resource_id=row.id,
          detail={"name": row.name, "cron": row.cron})
    return _resp(db, row)


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    row = db.query(ScheduledEngagement).filter(
        ScheduledEngagement.id == schedule_id).first()
    if not row:
        raise HTTPException(404, "Schedule not found")
    return _resp(db, row)


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(schedule_id: int, body: ScheduleUpdate,
                          request: Request, db: Session = Depends(get_db)):
    row = db.query(ScheduledEngagement).filter(
        ScheduledEngagement.id == schedule_id).first()
    if not row:
        raise HTTPException(404, "Schedule not found")
    fields = body.model_dump(exclude_unset=True)
    merged = {**ScheduleResponse.model_validate(row).model_dump(), **fields}
    _validate(db, fields.get("cron"), fields.get("model_config_id"),
              assessment_id=merged.get("assessment_id"), timezone=merged.get("timezone"),
              scan_profile=merged.get("scan_profile"), authorized_scope=merged.get("authorized_scope"),
              scan_profile_id=merged.get("scan_profile_id"),
              authorization_reference=merged.get("authorization_reference"),
              authorization_confirmed=merged.get("authorization_confirmed", False))
    for key, value in fields.items():
        setattr(row, key, value)
    # Recompute the next fire time when the schedule's shape changed (new cron,
    # re-enabled, or re-targeted) — from now, not the stale anchor.
    if fields.get("cron") or ("enabled" in fields):
        row.next_run_at = (next_run(row.cron, datetime.utcnow(), row.timezone)
                           if row.enabled else None)
    db.commit()
    db.refresh(row)
    audit(db, action="schedule.updated", request=request,
          resource_type="scheduled_engagement", resource_id=schedule_id,
          detail={"fields": sorted(fields)})
    return _resp(db, row)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, request: Request,
                          db: Session = Depends(get_db)):
    row = db.query(ScheduledEngagement).filter(
        ScheduledEngagement.id == schedule_id).first()
    if not row:
        raise HTTPException(404, "Schedule not found")
    db.delete(row)
    db.commit()
    audit(db, action="schedule.deleted", request=request,
          resource_type="scheduled_engagement", resource_id=schedule_id,
          detail={"name": row.name})


@router.post("/{schedule_id}/run-now", response_model=TaskResponse)
async def run_schedule_now(schedule_id: int, request: Request,
                           db: Session = Depends(get_db)):
    """Fire the engagement immediately, bypassing next_run_at."""
    from services.scheduler import scheduler
    row = db.query(ScheduledEngagement).filter(
        ScheduledEngagement.id == schedule_id).first()
    if not row:
        raise HTTPException(404, "Schedule not found")
    task = await scheduler.fire(db, row, datetime.utcnow())
    if task is None:
        raise HTTPException(
            409, "Previous scheduled run is still queued/running — "
                 "wait for it to finish before triggering again.")
    audit(db, action="schedule.run_now", request=request,
          resource_type="scheduled_engagement", resource_id=schedule_id,
          detail={"task_id": task.id})
    db.refresh(task)
    return task


@router.get("/{schedule_id}/runs", response_model=List[TaskResponse])
async def list_schedule_runs(schedule_id: int, skip: int = Query(0, ge=0),
                             limit: int = Query(50, ge=1, le=100),
                             db: Session = Depends(get_db)):
    """Tasks this engagement created, newest first."""
    if not db.query(ScheduledEngagement).filter(
            ScheduledEngagement.id == schedule_id).first():
        raise HTTPException(404, "Schedule not found")
    rows = (
        db.query(Task)
        .filter(Task.source == "schedule",
                Task.meta["scheduled"]["engagement_id"].as_string() == str(schedule_id))
        .order_by(Task.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows
