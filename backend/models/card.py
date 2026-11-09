"""
Card SQLAlchemy model (Finding/Observation/Info)
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    card_type = Column(String(50), nullable=False)  # finding, observation, info
    section_number = Column(String(20), index=True)  # "3.2", "4.5"

    title = Column(String(255), nullable=False)
    target_service = Column(String(255))

    # Finding specific
    status = Column(String(50))  # confirmed, potential, untested
    severity = Column(String(20))  # CRITICAL, HIGH, MEDIUM, LOW, INFO

    # CVSS 4.0
    cvss_vector = Column(String(255))  # e.g. "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
    cvss_score = Column(Float)          # e.g. 9.3

    # Common fields
    technical_analysis = Column(Text)
    notes = Column(Text)
    proof = Column(Text)
    context = Column(Text)

    # E4 compliance mapping: manual override of the auto-classifier,
    # {"owasp": ["A03:2021"], "pci": ["6.5.1"]} — framework → codes.
    compliance_refs = Column(JSONB)

    # Canonical identity across recurring Scan Runs. Mutable triage, severity
    # and evidence are deliberately excluded from the fingerprint.
    fingerprint = Column(String(64))
    lifecycle_status = Column(String(40), nullable=False, default="new", index=True)
    first_seen_run_id = Column(Integer)
    last_seen_run_id = Column(Integer)
    last_seen_at = Column(TIMESTAMP)
    seen_count = Column(Integer, nullable=False, default=0)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationship
    assessment = relationship("Assessment", back_populates="cards")

    __table_args__ = (
        Index("cards_assessment_fingerprint_idx", "assessment_id", "fingerprint", unique=True),
    )
