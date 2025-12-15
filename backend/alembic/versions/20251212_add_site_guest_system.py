"""Add Site Guest access system for external sharing

Revision ID: 20251212_add_site_guest_system
Revises: 20251212_add_folder_markers
Create Date: 2024-12-12

Implements SharePoint-like external sharing with:
- Site Guest accounts (email + OTP authentication)
- OTP codes for guest authentication
- Session management for authenticated guests
- Granular permissions per document/folder
- Complete audit logging
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '20251212_add_site_guest_system'
down_revision = '20251212_add_folder_markers'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
        ),
        {"table_name": table_name}
    )
    return result.scalar()


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = :table_name AND column_name = :column_name)"
        ),
        {"table_name": table_name, "column_name": column_name}
    )
    return result.scalar()


def upgrade():
    """Create Site Guest tables and add tenant slug field."""

    # Add slug and site settings to tenants table (only if not exist)
    if not column_exists('tenants', 'slug'):
        op.add_column('tenants', sa.Column('slug', sa.String(100), nullable=True, unique=True))
        op.create_index('idx_tenants_slug', 'tenants', ['slug'], unique=False)

    if not column_exists('tenants', 'site_enabled'):
        op.add_column('tenants', sa.Column('site_enabled', sa.Boolean(), nullable=False, server_default='false'))

    if not column_exists('tenants', 'site_logo_url'):
        op.add_column('tenants', sa.Column('site_logo_url', sa.String(500), nullable=True))

    if not column_exists('tenants', 'site_welcome_message'):
        op.add_column('tenants', sa.Column('site_welcome_message', sa.Text(), nullable=True))

    # Create site_guests table (only if not exists)
    if not table_exists('site_guests'):
        op.create_table(
            'site_guests',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('invited_by_user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('invited_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('last_access_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('access_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('can_view', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('can_download', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('can_upload', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.UniqueConstraint('tenant_id', 'email', name='uq_site_guest_tenant_email'),
        )
        op.create_index('idx_site_guests_tenant_active', 'site_guests', ['tenant_id', 'is_active'])
        op.create_index('idx_site_guests_email', 'site_guests', ['email'])

    # Create site_guest_otp table (only if not exists)
    if not table_exists('site_guest_otp'):
        op.create_table(
            'site_guest_otp',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('guest_id', UUID(as_uuid=True), sa.ForeignKey('site_guests.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('otp_hash', sa.String(64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        )
        op.create_index('idx_site_guest_otp_guest_expires', 'site_guest_otp', ['guest_id', 'expires_at'])

    # Create site_guest_sessions table (only if not exists)
    if not table_exists('site_guest_sessions'):
        op.create_table(
            'site_guest_sessions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('guest_id', UUID(as_uuid=True), sa.ForeignKey('site_guests.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('session_token_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.String(512), nullable=True),
        )
        op.create_index('idx_site_guest_sessions_token', 'site_guest_sessions', ['session_token_hash'])
        op.create_index('idx_site_guest_sessions_active', 'site_guest_sessions', ['is_active', 'expires_at'])
        op.create_index('idx_site_guest_sessions_guest', 'site_guest_sessions', ['guest_id', 'is_active'])

    # Create site_guest_permissions table (only if not exists)
    if not table_exists('site_guest_permissions'):
        op.create_table(
            'site_guest_permissions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('guest_id', UUID(as_uuid=True), sa.ForeignKey('site_guests.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True),
            sa.Column('folder_path', sa.String(2000), nullable=True),
            sa.Column('permission_type', sa.String(20), nullable=False),
            sa.Column('granted_by_user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                '(document_id IS NOT NULL AND folder_path IS NULL) OR (document_id IS NULL AND folder_path IS NOT NULL)',
                name='ck_site_guest_permission_target'
            ),
            sa.UniqueConstraint('guest_id', 'document_id', 'permission_type', name='uq_site_guest_doc_permission'),
            sa.UniqueConstraint('guest_id', 'folder_path', 'permission_type', name='uq_site_guest_folder_permission'),
        )
        op.create_index('idx_site_guest_permissions_guest', 'site_guest_permissions', ['guest_id'])
        op.create_index('idx_site_guest_permissions_document', 'site_guest_permissions', ['document_id'])

    # Create site_guest_access_logs table (only if not exists)
    if not table_exists('site_guest_access_logs'):
        op.create_table(
            'site_guest_access_logs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('guest_id', UUID(as_uuid=True), sa.ForeignKey('site_guests.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('site_guest_sessions.id', ondelete='SET NULL'), nullable=True),
            sa.Column('action', sa.String(50), nullable=False),
            sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
            sa.Column('folder_path', sa.String(2000), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.String(512), nullable=True),
            sa.Column('details', JSONB(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('idx_site_guest_access_logs_guest_created', 'site_guest_access_logs', ['guest_id', 'created_at'])
        op.create_index('idx_site_guest_access_logs_action', 'site_guest_access_logs', ['action', 'created_at'])
        op.create_index('idx_site_guest_access_logs_document', 'site_guest_access_logs', ['document_id'])


def downgrade():
    """Drop Site Guest tables and tenant slug field."""

    # Drop tables in reverse order (due to foreign keys)
    if table_exists('site_guest_access_logs'):
        op.drop_index('idx_site_guest_access_logs_document', table_name='site_guest_access_logs')
        op.drop_index('idx_site_guest_access_logs_action', table_name='site_guest_access_logs')
        op.drop_index('idx_site_guest_access_logs_guest_created', table_name='site_guest_access_logs')
        op.drop_table('site_guest_access_logs')

    if table_exists('site_guest_permissions'):
        op.drop_index('idx_site_guest_permissions_document', table_name='site_guest_permissions')
        op.drop_index('idx_site_guest_permissions_guest', table_name='site_guest_permissions')
        op.drop_table('site_guest_permissions')

    if table_exists('site_guest_sessions'):
        op.drop_index('idx_site_guest_sessions_guest', table_name='site_guest_sessions')
        op.drop_index('idx_site_guest_sessions_active', table_name='site_guest_sessions')
        op.drop_index('idx_site_guest_sessions_token', table_name='site_guest_sessions')
        op.drop_table('site_guest_sessions')

    if table_exists('site_guest_otp'):
        op.drop_index('idx_site_guest_otp_guest_expires', table_name='site_guest_otp')
        op.drop_table('site_guest_otp')

    if table_exists('site_guests'):
        op.drop_index('idx_site_guests_email', table_name='site_guests')
        op.drop_index('idx_site_guests_tenant_active', table_name='site_guests')
        op.drop_table('site_guests')

    # Remove tenant columns (only if they exist)
    if column_exists('tenants', 'slug'):
        op.drop_index('idx_tenants_slug', table_name='tenants')
        op.drop_column('tenants', 'slug')

    if column_exists('tenants', 'site_welcome_message'):
        op.drop_column('tenants', 'site_welcome_message')

    if column_exists('tenants', 'site_logo_url'):
        op.drop_column('tenants', 'site_logo_url')

    if column_exists('tenants', 'site_enabled'):
        op.drop_column('tenants', 'site_enabled')
