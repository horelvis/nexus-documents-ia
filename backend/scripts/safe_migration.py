#!/usr/bin/env python3
"""
Safe Migration Script
Handles migrations with automatic backup and rollback capabilities
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SafeMigration:
    def __init__(self):
        self.container = "docker-api-1"
        self.db_container = "docker-db-1"
        
    def backup_database(self):
        """Create a database backup before migration"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"db_backup_{timestamp}.sql"
        
        logger.info(f"Creating database backup: {backup_file}")
        
        cmd = f"docker exec {self.db_container} pg_dump -U postgres nexus_db > {backup_file}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Backup created successfully: {backup_file}")
            return backup_file
        else:
            logger.error(f"Backup failed: {result.stderr}")
            return None
    
    def restore_database(self, backup_file):
        """Restore database from backup"""
        logger.info(f"Restoring database from: {backup_file}")
        
        # Drop and recreate database
        cmd1 = f"docker exec {self.db_container} psql -U postgres -c 'DROP DATABASE IF EXISTS nexus_db;'"
        cmd2 = f"docker exec {self.db_container} psql -U postgres -c 'CREATE DATABASE nexus_db;'"
        cmd3 = f"docker exec -i {self.db_container} psql -U postgres nexus_db < {backup_file}"
        
        for cmd in [cmd1, cmd2, cmd3]:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Restore failed: {result.stderr}")
                return False
        
        logger.info("Database restored successfully")
        return True
    
    def check_migration_status(self):
        """Check current migration status"""
        cmd = f"docker exec {self.container} alembic current"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Current revision: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"Failed to check status: {result.stderr}")
            return False
    
    def clean_alembic_version(self):
        """Clean alembic_version table if needed"""
        logger.info("Cleaning alembic_version table...")
        
        cmd = f"docker exec {self.db_container} psql -U postgres -d nexus_db -c 'TRUNCATE TABLE alembic_version;'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Alembic version table cleaned")
            return True
        else:
            logger.error(f"Failed to clean: {result.stderr}")
            return False
    
    def create_migration(self, message, autogenerate=True):
        """Create a new migration"""
        logger.info(f"Creating migration: {message}")
        
        auto_flag = "--autogenerate" if autogenerate else ""
        cmd = f'docker exec {self.container} alembic revision {auto_flag} -m "{message}"'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Migration created successfully")
            logger.info(result.stdout)
            return True
        else:
            logger.error(f"Failed to create migration: {result.stderr}")
            
            # If error is about missing revision, clean and retry
            if "Can't locate revision" in result.stderr:
                logger.info("Detected missing revision error, cleaning and retrying...")
                self.clean_alembic_version()
                
                # Retry
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("Migration created successfully after cleanup")
                    return True
            
            return False
    
    def apply_migration(self, revision="head", backup=True):
        """Apply migration with optional backup"""
        backup_file = None
        
        if backup:
            backup_file = self.backup_database()
            if not backup_file:
                logger.error("Backup failed, aborting migration")
                return False
        
        logger.info(f"Applying migration to: {revision}")
        
        cmd = f"docker exec {self.container} alembic upgrade {revision}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Migration applied successfully")
            logger.info(result.stdout)
            return True
        else:
            logger.error(f"Migration failed: {result.stderr}")
            
            if backup_file:
                response = input("Would you like to restore from backup? (y/n): ")
                if response.lower() == 'y':
                    self.restore_database(backup_file)
            
            return False
    
    def downgrade_migration(self, revision="-1"):
        """Downgrade migration"""
        logger.info(f"Downgrading to: {revision}")
        
        cmd = f"docker exec {self.container} alembic downgrade {revision}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Downgrade successful")
            return True
        else:
            logger.error(f"Downgrade failed: {result.stderr}")
            return False
    
    def show_history(self):
        """Show migration history"""
        cmd = f"docker exec {self.container} alembic history"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("\nMigration History:")
            print("-" * 50)
            print(result.stdout)
            return True
        else:
            logger.error(f"Failed to get history: {result.stderr}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Safe Database Migration Tool")
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create migration
    create_parser = subparsers.add_parser('create', help='Create new migration')
    create_parser.add_argument('message', help='Migration message')
    create_parser.add_argument('--empty', action='store_true', help='Create empty migration')
    
    # Apply migration
    apply_parser = subparsers.add_parser('apply', help='Apply migrations')
    apply_parser.add_argument('--revision', default='head', help='Target revision')
    apply_parser.add_argument('--no-backup', action='store_true', help='Skip backup')
    
    # Downgrade
    downgrade_parser = subparsers.add_parser('downgrade', help='Downgrade migration')
    downgrade_parser.add_argument('--revision', default='-1', help='Target revision')
    
    # Status
    status_parser = subparsers.add_parser('status', help='Check migration status')
    
    # History
    history_parser = subparsers.add_parser('history', help='Show migration history')
    
    # Clean
    clean_parser = subparsers.add_parser('clean', help='Clean alembic version')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    migrator = SafeMigration()
    
    if args.command == 'create':
        migrator.create_migration(args.message, not args.empty)
    
    elif args.command == 'apply':
        migrator.apply_migration(args.revision, not args.no_backup)
    
    elif args.command == 'downgrade':
        migrator.downgrade_migration(args.revision)
    
    elif args.command == 'status':
        migrator.check_migration_status()
    
    elif args.command == 'history':
        migrator.show_history()
    
    elif args.command == 'clean':
        migrator.clean_alembic_version()


if __name__ == "__main__":
    main()