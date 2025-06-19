#!/usr/bin/env python3
"""
Script to help migrate all API endpoints from sync to async database operations
"""

import os
import re
from pathlib import Path

# Common replacements needed
REPLACEMENTS = [
    # Import replacements
    (r'from sqlalchemy\.orm import Session', 'from sqlalchemy.ext.asyncio import AsyncSession'),
    (r'from app\.db\.database import get_db', 'from app.db.async_database import get_async_db'),
    (r'from app\.api\.dependencies import (.*?)get_current_user', 
     r'from app.api.dependencies import \1get_current_user\nfrom app.api.async_dependencies import get_current_user_async, get_current_active_user_async'),
    
    # Dependency replacements
    (r'db: Session = Depends\(get_db\)', 'db: AsyncSession = Depends(get_async_db)'),
    (r'current_user: User = Depends\(get_current_user\)', 'current_user: User = Depends(get_current_user_async)'),
    (r'current_user: User = Depends\(get_current_active_user\)', 'current_user: User = Depends(get_current_active_user_async)'),
    
    # Query replacements - basic patterns
    (r'db\.query\((.*?)\)\.filter\((.*?)\)\.first\(\)', r'(await db.execute(select(\1).filter(\2))).scalar_one_or_none()'),
    (r'db\.query\((.*?)\)\.filter\((.*?)\)\.all\(\)', r'(await db.execute(select(\1).filter(\2))).scalars().all()'),
    (r'db\.query\((.*?)\)\.get\((.*?)\)', r'(await db.execute(select(\1).filter(\1.id == \2))).scalar_one_or_none()'),
    
    # Transaction replacements
    (r'db\.add\((.*?)\)', r'db.add(\1)'),  # add stays the same
    (r'db\.commit\(\)', r'await db.commit()'),
    (r'db\.refresh\((.*?)\)', r'await db.refresh(\1)'),
    (r'db\.flush\(\)', r'await db.flush()'),
    (r'db\.rollback\(\)', r'await db.rollback()'),
    
    # Count queries
    (r'db\.query\((.*?)\)\.count\(\)', r'(await db.execute(select(func.count()).select_from(\1))).scalar()'),
]

# Files to migrate
API_V1_PATH = Path(__file__).parent / "app" / "api" / "v1"
SERVICE_PATH = Path(__file__).parent / "app" / "services"

FILES_TO_MIGRATE = [
    "documents.py",
    "document_shares.py", 
    "auth.py",
    "chat.py",
    "admin.py",
    "tenants.py",
    "stripe.py",
    "signatures.py",
    "webhooks.py",
]

def add_imports(content: str) -> str:
    """Add necessary imports for async operations"""
    imports_to_add = [
        "from sqlalchemy import select, func",
        "from sqlalchemy.orm import selectinload",
    ]
    
    # Find the last import line
    import_lines = []
    lines = content.split('\n')
    last_import_idx = 0
    
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            last_import_idx = i
    
    # Add imports after the last import
    for imp in imports_to_add:
        if imp not in content:
            lines.insert(last_import_idx + 1, imp)
            last_import_idx += 1
    
    return '\n'.join(lines)

def migrate_file(filepath: Path, dry_run: bool = True):
    """Migrate a single file from sync to async"""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating {filepath.name}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Apply replacements
    for old, new in REPLACEMENTS:
        content = re.sub(old, new, content)
    
    # Add necessary imports
    content = add_imports(content)
    
    # Fix specific patterns that need more complex replacements
    # Example: db.query(Model).filter_by(**kwargs)
    content = re.sub(
        r'db\.query\((.*?)\)\.filter_by\(\*\*(.*?)\)\.(first|all)\(\)',
        lambda m: f'(await db.execute(select({m.group(1)}).filter_by(**{m.group(2)}))).{"scalar_one_or_none()" if m.group(3) == "first" else "scalars().all()"}',
        content
    )
    
    if content != original_content:
        if not dry_run:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Migrated {filepath.name}")
        else:
            print(f"Would migrate {filepath.name}")
            # Show a sample of changes
            lines_changed = sum(1 for a, b in zip(original_content.split('\n'), content.split('\n')) if a != b)
            print(f"  Lines changed: {lines_changed}")
    else:
        print(f"No changes needed for {filepath.name}")

def main(auto_run=False):
    """Main migration function"""
    print("Starting migration to async database operations...")
    print("=" * 60)
    
    # First do a dry run
    print("\nDRY RUN - Checking what would be changed:")
    for filename in FILES_TO_MIGRATE:
        filepath = API_V1_PATH / filename
        if filepath.exists():
            migrate_file(filepath, dry_run=True)
        else:
            print(f"⚠️  File not found: {filepath}")
    
    # Ask for confirmation or auto-run
    print("\n" + "=" * 60)
    
    if auto_run:
        response = 'yes'
        print("\nAuto-running migration (--auto flag)...")
    else:
        response = input("\nProceed with actual migration? (yes/no): ")
    
    if response.lower() == 'yes':
        print("\nPerforming actual migration...")
        for filename in FILES_TO_MIGRATE:
            filepath = API_V1_PATH / filename
            if filepath.exists():
                migrate_file(filepath, dry_run=False)
    else:
        print("Migration cancelled.")

if __name__ == "__main__":
    import sys
    auto_run = '--auto' in sys.argv
    main(auto_run=auto_run)