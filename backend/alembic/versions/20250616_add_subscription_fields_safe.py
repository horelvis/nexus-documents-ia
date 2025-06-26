"""add subscription fields to user (safe version)

Revision ID: add_sub_fields_001_safe
Revises: add_doc_categorization
Create Date: 2025-06-26 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'add_sub_fields_001_safe'
down_revision = 'add_doc_categorization'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add subscription_plan and subscription_status to users table"""
    # Check and add subscription_plan
    if not column_exists('users', 'subscription_plan'):
        op.add_column('users', sa.Column('subscription_plan', sa.String(50), nullable=True, server_default='free'))
        print("✅ Added subscription_plan to users table")
    else:
        print("ℹ️ Column subscription_plan already exists in users table")
    
    # Check and add subscription_status
    if not column_exists('users', 'subscription_status'):
        op.add_column('users', sa.Column('subscription_status', sa.String(50), nullable=True, server_default='active'))
        print("✅ Added subscription_status to users table")
    else:
        print("ℹ️ Column subscription_status already exists in users table")


def downgrade():
    """Remove subscription fields from users table"""
    # Check and remove subscription_status
    if column_exists('users', 'subscription_status'):
        op.drop_column('users', 'subscription_status')
        print("✅ Removed subscription_status from users table")
    
    # Check and remove subscription_plan
    if column_exists('users', 'subscription_plan'):
        op.drop_column('users', 'subscription_plan')
        print("✅ Removed subscription_plan from users table")