"""One immutable observation of a canonical finding in a Scan Run."""
from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class FindingSnapshot(Base):
    __tablename__ = "finding_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id = Column(Integer, ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    target_service = Column(Text)
    severity = Column(String(20))
    triage_status = Column(String(40))
    lifecycle_status = Column(String(40), nullable=False, default="new")
    technical_analysis = Column(Text)
    proof = Column(Text)
    observed_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "fingerprint", name="uq_finding_snapshot_run_fingerprint"),
        Index("finding_snapshots_assessment_run_idx", "assessment_id", "run_id"),
    )
