#!/usr/bin/env python3
"""
Safe migration runner for Alembic that prevents duplicate table/column errors
"""
import os
import sys
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from scripts.alembic_utils import AlembicMigrationManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseInspector:
    """Inspects database schema to prevent conflicts"""
    
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or settings.DATABASE_URL
        
    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.connection_string)
    
    def get_existing_tables(self) -> Set[str]:
        """Get all existing tables in the database"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
                return {row[0] for row in cur.fetchall()}
    
    def get_table_columns(self, table_name: str) -> Dict[str, str]:
        """Get columns for a specific table"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                """, (table_name,))
                return {row[0]: row[1] for row in cur.fetchall()}
    
    def get_indexes(self, table_name: str) -> Set[str]:
        """Get indexes for a specific table"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE schemaname = 'public' 
                    AND tablename = %s
                """, (table_name,))
                return {row[0] for row in cur.fetchall()}
    
    def get_foreign_keys(self, table_name: str) -> List[Dict]:
        """Get foreign key constraints for a table"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        tc.constraint_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_name = %s
                        AND tc.table_schema = 'public'
                """, (table_name,))
                return [
                    {
                        'name': row[0],
                        'column': row[1],
                        'foreign_table': row[2],
                        'foreign_column': row[3]
                    }
                    for row in cur.fetchall()
                ]
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""
        return table_name in self.get_existing_tables()
    
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table"""
        columns = self.get_table_columns(table_name)
        return column_name in columns
    
    def index_exists(self, index_name: str, table_name: Optional[str] = None) -> bool:
        """Check if an index exists"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT 1 
                    FROM pg_indexes 
                    WHERE schemaname = 'public' 
                    AND indexname = %s
                """
                params = [index_name]
                
                if table_name:
                    query += " AND tablename = %s"
                    params.append(table_name)
                
                cur.execute(query, params)
                return cur.fetchone() is not None
    
    def get_alembic_version(self) -> Optional[str]:
        """Get current alembic version from database"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT version_num 
                        FROM alembic_version 
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return result[0] if result else None
        except psycopg2.Error:
            return None
    
    def set_alembic_version(self, version: str) -> bool:
        """Manually set alembic version"""
        try:
            with self.get_connection() as conn:
                conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                with conn.cursor() as cur:
                    # Create alembic_version table if it doesn't exist
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS alembic_version (
                            version_num VARCHAR(32) NOT NULL,
                            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                        )
                    """)
                    
                    # Clear existing version
                    cur.execute("DELETE FROM alembic_version")
                    
                    # Insert new version
                    cur.execute(
                        "INSERT INTO alembic_version (version_num) VALUES (%s)",
                        (version,)
                    )
                    
                    logger.info(f"Set alembic version to: {version}")
                    return True
        except Exception as e:
            logger.error(f"Failed to set alembic version: {e}")
            return False


class MigrationAnalyzer:
    """Analyzes migration files to detect potential conflicts"""
    
    def __init__(self, migration_file: str):
        self.migration_file = Path(migration_file)
        self.content = self.migration_file.read_text()
        
    def extract_operations(self) -> Dict[str, List[Dict]]:
        """Extract database operations from migration file"""
        operations = {
            'create_table': [],
            'drop_table': [],
            'add_column': [],
            'drop_column': [],
            'create_index': [],
            'drop_index': [],
            'alter_column': []
        }
        
        # Extract create_table operations
        create_table_pattern = r"op\.create_table\s*\(\s*['\"](\w+)['\"]"
        for match in re.finditer(create_table_pattern, self.content):
            operations['create_table'].append({'table': match.group(1)})
        
        # Extract drop_table operations
        drop_table_pattern = r"op\.drop_table\s*\(\s*['\"](\w+)['\"]"
        for match in re.finditer(drop_table_pattern, self.content):
            operations['drop_table'].append({'table': match.group(1)})
        
        # Extract add_column operations
        add_column_pattern = r"op\.add_column\s*\(\s*['\"](\w+)['\"]\s*,\s*sa\.Column\s*\(\s*['\"](\w+)['\"]"
        for match in re.finditer(add_column_pattern, self.content):
            operations['add_column'].append({
                'table': match.group(1),
                'column': match.group(2)
            })
        
        # Extract drop_column operations
        drop_column_pattern = r"op\.drop_column\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]"
        for match in re.finditer(drop_column_pattern, self.content):
            operations['drop_column'].append({
                'table': match.group(1),
                'column': match.group(2)
            })
        
        # Extract create_index operations
        create_index_pattern = r"op\.create_index\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]"
        for match in re.finditer(create_index_pattern, self.content):
            operations['create_index'].append({
                'index': match.group(1),
                'table': match.group(2)
            })
        
        # Extract alter_column operations (including rename)
        alter_pattern = r"op\.alter_column\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"].*?new_column_name\s*=\s*['\"](\w+)['\"]"
        for match in re.finditer(alter_pattern, self.content, re.DOTALL):
            operations['alter_column'].append({
                'table': match.group(1),
                'old_column': match.group(2),
                'new_column': match.group(3)
            })
        
        return operations
    
    def get_revision_id(self) -> Optional[str]:
        """Extract revision ID from migration file"""
        revision_pattern = r"revision\s*=\s*['\"]([^'\"]+)['\"]"
        match = re.search(revision_pattern, self.content)
        return match.group(1) if match else None


class SafeMigrationRunner:
    """Runs migrations safely with pre-checks"""
    
    def __init__(self):
        self.inspector = DatabaseInspector()
        self.manager = AlembicMigrationManager()
        
    def check_migration_conflicts(self, migration_file: str) -> List[str]:
        """Check if a migration will cause conflicts"""
        conflicts = []
        analyzer = MigrationAnalyzer(migration_file)
        operations = analyzer.extract_operations()
        
        # Check create_table operations
        for op in operations['create_table']:
            if self.inspector.table_exists(op['table']):
                conflicts.append(f"Table '{op['table']}' already exists")
        
        # Check add_column operations
        for op in operations['add_column']:
            if self.inspector.table_exists(op['table']):
                if self.inspector.column_exists(op['table'], op['column']):
                    conflicts.append(f"Column '{op['column']}' already exists in table '{op['table']}'")
        
        # Check create_index operations
        for op in operations['create_index']:
            if self.inspector.index_exists(op['index']):
                conflicts.append(f"Index '{op['index']}' already exists")
        
        # Check drop operations (ensure they exist)
        for op in operations['drop_table']:
            if not self.inspector.table_exists(op['table']):
                conflicts.append(f"Table '{op['table']}' does not exist (cannot drop)")
        
        for op in operations['drop_column']:
            if self.inspector.table_exists(op['table']):
                if not self.inspector.column_exists(op['table'], op['column']):
                    conflicts.append(f"Column '{op['column']}' does not exist in table '{op['table']}' (cannot drop)")
        
        return conflicts
    
    def analyze_all_migrations(self) -> Dict[str, List[str]]:
        """Analyze all pending migrations for conflicts"""
        current_version = self.inspector.get_alembic_version()
        migrations = self.manager.get_all_migrations()
        
        results = {}
        
        for revision, info in migrations.items():
            migration_file = info['path']
            conflicts = self.check_migration_conflicts(migration_file)
            if conflicts:
                results[revision] = conflicts
        
        return results
    
    def generate_fix_script(self, conflicts: Dict[str, List[str]]) -> str:
        """Generate SQL script to fix conflicts"""
        sql_lines = ["-- Fix script for migration conflicts", "-- Generated on " + datetime.now().isoformat(), ""]
        
        for revision, conflict_list in conflicts.items():
            sql_lines.append(f"-- Conflicts in revision: {revision}")
            
            for conflict in conflict_list:
                if "already exists" in conflict:
                    if "Table" in conflict:
                        table_match = re.search(r"Table '(\w+)'", conflict)
                        if table_match:
                            table = table_match.group(1)
                            sql_lines.append(f"-- DROP TABLE IF EXISTS {table} CASCADE;")
                    elif "Column" in conflict:
                        match = re.search(r"Column '(\w+)' already exists in table '(\w+)'", conflict)
                        if match:
                            column, table = match.groups()
                            sql_lines.append(f"-- ALTER TABLE {table} DROP COLUMN IF EXISTS {column};")
                    elif "Index" in conflict:
                        index_match = re.search(r"Index '(\w+)'", conflict)
                        if index_match:
                            index = index_match.group(1)
                            sql_lines.append(f"-- DROP INDEX IF EXISTS {index};")
                
                elif "does not exist" in conflict:
                    sql_lines.append(f"-- Warning: {conflict}")
            
            sql_lines.append("")
        
        return "\n".join(sql_lines)
    
    def mark_migration_as_applied(self, revision: str) -> bool:
        """Mark a specific migration as already applied without running it"""
        logger.info(f"Marking migration {revision} as applied...")
        return self.inspector.set_alembic_version(revision)
    
    def safe_upgrade(self, target: str = "head", dry_run: bool = False) -> bool:
        """Safely run migrations with pre-checks"""
        logger.info(f"Starting safe migration to {target}...")
        
        # Check for conflicts
        conflicts = self.analyze_all_migrations()
        
        if conflicts:
            logger.warning("Conflicts detected in migrations:")
            for revision, conflict_list in conflicts.items():
                logger.warning(f"\nRevision {revision}:")
                for conflict in conflict_list:
                    logger.warning(f"  - {conflict}")
            
            if dry_run:
                fix_script = self.generate_fix_script(conflicts)
                logger.info("\nSuggested fix script:")
                print(fix_script)
                return False
            
            # Ask for confirmation
            response = input("\nDo you want to continue anyway? (y/N): ")
            if response.lower() != 'y':
                logger.info("Migration cancelled.")
                return False
        
        # Run the migration
        if not dry_run:
            try:
                result = subprocess.run(
                    ["alembic", "upgrade", target],
                    capture_output=True,
                    text=True,
                    cwd=Path(__file__).parent.parent
                )
                
                if result.returncode == 0:
                    logger.info("Migration completed successfully!")
                    return True
                else:
                    logger.error(f"Migration failed: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"Error running migration: {e}")
                return False
        else:
            logger.info("Dry run completed. No changes made.")
            return True
    
    def sync_database_state(self) -> bool:
        """Sync alembic version with actual database state"""
        logger.info("Analyzing database state...")
        
        # Get all migrations
        migrations = self.manager.get_all_migrations()
        chain = self.manager.get_migration_chain()
        
        # Find the latest migration that matches the database state
        latest_matching = None
        
        for revision, _ in reversed(chain):
            if revision in migrations:
                analyzer = MigrationAnalyzer(migrations[revision]['path'])
                operations = analyzer.extract_operations()
                
                # Check if this migration's operations match the database state
                matches = True
                
                # Check tables
                for op in operations['create_table']:
                    if not self.inspector.table_exists(op['table']):
                        matches = False
                        break
                
                # Check columns
                if matches:
                    for op in operations['add_column']:
                        if self.inspector.table_exists(op['table']):
                            if not self.inspector.column_exists(op['table'], op['column']):
                                matches = False
                                break
                
                if matches:
                    latest_matching = revision
                    break
        
        if latest_matching:
            logger.info(f"Database state matches revision: {latest_matching}")
            return self.mark_migration_as_applied(latest_matching)
        else:
            logger.warning("Could not determine database state automatically")
            return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Safely run Alembic migrations with conflict detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check for conflicts without running
  python scripts/alembic_safe_migrate.py --check
  
  # Run migrations safely
  python scripts/alembic_safe_migrate.py
  
  # Upgrade to specific revision
  python scripts/alembic_safe_migrate.py --target abc123
  
  # Mark migration as applied without running
  python scripts/alembic_safe_migrate.py --mark-applied abc123
  
  # Sync database state with migrations
  python scripts/alembic_safe_migrate.py --sync
  
  # Generate fix script for conflicts
  python scripts/alembic_safe_migrate.py --fix-script
"""
    )
    
    parser.add_argument('--check', action='store_true',
                       help='Check for conflicts without running migrations')
    parser.add_argument('--target', default='head',
                       help='Target revision (default: head)')
    parser.add_argument('--mark-applied', metavar='REVISION',
                       help='Mark a revision as applied without running it')
    parser.add_argument('--sync', action='store_true',
                       help='Sync alembic version with actual database state')
    parser.add_argument('--fix-script', action='store_true',
                       help='Generate SQL script to fix conflicts')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    runner = SafeMigrationRunner()
    
    if args.check or args.fix_script:
        conflicts = runner.analyze_all_migrations()
        if conflicts:
            logger.warning("Conflicts found:")
            for revision, conflict_list in conflicts.items():
                print(f"\nRevision {revision}:")
                for conflict in conflict_list:
                    print(f"  - {conflict}")
            
            if args.fix_script:
                print("\n" + "="*60)
                print(runner.generate_fix_script(conflicts))
                print("="*60)
        else:
            logger.info("No conflicts found!")
        sys.exit(0 if not conflicts else 1)
    
    if args.mark_applied:
        success = runner.mark_migration_as_applied(args.mark_applied)
        sys.exit(0 if success else 1)
    
    if args.sync:
        success = runner.sync_database_state()
        sys.exit(0 if success else 1)
    
    # Default: run migration
    success = runner.safe_upgrade(args.target, args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()