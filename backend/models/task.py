"""
Task = the unit of autonomous work, and the card on the Kanban board.

A task is created from the UI, the API, or Telegram. The agent runner picks up
tasks in the "queued" column, runs a plan→act→observe loop against the existing
tool surface, and moves the task across columns as it progresses. Kanban columns
ARE the workflow stages, so one model backs both the board and the runner.

Safety: every task must carry an explicit ``authorized_scope`` and its
``execution_target`` defaults to the sandboxed container. Host execution is
opt-in per task.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, object_session
from database import Base


# Kanban columns == workflow stages. Kept as a simple set for Phase 1;
# custom user columns can come later.
TASK_COLUMNS = (
    "backlog",       # captured, not ready
    "queued",        # ready for the agent to pick up
    "running",       # agent actively working
    "needs_review",  # agent produced findings / hit an approval gate
    "done",          # completed
    "failed",        # errored or aborted
)

TASK_PRIORITIES = ("low", "medium", "high", "critical")
EXECUTION_TARGETS = ("container", "host")
TASK_SOURCES = ("ui", "api", "telegram", "schedule")

# Kill-chain phases used to break an audit into ordered, specialized sub-tasks.
# Each phase primes its sub-agent with the relevant skills from the skill base.
TASK_PHASES = ("recon", "enumeration", "exploitation", "post_exploitation", "reporting")
PHASE_SKILLS = {
    "recon": ["pentest-methodology", "offensive-osint", "osint-methodology"],
    "enumeration": ["pentest-methodology", "network-service-exploitation", "api-security-testing"],
    "exploitation": ["web-cve-exploitation", "web-vuln-hunting",
                     "network-service-exploitation", "deserialization-attacks"],
    "post_exploitation": ["post-exploitation-pivoting", "privilege-escalation",
                          "active-directory-attack-paths"],
    "reporting": ["security-reporting"],
}
# Every active phase also inherits the mandatory safety doctrine.
MANDATORY_SKILL = "safe-testing-doctrine"
PHASE_ROLE = {
    "recon": "Recon Agent",
    "enumeration": "Enumeration Agent",
    "exploitation": "Exploitation Agent",
    "post_exploitation": "Post-Exploitation Agent",
    "reporting": "Reporting Agent",
}


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    # A task may spawn / attach to an assessment (nullable until it starts).
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # What to test: a URL, a bug-bounty program handle, an IP range, etc.
    target = Column(String(512), nullable=True)

    # SAFETY: explicit authorization boundary. The runner refuses to act
    # without it. Free text: in-scope hosts/domains, exclusions, rules.
    authorized_scope = Column(Text, nullable=True)

    # Kanban column / workflow stage (see TASK_COLUMNS).
    status = Column(String(30), nullable=False, default="backlog", index=True)
    # Ordering within a column.
    position = Column(Integer, nullable=False, default=0)

    # SQLAlchemy includes this in every ORM UPDATE, preventing stale sessions
    # from silently overwriting a newer task state.
    version = Column(Integer, nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}

    priority = Column(String(20), nullable=False, default="medium")

    # container (sandboxed, default) | host (opt-in, dangerous)
    execution_target = Column(String(20), nullable=False, default="container")

    # Which model backend runs this task (nullable → use default).
    model_config_id = Column(
        Integer,
        ForeignKey("ai_model_configs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # E3 reliability: token budget for this task (prompt+completion combined).
    # NULL → use the platform default (agent_token_budget; 0 = unlimited).
    token_budget = Column(Integer, nullable=True)

    source = Column(String(20), nullable=False, default="ui")

    # --- Orchestration (parent audit → ordered specialized sub-tasks) ---
    # A top-level task with orchestrate=True is decomposed by the planner into
    # child tasks (parent_task_id set), one per phase/role, executed in
    # order_index sequence. Children share the parent's assessment.
    parent_task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    orchestrate = Column(Boolean, default=True)   # plan sub-tasks on pickup
    phase = Column(String(30), nullable=True)     # recon/enumeration/... (children)
    role = Column(String(60), nullable=True)      # "Recon Agent", etc.
    order_index = Column(Integer, nullable=False, default=0)  # sequence within parent

    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Free label for who/what owns it (agent id or username).
    assignee = Column(String(120), nullable=True)

    # Durable worker ownership. A lease is renewed by heartbeat and can only be
    # recovered after lease_expires_at; a process-wide crash can recover it too.
    lease_owner = Column(String(120), nullable=True, index=True)
    lease_token = Column(String(36), nullable=True, index=True)
    heartbeat_at = Column(TIMESTAMP, nullable=True)
    lease_expires_at = Column(TIMESTAMP, nullable=True, index=True)

    # Rolling result summary produced by the agent.
    result_summary = Column(Text, nullable=True)
    # Structured extras (plan, step counts, error, tokens, etc.).
    meta = Column(JSONB, default={})

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)

    assessment = relationship("Assessment", foreign_keys=[assessment_id])

    @property
    def dependency_ids(self) -> list[int]:
        session = object_session(self)
        if session is None:
            return []
        return [row[0] for row in session.query(TaskDependency.depends_on_id).filter(
            TaskDependency.task_id == self.id).order_by(TaskDependency.depends_on_id).all()]


class TaskEvent(Base):
    """Append-only durable history of task lifecycle and reliability actions."""

    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    payload = Column(JSONB, nullable=False, default={})
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), index=True)


class TaskDependency(Base):
    """An explicit DAG edge: task_id may run only after depends_on_id is done."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependency"),
    )

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    depends_on_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
