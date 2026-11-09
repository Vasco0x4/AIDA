"""
Artifact = a binary evidence file (screenshot, capture, attachment) linked to an
assessment and optionally to a specific finding card. Bytes are stored in the DB
(bytea) so they embed cleanly into the PDF report and need no external storage.
"""
from sqlalchemy import (
    Column, Integer, String, Text, TIMESTAMP, ForeignKey, LargeBinary
)
from sqlalchemy.sql import func
from database import Base


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, index=True)

    assessment_id = Column(
        Integer, ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Optional link to the finding this evidence supports.
    card_id = Column(
        Integer, ForeignKey("cards.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    kind = Column(String(30), nullable=False, default="screenshot")  # screenshot | file
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False, default="application/octet-stream")
    caption = Column(Text, nullable=True)
    size_bytes = Column(Integer, nullable=True)

    data = Column(LargeBinary, nullable=False)

    # E3 evidence hash chain (tamper-evidence): each artifact's hash covers the
    # previous chained artifact's hash + this artifact's bytes, so any later
    # modification (or a removed artifact) breaks the chain for the assessment.
    hash_prev = Column(String(64), nullable=True)
    hash_self = Column(String(64), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
