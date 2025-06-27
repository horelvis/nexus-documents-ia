#!/usr/bin/env python3
"""
Squash all migrations into a single initial migration.
This is useful when you have too many migrations and want to start fresh.
"""
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def backup_migrations():
    """Backup current migrations"""
    versions_dir = Path("alembic/versions")
    backup_dir = Path(f"alembic/versions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    
    if versions_dir.exists():
        print(f"Backing up migrations to {backup_dir}")
        shutil.copytree(versions_dir, backup_dir)
        return backup_dir
    return None

def remove_all_migrations():
    """Remove all migration files"""
    versions_dir = Path("alembic/versions")
    if versions_dir.exists():
        for file in versions_dir.glob("*.py"):
            print(f"Removing {file}")
            file.unlink()
        
        # Remove __pycache__
        pycache = versions_dir / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache)

def create_squashed_migration():
    """Create a new migration with all current models"""
    from alembic import command
    from alembic.config import Config
    
    # Create alembic config
    alembic_cfg = Config("alembic.ini")
    
    # Generate new migration
    command.revision(
        alembic_cfg,
        autogenerate=True,
        message="Initial squashed migration",
        rev_id="initial_migration"
    )
    
    print("Created new squashed migration")

def main():
    """Main function"""
    print("WARNING: This will remove all existing migrations!")
    print("This action cannot be undone without the backup.")
    
    response = input("\nDo you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return
    
    # Backup current migrations
    backup_dir = backup_migrations()
    if backup_dir:
        print(f"\nBackup created at: {backup_dir}")
    
    # Remove all migrations
    print("\nRemoving all migrations...")
    remove_all_migrations()
    
    # Ask if user wants to create squashed migration
    response = input("\nDo you want to create a squashed migration? (yes/no): ")
    if response.lower() == 'yes':
        try:
            create_squashed_migration()
            print("\nSquashed migration created successfully!")
            print("\nNext steps:")
            print("1. Review the new migration file")
            print("2. Run: alembic stamp head")
            print("3. Commit the changes")
        except Exception as e:
            print(f"\nError creating squashed migration: {e}")
            print("You may need to create it manually with:")
            print("  alembic revision --autogenerate -m 'Initial migration'")
    
    print("\nDone!")
    print(f"\nYour old migrations are backed up in: {backup_dir}")

if __name__ == "__main__":
    main()