"""
TaskComment — a note/comment thread on a task.

Comments are context the agent reads: a user can drop instructions or hints on a
task (or its parent audit) and the agent picks them up on its next run. The agent
can also post comments back (author="agent").
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from database import Base


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author = Column(String(120), nullable=False, default="user")  # username | agent | system
    body = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
