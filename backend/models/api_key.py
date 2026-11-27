"""
API-key model for the HTTP MCP transport.

Each row represents a long-lived bearer token issued to a user so an
AI client (Claude Desktop, Claude Code, Cursor, etc.) can authenticate
against the ``/mcp`` endpoint.

Storage rules:
- Only the bcrypt hash of the full key is persisted (``key_hash``).
- A short human-readable prefix is kept for UI display (``key_prefix``).
- The full key is shown to the user exactly once at creation time.
- Revocation is soft (``revoked_at``) so the audit trail survives.
- ``assessment_id`` binds a key to one assessment: its MCP client only
  sees that assessment. Required for "agent" keys (one per `aida run`
  container); deleting the assessment deletes its keys.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(16), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope = Column(String(20), nullable=False, default="mcp")
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", backref="api_keys")
    assessment = relationship("Assessment")
