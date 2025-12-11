"""Add document ACL tables for granular access control

Revision ID: 20251210_add_document_acl
Revises: 20251208_add_information_channels
Create Date: 2024-12-10

Creates tables for document-level Access Control Lists:
- document_acls: Main ACL entries (user, role, or everyone)
- document_acl_audits: Audit trail for ACL changes

This enables:
- Granular permissions per document (view, edit, delete, share)
- Assignment to specific users, roles, or entire tenant
- Expiring permissions with timestamps
- Complete audit trail for compliance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '20251210_add_document_acl'
down_revision = '20251208_add_information_channels'
branch_labels = None
depends_on = None


def upgrade():
    """Create document ACL tables and backfill existing documents."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Create document_acls table
    if 'document_acls' not in existing_tables:
        op.create_table(
            'document_acls',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

            # Grantee: user, role, or everyone
            sa.Column('grantee_type', sa.String(20), nullable=False),  # 'user', 'role', 'everyone'
            sa.Column('grantee_id', UUID(as_uuid=True), nullable=True),  # NULL when grantee_type='everyone'

            # Granular permissions
            sa.Column('can_view', sa.Boolean, default=True, nullable=False),
            sa.Column('can_edit', sa.Boolean, default=False, nullable=False),
            sa.Column('can_delete', sa.Boolean, default=False, nullable=False),
            sa.Column('can_share', sa.Boolean, default=False, nullable=False),

            # Metadata
            sa.Column('granted_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('source', sa.String(50), default='manual', nullable=False),  # manual, share_link, inherited, migration

            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

        # Unique constraint: one ACL entry per document + grantee combination
        op.create_unique_constraint(
            'uq_document_acl_grantee',
            'document_acls',
            ['document_id', 'grantee_type', 'grantee_id']
        )

        # Indexes for document_acls
        op.create_index('idx_document_acls_document_id', 'document_acls', ['document_id'])
        op.create_index('idx_document_acls_tenant_id', 'document_acls', ['tenant_id'])
        op.create_index('idx_document_acls_grantee_type', 'document_acls', ['grantee_type'])
        op.create_index('idx_document_acls_grantee_id', 'document_acls', ['grantee_id'])
        op.create_index('idx_document_acls_expires_at', 'document_acls', ['expires_at'])
        op.create_index('idx_document_acls_tenant_grantee', 'document_acls', ['tenant_id', 'grantee_type'])
        op.create_index('idx_document_acls_document_view', 'document_acls', ['document_id', 'can_view'])

    # 2. Create document_acl_audits table
    if 'document_acl_audits' not in existing_tables:
        op.create_table(
            'document_acl_audits',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', UUID(as_uuid=True), nullable=False),  # No FK - document may be deleted
            sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),  # No FK - for audit retention
            sa.Column('acl_id', UUID(as_uuid=True), nullable=True),  # Reference to the ACL entry (may be deleted)

            # Action details
            sa.Column('action', sa.String(20), nullable=False),  # granted, revoked, modified, expired
            sa.Column('grantee_type', sa.String(20), nullable=False),
            sa.Column('grantee_id', UUID(as_uuid=True), nullable=True),

            # Permission state
            sa.Column('permissions_before', JSONB, nullable=True),
            sa.Column('permissions_after', JSONB, nullable=True),

            # Actor
            sa.Column('performed_by', UUID(as_uuid=True), nullable=True),  # NULL for system actions like expiration
            sa.Column('source', sa.String(50), nullable=True),  # Where the action originated

            # Context
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.Text, nullable=True),

            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        # Indexes for document_acl_audits
        op.create_index('idx_acl_audits_document_id', 'document_acl_audits', ['document_id'])
        op.create_index('idx_acl_audits_tenant_id', 'document_acl_audits', ['tenant_id'])
        op.create_index('idx_acl_audits_action', 'document_acl_audits', ['action'])
        op.create_index('idx_acl_audits_performed_by', 'document_acl_audits', ['performed_by'])
        op.create_index('idx_acl_audits_created_at', 'document_acl_audits', ['created_at'])
        op.create_index('idx_acl_audits_tenant_created', 'document_acl_audits', ['tenant_id', 'created_at'])
        op.create_index('idx_acl_audits_document_action', 'document_acl_audits', ['document_id', 'action'])

    # 3. Backfill existing documents with default ACL (everyone can view)
    # This maintains backward compatibility - existing documents remain accessible
    op.execute("""
        INSERT INTO document_acls (
            id, document_id, tenant_id, grantee_type, grantee_id,
            can_view, can_edit, can_delete, can_share,
            granted_by, source
        )
        SELECT
            gen_random_uuid(),
            d.id,
            d.tenant_id,
            'everyone',
            NULL,
            true,
            false,
            false,
            false,
            d.created_by,
            'migration'
        FROM documents d
        WHERE NOT EXISTS (
            SELECT 1 FROM document_acls acl
            WHERE acl.document_id = d.id AND acl.grantee_type = 'everyone'
        )
    """)

    # 4. Create audit entry for the migration
    op.execute("""
        INSERT INTO document_acl_audits (
            id, document_id, tenant_id, action, grantee_type, grantee_id,
            permissions_after, source
        )
        SELECT
            gen_random_uuid(),
            acl.document_id,
            acl.tenant_id,
            'granted',
            'everyone',
            NULL,
            '{"can_view": true, "can_edit": false, "can_delete": false, "can_share": false}'::jsonb,
            'migration'
        FROM document_acls acl
        WHERE acl.source = 'migration'
    """)


def downgrade():
    """Drop document ACL tables in reverse order."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Drop tables in reverse dependency order
    if 'document_acl_audits' in existing_tables:
        op.drop_table('document_acl_audits')

    if 'document_acls' in existing_tables:
        op.drop_table('document_acls')
