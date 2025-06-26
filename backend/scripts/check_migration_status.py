#!/usr/bin/env python3
"""
Check and diagnose Alembic migration status
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from alembic.config import Config
from alembic import command, script
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings


def get_db_connection():
    """Get database connection"""
    try:
        engine = create_engine(settings.DATABASE_URL, echo=False)
        return engine
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return None


def check_alembic_version(engine):
    """Check current alembic version in database"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            versions = [row[0] for row in result]
            return versions
    except Exception as e:
        print(f"❌ Error checking alembic_version: {e}")
        return None


def check_transaction_status(engine):
    """Check for any active/aborted transactions"""
    try:
        with engine.connect() as conn:
            # Check for active transactions
            result = conn.execute(text("""
                SELECT pid, state, query, state_change
                FROM pg_stat_activity
                WHERE datname = current_database()
                AND state != 'idle'
                AND pid != pg_backend_pid()
            """))
            active_transactions = result.fetchall()
            return active_transactions
    except Exception as e:
        print(f"❌ Error checking transaction status: {e}")
        return []


def check_migration_files():
    """Check migration files for issues"""
    alembic_dir = Path(__file__).parent.parent / "alembic"
    versions_dir = alembic_dir / "versions"
    
    if not versions_dir.exists():
        print(f"❌ Alembic versions directory not found: {versions_dir}")
        return {}
    
    # Get all migration files
    migration_files = list(versions_dir.glob("*.py"))
    migrations = {}
    
    for file in migration_files:
        if file.name == "__pycache__":
            continue
            
        with open(file, 'r') as f:
            content = f.read()
            
        # Extract revision info
        revision = None
        down_revision = None
        
        for line in content.split('\n'):
            if line.startswith('revision = '):
                revision = eval(line.split('=', 1)[1].strip())
            elif line.startswith('down_revision = '):
                down_revision = eval(line.split('=', 1)[1].strip())
                
        if revision:
            migrations[revision] = {
                'file': file.name,
                'down_revision': down_revision,
                'path': str(file)
            }
    
    return migrations


def check_migration_chain(migrations):
    """Check for issues in migration chain"""
    issues = []
    
    # Check for multiple heads
    heads = []
    for rev, info in migrations.items():
        # Check if this revision is not referenced by any other
        is_head = True
        for other_rev, other_info in migrations.items():
            if other_info['down_revision'] == rev:
                is_head = False
                break
        if is_head:
            heads.append(rev)
    
    if len(heads) > 1:
        issues.append(f"Multiple heads found: {heads}")
    
    # Check for circular dependencies
    for rev, info in migrations.items():
        down_rev = info['down_revision']
        if down_rev and down_rev in migrations:
            # Check if down_revision points back to this revision
            if migrations[down_rev]['down_revision'] == rev:
                issues.append(f"Circular dependency: {rev} <-> {down_rev}")
    
    # Check for missing dependencies
    for rev, info in migrations.items():
        down_rev = info['down_revision']
        if down_rev and down_rev not in migrations and down_rev != 'None':
            issues.append(f"Missing dependency: {rev} depends on non-existent {down_rev}")
    
    return issues


def main():
    print("🔍 Checking Alembic Migration Status...\n")
    
    # 1. Check database connection
    engine = get_db_connection()
    if not engine:
        return
    
    print("✅ Database connection successful\n")
    
    # 2. Check current alembic version
    print("📌 Current Alembic Version(s) in Database:")
    versions = check_alembic_version(engine)
    if versions:
        for v in versions:
            print(f"  - {v}")
    else:
        print("  - No version found (table may not exist)")
    print()
    
    # 3. Check transaction status
    print("🔄 Active Transactions:")
    transactions = check_transaction_status(engine)
    if transactions:
        for t in transactions:
            print(f"  - PID: {t[0]}, State: {t[1]}, Query: {t[2][:50]}...")
    else:
        print("  - No active transactions")
    print()
    
    # 4. Check migration files
    print("📁 Migration Files:")
    migrations = check_migration_files()
    for rev, info in sorted(migrations.items()):
        print(f"  - {rev}: {info['file']} (parent: {info['down_revision']})")
    print()
    
    # 5. Check for issues
    print("🚨 Checking for Issues:")
    issues = check_migration_chain(migrations)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ No issues found in migration chain")
    print()
    
    # 6. Check specific problematic migrations
    print("🔍 Checking Specific Migrations:")
    problematic = ['add_doc_categorization', 'add_sub_fields_001']
    for rev in problematic:
        if rev in migrations:
            info = migrations[rev]
            print(f"  - {rev}:")
            print(f"    File: {info['file']}")
            print(f"    Parent: {info['down_revision']}")
            print(f"    Path: {info['path']}")
    
    engine.dispose()


if __name__ == "__main__":
    main()