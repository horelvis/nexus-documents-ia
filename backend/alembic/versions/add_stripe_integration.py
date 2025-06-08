"""add stripe integration fields

Revision ID: add_stripe_integration
Revises: add_onboarding_completed
Create Date: 2025-01-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_stripe_integration'
down_revision = 'add_onboarding_completed'
branch_labels = None
depends_on = None

def upgrade():
    """Add Stripe integration fields"""
    conn = op.get_bind()
    
    # Add stripe_customer_id to users table
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' AND column_name='stripe_customer_id'
    """)
    
    if not result.fetchone():
        op.add_column('users', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
        op.create_index('ix_users_stripe_customer_id', 'users', ['stripe_customer_id'])
        print("✅ Column stripe_customer_id added to users table")
    else:
        print("✅ Column stripe_customer_id already exists in users table")
    
    # Update subscriptions table structure
    # Check if stripe_customer_id exists in subscriptions
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='subscriptions' AND column_name='stripe_customer_id'
    """)
    
    if not result.fetchone():
        op.add_column('subscriptions', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
        op.create_index('ix_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'])
        print("✅ Column stripe_customer_id added to subscriptions table")
    else:
        print("✅ Column stripe_customer_id already exists in subscriptions table")
    
    # Check if interval column exists
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='subscriptions' AND column_name='interval'
    """)
    
    if not result.fetchone():
        op.add_column('subscriptions', sa.Column('interval', sa.String(20), nullable=False, server_default='month'))
        print("✅ Column interval added to subscriptions table")
    else:
        print("✅ Column interval already exists in subscriptions table")
    
    # Modify plan_id column type if needed (from UUID to String)
    try:
        # Check current type of plan_id
        result = conn.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name='subscriptions' AND column_name='plan_id'
        """)
        
        current_type = result.fetchone()
        if current_type and current_type[0] == 'uuid':
            # Drop foreign key constraint if exists
            try:
                op.drop_constraint('subscriptions_plan_id_fkey', 'subscriptions', type_='foreignkey')
            except:
                pass  # Constraint might not exist
            
            # Change column type to String
            op.alter_column('subscriptions', 'plan_id',
                          existing_type=sa.dialects.postgresql.UUID(),
                          type_=sa.String(50),
                          existing_nullable=False)
            print("✅ Column plan_id type changed to String in subscriptions table")
        else:
            print("✅ Column plan_id already has correct type in subscriptions table")
    except Exception as e:
        print(f"⚠️  Could not modify plan_id column: {e}")
    
    # Update stripe_subscription_id index if needed
    try:
        op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'])
        print("✅ Index created for stripe_subscription_id")
    except:
        print("✅ Index for stripe_subscription_id already exists")


def downgrade():
    """Remove Stripe integration fields"""
    conn = op.get_bind()
    
    # Remove stripe_customer_id from users
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' AND column_name='stripe_customer_id'
    """)
    
    if result.fetchone():
        op.drop_index('ix_users_stripe_customer_id', 'users')
        op.drop_column('users', 'stripe_customer_id')
        print("✅ Column stripe_customer_id removed from users table")
    
    # Remove new columns from subscriptions
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='subscriptions' AND column_name='stripe_customer_id'
    """)
    
    if result.fetchone():
        op.drop_index('ix_subscriptions_stripe_customer_id', 'subscriptions')
        op.drop_column('subscriptions', 'stripe_customer_id')
        print("✅ Column stripe_customer_id removed from subscriptions table")
    
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='subscriptions' AND column_name='interval'
    """)
    
    if result.fetchone():
        op.drop_column('subscriptions', 'interval')
        print("✅ Column interval removed from subscriptions table")
    
    # Note: Reverting plan_id type change would be complex and might cause data loss
    # This is intentionally not implemented in downgrade
    print("⚠️  plan_id type change not reverted to avoid data loss")