"""Simplify subscriptions - remove Plan and Price tables

Revision ID: 20250608_180000
Revises: 20250608_150000
Create Date: 2025-06-08 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250608_180000'
down_revision = '20250608_150000'
branch_labels = None
depends_on = None


def upgrade():
    # Remove foreign key constraint from subscriptions to plans
    op.drop_constraint('subscriptions_plan_id_fkey', 'subscriptions', type_='foreignkey')
    
    # Drop the plan_id column from subscriptions (keeping stripe_plan_id)
    op.drop_column('subscriptions', 'plan_id')
    
    # Drop the prices table
    op.drop_table('prices')
    
    # Drop the plans table
    op.drop_table('plans')
    
    # Update subscriptions table indexes
    op.create_index('idx_subscriptions_stripe_plan', 'subscriptions', ['stripe_plan_id'])


def downgrade():
    # Recreate plans table
    op.create_table('plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_users', sa.Integer(), nullable=True),
        sa.Column('max_storage_mb', sa.Integer(), nullable=True),
        sa.Column('max_documents', sa.Integer(), nullable=True),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Recreate prices table
    op.create_table('prices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('interval', sa.String(length=20), nullable=False),
        sa.Column('stripe_price_id', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_price_id')
    )
    
    # Add plan_id back to subscriptions
    op.add_column('subscriptions', sa.Column('plan_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('subscriptions_plan_id_fkey', 'subscriptions', 'plans', ['plan_id'], ['id'])
    
    # Remove the new index
    op.drop_index('idx_subscriptions_stripe_plan', table_name='subscriptions')