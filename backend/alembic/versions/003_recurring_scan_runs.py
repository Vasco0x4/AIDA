"""Recurring Scan Runs reuse an existing Assessment.

Revision ID: 003_recurring_scan_runs
Revises: 002_user_roles
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "003_recurring_scan_runs"
down_revision: Union[str, None] = "002_user_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 001 predates the task runner and scheduler. Fresh Alembic deployments
    # need those compatibility tables before this revision can add its columns.
    # Existing installations are left untouched; startup create_all remains the
    # authority for unrelated models introduced after 001.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("tasks"):
        op.create_table(
            "tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id", ondelete="SET NULL")),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("target", sa.String(512)),
            sa.Column("authorized_scope", sa.Text()),
            sa.Column("status", sa.String(30), nullable=False, server_default="backlog"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
            sa.Column("execution_target", sa.String(20), nullable=False, server_default="container"),
            sa.Column("model_config_id", sa.Integer()),
            sa.Column("token_budget", sa.Integer()),
            sa.Column("source", sa.String(20), nullable=False, server_default="ui"),
            sa.Column("parent_task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
            sa.Column("orchestrate", sa.Boolean(), server_default=sa.true()),
            sa.Column("phase", sa.String(30)),
            sa.Column("role", sa.String(60)),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("assignee", sa.String(120)),
            sa.Column("lease_owner", sa.String(120)),
            sa.Column("lease_token", sa.String(36)),
            sa.Column("heartbeat_at", sa.TIMESTAMP()),
            sa.Column("lease_expires_at", sa.TIMESTAMP()),
            sa.Column("result_summary", sa.Text()),
            sa.Column("meta", JSONB()),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.Column("started_at", sa.TIMESTAMP()),
            sa.Column("completed_at", sa.TIMESTAMP()),
        )
        op.create_index("tasks_assessment_idx", "tasks", ["assessment_id"])
        op.create_index("tasks_status_idx", "tasks", ["status"])
        op.execute("COMMENT ON TABLE tasks IS 'aida:fresh-baseline:003'")
    if not inspector.has_table("scheduled_engagements"):
        op.create_table(
            "scheduled_engagements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("cron", sa.String(64), nullable=False),
            sa.Column("task_title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("target", sa.String(512)),
            sa.Column("authorized_scope", sa.Text()),
            sa.Column("priority", sa.String(20), server_default="medium"),
            sa.Column("model_config_id", sa.Integer()),
            sa.Column("orchestrate", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("token_budget", sa.Integer()),
            sa.Column("last_run_at", sa.TIMESTAMP()),
            sa.Column("next_run_at", sa.TIMESTAMP()),
            sa.Column("last_task_id", sa.Integer()),
            sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        )
        op.execute("COMMENT ON TABLE scheduled_engagements IS 'aida:fresh-baseline:003'")
    op.add_column("scheduled_engagements", sa.Column("assessment_id", sa.Integer(), nullable=True))
    op.add_column("scheduled_engagements", sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"))
    op.add_column("scheduled_engagements", sa.Column("scan_profile", sa.String(40), nullable=False, server_default="autonomous"))
    op.add_column("scheduled_engagements", sa.Column("rate_limit_seconds", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("scheduled_engagements", sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("scheduled_engagements", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("scheduled_engagements", sa.Column("authorization_reference", sa.Text(), nullable=True))
    op.add_column("scheduled_engagements", sa.Column("authorization_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key(
        "fk_scheduled_engagements_assessment", "scheduled_engagements", "assessments",
        ["assessment_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("scheduled_engagements_assessment_idx", "scheduled_engagements", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("scheduled_engagements_assessment_idx", table_name="scheduled_engagements")
    op.drop_constraint("fk_scheduled_engagements_assessment", "scheduled_engagements", type_="foreignkey")
    for column in (
        "authorization_confirmed", "authorization_reference", "last_error",
        "max_concurrency", "rate_limit_seconds", "scan_profile", "timezone", "assessment_id",
    ):
        op.drop_column("scheduled_engagements", column)
    # Remove compatibility tables only when this revision created them on a
    # fresh 001 database. Never drop pre-existing task/schedule data.
    bind = op.get_bind()
    marker = "aida:fresh-baseline:003"
    scheduled_marker = bind.execute(sa.text(
        "SELECT obj_description('scheduled_engagements'::regclass, 'pg_class')")).scalar()
    tasks_marker = bind.execute(sa.text(
        "SELECT obj_description('tasks'::regclass, 'pg_class')")).scalar()
    if scheduled_marker == marker:
        op.drop_table("scheduled_engagements")
    if tasks_marker == marker:
        op.drop_table("tasks")
