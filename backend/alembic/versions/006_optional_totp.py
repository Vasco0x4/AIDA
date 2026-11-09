"""Optional per-user TOTP enrollment and login challenges.

Revision ID: 006_optional_totp
Revises: 005_scan_profiles
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_optional_totp"
down_revision: Union[str, None] = "005_scan_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_provider", sa.String(20), nullable=False, server_default="local"))
    op.add_column("users", sa.Column("otp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("otp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("otp_pending_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("otp_last_timestep", sa.BigInteger(), nullable=True))

    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_otp_challenges_user_id", "otp_challenges", ["user_id"])
    op.create_index("ix_otp_challenges_expires_at", "otp_challenges", ["expires_at"])

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index("ix_otp_challenges_expires_at", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_user_id", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    op.drop_column("users", "otp_last_timestep")
    op.drop_column("users", "otp_pending_secret_encrypted")
    op.drop_column("users", "otp_secret_encrypted")
    op.drop_column("users", "otp_enabled")
    op.drop_column("users", "auth_provider")
