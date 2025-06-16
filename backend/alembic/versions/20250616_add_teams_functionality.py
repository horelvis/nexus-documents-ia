"""add teams functionality

Revision ID: add_teams_001
Revises: add_sub_fields_001
Create Date: 2025-06-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_teams_001'
down_revision = 'add_sub_fields_001'
branch_labels = None
depends_on = None


def upgrade():
    """Add team functionality"""
    
    # Add team member fields to users table
    op.add_column('users', sa.Column('is_team_member', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('users', sa.Column('invited_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create team_invitations table
    op.create_table('team_invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('invitation_code', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('used_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_invitation_code_expires', 'team_invitations', ['invitation_code', 'expires_at'])
    op.create_index('idx_team_invitations_tenant', 'team_invitations', ['tenant_id'])
    op.create_unique_constraint('uq_invitation_code', 'team_invitations', ['invitation_code'])
    
    # Create foreign key for invited_by in users table
    op.create_foreign_key('fk_users_invited_by', 'users', 'users', ['invited_by'], ['id'])
    
    print("✅ Added team functionality")


def downgrade():
    """Remove team functionality"""
    
    # Remove foreign key
    op.drop_constraint('fk_users_invited_by', 'users', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('idx_invitation_code_expires', table_name='team_invitations')
    op.drop_index('idx_team_invitations_tenant', table_name='team_invitations')
    
    # Drop table
    op.drop_table('team_invitations')
    
    # Remove columns from users table
    op.drop_column('users', 'invited_at')
    op.drop_column('users', 'invited_by')
    op.drop_column('users', 'is_team_member')