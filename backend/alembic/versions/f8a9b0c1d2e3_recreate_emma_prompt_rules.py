"""recreate emma_prompt_rules without tenant_id

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-04-24 08:30:00.000000

Sibling to e7f8a9b0c1d2. The archived prompt-management migration
(c3d4e5f6g7h8) created emma_prompt_rules alongside emma_guardrails
and was dropped from the active chain during the multi-tenancy
removal because of its tenant_id column. The /prompts/rules endpoint
still queries the table every time the RuleEngine evaluates context.

Rebuild without tenant_id, same column shape the endpoint SELECTs.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'emma_prompt_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('rule_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('conditions', JSONB, nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('action_config', JSONB, nullable=False),
        sa.Column('priority', sa.Integer(), server_default='100'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_prompt_rules_active', 'emma_prompt_rules', ['is_active'])
    op.create_index('idx_prompt_rules_priority', 'emma_prompt_rules', ['priority'])


def downgrade() -> None:
    op.drop_index('idx_prompt_rules_priority', table_name='emma_prompt_rules')
    op.drop_index('idx_prompt_rules_active', table_name='emma_prompt_rules')
    op.drop_table('emma_prompt_rules')
