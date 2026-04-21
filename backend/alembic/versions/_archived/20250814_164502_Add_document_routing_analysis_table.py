"""
Add document_routing_analysis table

Revision ID: Add_document_routing_analysis_table_20250814_164502
Revises: 60341decaf9a
Create Date: 2025-08-14 16:45:02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'Add_document_routing_analysis_table_20250814_164502'
down_revision = "60341decaf9a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration"""
    # Create document_routing_analysis table
    op.create_table('document_routing_analysis',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_type', sa.String(100), nullable=False),
        sa.Column('confidence_score', sa.Float, nullable=False, default=0.0),
        sa.Column('is_signable', sa.Boolean, nullable=False, default=False),
        sa.Column('requires_approval', sa.Boolean, nullable=False, default=False),
        sa.Column('is_confidential', sa.Boolean, nullable=False, default=False),
        sa.Column('has_financial_data', sa.Boolean, nullable=False, default=False),
        sa.Column('has_personal_data', sa.Boolean, nullable=False, default=False),
        sa.Column('has_legal_clauses', sa.Boolean, nullable=False, default=False),
        sa.Column('assigned_agents', postgresql.JSONB, nullable=True),
        sa.Column('routing_strategy', sa.String(50), nullable=False),
        sa.Column('priority_level', sa.String(20), nullable=False),
        sa.Column('routing_status', sa.String(50), nullable=False, default='routed'),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE')
    )
    
    # Create indexes for better performance
    op.create_index('ix_document_routing_analysis_document_id', 'document_routing_analysis', ['document_id'])
    op.create_index('ix_document_routing_analysis_tenant_id', 'document_routing_analysis', ['tenant_id'])
    op.create_index('ix_document_routing_analysis_document_type', 'document_routing_analysis', ['document_type'])
    op.create_index('ix_document_routing_analysis_routing_status', 'document_routing_analysis', ['routing_status'])


def downgrade() -> None:
    """Revert migration"""
    # Drop indexes first
    op.drop_index('ix_document_routing_analysis_routing_status', 'document_routing_analysis')
    op.drop_index('ix_document_routing_analysis_document_type', 'document_routing_analysis')
    op.drop_index('ix_document_routing_analysis_tenant_id', 'document_routing_analysis')
    op.drop_index('ix_document_routing_analysis_document_id', 'document_routing_analysis')
    
    # Drop the table
    op.drop_table('document_routing_analysis')
