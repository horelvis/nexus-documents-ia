"""Initial migration - Clean database start

Revision ID: unified_20250615
Revises: None
Create Date: 2025-06-15 23:00:00.000000

Note: Database structure is created from models.py
This migration serves as the initial version marker for Alembic
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
    """Initial migration - database created from models.py"""
    # Since database is reset and tables are created from models.py,
    # this migration just serves as the initial alembic version marker
    print("✅ Initial migration - database structure created from models.py")
    
    # Add a commit to ensure the migration completes
    connection = op.get_bind()
    connection.execute(sa.text("SELECT 1"))  # Simple query to ensure connection works
    print("✅ Migration completed successfully")


def downgrade():
    """No downgrade for initial migration"""
    pass