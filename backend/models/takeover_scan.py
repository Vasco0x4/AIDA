"""
Persisted subdomain-takeover scans + per-asset results.

A TakeoverScan is one run against a domain; TakeoverResult rows are the
per-subdomain verdicts, each with an optional user `note`. Persisting these
gives scan history that survives restarts, is deletable, and lets the operator
annotate individual assets.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class TakeoverScan(Base):
    __tablename__ = "takeover_scans"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running")  # running|done|error
    wildcard = Column(Boolean, default=False)
    checked = Column(Integer, default=0)
    total = Column(Integer, default=0)
    vulnerable = Column(Integer, default=0)
    edge_case = Column(Integer, default=0)
    not_vulnerable = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    finished_at = Column(TIMESTAMP, nullable=True)

    results = relationship("TakeoverResult", back_populates="scan",
                           cascade="all, delete-orphan")


class TakeoverResult(Base):
    __tablename__ = "takeover_results"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("takeover_scans.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    subdomain = Column(String(512), nullable=False)
    verdict = Column(String(20), nullable=False)          # VULNERABLE|EDGE_CASE|NOT_VULNERABLE
    service = Column(String(120), nullable=True)
    confidence = Column(String(20), nullable=True)
    cname_target = Column(String(512), nullable=True)
    dns_status = Column(String(30), nullable=True)
    evidence = Column(Text, nullable=True)
    fingerprint = Column(Text, nullable=True)
    documentation = Column(String(512), nullable=True)
    note = Column(Text, nullable=True)                    # operator's own note on the asset
    created_at = Column(TIMESTAMP, server_default=func.now())

    scan = relationship("TakeoverScan", back_populates="results")
