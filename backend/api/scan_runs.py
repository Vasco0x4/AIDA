"""Scan Run read models, evidence exports and operator controls.

A Scan Run is the existing durable Task row: this avoids competing lifecycle
systems and preserves leases, heartbeats, events, checkpoints and retries.
"""
from __future__ import annotations

from html import escape
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from models.assessment import Assessment
from models.finding_snapshot import FindingSnapshot
from models.task import Task
from schemas.task import TaskResponse
from schemas.task import TaskEventResponse
from services.audit_service import record as audit
from services.task_service import TaskService
from websocket.events import event_task_updated
from websocket.manager import manager

router = APIRouter(prefix="/scan-runs", tags=["scan-runs"])
assessment_router = APIRouter(prefix="/assessments", tags=["scan-runs"])


def _get(db: Session, run_id: int) -> Task:
    row = db.get(Task, run_id)
    if row is None or row.assessment_id is None:
        raise HTTPException(404, "Scan Run not found")
    return row


def _task_dict(row: Task) -> dict:
    return TaskResponse.model_validate(row).model_dump(mode="json")


def _snapshot(row: FindingSnapshot) -> dict:
    return {
        "id": row.id, "assessment_id": row.assessment_id, "run_id": row.run_id,
        "card_id": row.card_id, "fingerprint": row.fingerprint, "title": row.title,
        "target_service": row.target_service, "severity": row.severity,
        "triage_status": row.triage_status, "lifecycle_status": row.lifecycle_status,
        "technical_analysis": row.technical_analysis, "proof": row.proof,
        "observed_at": row.observed_at.isoformat() if row.observed_at else None,
    }


@router.get("", response_model=List[TaskResponse])
def list_scan_runs(assessment_id: Optional[int] = None, status: Optional[str] = None,
                   skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                   db: Session = Depends(get_db)):
    query = db.query(Task).filter(Task.assessment_id.isnot(None))
    if assessment_id is not None:
        query = query.filter(Task.assessment_id == assessment_id)
    if status:
        query = query.filter(Task.status == status)
    return query.order_by(Task.id.desc()).offset(skip).limit(limit).all()


@assessment_router.get("/{assessment_id}/runs", response_model=List[TaskResponse])
def list_assessment_runs(assessment_id: int, skip: int = Query(0, ge=0),
                         limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    if db.get(Assessment, assessment_id) is None:
        raise HTTPException(404, "Assessment not found")
    return (db.query(Task).filter(Task.assessment_id == assessment_id)
            .order_by(Task.id.desc()).offset(skip).limit(limit).all())


@router.get("/{run_id}", response_model=TaskResponse)
def get_scan_run(run_id: int, db: Session = Depends(get_db)):
    return _get(db, run_id)


@router.get("/{run_id}/findings")
def scan_run_findings(run_id: int, skip: int = Query(0, ge=0),
                      limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    _get(db, run_id)
    rows = (db.query(FindingSnapshot).filter(FindingSnapshot.run_id == run_id)
            .order_by(FindingSnapshot.id).offset(skip).limit(limit).all())
    return [_snapshot(row) for row in rows]


@router.get("/{run_id}/diff")
def scan_run_diff(run_id: int, db: Session = Depends(get_db)):
    run = _get(db, run_id)
    diff = (run.meta or {}).get("finding_diff")
    if diff is None:
        raise HTTPException(409, "Finding diff is not finalized for this Scan Run")
    return diff


@router.get("/{run_id}/events", response_model=list[TaskEventResponse])
def scan_run_events(run_id: int, limit: int = Query(default=200, ge=1, le=1000),
                    before_id: Optional[int] = Query(default=None, ge=1),
                    db: Session = Depends(get_db)):
    _get(db, run_id)
    return TaskService(db).list_events(run_id, limit=limit, before_id=before_id)


@router.get("/{run_id}/report")
def scan_run_report(run_id: int, format: str = Query("html", pattern="^(html|json)$"),
                    db: Session = Depends(get_db)):
    run = _get(db, run_id)
    snapshots = (db.query(FindingSnapshot).filter(FindingSnapshot.run_id == run_id)
                 .order_by(FindingSnapshot.id).all())
    diff = (run.meta or {}).get("finding_diff") or {
        "summary": {"new": 0, "recurring": 0, "remediated": 0, "reopened": 0}}
    payload = {"run": _task_dict(run), "diff": diff,
               "findings": [_snapshot(row) for row in snapshots]}
    if format == "json":
        return payload

    summary = diff.get("summary", {})
    cards = []
    for item in snapshots:
        cards.append(
            f"<article><h3>{escape(item.title)}</h3>"
            f"<p><strong>{escape(item.severity or 'INFO')}</strong> · "
            f"{escape(item.lifecycle_status or '')} · {escape(item.target_service or '')}</p>"
            f"<p>{escape(item.technical_analysis or '')}</p>"
            f"<pre>{escape(item.proof or '')}</pre></article>")
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Scan Run #{run.id}</title><style>body{{font:15px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#172033}}article{{border-top:1px solid #ccd4df;padding:1rem 0}}pre{{white-space:pre-wrap;background:#f3f5f8;padding:1rem;overflow-wrap:anywhere}}.counts{{display:flex;gap:1rem;flex-wrap:wrap}}</style></head>
<body><h1>{escape(run.title)}</h1><p>Scan Run #{run.id} · Assessment #{run.assessment_id} · {escape(run.status)}</p>
<p>{escape(run.result_summary or 'Run has no final summary yet.')}</p>
<div class="counts"><span>New: {summary.get('new', 0)}</span><span>Recurring: {summary.get('recurring', 0)}</span><span>Remediated: {summary.get('remediated', 0)}</span><span>Reopened: {summary.get('reopened', 0)}</span></div>
<h2>Finding evidence</h2>{''.join(cards) or '<p>No findings were observed.</p>'}</body></html>"""
    return HTMLResponse(html, headers={
        "Content-Disposition": f'attachment; filename="scan-run-{run.id}.html"',
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/{run_id}/pause", response_model=TaskResponse)
async def pause_scan_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    run = _get(db, run_id)
    if run.status not in ("queued", "running"):
        raise HTTPException(409, "Only queued or running Scan Runs can be paused")
    if run.status == "running":
        from services.agent.runner import runner
        await runner.cancel(run_id)
        run.status = "queued"
        run.lease_owner = None
        run.lease_token = None
        run.heartbeat_at = None
        run.lease_expires_at = None
    run.meta = {**(run.meta or {}), "paused": True}
    run.result_summary = "Paused by operator. Resume to continue from the saved checkpoint."
    TaskService(db).record_event(run.id, "paused", {})
    db.commit()
    db.refresh(run)
    audit(db, action="scan_run.paused", request=request, resource_type="task", resource_id=run_id)
    await manager.broadcast(event_task_updated(run_id, _task_dict(run)))
    return run


@router.post("/{run_id}/resume", response_model=TaskResponse)
async def resume_scan_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    run = _get(db, run_id)
    if run.status not in ("queued", "running") or not (run.meta or {}).get("paused"):
        raise HTTPException(409, "Scan Run is not paused")
    run.meta = {**(run.meta or {}), "paused": False}
    run.result_summary = None
    TaskService(db).record_event(run.id, "resumed", {})
    db.commit()
    db.refresh(run)
    audit(db, action="scan_run.resumed", request=request, resource_type="task", resource_id=run_id)
    await manager.broadcast(event_task_updated(run_id, _task_dict(run)))
    return run


@router.post("/{run_id}/cancel", response_model=TaskResponse)
async def cancel_scan_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    from api.tasks import stop_task
    return await stop_task(run_id, request, db)


@router.post("/{run_id}/retry", response_model=TaskResponse)
async def retry_scan_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    _get(db, run_id)
    row = TaskService(db).retry(run_id)
    if row is None:
        raise HTTPException(409, "Only failed, needs_review, or done Scan Runs can be retried")
    audit(db, action="scan_run.retried", request=request, resource_type="task", resource_id=run_id)
    await manager.broadcast(event_task_updated(run_id, _task_dict(row)))
    return row
