"""Add signature AI tables for intelligent placement

Revision ID: add_signature_ai_001
Revises: 
Create Date: 2025-01-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers
revision = 'add_signature_ai_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create signature_field_placements table
    op.create_table('signature_field_placements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('field_type', sa.String(50), nullable=False),
        sa.Column('signer_identifier', sa.String(100), nullable=True),
        sa.Column('x_position', sa.Float(), nullable=False),
        sa.Column('y_position', sa.Float(), nullable=False),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('is_required', sa.Boolean(), nullable=True, default=True),
        sa.Column('label', sa.String(200), nullable=True),
        sa.Column('field_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create document_type_classifications table
    op.create_table('document_type_classifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default=[]),
        sa.Column('patterns', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default=[]),
        sa.Column('default_signer_count', sa.Integer(), nullable=True, default=1),
        sa.Column('default_field_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default={}),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_document_type_tenant_name')
    )
    
    # Create signature_placement_patterns table
    op.create_table('signature_placement_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_type', sa.String(100), nullable=False),
        sa.Column('field_configurations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True, default=0.5),
        sa.Column('usage_count', sa.Integer(), nullable=True, default=0),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('pattern_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default={}),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_signature_field_placements_document', 'signature_field_placements', ['document_id'])
    op.create_index('idx_signature_field_placements_tenant', 'signature_field_placements', ['tenant_id'])
    op.create_index('idx_document_type_classifications_tenant', 'document_type_classifications', ['tenant_id'])
    op.create_index('idx_signature_placement_patterns_tenant_type', 'signature_placement_patterns', ['tenant_id', 'document_type'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_signature_placement_patterns_tenant_type', table_name='signature_placement_patterns')
    op.drop_index('idx_document_type_classifications_tenant', table_name='document_type_classifications')
    op.drop_index('idx_signature_field_placements_tenant', table_name='signature_field_placements')
    op.drop_index('idx_signature_field_placements_document', table_name='signature_field_placements')
    
    # Drop tables
    op.drop_table('signature_placement_patterns')
    op.drop_table('document_type_classifications')
    op.drop_table('signature_field_placements')