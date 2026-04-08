"""
Remove content field to eliminate duplication

Revision ID: Remove_content_field_to_eliminate_duplication_20250909_132646
Revises: 764a0cdee789
Create Date: 2025-09-09 13:26:46

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'Remove_content_field_to_eliminate_duplication_20250909_132646'
down_revision = "764a0cdee789"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Remove content field from documents table
    Content is stored in Elasticsearch, Vector DB, and GCP - no need to duplicate in PostgreSQL
    """
    # Drop the content column - saves 99.3% space in documents table
    op.drop_column('documents', 'content')


def downgrade() -> None:
    """
    Restore content field in documents table
    WARNING: Content will be empty after restore - would need to re-extract from files
    """
    # Add content column back (but it will be empty)
    op.add_column('documents', sa.Column('content', sa.TEXT(), nullable=True))
    
    # Note: We can't restore the actual content since it would require re-processing all files
    # Content should be retrieved from Elasticsearch/Vector DB instead
