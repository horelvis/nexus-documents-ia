"""recreate emma_guardrails without tenant_id

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-04-24 08:00:00.000000

The original prompt-management migration (c3d4e5f6g7h8, now in
_archived/) created emma_guardrails with a tenant_id column. That
migration was dropped from the active chain when multi-tenancy was
removed, so the fresh nouxcube DB never had the table — every poll
from emma-agent-service's guardrail_service returned HTTP 500 with
`relation "emma_guardrails" does not exist` and fell back to the
in-memory registry silently.

This rebuilds emma_guardrails with the current expected schema:
no tenant_id, keeps sector (the /prompts/guardrails endpoint still
SELECTs and filters on it; removing sector from the API is tracked
as separate cleanup).

Sibling tables emma_prompt_rules and emma_few_shot_examples have the
same story but are not reported as failing today — recreate them in
their own migration if/when their endpoints start paging.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'emma_guardrails',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('guardrail_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('guardrail_type', sa.String(50), nullable=False),
        sa.Column('config', JSONB, nullable=False),
        sa.Column('action_on_match', sa.String(50), nullable=False),
        sa.Column('applies_to', ARRAY(sa.String(100)), nullable=True),
        sa.Column('priority', sa.Integer(), server_default='100'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('sector', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_guardrails_active', 'emma_guardrails', ['is_active'])
    op.create_index('idx_guardrails_type', 'emma_guardrails', ['guardrail_type'])
    op.create_index('ix_emma_guardrails_sector', 'emma_guardrails', ['sector'])


def downgrade() -> None:
    op.drop_index('ix_emma_guardrails_sector', table_name='emma_guardrails')
    op.drop_index('idx_guardrails_type', table_name='emma_guardrails')
    op.drop_index('idx_guardrails_active', table_name='emma_guardrails')
    op.drop_table('emma_guardrails')
