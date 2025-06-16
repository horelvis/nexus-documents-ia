"""add subscription fields to user

Revision ID: add_subscription_fields
Revises: unified_migration_20250615
Create Date: 2025-06-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_subscription_fields'
down_revision = 'unified_migration_20250615'
branch_labels = None
depends_on = None


def upgrade():
    """Add subscription_plan and subscription_status to users table"""
    op.add_column('users', sa.Column('subscription_plan', sa.String(50), nullable=True, server_default='free'))
    op.add_column('users', sa.Column('subscription_status', sa.String(50), nullable=True, server_default='active'))


def downgrade():
    """Remove subscription fields from users table"""
    op.drop_column('users', 'subscription_status')
    op.drop_column('users', 'subscription_plan')