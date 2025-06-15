"""Fix subscription plan_id column issue

Revision ID: 20250615_fix_plan_id
Revises: 20250608_200000
Create Date: 2025-06-15 19:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20250615_fix_plan_id'
down_revision = '20250608_200000'
branch_labels = None
depends_on = None


def upgrade():
    """Fix the plan_id column issue in subscriptions table"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if subscriptions table exists
    if 'subscriptions' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('subscriptions')]
        print(f"Current columns in subscriptions: {columns}")
        
        # If plan_id exists, make it nullable first
        if 'plan_id' in columns:
            print("Making plan_id nullable...")
            op.alter_column('subscriptions', 'plan_id',
                          existing_type=sa.UUID(),
                          nullable=True)
        
        # Ensure stripe_plan_id exists
        if 'stripe_plan_id' not in columns:
            print("Adding stripe_plan_id column...")
            op.add_column('subscriptions', 
                         sa.Column('stripe_plan_id', sa.String(50), nullable=True))
            op.create_index('idx_subscriptions_stripe_plan', 'subscriptions', ['stripe_plan_id'])
        
        # Copy data from plan_id to stripe_plan_id if needed
        if 'plan_id' in columns and 'stripe_plan_id' in columns:
            print("Migrating data from plan_id to stripe_plan_id...")
            # First, handle UUID plan_id values by converting them to string names
            op.execute("""
                UPDATE subscriptions 
                SET stripe_plan_id = CASE 
                    WHEN plan_id IS NULL THEN 'free'
                    ELSE 'pro'  -- Default to pro for any existing plan_id
                END
                WHERE stripe_plan_id IS NULL
            """)
        
        # Drop foreign key constraints on plan_id if they exist
        if 'plan_id' in columns:
            print("Dropping foreign key constraints on plan_id...")
            constraints = inspector.get_foreign_keys('subscriptions')
            for constraint in constraints:
                if 'plan_id' in constraint['constrained_columns']:
                    print(f"Dropping constraint: {constraint['name']}")
                    op.drop_constraint(constraint['name'], 'subscriptions', type_='foreignkey')
        
        # Drop the plan_id column if it exists
        if 'plan_id' in columns:
            print("Dropping plan_id column...")
            op.drop_column('subscriptions', 'plan_id')
        
        print("✅ Migration completed successfully!")
    else:
        print("Subscriptions table not found, skipping...")


def downgrade():
    """Revert changes - add plan_id back"""
    # We won't implement downgrade as this is a fix migration
    pass