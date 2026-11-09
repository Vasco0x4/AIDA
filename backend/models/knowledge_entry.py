"""
KnowledgeEntry = one piece of offensive-security reference knowledge.

A research/reference layer the autonomous agent (and the human) can consult:
public CVE/advisory metadata, CWE references, and methodology playbooks. This is
deliberately a *knowledge* store — descriptions, references, and test methodology
— not a repository of weaponized exploits.
"""
from sqlalchemy import Column, Integer, String, Text, Float, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, index=True)

    # nvd | ghsa | exploitdb | playbook | manual
    source = Column(String(30), nullable=False, default="manual", index=True)
    # External id where applicable: CVE-2024-1234, GHSA-xxxx, etc.
    ext_id = Column(String(80), nullable=True, index=True)

    title = Column(String(400), nullable=False)
    description = Column(Text, nullable=True)
    # Methodology / notes / how-to-test (esp. for playbooks).
    content = Column(Text, nullable=True)

    severity = Column(String(20), nullable=True)     # CRITICAL/HIGH/... or CVSS band
    cvss_score = Column(Float, nullable=True)
    cwe = Column(String(40), nullable=True)          # e.g. CWE-89

    references = Column(JSONB, default=list)         # list of URLs
    tags = Column(String(400), nullable=True)        # comma-separated

    created_at = Column(TIMESTAMP, server_default=func.now())
