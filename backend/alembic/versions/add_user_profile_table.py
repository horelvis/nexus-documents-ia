"""Add user profile table for extended onboarding data

Revision ID: add_user_profile_table
Revises: add_onboarding_completed_column
Create Date: 2025-01-06 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_user_profile_table'
down_revision = 'add_onboarding_completed_column'
branch_labels = None
depends_on = None


def upgrade():
    # Create user_profiles table
    op.create_table('user_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('role', sa.String(length=100), nullable=True),
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('team_size', sa.String(length=50), nullable=True),
        sa.Column('use_case', sa.Text(), nullable=True),
        sa.Column('selected_plan', sa.String(length=50), nullable=True),
        sa.Column('payment_interval', sa.String(length=20), nullable=True),
        sa.Column('onboarding_step', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    
    # Create indexes
    op.create_index('idx_user_profiles_user_id', 'user_profiles', ['user_id'], unique=False)
    op.create_index('idx_user_profiles_selected_plan', 'user_profiles', ['selected_plan'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('idx_user_profiles_selected_plan', table_name='user_profiles')
    op.drop_index('idx_user_profiles_user_id', table_name='user_profiles')
    
    # Drop table
    op.drop_table('user_profiles')