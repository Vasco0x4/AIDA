"""Initial schema - all existing tables

Revision ID: 001_initial
Revises: None
Create Date: 2026-04-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- folders (no FK deps) ---
    op.create_table(
        'folders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), server_default='#06b6d4'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    # --- platform_settings (no FK deps) ---
    op.create_table(
        'platform_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
    )

    # --- users (no FK deps) ---
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('username', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('email', sa.String(255), nullable=True, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # --- assessments (FK -> folders) ---
    op.create_table(
        'assessments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('status', sa.String(50), server_default='active'),
        sa.Column('workspace_path', sa.String(512), nullable=True),
        sa.Column('container_name', sa.String(255), nullable=True),
        sa.Column('client_name', sa.String(255), nullable=True),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column('limitations', sa.Text(), nullable=True),
        sa.Column('objectives', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('target_domains', sa.ARRAY(sa.Text()), nullable=True),
        sa.Column('ip_scopes', sa.ARRAY(sa.Text()), nullable=True),
        sa.Column('credentials', sa.Text(), nullable=True),
        sa.Column('access_info', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('environment', sa.String(50), server_default='non_specifie'),
        sa.Column('environment_notes', sa.Text(), nullable=True),
        sa.Column('folder_id', sa.Integer(), sa.ForeignKey('folders.id'), nullable=True),
    )

    # --- cards (FK -> assessments CASCADE) ---
    op.create_table(
        'cards',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('card_type', sa.String(50), nullable=False),
        sa.Column('section_number', sa.String(20), nullable=True, index=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('target_service', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('severity', sa.String(20), nullable=True),
        sa.Column('cvss_vector', sa.String(255), nullable=True),
        sa.Column('cvss_score', sa.Float(), nullable=True),
        sa.Column('technical_analysis', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('proof', sa.Text(), nullable=True),
        sa.Column('context', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    # --- command_history (FK -> assessments CASCADE) ---
    op.create_table(
        'command_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('container_name', sa.String(100), nullable=True),
        sa.Column('command', sa.Text(), nullable=False),
        sa.Column('stdout', sa.Text(), nullable=True),
        sa.Column('stderr', sa.Text(), nullable=True),
        sa.Column('returncode', sa.Integer(), nullable=True),
        sa.Column('execution_time', sa.Float(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('phase', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), server_default='completed'),
        sa.Column('timeout_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('command_type', sa.String(20), server_default='shell'),
        sa.Column('source_code', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    # --- recon_data (FK -> assessments CASCADE) ---
    op.create_table(
        'recon_data',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('data_type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('discovered_in_phase', sa.String(50), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    # --- assessment_sections (FK -> assessments CASCADE) ---
    op.create_table(
        'assessment_sections',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('section_type', sa.String(50), nullable=False),
        sa.Column('section_number', sa.Numeric(3, 1), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    # --- credentials (FK -> assessments CASCADE) ---
    op.create_table(
        'credentials',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('credential_type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('placeholder', sa.String(100), nullable=False),
        sa.Column('token', sa.Text(), nullable=True),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('password', sa.Text(), nullable=True),
        sa.Column('cookie_value', sa.Text(), nullable=True),
        sa.Column('custom_data', postgresql.JSONB(), nullable=True),
        sa.Column('service', sa.String(100), nullable=True),
        sa.Column('target', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('discovered_by', sa.String(50), server_default='manual'),
    )

    # --- custom_tables (FK -> assessments CASCADE) ---
    op.create_table(
        'custom_tables',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('table_name', sa.String(255), nullable=False),
        sa.Column('section_number', sa.String(20), nullable=True),
        sa.Column('headers', sa.ARRAY(sa.Text()), nullable=True),
        sa.Column('rows', sa.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    # --- pending_commands (FK -> assessments CASCADE) ---
    op.create_table(
        'pending_commands',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('command', sa.Text(), nullable=False),
        sa.Column('phase', sa.String(50), nullable=True),
        sa.Column('command_type', sa.String(20), server_default='shell'),
        sa.Column('matched_keywords', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', index=True),
        sa.Column('resolved_by', sa.String(100), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('execution_result', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('pending_commands')
    op.drop_table('custom_tables')
    op.drop_table('credentials')
    op.drop_table('assessment_sections')
    op.drop_table('recon_data')
    op.drop_table('command_history')
    op.drop_table('cards')
    op.drop_table('assessments')
    op.drop_table('users')
    op.drop_table('platform_settings')
    op.drop_table('folders')
