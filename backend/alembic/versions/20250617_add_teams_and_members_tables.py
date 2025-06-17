"""add teams and team members tables

Revision ID: add_teams_002
Revises: add_teams_001
Create Date: 2025-06-17 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_teams_002'
down_revision = 'add_teams_001'
branch_labels = None
depends_on = None


def upgrade():
    """Add teams and team_members tables"""
    
    # Create teams table
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
    
    # Create team_members table
    op.create_table('team_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_member')
    )
    
    # Create indexes
    op.create_index('idx_teams_tenant', 'teams', ['tenant_id'])
    op.create_index('idx_team_members_team', 'team_members', ['team_id'])
    op.create_index('idx_team_members_user', 'team_members', ['user_id'])
    
    print("✅ Added teams and team_members tables")


def downgrade():
    """Remove teams and team_members tables"""
    
    # Drop indexes
    op.drop_index('idx_team_members_user', table_name='team_members')
    op.drop_index('idx_team_members_team', table_name='team_members')
    op.drop_index('idx_teams_tenant', table_name='teams')
    
    # Drop tables
    op.drop_table('team_members')
    op.drop_table('teams')
    
    print("✅ Removed teams and team_members tables")