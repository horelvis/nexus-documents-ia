"""drop domain column from knowledge_entities

Revision ID: a2b3c4d5e6f7
Revises: 125fb6c09803
Create Date: 2026-04-22 00:00:00.000000

Phase 6/9 of remove-domain-field refactor.
Drops the `domain` column (String(100), nullable, indexed) from the
`knowledge_entities` table. Business-domain classification is no longer
stored at this layer — TrustGraph (FalkorDB) handles entity relationships.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = '125fb6c09803'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the auto-generated index on domain first, then the column
    op.drop_index(op.f('ix_knowledge_entities_domain'), table_name='knowledge_entities')
    op.drop_column('knowledge_entities', 'domain')


def downgrade():
    # Restore the column and index for rollback
    op.add_column(
        'knowledge_entities',
        sa.Column('domain', sa.String(length=100), nullable=True)
    )
    op.create_index(
        op.f('ix_knowledge_entities_domain'),
        'knowledge_entities',
        ['domain'],
        unique=False
    )
