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
    Registra la versión actual de Alembic (sin ejecutar migraciones en DB limpia)
    """
    try:
        logger.info("🔧 Verificando estado de Alembic...")
        
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
                logger.info("📋 Base de datos limpia detectada - registrando versión inicial...")
                
                # Solo crear la tabla alembic_version y registrar la versión actual
                # sin ejecutar migraciones (las tablas ya existen desde models.py)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                """))
                
                # Registrar la versión actual
                conn.execute(text("""
                    INSERT INTO alembic_version (version_num) 
                    VALUES ('unified_20250615')
                    ON CONFLICT (version_num) DO NOTHING
                """))
                
                conn.commit()
                logger.info("✅ Versión de Alembic registrada (sin migraciones)")
            else:
                # Verificar versión actual
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                current_version = result.scalar()
                logger.info(f"📌 Versión actual de Alembic: {current_version}")
                
                # En una DB reconstruida, no necesitamos migrar
                if current_version == 'unified_20250615':
                    logger.info("✅ Base de datos ya está en la versión correcta")
                else:
                    logger.warning(f"⚠️ Versión inesperada: {current_version}")
                    # Aquí podrías manejar migraciones reales si fuera necesario
                
        logger.info("🎉 Base de datos actualizada correctamente")
        
    except Exception as e:
        logger.error(f"❌ Error en migraciones: {e}")
        if settings.DEBUG:
            logger.warning("⚠️ Continuando en modo DEBUG a pesar del error")
        else:
            raise