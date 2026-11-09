"""
Scheduled Engagement model — cron-triggered recurring audits (E4).

A scheduled engagement is a task TEMPLATE plus a cron expression: when due, the
scheduler enqueues a Task from it (source="schedule") carrying provenance in
meta.scheduled (engagement id, run number, previous assessment) so recurring
audits can be diffed and traced back to the schedule.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func

from database import Base


class ScheduledEngagement(Base):
    __tablename__ = "scheduled_engagements"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    # Standard 5-field cron expression, interpreted in UTC.
    cron = Column(String(64), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")

    # One Assessment owns every recurring Scan Run (Task). NULL is retained
    # only for legacy schedules; their first new run adopts the created
    # Assessment and subsequent runs reuse it.
    assessment_id = Column(
        Integer, ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scan_profile = Column(String(40), nullable=False, default="autonomous")
    scan_profile_id = Column(Integer, ForeignKey("scan_profiles.id", ondelete="SET NULL"), nullable=True)
    rate_limit_seconds = Column(Integer, nullable=False, default=60)
    max_concurrency = Column(Integer, nullable=False, default=1)
    authorization_reference = Column(Text)
    authorization_confirmed = Column(Boolean, nullable=False, default=False)

    # Task template (mirrors the New-Task modal fields).
    task_title = Column(String(255), nullable=False)
    description = Column(Text)
    target = Column(String(512))
    authorized_scope = Column(Text)
    priority = Column(String(20), default="medium")
    model_config_id = Column(Integer)
    orchestrate = Column(Boolean, nullable=False, default=True)
    token_budget = Column(Integer)

    # Scheduling state.
    last_run_at = Column(TIMESTAMP)
    next_run_at = Column(TIMESTAMP, index=True)
    last_task_id = Column(Integer)
    run_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)

    created_by = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
