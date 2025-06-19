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
    # Rename metadata column to document_metadata to avoid SQLAlchemy reserved name conflict
    op.alter_column('documents', 'metadata', new_column_name='document_metadata')


def downgrade() -> None:
    # Rename back to original column name
    op.alter_column('documents', 'document_metadata', new_column_name='metadata')