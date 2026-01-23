#!/usr/bin/env python3
"""
Rebrand Script: NouxCubeIA → NouxCubeIA

This script performs a systematic rebranding of the codebase:
- NouxCubeIA → NouxCubeIA
- nouxcubeia → nouxcubeia
- NOUXCUBE → NOUXCUBE
- Nouxcube_ (Weaviate prefix) → Nouxcube_
- nouxcube (slug/lowercase) → nouxcube

Usage:
    python scripts/rebrand_to_nouxcube.py --dry-run    # Preview changes
    python scripts/rebrand_to_nouxcube.py --execute    # Apply changes
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict

# Root directories to process
BACKEND_ROOT = Path(__file__).parent.parent
FRONTEND_ROOT = BACKEND_ROOT.parent / "frontend"
PROJECT_ROOT = BACKEND_ROOT.parent

# File extensions to process
EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.yaml', '.yml',
    '.md', '.env', '.example', '.sh', '.html', '.css', '.scss'
}

# Directories to skip
SKIP_DIRS = {
    'node_modules', '.next', '__pycache__', '.git', 'venv',
    '.venv', 'dist', 'build', '.pytest_cache', 'coverage_report',
    'htmlcov', '.mypy_cache'
}

# Replacement patterns (order matters - more specific first)
REPLACEMENTS = [
    # Brand names
    ('NouxCubeIA', 'NouxCubeIA'),
    ('nouxcubeia', 'nouxcubeia'),
    ('NOUXCUBEIA', 'NOUXCUBEIA'),
    ('NOUXCUBE', 'NOUXCUBE'),

    # Weaviate collection prefix (case sensitive)
    ('Nouxcube_', 'Nouxcube_'),

    # Slugs and lowercase references
    ('nouxcube', 'nouxcube'),

    # Service names in logs/structured logging
    ('"nouxcubeia"', '"nouxcubeia"'),
    ("'nouxcubeia'", "'nouxcubeia'"),

    # URLs (be careful with these)
    ('nouxcubeia.app', 'nouxcube.ai'),
    ('nouxcubeia.local', 'nouxcube.local'),
]

# Files to skip entirely
SKIP_FILES = {
    'package-lock.json',  # Auto-generated
    'yarn.lock',
    'pnpm-lock.yaml',
}


def should_process_file(filepath: Path) -> bool:
    """Check if file should be processed."""
    # Skip by name
    if filepath.name in SKIP_FILES:
        return False

    # Skip by directory
    for part in filepath.parts:
        if part in SKIP_DIRS:
            return False

    # Check extension
    suffix = filepath.suffix.lower()
    if suffix in EXTENSIONS:
        return True

    # Also process files without extension if they look like config
    if filepath.suffix == '' and filepath.name in {'.env', 'Dockerfile', 'Makefile'}:
        return True

    # Process .env files with any suffix
    if '.env' in filepath.name:
        return True

    return False


def find_files(root: Path) -> List[Path]:
    """Find all files to process."""
    files = []
    for filepath in root.rglob('*'):
        if filepath.is_file() and should_process_file(filepath):
            files.append(filepath)
    return sorted(files)


def apply_replacements(content: str) -> Tuple[str, List[Tuple[str, str, int]]]:
    """Apply all replacements to content. Returns new content and list of changes."""
    changes = []
    new_content = content

    for old, new in REPLACEMENTS:
        count = new_content.count(old)
        if count > 0:
            new_content = new_content.replace(old, new)
            changes.append((old, new, count))

    return new_content, changes


def process_file(filepath: Path, dry_run: bool = True) -> Dict:
    """Process a single file. Returns info about changes made."""
    result = {
        'file': str(filepath),
        'changes': [],
        'error': None
    }

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        new_content, changes = apply_replacements(content)

        if changes:
            result['changes'] = changes

            if not dry_run:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

    except Exception as e:
        result['error'] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description='Rebrand NouxCubeIA to NouxCubeIA')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--execute', action='store_true', help='Apply changes')
    parser.add_argument('--backend-only', action='store_true', help='Only process backend')
    parser.add_argument('--frontend-only', action='store_true', help='Only process frontend')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.print_help()
        print("\nPlease specify --dry-run or --execute")
        return

    dry_run = args.dry_run

    print("=" * 70)
    print("REBRAND: NouxCubeIA → NouxCubeIA")
    print("=" * 70)
    print(f"\nMode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (applying changes)'}")

    # Collect files
    files = []

    if not args.frontend_only:
        print(f"\nScanning backend: {BACKEND_ROOT}")
        files.extend(find_files(BACKEND_ROOT))

    if not args.backend_only:
        print(f"Scanning frontend: {FRONTEND_ROOT}")
        files.extend(find_files(FRONTEND_ROOT))

    # Also process root files like CLAUDE.md
    root_files = [
        PROJECT_ROOT / "CLAUDE.md",
        PROJECT_ROOT / "README.md",
    ]
    for rf in root_files:
        if rf.exists():
            files.append(rf)

    print(f"\nFound {len(files)} files to process")

    # Process files
    print("\nProcessing files...")
    total_changes = 0
    files_changed = 0

    for filepath in files:
        result = process_file(filepath, dry_run)

        if result['error']:
            print(f"  ERROR: {result['file']}: {result['error']}")
        elif result['changes']:
            files_changed += 1
            file_changes = sum(c[2] for c in result['changes'])
            total_changes += file_changes

            # Show relative path
            try:
                rel_path = filepath.relative_to(PROJECT_ROOT)
            except ValueError:
                rel_path = filepath

            print(f"\n  {rel_path}:")
            for old, new, count in result['changes']:
                print(f"    {old} → {new} ({count}x)")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files scanned: {len(files)}")
    print(f"Files {'to change' if dry_run else 'changed'}: {files_changed}")
    print(f"Total replacements: {total_changes}")

    if dry_run:
        print("\n[DRY RUN] No changes were made.")
        print("Run with --execute to apply changes.")
    else:
        print("\n✓ Changes applied successfully!")

    print("\nReplacement patterns used:")
    for old, new in REPLACEMENTS:
        print(f"  {old} → {new}")


if __name__ == '__main__':
    main()
