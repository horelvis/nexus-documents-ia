"""add user memory facts table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-26 10:00:00.000000

Adds table for Emma's persistent user memory:
- emma_user_memory_facts: Cross-session user facts (identity, work, preferences)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade():
    # ── User Memory Facts ─────────────────────────────────────────────
    op.create_table(
        'emma_user_memory_facts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('fact_key', sa.String(100), nullable=False),
        sa.Column('fact_value', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('source', sa.String(20), nullable=False, server_default='declared'),
        sa.Column('source_query', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Standard indexes
    op.create_index('idx_user_memory_tenant_id', 'emma_user_memory_facts', ['tenant_id'])
    op.create_index('idx_user_memory_user_id', 'emma_user_memory_facts', ['user_id'])
    op.create_index('idx_user_memory_tenant_user', 'emma_user_memory_facts', ['tenant_id', 'user_id'])
    op.create_index('idx_user_memory_active', 'emma_user_memory_facts', ['tenant_id', 'user_id', 'is_active'])

    # Partial unique index: one active fact per (tenant, user, category, key)
    op.create_index(
        'uq_user_memory_active_fact',
        'emma_user_memory_facts',
        ['tenant_id', 'user_id', 'category', 'fact_key'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
    )


def downgrade():
    op.drop_index('uq_user_memory_active_fact', table_name='emma_user_memory_facts')
    op.drop_index('idx_user_memory_active', table_name='emma_user_memory_facts')
    op.drop_index('idx_user_memory_tenant_user', table_name='emma_user_memory_facts')
    op.drop_index('idx_user_memory_user_id', table_name='emma_user_memory_facts')
    op.drop_index('idx_user_memory_tenant_id', table_name='emma_user_memory_facts')
    op.drop_table('emma_user_memory_facts')
