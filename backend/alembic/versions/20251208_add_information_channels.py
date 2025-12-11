"""Add information channels tables for RAG data sources

Revision ID: 20251208_add_information_channels
Revises: 20251206_add_document_analyses_table
Create Date: 2024-12-08

Creates tables for information channels (Gmail, Google Drive, External DB):
- information_channels: Main channel configuration
- channel_credentials: Encrypted credentials (OAuth, DB)
- channel_documents: Tracks indexed documents from channels
- channel_sync_logs: Sync operation audit log
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '20251208_add_information_channels'
down_revision = '20251206_add_document_analyses_table'
branch_labels = None
depends_on = None


def upgrade():
    """Create information channel tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Create information_channels table
    if 'information_channels' not in existing_tables:
        op.create_table(
            'information_channels',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

            # Channel identification
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('channel_type', sa.String(50), nullable=False),  # gmail, google_drive, external_db

            # Visibility control
            sa.Column('visibility', sa.String(20), nullable=False, default='personal'),  # personal, tenant

            # Type-specific configuration (non-sensitive)
            sa.Column('configuration', JSONB, nullable=False, default={}),

            # Status
            sa.Column('is_active', sa.Boolean, default=True, nullable=False),
            sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_sync_status', sa.String(50), nullable=True),
            sa.Column('last_sync_error', sa.Text, nullable=True),
            sa.Column('documents_indexed', sa.Integer, default=0, nullable=False),

            # Sync schedule
            sa.Column('sync_interval_minutes', sa.Integer, default=60, nullable=False),
            sa.Column('next_sync_at', sa.DateTime(timezone=True), nullable=True),

            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

        # Indexes for information_channels
        op.create_index('idx_channels_tenant_type', 'information_channels', ['tenant_id', 'channel_type'])
        op.create_index('idx_channels_creator_visibility', 'information_channels', ['created_by', 'visibility'])
        op.create_index('idx_channels_next_sync', 'information_channels', ['next_sync_at', 'is_active'])
        op.create_index('idx_channels_tenant_active', 'information_channels', ['tenant_id', 'is_active'])
        op.create_index('idx_channels_tenant_id', 'information_channels', ['tenant_id'])
        op.create_index('idx_channels_created_by', 'information_channels', ['created_by'])
        op.create_index('idx_channels_channel_type', 'information_channels', ['channel_type'])

    # 2. Create channel_credentials table
    if 'channel_credentials' not in existing_tables:
        op.create_table(
            'channel_credentials',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('information_channels.id', ondelete='CASCADE'), nullable=False, unique=True),

            # Encrypted credentials blob
            sa.Column('credentials_encrypted', sa.LargeBinary, nullable=False),

            # OAuth-specific fields
            sa.Column('oauth_provider', sa.String(50), nullable=True),
            sa.Column('oauth_user_id', sa.String(255), nullable=True),
            sa.Column('oauth_email', sa.String(255), nullable=True),
            sa.Column('oauth_scopes', JSONB, nullable=True),
            sa.Column('token_expiry', sa.DateTime(timezone=True), nullable=True),

            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

    # 3. Create channel_documents table
    if 'channel_documents' not in existing_tables:
        op.create_table(
            'channel_documents',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('information_channels.id', ondelete='CASCADE'), nullable=False),

            # External source reference
            sa.Column('external_id', sa.String(500), nullable=False),
            sa.Column('external_url', sa.String(2000), nullable=True),

            # Content hash for change detection
            sa.Column('content_hash', sa.String(64), nullable=False),

            # Indexed document reference
            sa.Column('weaviate_id', sa.String(100), nullable=True),

            # Metadata snapshot
            sa.Column('title', sa.String(500), nullable=True),
            sa.Column('source_metadata', JSONB, nullable=True),

            # Processing status
            sa.Column('status', sa.String(30), nullable=False, default='pending'),
            sa.Column('error_message', sa.Text, nullable=True),

            # Source timestamps
            sa.Column('source_created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('source_modified_at', sa.DateTime(timezone=True), nullable=True),

            # Indexing timestamps
            sa.Column('first_indexed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_indexed_at', sa.DateTime(timezone=True), nullable=True),

            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

        # Indexes and constraints for channel_documents
        op.create_unique_constraint('uq_channel_document_external', 'channel_documents', ['channel_id', 'external_id'])
        op.create_index('idx_channel_docs_channel_id', 'channel_documents', ['channel_id'])
        op.create_index('idx_channel_docs_status', 'channel_documents', ['channel_id', 'status'])
        op.create_index('idx_channel_docs_hash', 'channel_documents', ['content_hash'])
        op.create_index('idx_channel_docs_weaviate', 'channel_documents', ['weaviate_id'])
        op.create_index('idx_channel_docs_status_only', 'channel_documents', ['status'])

    # 4. Create channel_sync_logs table
    if 'channel_sync_logs' not in existing_tables:
        op.create_table(
            'channel_sync_logs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('information_channels.id', ondelete='CASCADE'), nullable=False),

            # Sync execution
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('status', sa.String(30), nullable=False),
            sa.Column('trigger_type', sa.String(20), nullable=False),

            # Results
            sa.Column('items_found', sa.Integer, default=0, nullable=False),
            sa.Column('items_new', sa.Integer, default=0, nullable=False),
            sa.Column('items_updated', sa.Integer, default=0, nullable=False),
            sa.Column('items_deleted', sa.Integer, default=0, nullable=False),
            sa.Column('items_failed', sa.Integer, default=0, nullable=False),

            # Error details
            sa.Column('error_message', sa.Text, nullable=True),
            sa.Column('error_details', JSONB, nullable=True),

            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        # Indexes for channel_sync_logs
        op.create_index('idx_sync_logs_channel_id', 'channel_sync_logs', ['channel_id'])
        op.create_index('idx_sync_logs_channel_started', 'channel_sync_logs', ['channel_id', 'started_at'])
        op.create_index('idx_sync_logs_status', 'channel_sync_logs', ['status'])


def downgrade():
    """Drop information channel tables in reverse order."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Drop tables in reverse dependency order
    if 'channel_sync_logs' in existing_tables:
        op.drop_table('channel_sync_logs')

    if 'channel_documents' in existing_tables:
        op.drop_table('channel_documents')

    if 'channel_credentials' in existing_tables:
        op.drop_table('channel_credentials')

    if 'information_channels' in existing_tables:
        op.drop_table('information_channels')
