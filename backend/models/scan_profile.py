"""Reusable bounded Scan Profile definitions."""
from sqlalchemy import Boolean, Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from database import Base


class ScanProfile(Base):
    __tablename__ = "scan_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    kind = Column(String(40), nullable=False, default="safe_web_baseline")
    description = Column(Text)
    rate_limit_seconds = Column(Integer, nullable=False, default=60)
    max_pages = Column(Integer, nullable=False, default=8)
    max_response_bytes = Column(Integer, nullable=False, default=1_000_000)
    timeout_seconds = Column(Integer, nullable=False, default=5)
    max_concurrency = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
