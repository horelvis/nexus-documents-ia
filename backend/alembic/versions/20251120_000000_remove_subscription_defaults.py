"""Remove subscription defaults to ensure NULL on creation

Revision ID: 20251120_000000_remove_sub_defaults
Revises: 20251117_223000_mark_tenant_owners_admin
Create Date: 2025-11-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251120_000000_remove_sub_defaults'
down_revision = '20251117_223000_mark_tenant_owners_admin'
branch_labels = None
depends_on = None


def upgrade():
    # Remove server_default from subscription_plan and subscription_status
    # This ensures that if no value is provided, it stays NULL (no plan selected)
    op.alter_column('users', 'subscription_plan', server_default=None)
    op.alter_column('users', 'subscription_status', server_default=None)


def downgrade():
    # Restore the previous defaults if needed
    op.alter_column('users', 'subscription_plan', server_default='free')
    op.alter_column('users', 'subscription_status', server_default='active')
