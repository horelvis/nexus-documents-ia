"""Add emma_sessions table for persistent chat history

Revision ID: 20260127_emma_sessions
Revises: 20260125_presentations
Create Date: 2026-01-27

This migration adds:
- emma_sessions table for persisting Emma AI chat conversations

EmmaSession stores chat history as JSONB, following the NotebookChat pattern.
Redis remains the hot cache for active sessions; PostgreSQL provides durability.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260127_emma_sessions'
down_revision = '20260125_presentations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if table already exists (idempotent migration)
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'emma_sessions'")
    ).fetchone()

    if not table_exists:
        # Create emma_sessions table
        op.create_table(
            'emma_sessions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
            sa.Column('session_id', sa.String(255), nullable=False, unique=True),
            sa.Column('title', sa.String(255), nullable=True),
            sa.Column('messages', postgresql.JSONB(astext_type=sa.Text()),
                      nullable=False, server_default='[]'),
            sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_tokens', sa.Integer(), nullable=True),
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('session_metadata', postgresql.JSONB(astext_type=sa.Text()),
                      nullable=True, server_default='{}'),
            sa.Column('last_message_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

        # Create indexes for efficient querying
        op.create_index('idx_emma_sessions_user_id', 'emma_sessions', ['user_id'])
        op.create_index('idx_emma_sessions_tenant_id', 'emma_sessions', ['tenant_id'])
        op.create_index('idx_emma_sessions_session_id', 'emma_sessions', ['session_id'])
        op.create_index('idx_emma_sessions_user_tenant', 'emma_sessions', ['user_id', 'tenant_id'])
        op.create_index('idx_emma_sessions_user_last_message', 'emma_sessions',
                        ['user_id', 'last_message_at'])
        op.create_index('idx_emma_sessions_tenant_created', 'emma_sessions',
                        ['tenant_id', 'created_at'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_emma_sessions_tenant_created', table_name='emma_sessions')
    op.drop_index('idx_emma_sessions_user_last_message', table_name='emma_sessions')
    op.drop_index('idx_emma_sessions_user_tenant', table_name='emma_sessions')
    op.drop_index('idx_emma_sessions_session_id', table_name='emma_sessions')
    op.drop_index('idx_emma_sessions_tenant_id', table_name='emma_sessions')
    op.drop_index('idx_emma_sessions_user_id', table_name='emma_sessions')

    # Drop table
    op.drop_table('emma_sessions')
