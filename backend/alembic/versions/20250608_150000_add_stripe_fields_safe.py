"""add stripe fields safely

Revision ID: 20250608_150000
Revises: add_onboarding_completed
Create Date: 2025-01-08 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250608_150000'
down_revision = 'add_onboarding_completed'
branch_labels = None
depends_on = None


def upgrade():
    """Add Stripe integration fields safely"""
    # Add stripe_customer_id to users table
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    op.create_index('ix_users_stripe_customer_id', 'users', ['stripe_customer_id'])

    # Update subscriptions table with Stripe fields
    # First add new columns
    op.add_column('subscriptions', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    op.add_column('subscriptions', sa.Column('stripe_plan_id', sa.String(50), nullable=True))
    op.add_column('subscriptions', sa.Column('interval', sa.String(20), nullable=False, server_default='month'))
    
    # Create indexes for new columns
    op.create_index('ix_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'])
    
    # Ensure stripe_subscription_id has index if it doesn't exist
    try:
        op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'])
    except:
        pass  # Index might already exist


def downgrade():
    """Remove Stripe integration fields"""
    # Remove new columns from subscriptions
    op.drop_index('ix_subscriptions_stripe_customer_id', 'subscriptions')
    op.drop_column('subscriptions', 'stripe_customer_id')
    op.drop_column('subscriptions', 'stripe_plan_id')
    op.drop_column('subscriptions', 'interval')

    # Remove stripe_customer_id from users
    op.drop_index('ix_users_stripe_customer_id', 'users')
    op.drop_column('users', 'stripe_customer_id')