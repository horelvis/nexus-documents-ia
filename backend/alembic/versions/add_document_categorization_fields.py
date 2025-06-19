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
    
    # Add document_metadata JSONB field to documents (using correct name to avoid SQLAlchemy conflict)
    if 'document_metadata' not in columns:
        op.add_column('documents', sa.Column('document_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
    
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
    
    # Set default values for existing documents only if columns were just created
    bind = op.get_bind()
    result = bind.execute(sa.text("SELECT COUNT(*) FROM documents"))
    if result.scalar() > 0:
        try:
            op.execute("UPDATE documents SET category = 'general' WHERE category IS NULL")
        except:
            pass
        try:
            op.execute("UPDATE documents SET document_metadata = '{}' WHERE document_metadata IS NULL")
        except:
            pass


def downgrade() -> None:
    # Drop indexes
    try:
        op.drop_index('idx_documents_category_tenant', 'documents')
    except:
        pass
    try:
        op.drop_index('idx_documents_category', 'documents')
    except:
        pass
    
    # Drop columns
    try:
        op.drop_column('documents', 'extracted_entities')
    except:
        pass
    try:
        op.drop_column('documents', 'content')
    except:
        pass
    try:
        op.drop_column('documents', 'document_metadata')
    except:
        pass
    try:
        op.drop_column('documents', 'category')
    except:
        pass