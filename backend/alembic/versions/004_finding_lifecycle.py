"""Canonical finding lifecycle and per-Scan-Run snapshots.

Revision ID: 004_finding_lifecycle
Revises: 003_recurring_scan_runs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_finding_lifecycle"
down_revision: Union[str, None] = "003_recurring_scan_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column("lifecycle_status", sa.String(40), nullable=False, server_default="new"),
        sa.Column("first_seen_run_id", sa.Integer(), nullable=True),
        sa.Column("last_seen_run_id", sa.Integer(), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("cards", column)
    op.create_index("cards_assessment_fingerprint_idx", "cards", ["assessment_id", "fingerprint"], unique=True)
    op.create_index("cards_lifecycle_status_idx", "cards", ["lifecycle_status"])

    op.create_table(
        "finding_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("target_service", sa.Text()),
        sa.Column("severity", sa.String(20)),
        sa.Column("triage_status", sa.String(40)),
        sa.Column("lifecycle_status", sa.String(40), nullable=False, server_default="new"),
        sa.Column("technical_analysis", sa.Text()),
        sa.Column("proof", sa.Text()),
        sa.Column("observed_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "fingerprint", name="uq_finding_snapshot_run_fingerprint"),
    )
    op.create_index("finding_snapshots_assessment_run_idx", "finding_snapshots", ["assessment_id", "run_id"])
    op.create_index("finding_snapshots_run_idx", "finding_snapshots", ["run_id"])
    op.create_index("finding_snapshots_card_idx", "finding_snapshots", ["card_id"])


def downgrade() -> None:
    op.drop_table("finding_snapshots")
    op.drop_index("cards_lifecycle_status_idx", table_name="cards")
    op.drop_index("cards_assessment_fingerprint_idx", table_name="cards")
    for column in ("seen_count", "last_seen_at", "last_seen_run_id", "first_seen_run_id", "lifecycle_status", "fingerprint"):
        op.drop_column("cards", column)
