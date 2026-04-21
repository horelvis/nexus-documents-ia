"""Add sector column to emma_guardrails for sector-aware filtering

Revision ID: 20260315_sector_guardrails
Revises: 20260127_indexing_duration
Create Date: 2026-03-15

This migration adds:
- sector VARCHAR(50) nullable column to emma_guardrails
- Index on sector for efficient filtering by deployment sector (legal, medical, documental)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260315_sector_guardrails'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('emma_guardrails', sa.Column('sector', sa.String(50), nullable=True))
    op.create_index('ix_emma_guardrails_sector', 'emma_guardrails', ['sector'])


def downgrade() -> None:
    op.drop_index('ix_emma_guardrails_sector', table_name='emma_guardrails')
    op.drop_column('emma_guardrails', 'sector')
