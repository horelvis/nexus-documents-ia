#!/usr/bin/env python3
"""
Analyze and fix Alembic migration issues
This script can be run inside the Docker container
"""
import os
import sys
from pathlib import Path
from datetime import datetime


def analyze_migration_files():
    """Analyze migration files for issues"""
    versions_dir = Path("/app/alembic/versions")
    if not versions_dir.exists():
        versions_dir = Path("alembic/versions")
    
    print("📁 Analyzing Migration Files...")
    print("=" * 60)
    
    migrations = {}
    issues = []
    
    # Read all migration files
    for file in versions_dir.glob("*.py"):
        if file.name == "__init__.py" or file.name.endswith('.bak'):
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
            print(f"\n📄 {file.name}")
            print(f"   Revision: {revision}")
            print(f"   Parent: {down_revision}")
    
    print("\n\n🔍 Checking for Issues...")
    print("=" * 60)
    
    # Check for circular dependencies
    for rev, info in migrations.items():
        if info['down_revision'] in migrations:
            parent_info = migrations[info['down_revision']]
            if parent_info['down_revision'] == rev:
                issue = f"Circular dependency: {rev} <-> {info['down_revision']}"
                issues.append(issue)
                print(f"❌ {issue}")
    
    # Check for multiple heads
    heads = []
    for rev, info in migrations.items():
        is_head = True
        for other_rev, other_info in migrations.items():
            if other_info['down_revision'] == rev:
                is_head = False
                break
        if is_head:
            heads.append(rev)
    
    if len(heads) > 1:
        issue = f"Multiple heads found: {', '.join(heads)}"
        issues.append(issue)
        print(f"❌ {issue}")
    
    # Check for missing dependencies
    for rev, info in migrations.items():
        down_rev = info['down_revision']
        if down_rev and down_rev not in migrations and down_rev not in ['None', None]:
            issue = f"Missing dependency: {rev} depends on non-existent {down_rev}"
            issues.append(issue)
            print(f"❌ {issue}")
    
    if not issues:
        print("✅ No issues found in migration chain")
    
    # Build dependency tree
    print("\n\n🌳 Migration Dependency Tree:")
    print("=" * 60)
    
    # Find root nodes
    roots = []
    for rev, info in migrations.items():
        if not info['down_revision'] or info['down_revision'] == 'None':
            roots.append(rev)
    
    def print_tree(rev, indent=0):
        if rev not in migrations:
            return
        info = migrations[rev]
        print("  " * indent + f"└─ {rev} ({info['file']})")
        # Find children
        for child_rev, child_info in migrations.items():
            if child_info['down_revision'] == rev:
                print_tree(child_rev, indent + 1)
    
    for root in roots:
        print(f"\n🌱 Root: {root}")
        print_tree(root)
    
    return migrations, issues


def check_database_status():
    """Check database and alembic status"""
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        
        print("\n\n💾 Database Status:")
        print("=" * 60)
        
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check alembic version
            try:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                versions = [row[0] for row in result]
                print(f"Current alembic version(s): {', '.join(versions)}")
            except Exception as e:
                print(f"❌ Error reading alembic_version: {e}")
            
            # Check for transaction issues
            try:
                result = conn.execute(text("""
                    SELECT pid, state, query 
                    FROM pg_stat_activity 
                    WHERE datname = current_database() 
                    AND state = 'idle in transaction'
                    AND pid != pg_backend_pid()
                """))
                blocked = result.fetchall()
                if blocked:
                    print(f"\n⚠️  Found {len(blocked)} idle transactions:")
                    for row in blocked:
                        print(f"   PID: {row[0]}, State: {row[1]}")
                else:
                    print("✅ No idle transactions found")
            except Exception as e:
                print(f"❌ Error checking transactions: {e}")
                
    except ImportError:
        print("⚠️  Cannot check database (SQLAlchemy not available in this context)")
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")


def suggest_fixes(migrations, issues):
    """Suggest fixes for found issues"""
    print("\n\n🛠️  Suggested Fixes:")
    print("=" * 60)
    
    if 'add_doc_categorization' in migrations and 'add_sub_fields_001' in migrations:
        doc_cat = migrations['add_doc_categorization']
        sub_fields = migrations['add_sub_fields_001']
        
        if doc_cat['down_revision'] == 'unified_20250615' and sub_fields['down_revision'] == 'add_doc_categorization':
            print("\n📌 Fix for circular dependency:")
            print("1. The migration chain should be linear:")
            print("   unified_20250615 → add_doc_categorization → add_sub_fields_001")
            print("\n2. Run the fix script:")
            print("   ./scripts/fix_migration_transaction.sh")
            print("\n3. Then run migrations:")
            print("   alembic upgrade head")
    
    if any("Multiple heads" in issue for issue in issues):
        print("\n📌 Fix for multiple heads:")
        print("1. Create a merge migration:")
        print("   alembic merge -m 'merge heads'")
        print("2. Or use the alembic utils:")
        print("   python scripts/create_migration.py --fix-heads")


def main():
    print("🔧 Alembic Migration Analysis Tool")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Working Directory: {os.getcwd()}")
    
    migrations, issues = analyze_migration_files()
    check_database_status()
    
    if issues:
        suggest_fixes(migrations, issues)
    
    print("\n\n✅ Analysis complete!")


if __name__ == "__main__":
    main()