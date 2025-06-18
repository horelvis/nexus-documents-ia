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
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add category field to documents
    op.add_column('documents', sa.Column('category', sa.String(50), nullable=True))
    
    # Add metadata JSONB field to documents
    op.add_column('documents', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default={}))
    
    # Add content field for storing extracted text
    op.add_column('documents', sa.Column('content', sa.Text(), nullable=True))
    
    # Add extracted_entities JSONB field
    op.add_column('documents', sa.Column('extracted_entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Create indexes for better performance
    op.create_index('idx_documents_category', 'documents', ['category'])
    op.create_index('idx_documents_category_tenant', 'documents', ['category', 'tenant_id'])
    
    # Set default category for existing documents
    op.execute("UPDATE documents SET category = 'general' WHERE category IS NULL")
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