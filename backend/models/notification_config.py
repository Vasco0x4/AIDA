"""
Notification Configuration SQLAlchemy model
Stores notification channel settings (Telegram, Slack, Email)
"""
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id = Column(Integer, primary_key=True, index=True)

    # Channel type: telegram, slack, email
    channel = Column(String(50), nullable=False, unique=True)
    enabled = Column(Boolean, default=False)

    # Channel-specific config stored as JSON
    # Telegram: {"bot_token": "...", "chat_id": "..."}
    # Slack: {"webhook_url": "..."}
    # Email: {"smtp_host": "...", "smtp_port": 587, "username": "...", "password": "...", "from_email": "...", "to_emails": ["..."]}
    config = Column(JSONB, default={})

    # What events trigger notifications
    on_critical_finding = Column(Boolean, default=True)
    on_high_finding = Column(Boolean, default=True)
    on_scan_complete = Column(Boolean, default=False)
    on_assessment_complete = Column(Boolean, default=False)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
