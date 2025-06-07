"""add onboarding_completed column

Revision ID: add_onboarding_completed
Revises: add_agents_system
Create Date: 2025-06-07 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_onboarding_completed'
down_revision = 'add_agents_system'
branch_labels = None
depends_on = None

def upgrade():
    """Add onboarding_completed column to users table"""
    # Verificar si la columna ya existe antes de agregarla
    conn = op.get_bind()
    
    # Verificar si la columna existe
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' AND column_name='onboarding_completed'
    """)
    
    if not result.fetchone():
        # La columna no existe, agregarla
        op.add_column('users', sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'))
        print("✅ Column onboarding_completed added to users table")
    else:
        print("✅ Column onboarding_completed already exists in users table")

def downgrade():
    """Remove onboarding_completed column from users table"""
    # Verificar si la columna existe antes de eliminarla
    conn = op.get_bind()
    
    result = conn.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' AND column_name='onboarding_completed'
    """)
    
    if result.fetchone():
        # La columna existe, eliminarla
        op.drop_column('users', 'onboarding_completed')
        print("✅ Column onboarding_completed removed from users table")
    else:
        print("✅ Column onboarding_completed does not exist in users table")