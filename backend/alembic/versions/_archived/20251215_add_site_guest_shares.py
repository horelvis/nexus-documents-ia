"""Add Site Guest Shares for document collections

Revision ID: 20251215_add_site_guest_shares
Revises: 20251212_add_site_guest_system
Create Date: 2024-12-15

Adds virtual folder/collection support for Site Guests:
- SiteGuestShare: Groups documents shared with a guest (like a virtual folder)
- SiteGuestShareDocument: Junction table linking shares to documents
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '20251215_add_site_guest_shares'
down_revision = '20251212_add_site_guest_system'
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


def upgrade():
    """Create Site Guest Share tables."""

    # Create site_guest_shares table
    if not table_exists('site_guest_shares'):
        op.create_table(
            'site_guest_shares',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
            sa.Column('guest_id', UUID(as_uuid=True), sa.ForeignKey('site_guests.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('permission_type', sa.String(20), nullable=False, server_default='view'),
            sa.Column('created_by_user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index('idx_site_guest_shares_guest', 'site_guest_shares', ['guest_id'])
        op.create_index('idx_site_guest_shares_tenant', 'site_guest_shares', ['tenant_id'])

    # Create site_guest_share_documents table
    if not table_exists('site_guest_share_documents'):
        op.create_table(
            'site_guest_share_documents',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('share_id', UUID(as_uuid=True), sa.ForeignKey('site_guest_shares.id', ondelete='CASCADE'), nullable=False),
            sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('idx_site_guest_share_documents_share', 'site_guest_share_documents', ['share_id'])
        op.create_index('idx_site_guest_share_documents_document', 'site_guest_share_documents', ['document_id'])
        op.create_unique_constraint('uq_site_guest_share_document', 'site_guest_share_documents', ['share_id', 'document_id'])


def downgrade():
    """Drop Site Guest Share tables."""
    op.drop_table('site_guest_share_documents')
    op.drop_table('site_guest_shares')
