"""Add connector models for on-premise Emma

Revision ID: 20260116_connectors
Revises:
Create Date: 2026-01-16

This migration adds:
- SSO fields to users table (sso_external_id, sso_provider, sso_groups)
- connectors table (admin-managed data source configs)
- user_connector_auths table (user OAuth tokens for delegated access)
- user_document_syncs table (tracks sync status per user/connector)
- indexed_documents table (documents indexed in Weaviate from connectors)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260116_connectors'
down_revision = '20260112_add_emma_learning_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add SSO fields to users table
    op.add_column('users', sa.Column('sso_external_id', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('sso_provider', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('sso_groups', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))

    op.create_index('idx_users_sso_external_id', 'users', ['sso_external_id'], unique=True)

    # Create connectors table
    op.create_table(
        'connectors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('connector_type', sa.String(50), nullable=False),
        sa.Column('auth_type', sa.String(50), nullable=False, server_default='delegated'),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sync_interval_hours', sa.Integer(), server_default='24'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('health_status', sa.String(20), server_default='unknown'),
        sa.Column('health_message', sa.Text(), nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_connector_tenant_active', 'connectors', ['tenant_id', 'is_active'])
    op.create_index('idx_connector_type', 'connectors', ['connector_type'])
    op.create_unique_constraint('uq_connector_tenant_type_name', 'connectors', ['tenant_id', 'connector_type', 'name'])

    # Create user_connector_auths table
    op.create_table(
        'user_connector_auths',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_type', sa.String(50), server_default='Bearer'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('is_valid', sa.Boolean(), server_default='true'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_user_connector_auth_user', 'user_connector_auths', ['user_id'])
    op.create_index('idx_user_connector_auth_connector', 'user_connector_auths', ['connector_id'])
    op.create_index('idx_user_connector_auth_valid', 'user_connector_auths', ['user_id', 'is_valid'])
    op.create_unique_constraint('uq_user_connector_auth', 'user_connector_auths', ['user_id', 'connector_id'])

    # Create user_document_syncs table
    op.create_table(
        'user_document_syncs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sync_enabled', sa.Boolean(), server_default='true'),
        sa.Column('include_paths', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('exclude_paths', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('status_message', sa.Text(), nullable=True),
        sa.Column('last_sync_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delta_token', sa.Text(), nullable=True),
        sa.Column('documents_total', sa.Integer(), server_default='0'),
        sa.Column('documents_indexed', sa.Integer(), server_default='0'),
        sa.Column('documents_failed', sa.Integer(), server_default='0'),
        sa.Column('total_size_bytes', sa.BigInteger(), server_default='0'),
        sa.Column('consecutive_failures', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_user_doc_sync_user', 'user_document_syncs', ['user_id'])
    op.create_index('idx_user_doc_sync_connector', 'user_document_syncs', ['connector_id'])
    op.create_index('idx_user_doc_sync_status', 'user_document_syncs', ['status'])
    op.create_index('idx_user_doc_sync_next', 'user_document_syncs', ['next_sync_at'])
    op.create_unique_constraint('uq_user_document_sync', 'user_document_syncs', ['user_id', 'connector_id'])

    # Create indexed_documents table
    op.create_table(
        'indexed_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('connectors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('external_id', sa.String(512), nullable=False),
        sa.Column('external_url', sa.Text(), nullable=True),
        sa.Column('external_path', sa.Text(), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_tenant_public', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('shared_with_users', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('shared_with_groups', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('file_extension', sa.String(20), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), server_default='0'),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('weaviate_collection', sa.String(100), nullable=True),
        sa.Column('weaviate_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('indexing_status', sa.String(20), server_default='pending'),
        sa.Column('indexing_error', sa.Text(), nullable=True),
        sa.Column('source_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_modified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_indexed_doc_tenant', 'indexed_documents', ['tenant_id'])
    op.create_index('idx_indexed_doc_connector', 'indexed_documents', ['connector_id'])
    op.create_index('idx_indexed_doc_owner', 'indexed_documents', ['owner_id'])
    op.create_index('idx_indexed_doc_tenant_public', 'indexed_documents', ['tenant_id', 'is_tenant_public'])
    op.create_index('idx_indexed_doc_weaviate', 'indexed_documents', ['weaviate_id'])
    op.create_index('idx_indexed_doc_status', 'indexed_documents', ['indexing_status'])
    op.create_index('idx_indexed_doc_content_hash', 'indexed_documents', ['content_hash'])
    op.create_unique_constraint('uq_indexed_doc_connector_external', 'indexed_documents', ['connector_id', 'external_id'])


def downgrade() -> None:
    # Drop indexed_documents table
    op.drop_constraint('uq_indexed_doc_connector_external', 'indexed_documents', type_='unique')
    op.drop_index('idx_indexed_doc_content_hash', 'indexed_documents')
    op.drop_index('idx_indexed_doc_status', 'indexed_documents')
    op.drop_index('idx_indexed_doc_weaviate', 'indexed_documents')
    op.drop_index('idx_indexed_doc_tenant_public', 'indexed_documents')
    op.drop_index('idx_indexed_doc_owner', 'indexed_documents')
    op.drop_index('idx_indexed_doc_connector', 'indexed_documents')
    op.drop_index('idx_indexed_doc_tenant', 'indexed_documents')
    op.drop_table('indexed_documents')

    # Drop user_document_syncs table
    op.drop_constraint('uq_user_document_sync', 'user_document_syncs', type_='unique')
    op.drop_index('idx_user_doc_sync_next', 'user_document_syncs')
    op.drop_index('idx_user_doc_sync_status', 'user_document_syncs')
    op.drop_index('idx_user_doc_sync_connector', 'user_document_syncs')
    op.drop_index('idx_user_doc_sync_user', 'user_document_syncs')
    op.drop_table('user_document_syncs')

    # Drop user_connector_auths table
    op.drop_constraint('uq_user_connector_auth', 'user_connector_auths', type_='unique')
    op.drop_index('idx_user_connector_auth_valid', 'user_connector_auths')
    op.drop_index('idx_user_connector_auth_connector', 'user_connector_auths')
    op.drop_index('idx_user_connector_auth_user', 'user_connector_auths')
    op.drop_table('user_connector_auths')

    # Drop connectors table
    op.drop_constraint('uq_connector_tenant_type_name', 'connectors', type_='unique')
    op.drop_index('idx_connector_type', 'connectors')
    op.drop_index('idx_connector_tenant_active', 'connectors')
    op.drop_table('connectors')

    # Remove SSO fields from users table
    op.drop_index('idx_users_sso_external_id', 'users')
    op.drop_column('users', 'sso_groups')
    op.drop_column('users', 'sso_provider')
    op.drop_column('users', 'sso_external_id')
