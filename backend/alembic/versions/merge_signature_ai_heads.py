"""Merge signature AI heads

Revision ID: merge_signature_ai_heads
Revises: ensure_doc_columns, add_signature_ai_001
Create Date: 2025-01-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'merge_signature_ai_heads'
down_revision = ('ensure_doc_columns', 'add_signature_ai_001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a merge migration, no operations needed
    pass


def downgrade() -> None:
    # This is a merge migration, no operations needed
    pass