"""Unified migration to fix all issues

Revision ID: unified_20250615
Revises: add_agents_system
Create Date: 2025-06-15 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'unified_20250615'
down_revision = 'add_agents_system'
branch_labels = None
depends_on = None


def upgrade():
    """Apply all necessary changes"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # 1. Add onboarding_completed to users if not exists
    if 'users' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('users')]
        if 'onboarding_completed' not in columns:
            op.add_column('users', sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'))
            print("✅ Added onboarding_completed to users")
    
    # 2. Add stripe_customer_id to users if not exists
    if 'users' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('users')]
        if 'stripe_customer_id' not in columns:
            op.add_column('users', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
            op.create_index('idx_users_stripe_customer_id', 'users', ['stripe_customer_id'], unique=True)
            print("✅ Added stripe_customer_id to users")
    
    # 3. Fix subscriptions table if it exists
    if 'subscriptions' in inspector.get_table_names():
        columns = {col['name']: col for col in inspector.get_columns('subscriptions')}
        
        # Make problematic columns nullable
        for col_name in ['plan_id', 'price_id']:
            if col_name in columns and not columns[col_name]['nullable']:
                op.alter_column('subscriptions', col_name,
                               existing_type=columns[col_name]['type'],
                               nullable=True)
                print(f"✅ Made {col_name} nullable in subscriptions")
        
        # Ensure stripe_plan_id exists
        if 'stripe_plan_id' not in columns:
            op.add_column('subscriptions', sa.Column('stripe_plan_id', sa.String(50), nullable=True))
            op.create_index('idx_subscriptions_stripe_plan', 'subscriptions', ['stripe_plan_id'])
            print("✅ Added stripe_plan_id to subscriptions")
        
        # Drop old foreign key constraints if they exist
        foreign_keys = inspector.get_foreign_keys('subscriptions')
        for fk in foreign_keys:
            if 'plan_id' in fk['constrained_columns']:
                op.drop_constraint(fk['name'], 'subscriptions', type_='foreignkey')
                print(f"✅ Dropped foreign key {fk['name']}")
    
    print("✅ Unified migration completed")


def downgrade():
    """Revert changes"""
    # We generally don't want to remove these columns
    pass