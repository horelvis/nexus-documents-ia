#!/usr/bin/env python3
"""
Alembic Migration Manager - Sistema robusto de migraciones
"""
import os
import sys
import logging
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlembicManager:
    """Gestor robusto de migraciones con Alembic"""
    
    def __init__(self, database_url: str, alembic_ini_path: str = None):
        self.database_url = database_url
        self.engine = create_engine(database_url)
        
        # Buscar alembic.ini
        if alembic_ini_path:
            self.alembic_cfg_path = Path(alembic_ini_path)
        else:
            self.alembic_cfg_path = self._find_alembic_ini()
        
        self.alembic_cfg = self._get_alembic_config()
    
    def _find_alembic_ini(self) -> Path:
        """Busca alembic.ini en ubicaciones comunes"""
        possible_paths = [
            Path.cwd() / "alembic.ini",
            Path(__file__).parent / "alembic.ini",
            Path("/app/alembic.ini"),
        ]
        
        for path in possible_paths:
            if path.exists():
                logger.info(f"Found alembic.ini at: {path}")
                return path
        
        raise FileNotFoundError("alembic.ini not found")
    
    def _get_alembic_config(self) -> Config:
        """Configura Alembic"""
        cfg = Config(str(self.alembic_cfg_path))
        cfg.set_main_option("sqlalchemy.url", self.database_url)
        
        # Configurar script location
        script_location = self.alembic_cfg_path.parent / "alembic"
        cfg.set_main_option("script_location", str(script_location))
        
        return cfg
    
    def get_current_revision(self) -> str:
        """Obtiene la revisión actual de la BD"""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ))
            row = result.fetchone()
            return row[0] if row else None
    
    def get_pending_migrations(self) -> list:
        """Lista las migraciones pendientes"""
        script = ScriptDirectory.from_config(self.alembic_cfg)
        current = self.get_current_revision()
        
        if current:
            # Obtener todas las revisiones desde current hasta head
            revisions = []
            for rev in script.walk_revisions("head", current):
                if rev.revision != current:
                    revisions.append({
                        'revision': rev.revision,
                        'message': rev.doc,
                        'branch_labels': rev.branch_labels
                    })
            return revisions
        else:
            # Si no hay revisión actual, todas son pendientes
            return [{'revision': rev.revision, 'message': rev.doc} 
                    for rev in script.walk_revisions()]
    
    def init_alembic(self):
        """Inicializa Alembic en una BD nueva"""
        try:
            # Verificar si alembic_version existe
            inspector = inspect(self.engine)
            if 'alembic_version' not in inspector.get_table_names():
                logger.info("Initializing Alembic...")
                command.stamp(self.alembic_cfg, "head")
                logger.info("✅ Alembic initialized")
            else:
                logger.info("Alembic already initialized")
        except Exception as e:
            logger.error(f"Error initializing Alembic: {e}")
            raise
    
    def create_migration(self, message: str, autogenerate: bool = True):
        """Crea una nueva migración"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            full_message = f"{timestamp}_{message}"
            
            if autogenerate:
                logger.info(f"Auto-generating migration: {message}")
                command.revision(self.alembic_cfg, 
                               message=full_message, 
                               autogenerate=True)
            else:
                logger.info(f"Creating empty migration: {message}")
                command.revision(self.alembic_cfg, message=full_message)
            
            logger.info("✅ Migration created")
        except Exception as e:
            logger.error(f"Error creating migration: {e}")
            raise
    
    def upgrade(self, revision: str = "head"):
        """Aplica migraciones hasta la revisión especificada"""
        try:
            logger.info(f"Upgrading to {revision}...")
            command.upgrade(self.alembic_cfg, revision)
            logger.info("✅ Upgrade complete")
        except Exception as e:
            logger.error(f"Error during upgrade: {e}")
            raise
    
    def downgrade(self, revision: str = "-1"):
        """Revierte migraciones"""
        try:
            logger.info(f"Downgrading to {revision}...")
            command.downgrade(self.alembic_cfg, revision)
            logger.info("✅ Downgrade complete")
        except Exception as e:
            logger.error(f"Error during downgrade: {e}")
            raise
    
    def get_history(self) -> list:
        """Obtiene el historial de migraciones aplicadas"""
        script = ScriptDirectory.from_config(self.alembic_cfg)
        current = self.get_current_revision()
        
        if not current:
            return []
        
        history = []
        for rev in script.walk_revisions(current, "base"):
            history.append({
                'revision': rev.revision,
                'message': rev.doc,
                'create_date': rev.create_date
            })
        
        return history
    
    def verify_migration_health(self) -> dict:
        """Verifica el estado de salud de las migraciones"""
        try:
            current = self.get_current_revision()
            pending = self.get_pending_migrations()
            history = self.get_history()
            
            # Verificar si hay conflictos
            script = ScriptDirectory.from_config(self.alembic_cfg)
            heads = script.get_heads()
            
            health = {
                'status': 'healthy',
                'current_revision': current,
                'pending_count': len(pending),
                'history_count': len(history),
                'multiple_heads': len(heads) > 1,
                'heads': heads
            }
            
            if len(heads) > 1:
                health['status'] = 'warning'
                health['message'] = 'Multiple heads detected - possible branch conflict'
            elif not current and pending:
                health['status'] = 'needs_init'
                health['message'] = 'Database needs initialization'
            
            return health
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def auto_upgrade(self, dry_run: bool = False):
        """Aplica automáticamente todas las migraciones pendientes"""
        try:
            health = self.verify_migration_health()
            
            if health['status'] == 'error':
                raise Exception(f"Migration health check failed: {health['message']}")
            
            if health['status'] == 'needs_init':
                if not dry_run:
                    self.init_alembic()
                else:
                    logger.info("[DRY RUN] Would initialize Alembic")
            
            pending = self.get_pending_migrations()
            
            if not pending:
                logger.info("No pending migrations")
                return
            
            logger.info(f"Found {len(pending)} pending migrations")
            
            for migration in pending:
                logger.info(f"  - {migration['revision']}: {migration['message']}")
            
            if not dry_run:
                self.upgrade()
            else:
                logger.info("[DRY RUN] Would apply migrations")
                
        except Exception as e:
            logger.error(f"Auto-upgrade failed: {e}")
            raise


def main():
    """CLI para gestionar migraciones"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Alembic Migration Manager')
    parser.add_argument('command', choices=['status', 'upgrade', 'downgrade', 
                                           'create', 'history', 'auto-upgrade'])
    parser.add_argument('--message', '-m', help='Migration message')
    parser.add_argument('--revision', '-r', help='Target revision')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    
    args = parser.parse_args()
    
    # Importar settings
    from app.core.config import settings
    
    manager = AlembicManager(settings.SQLALCHEMY_DATABASE_URI)
    
    if args.command == 'status':
        health = manager.verify_migration_health()
        print(f"Status: {health['status']}")
        print(f"Current revision: {health.get('current_revision', 'None')}")
        print(f"Pending migrations: {health.get('pending_count', 0)}")
        
    elif args.command == 'upgrade':
        manager.upgrade(args.revision or 'head')
        
    elif args.command == 'downgrade':
        manager.downgrade(args.revision or '-1')
        
    elif args.command == 'create':
        if not args.message:
            print("Error: --message required for create command")
            sys.exit(1)
        manager.create_migration(args.message)
        
    elif args.command == 'history':
        history = manager.get_history()
        for item in history:
            print(f"{item['revision']}: {item['message']}")
            
    elif args.command == 'auto-upgrade':
        manager.auto_upgrade(dry_run=args.dry_run)


if __name__ == '__main__':
    main()