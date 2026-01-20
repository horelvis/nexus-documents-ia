"""Add NexusLM notebook models

Revision ID: 20260120_nexuslm
Revises: 20260116_connectors
Create Date: 2026-01-20

This migration adds:
- notebooks table (main notebook entity)
- notebook_sources table (documents added to notebooks)
- notebook_audios table (generated podcast audio files)
- notebook_chats table (Q&A conversations with sources)

NexusLM is an on-premise NotebookLM alternative using Qwen3-4B-Thinking
for LLM and VibeVoice for TTS podcast generation.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260120_nexuslm'
down_revision = '20260116_connectors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create notebooks table
    op.create_table(
        'notebooks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('emoji', sa.String(10), nullable=True, server_default="'📓'"),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('source_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_words', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chat_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('audio_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('idx_notebooks_tenant_user', 'notebooks', ['tenant_id', 'user_id'])
    op.create_index('idx_notebooks_user_activity', 'notebooks', ['user_id', 'last_activity_at'])
    op.create_index('idx_notebooks_archived', 'notebooks', ['is_archived'])

    # Create notebook_sources table
    op.create_table(
        'notebook_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('notebook_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notebooks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('indexed_document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('indexed_documents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('key_points', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(document_id IS NOT NULL AND indexed_document_id IS NULL) OR "
            "(document_id IS NULL AND indexed_document_id IS NOT NULL)",
            name="ck_notebook_source_single_ref"
        ),
    )

    op.create_index('idx_notebook_sources_notebook', 'notebook_sources', ['notebook_id'])
    op.create_index('idx_notebook_sources_document', 'notebook_sources', ['document_id'])
    op.create_index('idx_notebook_sources_indexed', 'notebook_sources', ['indexed_document_id'])
    op.create_index('idx_notebook_sources_processed', 'notebook_sources', ['is_processed'])

    # Create notebook_audios table
    op.create_table(
        'notebook_audios',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('notebook_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notebooks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column('status_message', sa.Text(), nullable=True),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('script', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('audio_url', sa.String(1000), nullable=True),
        sa.Column('audio_format', sa.String(10), nullable=False, server_default="'mp3'"),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('transcript', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('generation_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generation_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('idx_notebook_audios_notebook', 'notebook_audios', ['notebook_id'])
    op.create_index('idx_notebook_audios_status', 'notebook_audios', ['status'])
    op.create_index('idx_notebook_audios_created', 'notebook_audios', ['created_at'])

    # Create notebook_chats table
    op.create_table(
        'notebook_chats',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('notebook_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notebooks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('messages', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_message_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('idx_notebook_chats_notebook', 'notebook_chats', ['notebook_id'])
    op.create_index('idx_notebook_chats_user', 'notebook_chats', ['user_id'])
    op.create_index('idx_notebook_chats_last_message', 'notebook_chats', ['last_message_at'])


def downgrade() -> None:
    # Drop tables in reverse order (respect foreign key constraints)
    op.drop_table('notebook_chats')
    op.drop_table('notebook_audios')
    op.drop_table('notebook_sources')
    op.drop_table('notebooks')
