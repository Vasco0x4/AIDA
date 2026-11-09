"""Write-only Git credentials and explicit repository grants."""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func
from database import Base


class GitConnection(Base):
    __tablename__ = 'appsec_git_connections'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(12), nullable=False)
    origin = Column(String(255), nullable=False)
    token_encrypted = Column(Text, nullable=False)
    allow_private_network = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    account = Column(String(160), nullable=False, default='')
    checked_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())


class GitRepository(Base):
    __tablename__ = 'appsec_git_repositories'
    __table_args__ = (UniqueConstraint('connection_id', 'provider_id'),)
    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey('appsec_git_connections.id'), nullable=False, index=True)
    provider_id = Column(String(40), nullable=False)
    path = Column(String(500), nullable=False)
    default_branch = Column(String(160), nullable=False, default='main')
    allowed = Column(Boolean, nullable=False, default=False)
    project_id = Column(Integer, ForeignKey('appsec_projects.id'), unique=True, nullable=False)
