#!/usr/bin/env python3
"""
Create a proper migration for adding role field to signature_request_signers
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_migration():
    """Create a migration file that properly handles existing data"""
    
    migrations_dir = Path(__file__).parent.parent / "alembic" / "versions"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    revision_id = f"add_role_to_signers_{timestamp}"
    
    migration_content = f'''"""add role field to signature request signers

Revision ID: {revision_id}
Revises: head
Create Date: {datetime.now()}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '{revision_id}'
down_revision: Union[str, None] = 'head'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add role column as nullable first
    op.add_column('signature_request_signers', 
        sa.Column('role', sa.String(length=20), nullable=True)
    )
    
    # Update existing records to have default value
    op.execute("UPDATE signature_request_signers SET role = 'signer' WHERE role IS NULL")
    
    # Now make the column NOT NULL
    op.alter_column('signature_request_signers', 'role',
        existing_type=sa.String(length=20),
        nullable=False
    )


def downgrade() -> None:
    op.drop_column('signature_request_signers', 'role')
'''
    
    # Write the migration file
    migration_file = migrations_dir / f"{revision_id}.py"
    
    with open(migration_file, 'w') as f:
        f.write(migration_content)
    
    print(f"✅ Created migration file: {migration_file}")
    print("\nNow run:")
    print(f"  alembic upgrade {revision_id}")
    
    return revision_id

if __name__ == "__main__":
    create_migration()