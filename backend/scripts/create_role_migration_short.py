#!/usr/bin/env python3
"""
Create migration with short revision ID
"""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    # Generate a short revision ID (max 32 chars)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    revision_id = f"add_signer_role_{timestamp}"  # This is 29 chars max
    
    print(f"Creating migration with ID: {revision_id} (length: {len(revision_id)})")
    
    # Create the migration using alembic
    cmd = [
        "alembic", "revision",
        "-m", "add role field to signers",
        "--rev-id", revision_id
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, 
                              cwd=Path(__file__).parent.parent)
        
        if result.returncode == 0:
            print("✅ Migration created successfully!")
            print(result.stdout)
            
            # Find the created file
            for line in result.stdout.split('\n'):
                if '.py' in line and 'Generating' in line:
                    filepath = line.split()[-1]
                    print(f"\n📝 Edit this file to add the migration logic: {filepath}")
                    print("\nAdd this to the upgrade() function:")
                    print("""
    # Add role column as nullable first
    op.add_column('signature_request_signers', 
        sa.Column('role', sa.String(length=20), nullable=True)
    )
    
    # Update existing records
    op.execute("UPDATE signature_request_signers SET role = 'signer' WHERE role IS NULL")
    
    # Make column NOT NULL
    op.alter_column('signature_request_signers', 'role',
        existing_type=sa.String(length=20),
        nullable=False
    )
    
    # Add default
    op.execute("ALTER TABLE signature_request_signers ALTER COLUMN role SET DEFAULT 'signer'")
""")
                    print("\nAdd this to the downgrade() function:")
                    print("""
    op.drop_column('signature_request_signers', 'role')
""")
        else:
            print("❌ Failed to create migration")
            print(result.stderr)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()