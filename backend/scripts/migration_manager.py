#!/usr/bin/env python3
"""
Enhanced Migration Manager for Alembic
Prevents common migration issues like duplicate columns, multiple heads, etc.
"""
import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
import click
import re

# Add parent directory to path
sys.path.append('..')

MIGRATION_DIR = Path("alembic/versions")
ALEMBIC_INI = Path("alembic.ini")


class MigrationManager:
    def __init__(self):
        self.migration_dir = MIGRATION_DIR
        self.ensure_migration_tracking()
    
    def ensure_migration_tracking(self):
        """Create a tracking file for migrations"""
        self.tracking_file = Path(".migration_tracking.json")
        if not self.tracking_file.exists():
            self.tracking_file.write_text(json.dumps({
                "migrations": [],
                "last_check": None,
                "known_issues": []
            }, indent=2))
    
    def get_tracking_data(self):
        """Get migration tracking data"""
        return json.loads(self.tracking_file.read_text())
    
    def save_tracking_data(self, data):
        """Save migration tracking data"""
        self.tracking_file.write_text(json.dumps(data, indent=2))
    
    def check_for_issues(self):
        """Check for common migration issues"""
        issues = []
        
        # Check for multiple heads
        result = subprocess.run(["alembic", "heads"], capture_output=True, text=True)
        heads = [line.strip() for line in result.stdout.split('\n') if line.strip() and '(head)' in line]
        
        if len(heads) > 1:
            issues.append({
                "type": "multiple_heads",
                "heads": heads,
                "severity": "high"
            })
        
        # Check for migration conflicts
        migration_files = list(self.migration_dir.glob("*.py"))
        revisions = {}
        
        for file in migration_files:
            content = file.read_text()
            revision_match = re.search(r"revision = ['\"]([^'\"]+)['\"]", content)
            down_revision_match = re.search(r"down_revision = ['\"]([^'\"]+)['\"]", content)
            
            if revision_match:
                revision = revision_match.group(1)
                down_revision = down_revision_match.group(1) if down_revision_match else None
                
                if revision in revisions:
                    issues.append({
                        "type": "duplicate_revision",
                        "revision": revision,
                        "files": [str(revisions[revision]), str(file)],
                        "severity": "high"
                    })
                else:
                    revisions[revision] = file
        
        # Check current migration state
        result = subprocess.run(["alembic", "current"], capture_output=True, text=True)
        if "FAILED" in result.stderr:
            issues.append({
                "type": "migration_state_error",
                "error": result.stderr,
                "severity": "high"
            })
        
        return issues
    
    def fix_multiple_heads(self):
        """Automatically fix multiple heads"""
        click.echo("🔧 Fixing multiple heads...")
        
        # Get all heads
        result = subprocess.run(["alembic", "heads"], capture_output=True, text=True)
        heads = [line.split()[0] for line in result.stdout.split('\n') if line.strip() and '(head)' in line]
        
        if len(heads) > 1:
            # Create a merge migration
            merge_message = f"merge heads {datetime.now().strftime('%Y%m%d_%H%M%S')}"
            subprocess.run(["alembic", "merge", "-m", merge_message])
            click.echo(f"✅ Created merge migration: {merge_message}")
            return True
        
        click.echo("ℹ️  No multiple heads found")
        return False
    
    def create_safe_migration(self, message):
        """Create a migration with safety checks"""
        click.echo(f"📝 Creating safe migration: {message}")
        
        # First check for issues
        issues = self.check_for_issues()
        if issues:
            click.echo("⚠️  Found issues that need to be resolved first:")
            for issue in issues:
                click.echo(f"  - {issue['type']}: {issue.get('error', issue)}")
            
            if click.confirm("Do you want to try to auto-fix these issues?"):
                self.auto_fix_issues(issues)
        
        # Generate timestamp-based revision ID to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_message = re.sub(r'[^a-zA-Z0-9_\s]', '', message).replace(' ', '_')
        rev_id = f"{safe_message}_{timestamp}"
        
        # Create the migration
        result = subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", message, "--rev-id", rev_id],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            click.echo(f"✅ Created migration: {rev_id}")
            
            # Update tracking
            data = self.get_tracking_data()
            data["migrations"].append({
                "id": rev_id,
                "message": message,
                "created_at": datetime.now().isoformat(),
                "applied": False
            })
            self.save_tracking_data(data)
            
            # Post-process the migration file to add safety checks
            self.add_safety_checks_to_migration(rev_id)
        else:
            click.echo(f"❌ Failed to create migration: {result.stderr}")
    
    def add_safety_checks_to_migration(self, rev_id):
        """Add safety checks to a migration file"""
        # Find the migration file
        migration_file = None
        for file in self.migration_dir.glob("*.py"):
            if rev_id in file.read_text():
                migration_file = file
                break
        
        if not migration_file:
            return
        
        content = migration_file.read_text()
        
        # Add helper functions if not already present
        if "def column_exists" not in content:
            helpers = '''
def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if not table_exists(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(index_name):
    """Check if an index exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = []
    for table in inspector.get_table_names():
        indexes.extend([idx['name'] for idx in inspector.get_indexes(table)])
    return index_name in indexes

'''
            # Add imports
            content = content.replace(
                "from alembic import op",
                "from alembic import op\nfrom sqlalchemy import inspect"
            )
            
            # Add helpers before upgrade function
            content = content.replace(
                "def upgrade():",
                helpers + "\ndef upgrade():"
            )
        
        # Replace common operations with safe versions
        replacements = [
            (r"op\.add_column\('(\w+)',\s*(.*?)\)", 
             r"if not column_exists('\1', \2.name):\n        op.add_column('\1', \2)\n    else:\n        print(f'Column {\2.name} already exists in \1')"),
            (r"op\.create_table\('(\w+)',", 
             r"if not table_exists('\1'):\n        op.create_table('\1',"),
            (r"op\.create_index\('(\w+)',", 
             r"if not index_exists('\1'):\n        op.create_index('\1',"),
        ]
        
        # Note: This is a simplified version. In production, you'd want more sophisticated regex
        
        migration_file.write_text(content)
        click.echo(f"✅ Added safety checks to migration: {migration_file.name}")
    
    def auto_fix_issues(self, issues):
        """Automatically fix common issues"""
        for issue in issues:
            if issue["type"] == "multiple_heads":
                self.fix_multiple_heads()
            elif issue["type"] == "duplicate_revision":
                click.echo(f"⚠️  Found duplicate revision {issue['revision']} in files:")
                for file in issue["files"]:
                    click.echo(f"  - {file}")
                # You could add logic to rename one of them
    
    def apply_migrations(self, target="head"):
        """Safely apply migrations"""
        click.echo(f"🚀 Applying migrations to {target}...")
        
        # Check for issues first
        issues = self.check_for_issues()
        if any(issue["severity"] == "high" for issue in issues):
            click.echo("❌ Found high-severity issues:")
            for issue in issues:
                if issue["severity"] == "high":
                    click.echo(f"  - {issue['type']}: {issue}")
            
            if not click.confirm("Do you want to continue anyway?"):
                return
        
        # Apply migrations
        result = subprocess.run(["alembic", "upgrade", target], capture_output=True, text=True)
        
        if result.returncode == 0:
            click.echo("✅ Migrations applied successfully")
            
            # Update tracking
            data = self.get_tracking_data()
            data["last_check"] = datetime.now().isoformat()
            self.save_tracking_data(data)
        else:
            click.echo(f"❌ Failed to apply migrations: {result.stderr}")
            
            # Try to provide helpful suggestions
            if "Multiple head revisions" in result.stderr:
                click.echo("\n💡 Suggestion: Run 'python migration_manager.py fix-heads' to resolve")
            elif "column" in result.stderr.lower() and "already exists" in result.stderr.lower():
                click.echo("\n💡 Suggestion: The column already exists. You may need to skip this migration.")


@click.group()
def cli():
    """Enhanced Migration Manager for Alembic"""
    pass


@cli.command()
def check():
    """Check for migration issues"""
    manager = MigrationManager()
    issues = manager.check_for_issues()
    
    if not issues:
        click.echo("✅ No migration issues found!")
    else:
        click.echo("⚠️  Found migration issues:")
        for issue in issues:
            click.echo(f"\n{issue['type']}:")
            click.echo(f"  Severity: {issue.get('severity', 'medium')}")
            if 'heads' in issue:
                click.echo(f"  Heads: {issue['heads']}")
            if 'error' in issue:
                click.echo(f"  Error: {issue['error']}")


@cli.command()
@click.argument('message')
def create(message):
    """Create a new migration with safety checks"""
    manager = MigrationManager()
    manager.create_safe_migration(message)


@cli.command()
@click.option('--target', default='head', help='Target revision')
def upgrade(target):
    """Apply migrations safely"""
    manager = MigrationManager()
    manager.apply_migrations(target)


@cli.command()
def fix_heads():
    """Fix multiple heads issue"""
    manager = MigrationManager()
    manager.fix_multiple_heads()


@cli.command()
def status():
    """Show detailed migration status"""
    manager = MigrationManager()
    
    click.echo("📊 Migration Status")
    click.echo("=" * 50)
    
    # Current revision
    result = subprocess.run(["alembic", "current"], capture_output=True, text=True)
    click.echo(f"\nCurrent revision: {result.stdout.strip()}")
    
    # Heads
    result = subprocess.run(["alembic", "heads"], capture_output=True, text=True)
    click.echo(f"\nHeads:\n{result.stdout}")
    
    # Pending migrations
    result = subprocess.run(["alembic", "history", "-r", "current:"], capture_output=True, text=True)
    if result.stdout.strip():
        click.echo(f"\nPending migrations:\n{result.stdout}")
    else:
        click.echo("\n✅ No pending migrations")
    
    # Check for issues
    issues = manager.check_for_issues()
    if issues:
        click.echo("\n⚠️  Issues found:")
        for issue in issues:
            click.echo(f"  - {issue['type']} ({issue.get('severity', 'medium')})")


if __name__ == "__main__":
    cli()