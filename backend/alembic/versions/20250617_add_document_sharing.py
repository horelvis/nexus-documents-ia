"""Add document sharing functionality

Revision ID: add_document_sharing_20250617
Revises: 20250617_remove_teams_tables
Create Date: 2025-06-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'add_document_sharing_20250617'
down_revision = '20250617_remove_teams_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Create document_shares table
    op.create_table(
        'document_shares',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Share settings
        sa.Column('share_token', sa.String(255), nullable=False, unique=True),
        sa.Column('share_type', sa.String(50), nullable=False, default='view'),  # view, download, edit
        sa.Column('permissions', postgresql.JSONB, nullable=True),  # Additional permissions
        
        # Access control
        sa.Column('password_hash', sa.String(255), nullable=True),  # Optional password protection
        sa.Column('max_access_count', sa.Integer, nullable=True),  # Limit number of accesses
        sa.Column('current_access_count', sa.Integer, nullable=False, default=0),
        
        # Expiration
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Recipient info (optional)
        sa.Column('recipient_email', sa.String(255), nullable=True),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('share_message', sa.Text, nullable=True),
        
        # Tracking
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_accessed_at', sa.DateTime(timezone=True), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revoked_by'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for document_shares
    op.create_index('idx_document_shares_token', 'document_shares', ['share_token'])
    op.create_index('idx_document_shares_document', 'document_shares', ['document_id'])
    op.create_index('idx_document_shares_tenant', 'document_shares', ['tenant_id'])
    op.create_index('idx_document_shares_expires', 'document_shares', ['expires_at'])
    op.create_index('idx_document_shares_active', 'document_shares', ['is_active'])
    op.create_index('idx_document_shares_created_by', 'document_shares', ['created_by'])
    
    # Create document_share_access_logs table for tracking access
    op.create_table(
        'document_share_access_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('share_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Access details
        sa.Column('accessed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('referrer', sa.Text, nullable=True),
        
        # Action performed
        sa.Column('action', sa.String(50), nullable=False, default='view'),  # view, download, print
        sa.Column('success', sa.Boolean, nullable=False, default=True),
        sa.Column('error_message', sa.Text, nullable=True),
        
        # Geographic info (optional)
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        
        # Device info
        sa.Column('device_type', sa.String(50), nullable=True),  # desktop, mobile, tablet
        sa.Column('browser', sa.String(50), nullable=True),
        sa.Column('os', sa.String(50), nullable=True),
        
        # User info if authenticated
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['share_id'], ['document_shares.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for access logs
    op.create_index('idx_share_access_logs_share', 'document_share_access_logs', ['share_id'])
    op.create_index('idx_share_access_logs_document', 'document_share_access_logs', ['document_id'])
    op.create_index('idx_share_access_logs_accessed', 'document_share_access_logs', ['accessed_at'])
    op.create_index('idx_share_access_logs_tenant', 'document_share_access_logs', ['tenant_id'])
    
    # Create document_share_recipients table for managing specific recipients
    op.create_table(
        'document_share_recipients',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('share_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Recipient info
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('verification_code', sa.String(100), nullable=True),  # For email verification
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        
        # Notification status
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notification_error', sa.Text, nullable=True),
        
        # Access status
        sa.Column('first_accessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('access_count', sa.Integer, nullable=False, default=0),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['share_id'], ['document_shares.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('share_id', 'email', name='uq_share_recipient_email')
    )
    
    # Create indexes for recipients
    op.create_index('idx_share_recipients_share', 'document_share_recipients', ['share_id'])
    op.create_index('idx_share_recipients_email', 'document_share_recipients', ['email'])
    op.create_index('idx_share_recipients_tenant', 'document_share_recipients', ['tenant_id'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_share_recipients_tenant', table_name='document_share_recipients')
    op.drop_index('idx_share_recipients_email', table_name='document_share_recipients')
    op.drop_index('idx_share_recipients_share', table_name='document_share_recipients')
    
    op.drop_index('idx_share_access_logs_tenant', table_name='document_share_access_logs')
    op.drop_index('idx_share_access_logs_accessed', table_name='document_share_access_logs')
    op.drop_index('idx_share_access_logs_document', table_name='document_share_access_logs')
    op.drop_index('idx_share_access_logs_share', table_name='document_share_access_logs')
    
    op.drop_index('idx_document_shares_created_by', table_name='document_shares')
    op.drop_index('idx_document_shares_active', table_name='document_shares')
    op.drop_index('idx_document_shares_expires', table_name='document_shares')
    op.drop_index('idx_document_shares_tenant', table_name='document_shares')
    op.drop_index('idx_document_shares_document', table_name='document_shares')
    op.drop_index('idx_document_shares_token', table_name='document_shares')
    
    # Drop tables
    op.drop_table('document_share_recipients')
    op.drop_table('document_share_access_logs')
    op.drop_table('document_shares')