"""Safe migration to handle any existing state

Revision ID: 20250608_200000
Revises: 20250608_150000
Create Date: 2025-06-08 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20250608_200000'
down_revision = '20250608_150000'  # Go back to the last known good state
branch_labels = None
depends_on = None


def upgrade():
    """Safe upgrade that handles any existing state"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    print(f"Existing tables: {existing_tables}")
    
    # 1. Handle subscriptions table
    if 'subscriptions' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('subscriptions')]
        print(f"Existing columns in subscriptions: {existing_columns}")
        
        # Add stripe_plan_id if it doesn't exist
        if 'stripe_plan_id' not in existing_columns:
            op.add_column('subscriptions', sa.Column('stripe_plan_id', sa.String(50), nullable=True))
            op.create_index('idx_subscriptions_stripe_plan', 'subscriptions', ['stripe_plan_id'])
        
        # Remove plan_id foreign key constraint if it exists
        try:
            constraints = inspector.get_foreign_keys('subscriptions')
            for constraint in constraints:
                if constraint['constrained_columns'] == ['plan_id']:
                    op.drop_constraint(constraint['name'], 'subscriptions', type_='foreignkey')
                    print(f"Dropped foreign key: {constraint['name']}")
        except Exception as e:
            print(f"No foreign key to drop: {e}")
        
        # Remove plan_id column if it exists
        if 'plan_id' in existing_columns:
            try:
                op.drop_column('subscriptions', 'plan_id')
                print("Dropped plan_id column")
            except Exception as e:
                print(f"Could not drop plan_id: {e}")
    
    # 2. Drop prices table if it exists
    if 'prices' in existing_tables:
        try:
            op.drop_table('prices')
            print("Dropped prices table")
        except Exception as e:
            print(f"Could not drop prices table: {e}")
    
    # 3. Drop plans table if it exists
    if 'plans' in existing_tables:
        try:
            op.drop_table('plans')
            print("Dropped plans table")
        except Exception as e:
            print(f"Could not drop plans table: {e}")
    
    print("Migration completed successfully")


def downgrade():
    """Downgrade is not supported for this cleanup migration"""
    pass