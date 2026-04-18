"""Add agent_runs table for UI-initiated Claude sessions

Revision ID: 003_agent_runs
Revises: 002_user_roles
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '003_agent_runs'
down_revision: Union[str, None] = '002_user_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'assessment_id',
            sa.Integer(),
            sa.ForeignKey('assessments.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('goal', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='queued',
        ),
        sa.Column('permission_mode', sa.String(32), nullable=True),
        sa.Column('model', sa.String(64), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('num_turns', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('transcript', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('started_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('ended_at', sa.TIMESTAMP(), nullable=True),
    )
    op.create_index(
        'ix_agent_runs_assessment_id', 'agent_runs', ['assessment_id']
    )
    op.create_index('ix_agent_runs_user_id', 'agent_runs', ['user_id'])
    op.create_index('ix_agent_runs_status', 'agent_runs', ['status'])
    op.create_index('ix_agent_runs_created_at', 'agent_runs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_agent_runs_created_at', table_name='agent_runs')
    op.drop_index('ix_agent_runs_status', table_name='agent_runs')
    op.drop_index('ix_agent_runs_user_id', table_name='agent_runs')
    op.drop_index('ix_agent_runs_assessment_id', table_name='agent_runs')
    op.drop_table('agent_runs')
