"""
Agent Run SQLAlchemy model

Represents a headless Claude Code session launched from the UI against a
specific assessment. The CLI path (`python3 aida.py`) does not create rows
here — it remains a fully independent workflow.
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # User who started the run. SET NULL on delete so audit history survives
    # user removal.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # User-provided goal / prompt fragment for this scan
    goal = Column(Text, nullable=False)

    # queued | running | completed | failed | stopped
    status = Column(String(20), nullable=False, default="queued", index=True)

    # Claude permission mode (e.g. "acceptEdits", "bypassPermissions")
    permission_mode = Column(String(32), nullable=True)

    # Model name reported by the SDK (e.g. "claude-sonnet-4-6")
    model = Column(String(64), nullable=True)

    # Populated on failure
    error = Column(Text, nullable=True)

    # Summary stats pulled from the SDK "result" message
    num_turns = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Full event stream captured from the SDK. List[dict]. Kept inline for
    # now; can be split into a child table later without changing the API
    # surface.
    transcript = Column(JSONB, nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)
    started_at = Column(TIMESTAMP, nullable=True)
    ended_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    assessment = relationship("Assessment", back_populates="agent_runs")
    user = relationship("User")
