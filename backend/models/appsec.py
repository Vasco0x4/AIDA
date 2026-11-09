"""AppSec source snapshots and review results, independent of network scans."""
from sqlalchemy import Column, Integer, String, Text, JSON, LargeBinary, ForeignKey, TIMESTAMP
from sqlalchemy.orm import deferred
from sqlalchemy.sql import func
from database import Base


class AppSecProject(Base):
    __tablename__ = 'appsec_projects'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    repository_url = Column(String(500), nullable=False, default='')
    created_at = Column(TIMESTAMP, server_default=func.now())


class AppSecScan(Base):
    __tablename__ = 'appsec_scans'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('appsec_projects.id'), nullable=False, index=True)
    status = Column(String(24), nullable=False, default='queued', index=True)
    source = Column(String(24), nullable=False)
    requested_ref = Column(String(160), nullable=False)
    commit_sha = Column(String(64))
    archive_sha256 = Column(String(64))
    archive = deferred(Column(LargeBinary))
    model_config_id = Column(Integer, ForeignKey('ai_model_configs.id', ondelete='SET NULL'))
    ai_requested = Column(Integer, nullable=False, default=0)
    summary = Column(JSON, nullable=False, default=dict)
    error = Column(Text)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    created_at = Column(TIMESTAMP, server_default=func.now())
    completed_at = Column(TIMESTAMP)


class AppSecFinding(Base):
    __tablename__ = 'appsec_findings'
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey('appsec_scans.id'), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    rule_id = Column(String(80), nullable=False)
    category = Column(String(30), nullable=False)
    severity = Column(String(16), nullable=False)
    confidence = Column(String(16), nullable=False)
    path = Column(String(500), nullable=False)
    line = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default='open')
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='SET NULL'))
