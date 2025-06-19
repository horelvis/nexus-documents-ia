"""rename metadata column to document_metadata

Revision ID: rename_metadata_column
Revises: add_doc_categorization
Create Date: 2025-06-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rename_metadata_column'
down_revision = 'add_document_sharing_20250617'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if columns exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('documents')]
    
    # Rename metadata column to document_metadata to avoid SQLAlchemy reserved name conflict
    if 'metadata' in columns and 'document_metadata' not in columns:
        op.alter_column('documents', 'metadata', new_column_name='document_metadata')
    elif 'metadata' not in columns and 'document_metadata' not in columns:
        # If neither exists, create document_metadata
        op.add_column('documents', sa.Column('document_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))


def downgrade() -> None:
    # Check if columns exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('documents')]
    
    # Rename back to original column name
    if 'document_metadata' in columns and 'metadata' not in columns:
        op.alter_column('documents', 'document_metadata', new_column_name='metadata')