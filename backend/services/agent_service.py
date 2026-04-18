"""
Agent runs service — thin DB layer + hook into the AgentRunner.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from agent import agent_runner
from models import AgentRun, Assessment
from schemas.agent_run import AgentRunCreate
from utils.logger import get_logger

logger = get_logger(__name__)


ACTIVE_STATUSES = {"queued", "running"}


class AgentServiceError(Exception):
    """Domain-level error raised by AgentService; translated to HTTP in the API."""


class AgentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- queries -------------------------------------------------------
    def get_run(self, run_id: int) -> Optional[AgentRun]:
        return self.db.query(AgentRun).filter(AgentRun.id == run_id).first()

    def list_runs(
        self,
        assessment_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AgentRun]:
        return (
            self.db.query(AgentRun)
            .filter(AgentRun.assessment_id == assessment_id)
            .order_by(AgentRun.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_runs(self, assessment_id: int) -> int:
        return (
            self.db.query(AgentRun)
            .filter(AgentRun.assessment_id == assessment_id)
            .count()
        )

    def has_active_run(self, assessment_id: int) -> bool:
        return (
            self.db.query(AgentRun)
            .filter(
                AgentRun.assessment_id == assessment_id,
                AgentRun.status.in_(ACTIVE_STATUSES),
            )
            .first()
            is not None
        )

    # --- commands ------------------------------------------------------
    async def create_run(
        self,
        assessment_id: int,
        user_id: Optional[int],
        payload: AgentRunCreate,
    ) -> AgentRun:
        """Create a queued AgentRun row and schedule the session task."""
        assessment = (
            self.db.query(Assessment).filter(Assessment.id == assessment_id).first()
        )
        if assessment is None:
            raise AgentServiceError(f"Assessment {assessment_id} not found")

        # One active run per assessment keeps the mock path simple and
        # prevents mixed transcripts in the UI. Relax later if needed.
        if self.has_active_run(assessment_id):
            raise AgentServiceError(
                "An agent run is already active for this assessment"
            )

        run = AgentRun(
            assessment_id=assessment_id,
            user_id=user_id,
            goal=payload.goal.strip(),
            status="queued",
            permission_mode=payload.permission_mode,
            model=payload.model,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            await agent_runner.start(
                run_id=run.id,
                assessment_id=assessment_id,
                goal=run.goal,
                permission_mode=run.permission_mode,
                model=run.model,
            )
        except Exception:
            # If scheduling fails, don't leave a ghost "queued" row behind.
            logger.exception("Failed to schedule agent run", run_id=run.id)
            run.status = "failed"
            run.error = "Failed to schedule session task"
            self.db.commit()
            raise

        logger.info(
            "Agent run created",
            run_id=run.id,
            assessment_id=assessment_id,
            user_id=user_id,
        )
        return run

    async def stop_run(self, run_id: int) -> AgentRun:
        run = self.get_run(run_id)
        if run is None:
            raise AgentServiceError(f"Agent run {run_id} not found")
        if run.status not in ACTIVE_STATUSES:
            raise AgentServiceError(
                f"Agent run {run_id} is not active (status={run.status})"
            )

        cancelled = await agent_runner.stop(run_id)
        if not cancelled:
            # Task isn't in the registry (e.g. process restart after crash).
            # Reconcile the DB state so the UI doesn't show a stuck row.
            from datetime import datetime, timezone

            run.status = "stopped"
            run.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.commit()
            self.db.refresh(run)

        return run
