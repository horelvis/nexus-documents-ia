#!/usr/bin/env python3
"""
Script para crear migraciones de Alembic de forma segura, evitando múltiples cabezas
"""
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.alembic_utils import AlembicMigrationManager
try:
    from scripts.alembic_safe_migrate import SafeMigrationRunner
except ImportError:
    SafeMigrationRunner = None


def run_alembic_command(command: str) -> tuple[bool, str]:
    """Ejecuta un comando de alembic y captura la salida"""
    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent  # backend directory
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create Alembic migrations safely',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new migration
  python scripts/create_migration.py -m "add user preferences table"
  
  # Check for problems before creating
  python scripts/create_migration.py --check
  
  # Auto-generate migration from model changes
  python scripts/create_migration.py -m "add new fields" --autogenerate
  
  # Fix multiple heads if they exist
  python scripts/create_migration.py --fix-heads
"""
    )
    
    parser.add_argument('-m', '--message', help='Migration message')
    parser.add_argument('--autogenerate', action='store_true', 
                       help='Use alembic autogenerate to detect model changes')
    parser.add_argument('--check', action='store_true',
                       help='Check for migration problems')
    parser.add_argument('--fix-heads', action='store_true',
                       help='Fix multiple heads if they exist')
    parser.add_argument('--sql', action='store_true',
                       help='Generate SQL script instead of Python migration')
    parser.add_argument('--safe-check', action='store_true',
                       help='Check for table/column conflicts before creating')
    
    args = parser.parse_args()
    
    manager = AlembicMigrationManager()
    
    # Run safe check if requested
    if args.safe_check and SafeMigrationRunner:
        print("Running safe migration check...")
        safe_runner = SafeMigrationRunner()
        conflicts = safe_runner.analyze_all_migrations()
        
        if conflicts:
            print("⚠️  Potential conflicts detected:")
            for revision, conflict_list in conflicts.items():
                print(f"\nRevision {revision}:")
                for conflict in conflict_list:
                    print(f"  - {conflict}")
            print("\nUse 'alembic_safe_migrate.py --fix-script' to generate fix SQL")
        else:
            print("✅ No conflicts detected")
        
        if args.check:
            sys.exit(0 if not conflicts else 1)
    
    # Check for problems first
    if args.check or not args.fix_heads:
        print("Checking for migration problems...")
        problems = manager.detect_problems()
        
        if problems['multiple_heads']:
            print(f"⚠️  Multiple heads detected: {problems['multiple_heads']}")
            if not args.fix_heads:
                print("Run with --fix-heads to automatically fix this issue")
                if not args.check:
                    sys.exit(1)
        
        if problems['missing_dependencies']:
            print(f"⚠️  Missing dependencies detected:")
            for dep in problems['missing_dependencies']:
                print(f"   - {dep['revision']} depends on missing {dep['missing']}")
        
        if args.check:
            if not any(problems.values()):
                print("✅ No problems detected!")
            sys.exit(0 if not any(problems.values()) else 1)
    
    # Fix heads if requested
    if args.fix_heads:
        print("Fixing multiple heads...")
        success = manager.fix_multiple_heads()
        if success:
            print("✅ Multiple heads fixed!")
        else:
            print("❌ Could not fix multiple heads automatically")
            sys.exit(1)
        sys.exit(0)
    
    # Create migration
    if not args.message:
        print("Error: -m/--message is required to create a migration")
        sys.exit(1)
    
    # Ensure single head before creating
    heads = manager.find_heads()
    if len(heads) > 1:
        print(f"❌ Cannot create migration: multiple heads exist ({heads})")
        print("Run with --fix-heads first")
        sys.exit(1)
    
    if args.autogenerate:
        # Use alembic autogenerate
        print(f"Generating migration with alembic autogenerate: {args.message}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_message = args.message.replace(' ', '_').replace('-', '_').lower()
        revision_id = f"{safe_message}_{timestamp}"
        
        command = f"alembic revision --autogenerate -m \"{args.message}\" --rev-id {revision_id}"
        success, output = run_alembic_command(command)
        
        if success:
            print("✅ Migration created successfully!")
            # Extract file path from output
            for line in output.split('\n'):
                if 'Generating' in line and '.py' in line:
                    print(f"   File: {line.strip()}")
        else:
            print(f"❌ Failed to create migration:")
            print(output)
            sys.exit(1)
    else:
        # Use our custom creation
        print(f"Creating migration: {args.message}")
        
        try:
            file_path = manager.create_migration(args.message)
            print(f"✅ Migration created successfully!")
            print(f"   File: {file_path}")
            print(f"\n⚠️  Remember to implement the upgrade() and downgrade() functions!")
        except Exception as e:
            print(f"❌ Failed to create migration: {e}")
            sys.exit(1)
    
    # Show current chain
    print("\nCurrent migration chain:")
    manager.visualize_chain()


if __name__ == '__main__':
    main()