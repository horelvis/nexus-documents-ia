"""add cached_path to indexed_documents

Revision ID: c3d4e5f6g7h8
Revises: 20260315_sector_guardrails
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'c3d4e5f6g7h8'
down_revision = '20260315_sector_guardrails'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('indexed_documents', sa.Column('cached_path', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('indexed_documents', 'cached_path')
