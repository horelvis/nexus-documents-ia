"""Add indexing_duration_seconds to indexed_documents for accurate time estimates

Revision ID: 20260127_indexing_duration
Revises: 20260127_emma_sessions
Create Date: 2026-01-27

This migration adds:
- indexing_duration_seconds column to track actual processing time (not queue wait time)

This enables accurate time estimates for pending document indexing in the UI.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260127_indexing_duration'
down_revision = '20260127_emma_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if column already exists (idempotent migration)
    column_exists = conn.execute(
        sa.text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'indexed_documents'
            AND column_name = 'indexing_duration_seconds'
        """)
    ).fetchone()

    if not column_exists:
        op.add_column(
            'indexed_documents',
            sa.Column('indexing_duration_seconds', sa.Float(), nullable=True)
        )


def downgrade() -> None:
    op.drop_column('indexed_documents', 'indexing_duration_seconds')
