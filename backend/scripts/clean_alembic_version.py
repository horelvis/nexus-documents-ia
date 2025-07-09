#!/usr/bin/env python3
"""
Clean up alembic_version table after removing migration files
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

def clean_alembic_version():
    """Remove all entries from alembic_version table"""
    engine = create_engine(settings.SYNC_DATABASE_URL)
    
    with engine.begin() as conn:
        # Check current versions
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        versions = [row[0] for row in result]
        
        if versions:
            print("Current alembic versions in database:")
            for v in versions:
                print(f"  - {v}")
            
            response = input("\nDo you want to clear all alembic versions? (yes/no): ")
            if response.lower() == 'yes':
                # Clear the table
                conn.execute(text("DELETE FROM alembic_version"))
                print("\nAlembic version table cleared!")
                print("\nNext steps:")
                print("1. Create a new initial migration:")
                print("   cd backend && alembic revision --autogenerate -m 'Initial migration'")
                print("2. Review the generated migration file")
                print("3. Stamp the database as up-to-date:")
                print("   cd backend && alembic stamp head")
            else:
                print("Aborted.")
        else:
            print("Alembic version table is already empty.")

if __name__ == "__main__":
    clean_alembic_version()