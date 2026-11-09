"""Saved Scan Profiles and schedule policy snapshots.

Revision ID: 005_scan_profiles
Revises: 004_finding_lifecycle
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_scan_profiles"
down_revision: Union[str, None] = "004_finding_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("kind", sa.String(40), nullable=False, server_default="safe_web_baseline"),
        sa.Column("description", sa.Text()),
        sa.Column("rate_limit_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False, server_default="1000000"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now()),
    )
    op.create_index("scan_profiles_name_idx", "scan_profiles", ["name"], unique=True)
    op.add_column("scheduled_engagements", sa.Column("scan_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_schedules_scan_profile", "scheduled_engagements", "scan_profiles",
                          ["scan_profile_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_schedules_scan_profile", "scheduled_engagements", type_="foreignkey")
    op.drop_column("scheduled_engagements", "scan_profile_id")
    op.drop_table("scan_profiles")
