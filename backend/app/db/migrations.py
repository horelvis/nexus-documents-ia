# app/db/migrations_simple.py
"""
Sistema simplificado de migraciones usando solo Alembic
"""
import logging
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine

logger = logging.getLogger(__name__)

def get_alembic_config() -> Config:
    """Obtiene la configuración de Alembic"""
    # Buscar alembic.ini
    possible_paths = [
        Path("/app/alembic.ini"),  # Docker
        Path(__file__).parent.parent.parent / "alembic.ini",  # Desarrollo
        Path.cwd() / "alembic.ini",
    ]
    
    alembic_cfg_path = None
    for path in possible_paths:
        if path.exists():
            alembic_cfg_path = path
            break
    
    if not alembic_cfg_path:
        raise FileNotFoundError(f"alembic.ini not found in: {possible_paths}")
    
    logger.info(f"📁 Using alembic.ini from: {alembic_cfg_path}")
    
    # Crear configuración
    alembic_cfg = Config(str(alembic_cfg_path))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI)
    
    # Script location
    script_location = alembic_cfg_path.parent / "alembic"
    alembic_cfg.set_main_option("script_location", str(script_location))
    
    return alembic_cfg

def auto_upgrade_database():
    """
    Aplica todas las migraciones pendientes de Alembic
    """
    try:
        logger.info("🔧 Iniciando migraciones con Alembic...")
        
        # Verificar si alembic_version existe
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                )
            """))
            
            table_exists = result.scalar()
            
            if not table_exists:
                logger.info("📋 Creando tabla alembic_version...")
                # Crear tabla y marcar como head
                alembic_cfg = get_alembic_config()
                command.upgrade(alembic_cfg, "head")
                logger.info("✅ Base de datos inicializada con Alembic")
            else:
                # Aplicar migraciones pendientes
                logger.info("⬆️ Aplicando migraciones pendientes...")
                alembic_cfg = get_alembic_config()
                command.upgrade(alembic_cfg, "head")
                logger.info("✅ Migraciones completadas")
                
        logger.info("🎉 Base de datos actualizada correctamente")
        
    except Exception as e:
        logger.error(f"❌ Error en migraciones: {e}")
        if settings.DEBUG:
            logger.warning("⚠️ Continuando en modo DEBUG a pesar del error")
        else:
            raise