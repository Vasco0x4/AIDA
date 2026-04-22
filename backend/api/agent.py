"""
Agent runs API — start, inspect and stop UI-initiated Claude sessions.

Endpoints:
    POST   /assessments/{assessment_id}/agent/runs       — start a new run
    GET    /assessments/{assessment_id}/agent/runs       — list runs (newest first)
    GET    /agent/runs/{run_id}                          — full run (with transcript)
    POST   /agent/runs/{run_id}/stop                     — cancel a running session
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User
from schemas.agent_run import (
    AgentRunCreate,
    AgentRunResponse,
    AgentRunSummary,
    AgentRunListResponse,
)
from services.agent_service import AgentService, AgentServiceError
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["agent"])


@router.post(
    "/assessments/{assessment_id}/agent/runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_run(
    assessment_id: int,
    payload: AgentRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new agent run for this assessment."""
    service = AgentService(db)
    try:
        run = await service.create_run(
            assessment_id=assessment_id,
            user_id=current_user.id,
            payload=payload,
        )
    except AgentServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    return run


@router.get(
    "/assessments/{assessment_id}/agent/runs",
    response_model=AgentRunListResponse,
)
async def list_agent_runs(
    assessment_id: int,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Return runs for this assessment (newest first, transcript omitted)."""
    service = AgentService(db)
    runs = service.list_runs(assessment_id, skip=skip, limit=limit)
    total = service.count_runs(assessment_id)
    return AgentRunListResponse(
        runs=[AgentRunSummary.model_validate(r) for r in runs],
        total=total,
    )


@router.get("/agent/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: int, db: Session = Depends(get_db)):
    """Return the full state of a single run, including transcript."""
    service = AgentService(db)
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )
    return run


@router.post("/agent/runs/{run_id}/stop", response_model=AgentRunResponse)
async def stop_agent_run(run_id: int, db: Session = Depends(get_db)):
    """Request cancellation of an active agent run."""
    service = AgentService(db)
    try:
        run = await service.stop_run(run_id)
    except AgentServiceError as exc:
        # "not found" maps to 404, everything else to 400
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(exc))
    return run
