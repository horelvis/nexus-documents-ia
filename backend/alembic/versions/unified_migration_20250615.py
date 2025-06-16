"""Unified migration to fix all issues

Revision ID: unified_20250615
Revises: None
Create Date: 2025-06-15 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers
revision = 'unified_20250615'
down_revision = None  # This is the first migration now
branch_labels = None
depends_on = None


def upgrade():
    """Apply all necessary changes"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Fix alembic version history if needed
    try:
        # Check current alembic version
        result = connection.execute(sa.text("SELECT version_num FROM alembic_version"))
        current_version = result.scalar()
        if current_version and current_version not in ['unified_20250615']:
            print(f"⚠️ Found old alembic version: {current_version}")
            # Update to this migration
            connection.execute(sa.text("UPDATE alembic_version SET version_num = :new_version"), 
                             {"new_version": revision})
            print(f"✅ Updated alembic version to {revision}")
    except Exception as e:
        print(f"⚠️ Could not check alembic version: {e}")
    
    # 0. Drop unnecessary tables (agents moved to LangChain, subscriptions to Stripe)
    tables_to_drop = [
        # Agent tables - order matters due to foreign keys
        'agent_messages',
        'agent_executions', 
        'agent_conversations',
        'agents',
        'agent_tools',
        # Subscription table (Stripe is source of truth)
        'subscriptions'
    ]
    
    existing_tables = inspector.get_table_names()
    
    # Drop tables with CASCADE to handle foreign keys
    for table in tables_to_drop:
        if table in existing_tables:
            try:
                # Use raw SQL with CASCADE for PostgreSQL
                connection.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                if 'agent' in table:
                    print(f"✅ Dropped {table} table (agents now handled by LangChain)")
                elif table == 'subscriptions':
                    print(f"✅ Dropped {table} table (Stripe is source of truth)")
            except Exception as e:
                print(f"⚠️ Error dropping {table}: {e}")
    
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
    
    # 3. Note: Subscriptions table is dropped above since Stripe is the source of truth
    
    print("✅ Unified migration completed")


def downgrade():
    """Revert changes"""
    # We generally don't want to remove these columns
    pass