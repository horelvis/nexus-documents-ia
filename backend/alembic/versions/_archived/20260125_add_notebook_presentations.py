"""Add notebook presentations table

Revision ID: 20260125_presentations
Revises: 20260123_identity_docs
Create Date: 2026-01-25

This migration adds:
- notebook_presentations table (generated PowerPoint presentations)
- presentation_count column to notebooks table

NotebookPresentation stores PPTX presentations generated from notebook sources
using LLM for outline generation and python-pptx for slide creation.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260125_presentations'
down_revision = '20260123_identity_docs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if table already exists
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'notebook_presentations'")
    ).fetchone()

    if not table_exists:
        # Create notebook_presentations table
        op.create_table(
            'notebook_presentations',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('notebook_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('notebooks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
            sa.Column('status', sa.String(20), nullable=False, server_default="'pending'"),
            sa.Column('status_message', sa.Text(), nullable=True),
            sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('outline', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('pptx_url', sa.String(1000), nullable=True),
            sa.Column('thumbnail_url', sa.String(1000), nullable=True),
            sa.Column('slide_count', sa.Integer(), nullable=True),
            sa.Column('file_size_bytes', sa.Integer(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('generation_started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('generation_completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('idx_notebook_presentations_notebook', 'notebook_presentations', ['notebook_id'])
        op.create_index('idx_notebook_presentations_status', 'notebook_presentations', ['status'])
        op.create_index('idx_notebook_presentations_created', 'notebook_presentations', ['created_at'])

    # Add presentation_count column to notebooks table if not exists
    column_exists = conn.execute(
        sa.text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'notebooks' AND column_name = 'presentation_count'
        """)
    ).fetchone()

    if not column_exists:
        op.add_column('notebooks', sa.Column('presentation_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove presentation_count column from notebooks
    op.drop_column('notebooks', 'presentation_count')

    # Drop notebook_presentations table
    op.drop_table('notebook_presentations')
