"""Persistent cache and scheduling state for the NVD CVE digest."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class NVDCVE(Base):
    """One deduplicated CVE, retained across refreshes for stale fallback."""

    __tablename__ = "nvd_cves"

    cve_id = Column(String(32), primary_key=True)
    cvss_score = Column(Float)
    cvss_severity = Column(String(16))
    cvss_version = Column(String(8))
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_modified_at = Column(DateTime(timezone=True))
    description = Column(Text, nullable=False, default="")
    affected_products = Column(JSONB, nullable=False, default=list)
    nvd_url = Column(String(512), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class NVDDigestState(Base):
    """Singleton (id=1) schedule, last successful window, and freshness state."""

    __tablename__ = "nvd_digest_state"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    refresh_interval_hours = Column(Integer, nullable=False, default=24)
    lookback_days = Column(Integer, nullable=False, default=1)
    max_items = Column(Integer, nullable=False, default=100)
    include_cvss_v4 = Column(Boolean, nullable=False, default=False)
    window_start = Column(DateTime(timezone=True))
    window_end = Column(DateTime(timezone=True))
    last_attempt_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    next_refresh_at = Column(DateTime(timezone=True), index=True)
    last_error = Column(Text)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    item_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
