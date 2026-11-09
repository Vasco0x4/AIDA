"""
Pending Command model for command approval workflow
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class PendingCommand(Base):
    __tablename__ = "pending_commands"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    command = Column(Text, nullable=False)
    phase = Column(String(50))
    command_type = Column(String(20), default='shell')  # 'shell' | 'python'
    matched_keywords = Column(JSON, default=[])  # Keywords that triggered the filter
    status = Column(String(20), default="pending", index=True)  # pending, approved, rejected, executed, timeout
    # E4 PoC approval chain: exploit-class commands are flagged at creation so
    # they can require admin sign-off (and a longer human timeout).
    risk_level = Column(String(20), default="normal")   # 'normal' | 'high'
    risk_reason = Column(String(100))
    
    # Resolution tracking
    resolved_by = Column(String(100))
    rejection_reason = Column(Text)
    resolved_at = Column(TIMESTAMP)
    
    # Execution result (after approval)
    execution_result = Column(JSON)  # Stores result once executed
    
    created_at = Column(TIMESTAMP, server_default=func.now())
    timeout_seconds = Column(Integer, nullable=True)  # None = use global setting

    # Relationship
    assessment = relationship("Assessment", back_populates="pending_commands")

