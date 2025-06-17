"""Remove teams and team_members tables

Revision ID: remove_teams_tables
Revises: add_teams_and_members_tables
Create Date: 2025-06-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'remove_teams_tables'
down_revision = 'add_teams_and_members_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop team_members table first (due to foreign key constraints)
    op.drop_table('team_members')
    
    # Drop teams table
    op.drop_table('teams')


def downgrade() -> None:
    # Recreate teams table
    op.create_table('teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'tenant_id', name='uq_team_name_tenant')
    )
    op.create_index('idx_teams_tenant', 'teams', ['tenant_id'], unique=False)
    
    # Recreate team_members table
    op.create_table('team_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_member')
    )
    op.create_index('idx_team_members_team', 'team_members', ['team_id'], unique=False)
    op.create_index('idx_team_members_user', 'team_members', ['user_id'], unique=False)