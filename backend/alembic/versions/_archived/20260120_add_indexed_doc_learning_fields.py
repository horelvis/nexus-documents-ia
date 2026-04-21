"""Add learning fields to indexed_documents

Revision ID: 20260120_idx_doc_learning
Revises: 20260120_data_learning
Create Date: 2026-01-20

This migration adds Data Learning fields to indexed_documents:
- connector_type: Denormalized connector type for fast queries (avoids JOINs)
- source_metadata: Native metadata from connector (preserved for re-learning)
- learned_context: Cached learned context for efficient RAG
- indexing_strategy_id: Reference to strategy used (for intelligent re-indexing)

These fields enable:
1. Fast filtering by connector type without JOINs
2. Preservation of native connector metadata (Alfresco aspects, SharePoint columns)
3. Cached learned context directly in document for RAG efficiency
4. Tracking of indexing strategy used for re-indexing decisions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = '20260120_idx_doc_learning'
down_revision = '20260120_data_learning'
branch_labels = None
depends_on = None


def column_exists(table, column):
    """Check if a column exists in a table."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns(table)]
    return column in columns


def index_exists(index_name):
    """Check if an index exists."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx['name'] for idx in inspector.get_indexes('indexed_documents')]
    return index_name in indexes


def upgrade() -> None:
    # Add connector_type column (denormalized for fast queries)
    if not column_exists('indexed_documents', 'connector_type'):
        op.add_column(
            'indexed_documents',
            sa.Column('connector_type', sa.String(50), nullable=True)
        )
    if not index_exists('idx_indexed_doc_connector_type'):
        op.create_index(
            'idx_indexed_doc_connector_type',
            'indexed_documents',
            ['connector_type']
        )

    # Add source_metadata column (native metadata from connector)
    if not column_exists('indexed_documents', 'source_metadata'):
        op.add_column(
            'indexed_documents',
            sa.Column('source_metadata', JSONB, nullable=True)
        )

    # Add learned_context column (cached for RAG efficiency)
    # Note: This column may already exist from a previous partial migration
    if not column_exists('indexed_documents', 'learned_context'):
        op.add_column(
            'indexed_documents',
            sa.Column('learned_context', JSONB, nullable=True)
        )

    # Add indexing_strategy_id column (for intelligent re-indexing)
    if not column_exists('indexed_documents', 'indexing_strategy_id'):
        op.add_column(
            'indexed_documents',
            sa.Column(
                'indexing_strategy_id',
                UUID(as_uuid=True),
                sa.ForeignKey('connector_indexing_strategies.id', ondelete='SET NULL'),
                nullable=True
            )
        )
    if not index_exists('idx_indexed_doc_strategy'):
        op.create_index(
            'idx_indexed_doc_strategy',
            'indexed_documents',
            ['indexing_strategy_id']
        )

    # Backfill connector_type from connector table for existing documents
    # This is done as a raw SQL for efficiency
    op.execute("""
        UPDATE indexed_documents id
        SET connector_type = c.connector_type
        FROM connectors c
        WHERE id.connector_id = c.id
        AND id.connector_type IS NULL
    """)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_indexed_doc_strategy', table_name='indexed_documents')
    op.drop_index('idx_indexed_doc_connector_type', table_name='indexed_documents')

    # Drop columns
    op.drop_column('indexed_documents', 'indexing_strategy_id')
    op.drop_column('indexed_documents', 'learned_context')
    op.drop_column('indexed_documents', 'source_metadata')
    op.drop_column('indexed_documents', 'connector_type')
