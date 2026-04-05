"""
Timeline Event SQLAlchemy model
Tracks attack chain events: recon -> exploitation -> post-exploitation
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)

    # Event classification
    phase = Column(String(50), nullable=False, index=True)  # recon, scanning, exploitation, post_exploitation, reporting
    event_type = Column(String(50), nullable=False)  # command, finding, observation, recon, credential, manual
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # Links to related entities (optional)
    command_id = Column(Integer, ForeignKey("command_history.id", ondelete="SET NULL"), nullable=True)
    card_id = Column(Integer, ForeignKey("cards.id", ondelete="SET NULL"), nullable=True)
    recon_id = Column(Integer, ForeignKey("recon_data.id", ondelete="SET NULL"), nullable=True)

    # Visual metadata
    severity = Column(String(20))  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    icon = Column(String(50))  # icon hint for frontend
    tags = Column(Text)  # comma-separated tags

    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    assessment = relationship("Assessment", back_populates="timeline_events")
    command = relationship("CommandHistory", foreign_keys=[command_id])
    card = relationship("Card", foreign_keys=[card_id])
    recon = relationship("ReconData", foreign_keys=[recon_id])
