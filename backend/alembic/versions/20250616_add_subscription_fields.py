"""add subscription fields to user

Revision ID: add_sub_fields_001
Revises: unified_20250615
Create Date: 2025-06-16 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_sub_fields_001'
down_revision = 'unified_20250615'
branch_labels = None
depends_on = None


def upgrade():
    """Add subscription_plan and subscription_status to users table"""
    try:
        op.add_column('users', sa.Column('subscription_plan', sa.String(50), nullable=True, server_default='free'))
        op.add_column('users', sa.Column('subscription_status', sa.String(50), nullable=True, server_default='active'))
        print("✅ Added subscription fields to users table")
    except Exception as e:
        print(f"⚠️ Could not add subscription fields (may already exist): {e}")


def downgrade():
    """Remove subscription fields from users table"""
    try:
        op.drop_column('users', 'subscription_status')
        op.drop_column('users', 'subscription_plan')
    except Exception as e:
        print(f"⚠️ Could not remove subscription fields: {e}")