#!/usr/bin/env python3
"""
Reset migrations - mark all as applied without running them
"""
import sys
import subprocess
from pathlib import Path

def run_command(cmd):
    """Run a command and return success status"""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            cwd=Path(__file__).parent.parent
        )
        print(f"Command: {cmd}")
        if result.stdout:
            print(f"Output: {result.stdout}")
        if result.stderr:
            print(f"Error: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Failed to run command: {e}")
        return False

def main():
    print("🔄 Resetting Alembic migrations...")
    
    # Check current status
    print("\n📊 Current migration status:")
    run_command("alembic current")
    
    # Show heads
    print("\n🎯 Current heads:")
    run_command("alembic heads")
    
    # Ask for confirmation
    response = input("\n⚠️  This will mark ALL migrations as applied without running them.\n"
                    "Are you sure? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ Cancelled")
        return
    
    # Stamp head
    print("\n✅ Marking all migrations as applied...")
    if run_command("alembic stamp head"):
        print("✅ Successfully reset migrations!")
        print("\n📊 New status:")
        run_command("alembic current")
    else:
        print("❌ Failed to reset migrations")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())