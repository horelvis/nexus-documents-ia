#!/usr/bin/env python3
"""
Initialize fresh migrations after clearing all migration files.
This script will:
1. Clear alembic_version table
2. Create a new initial migration
3. Stamp the database as current
"""
import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_command(cmd, cwd=None):
    """Run a command and return the result"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    print(result.stdout)
    return True

def main():
    """Main function"""
    backend_dir = Path(__file__).parent.parent
    
    print("=" * 60)
    print("Fresh Migration Initialization")
    print("=" * 60)
    
    print("\nThis script will:")
    print("1. Clear the alembic_version table")
    print("2. Create a new initial migration")
    print("3. Stamp the database as current")
    print("\nWARNING: Only run this if you've already removed all migration files!")
    
    response = input("\nDo you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return
    
    # Step 1: Clear alembic_version table using docker
    print("\n" + "="*60)
    print("Step 1: Clearing alembic_version table...")
    print("="*60)
    
    docker_cmd = 'docker compose -f docker/docker-compose.yml exec -T db psql -U postgres -d doc_management -c "DELETE FROM alembic_version;"'
    if not run_command(docker_cmd, cwd=backend_dir):
        print("Failed to clear alembic_version table. It might already be empty or database might not be running.")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != 'yes':
            return
    
    # Step 2: Create initial migration
    print("\n" + "="*60)
    print("Step 2: Creating initial migration...")
    print("="*60)
    
    alembic_cmd = 'alembic revision --autogenerate -m "Initial migration"'
    if not run_command(alembic_cmd, cwd=backend_dir):
        print("Failed to create migration.")
        print("\nYou can create it manually with:")
        print(f"  cd {backend_dir}")
        print("  alembic revision --autogenerate -m 'Initial migration'")
        return
    
    # Step 3: Stamp database
    print("\n" + "="*60)
    print("Step 3: Stamping database as current...")
    print("="*60)
    
    response = input("\nDo you want to stamp the database as current? (yes/no): ")
    if response.lower() == 'yes':
        stamp_cmd = 'alembic stamp head'
        if not run_command(stamp_cmd, cwd=backend_dir):
            print("Failed to stamp database.")
            print("\nYou can stamp it manually with:")
            print(f"  cd {backend_dir}")
            print("  alembic stamp head")
        else:
            print("\n✅ Database stamped successfully!")
    
    print("\n" + "="*60)
    print("Migration initialization complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Review the generated migration file in alembic/versions/")
    print("2. If the migration looks correct, commit it to git")
    print("3. For new databases, run: alembic upgrade head")

if __name__ == "__main__":
    main()