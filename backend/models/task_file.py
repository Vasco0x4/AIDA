"""
TaskFile — a user-uploaded context file attached to a task (txt, pdf, html, md…).

Unlike Artifact (evidence OUTPUT tied to a finding), a TaskFile is INPUT context:
supporting material the agent should read while working (a scope doc, a prior
report, notes). We store the bytes plus extracted text so the agent can consume
it directly.
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, LargeBinary
from sqlalchemy.sql import func
from database import Base


class TaskFile(Base):
    __tablename__ = "task_files"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False, default="application/octet-stream")
    size_bytes = Column(Integer, nullable=True)
    # Extracted plain text for the agent to read (empty if not extractable).
    extracted_text = Column(Text, nullable=True)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
