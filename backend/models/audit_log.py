"""
Immutable-style audit trail (E2): who did what, when, from where.

Rows are append-only by convention (no update/delete endpoints exist). Details
are PII/secret-redacted at write time (services/audit_service.record).
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    actor_id = Column(Integer, nullable=True, index=True)
    actor_username = Column(String(50), nullable=True)  # snapshot, survives user deletion
    action = Column(String(100), nullable=False, index=True)  # dotted, e.g. "auth.login.success"
    resource_type = Column(String(50), nullable=True)   # task / user / model / …
    resource_id = Column(String(64), nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    detail = Column(JSONB, default={})
    success = Column(Boolean, default=True, nullable=False, index=True)
