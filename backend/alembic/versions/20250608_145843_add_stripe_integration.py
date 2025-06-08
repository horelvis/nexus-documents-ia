"""add stripe integration

Revision ID: 20250608_145843
Revises: add_onboarding_completed
Create Date: 2025-01-08 14:58:43.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250608_145843'
down_revision = 'add_onboarding_completed'
branch_labels = None
depends_on = None


def upgrade():
    """Add Stripe integration fields"""
    # Add stripe_customer_id to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(255), nullable=True))
        batch_op.create_index('ix_users_stripe_customer_id', ['stripe_customer_id'])

    # Add stripe fields to subscriptions table
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('interval', sa.String(20), nullable=False, server_default='month'))
        batch_op.create_index('ix_subscriptions_stripe_customer_id', ['stripe_customer_id'])
        batch_op.create_index('ix_subscriptions_stripe_subscription_id', ['stripe_subscription_id'])
        
        # Modify plan_id column type from UUID to String
        batch_op.alter_column('plan_id',
                             existing_type=sa.dialects.postgresql.UUID(),
                             type_=sa.String(50),
                             existing_nullable=False)


def downgrade():
    """Remove Stripe integration fields"""
    # Remove new columns from subscriptions
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index('ix_subscriptions_stripe_customer_id')
        batch_op.drop_index('ix_subscriptions_stripe_subscription_id')
        batch_op.drop_column('stripe_customer_id')
        batch_op.drop_column('interval')
        
        # Revert plan_id column type back to UUID (note: this may cause data loss)
        batch_op.alter_column('plan_id',
                             existing_type=sa.String(50),
                             type_=sa.dialects.postgresql.UUID(),
                             existing_nullable=False)

    # Remove stripe_customer_id from users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_stripe_customer_id')
        batch_op.drop_column('stripe_customer_id')