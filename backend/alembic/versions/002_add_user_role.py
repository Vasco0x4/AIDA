"""Add role column to users table

Revision ID: 002_add_user_role
Revises: 001_initial_schema
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "002_add_user_role"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
    )


def downgrade():
    op.drop_column("users", "role")
