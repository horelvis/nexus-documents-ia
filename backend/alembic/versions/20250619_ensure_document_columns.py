"""ensure document columns exist

Revision ID: ensure_doc_columns
Revises: rename_metadata_column
Create Date: 2025-06-19 11:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = 'ensure_doc_columns'
down_revision = 'rename_metadata_column'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    result = bind.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table_name, "column": column_name}
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # Add category column if it doesn't exist
    if not column_exists('documents', 'category'):
        op.add_column('documents', sa.Column('category', sa.String(50), nullable=True))
        op.create_index('idx_documents_category', 'documents', ['category'])
        op.create_index('idx_documents_category_tenant', 'documents', ['category', 'tenant_id'])
        # Set default category for existing documents
        op.execute("UPDATE documents SET category = 'general' WHERE category IS NULL")
    
    # Add tags_array column if it doesn't exist
    if not column_exists('documents', 'tags_array'):
        op.add_column('documents', sa.Column('tags_array', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Add content column if it doesn't exist
    if not column_exists('documents', 'content'):
        op.add_column('documents', sa.Column('content', sa.Text(), nullable=True))
    
    # Add extracted_entities column if it doesn't exist
    if not column_exists('documents', 'extracted_entities'):
        op.add_column('documents', sa.Column('extracted_entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Ensure document_metadata exists (was renamed from metadata)
    if not column_exists('documents', 'document_metadata') and column_exists('documents', 'metadata'):
        op.alter_column('documents', 'metadata', new_column_name='document_metadata')
    elif not column_exists('documents', 'document_metadata'):
        op.add_column('documents', sa.Column('document_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, default={}))


def downgrade() -> None:
    # This migration is defensive and shouldn't be rolled back
    pass