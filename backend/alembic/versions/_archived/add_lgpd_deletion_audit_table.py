"""add lgpd deletion audit table

Revision ID: add_lgpd_deletion_audit
Revises: [previous_revision_id]
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = 'add_lgpd_deletion_audit'
down_revision = '6f6ae23807be'  # Initial migration (creates users table)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add LGPD deletion audit table for compliance"""
    
    # Create the lgpd_deletion_audits table
    op.create_table(
        'lgpd_deletion_audits',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('user_email', sa.String(255), nullable=False),
        sa.Column('requested_by', UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_summary', JSONB, nullable=True),
        sa.Column('total_records_deleted', sa.Integer, nullable=True, default=0),
        sa.Column('anonymized_records', sa.Integer, nullable=True, default=0),
        sa.Column('lgpd_article', sa.String(50), nullable=False, default='Article 18'),
        sa.Column('deletion_method', sa.String(100), nullable=False, default='complete_data_destruction'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_lgpd_deletion_audits_requested_by',
        'lgpd_deletion_audits', 'users',
        ['requested_by'], ['id']
    )
    
    op.create_foreign_key(
        'fk_lgpd_deletion_audits_tenant',
        'lgpd_deletion_audits', 'tenants', 
        ['tenant_id'], ['id']
    )
    
    # Create indexes
    op.create_index(
        'idx_lgpd_deletions_tenant_status',
        'lgpd_deletion_audits',
        ['tenant_id', 'status']
    )
    
    op.create_index(
        'idx_lgpd_deletions_user_date', 
        'lgpd_deletion_audits',
        ['user_id', 'created_at']
    )


def downgrade() -> None:
    """Remove LGPD deletion audit table"""
    
    # Drop indexes
    op.drop_index('idx_lgpd_deletions_user_date', 'lgpd_deletion_audits')
    op.drop_index('idx_lgpd_deletions_tenant_status', 'lgpd_deletion_audits')
    
    # Drop foreign key constraints
    op.drop_constraint('fk_lgpd_deletion_audits_tenant', 'lgpd_deletion_audits', type_='foreignkey')
    op.drop_constraint('fk_lgpd_deletion_audits_requested_by', 'lgpd_deletion_audits', type_='foreignkey')
    
    # Drop table
    op.drop_table('lgpd_deletion_audits')