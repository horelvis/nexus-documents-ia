"""add document categorization fields

Revision ID: add_doc_categorization
Revises: 
Create Date: 2024-01-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_doc_categorization'
down_revision = 'unified_20250615'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if columns already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('documents')]
    
    # Add category field to documents
    if 'category' not in columns:
        op.add_column('documents', sa.Column('category', sa.String(50), nullable=True))
    
    # Add metadata JSONB field to documents
    if 'metadata' not in columns and 'document_metadata' not in columns:
        op.add_column('documents', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default={}))
    
    # Add content field for storing extracted text
    if 'content' not in columns:
        op.add_column('documents', sa.Column('content', sa.Text(), nullable=True))
    
    # Add extracted_entities JSONB field
    if 'extracted_entities' not in columns:
        op.add_column('documents', sa.Column('extracted_entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Create indexes for better performance
    indexes = [idx['name'] for idx in inspector.get_indexes('documents')]
    if 'idx_documents_category' not in indexes:
        try:
            op.create_index('idx_documents_category', 'documents', ['category'])
        except:
            pass
    if 'idx_documents_category_tenant' not in indexes:
        try:
            op.create_index('idx_documents_category_tenant', 'documents', ['category', 'tenant_id'])
        except:
            pass
    
    # Set default category for existing documents
    if 'category' not in columns:
        op.execute("UPDATE documents SET category = 'general' WHERE category IS NULL")
    if 'metadata' not in columns and 'document_metadata' not in columns:
        op.execute("UPDATE documents SET metadata = '{}' WHERE metadata IS NULL")


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_documents_category_tenant', 'documents')
    op.drop_index('idx_documents_category', 'documents')
    
    # Drop columns
    op.drop_column('documents', 'extracted_entities')
    op.drop_column('documents', 'content')
    op.drop_column('documents', 'metadata')
    op.drop_column('documents', 'category')