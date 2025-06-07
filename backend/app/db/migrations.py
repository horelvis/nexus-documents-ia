# app/db/migrations.py
"""
Sistema de migraciones automáticas usando Alembic
"""
import logging
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.environment import EnvironmentContext
from sqlalchemy import engine_from_config, pool, text

from app.core.config import settings
from app.db.database import engine

logger = logging.getLogger(__name__)

def get_alembic_config() -> Config:
    """Obtiene la configuración de Alembic"""
    # Buscar alembic.ini en múltiples ubicaciones posibles
    possible_paths = [
        Path(__file__).parent.parent.parent / "alembic.ini",  # Desarrollo
        Path("/app/alembic.ini"),  # Docker
        Path.cwd() / "alembic.ini",  # Working directory
    ]
    
    alembic_cfg_path = None
    for path in possible_paths:
        if path.exists():
            alembic_cfg_path = path
            break
    
    if not alembic_cfg_path:
        raise FileNotFoundError(f"alembic.ini not found in any of: {[str(p) for p in possible_paths]}")
    
    logger.info(f"📁 Using alembic.ini from: {alembic_cfg_path}")
    
    # Crear configuración de Alembic
    alembic_cfg = Config(str(alembic_cfg_path))
    
    # Establecer la URL de la base de datos
    alembic_cfg.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI)
    
    # Asegurar que script_location sea correcto
    script_location = alembic_cfg_path.parent / "alembic"
    alembic_cfg.set_main_option("script_location", str(script_location))
    
    logger.info(f"📁 Script location: {script_location}")
    
    return alembic_cfg

def get_current_revision() -> str | None:
    """Obtiene la revisión actual de la base de datos"""
    try:
        with engine.connect() as conn:
            # Verificar si la tabla alembic_version existe
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                )
            """))
            
            table_exists = result.scalar()
            
            if not table_exists:
                logger.info("📋 Tabla alembic_version no existe - BD nueva")
                return None
            
            # Obtener la revisión actual
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            
            if row:
                return row[0]
            else:
                return None
                
    except Exception as e:
        logger.warning(f"⚠️ No se pudo obtener la revisión actual: {e}")
        return None

def get_head_revision() -> str:
    """Obtiene la última revisión disponible en los scripts"""
    try:
        alembic_cfg = get_alembic_config()
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        return script_dir.get_current_head()
    except Exception as e:
        logger.error(f"❌ Error obteniendo head revision: {e}")
        raise

def needs_upgrade() -> bool:
    """Verifica si la BD necesita actualización"""
    try:
        current = get_current_revision()
        head = get_head_revision()
        
        logger.info(f"🔍 Revisión actual: {current}")
        logger.info(f"🔍 Revisión objetivo: {head}")
        
        if current is None:
            # BD nueva, necesita stamp + upgrade
            return True
        
        return current != head
        
    except Exception as e:
        logger.error(f"❌ Error verificando si necesita upgrade: {e}")
        return False

def run_migrations():
    """Ejecuta las migraciones pendientes"""
    try:
        logger.info("🚀 Iniciando proceso de migraciones...")
        
        alembic_cfg = get_alembic_config()
        current = get_current_revision()
        
        if current is None:
            # BD nueva - crear tabla alembic_version y marcar como head
            logger.info("🆕 BD nueva detectada - inicializando Alembic...")
            command.stamp(alembic_cfg, "head")
            logger.info("✅ BD marcada como actualizada")
        else:
            # BD existente - ejecutar upgrade
            logger.info("⬆️ Ejecutando migraciones pendientes...")
            command.upgrade(alembic_cfg, "head")
            logger.info("✅ Migraciones completadas")
            
    except Exception as e:
        logger.error(f"❌ Error ejecutando migraciones: {e}")
        raise

def manual_add_onboarding_column():
    """Fallback manual para añadir la columna onboarding_completed"""
    try:
        logger.info("🔧 Intentando agregar columna onboarding_completed manualmente...")
        
        with engine.connect() as conn:
            # Verificar si la columna existe
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='onboarding_completed'
            """))
            
            if not result.fetchone():
                logger.info("➕ Agregando columna onboarding_completed...")
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE NOT NULL
                """))
                conn.commit()
                logger.info("✅ Columna onboarding_completed agregada exitosamente")
                return True
            else:
                logger.info("✅ Columna onboarding_completed ya existe")
                return True
                
    except Exception as e:
        logger.error(f"❌ Error agregando columna manualmente: {e}")
        return False

def auto_upgrade_database():
    """
    Función principal para auto-upgrade de la BD al inicio de la aplicación
    """
    try:
        logger.info("🔧 Verificando estado de la base de datos...")
        
        # Intentar con Alembic primero
        try:
            if needs_upgrade():
                logger.info("📈 La BD necesita actualización")
                run_migrations()
                logger.info("🎉 Base de datos actualizada correctamente con Alembic")
            else:
                logger.info("✅ La BD está actualizada")
        except Exception as alembic_error:
            logger.warning(f"⚠️ Alembic falló: {alembic_error}")
            logger.info("🔄 Intentando upgrade manual...")
            
            # Fallback a upgrade manual
            if manual_add_onboarding_column():
                logger.info("✅ Upgrade manual completado exitosamente")
            else:
                raise Exception("Tanto Alembic como upgrade manual fallaron")
            
    except Exception as e:
        logger.error(f"💥 Error en auto-upgrade de BD: {e}")
        # En desarrollo, continuamos; en producción podríamos fallar
        if settings.DEBUG:
            logger.warning("⚠️ Continuando en modo DEBUG a pesar del error")
        else:
            raise

def create_migration(message: str):
    """Crea una nueva migración (solo para desarrollo)"""
    if not settings.DEBUG:
        raise RuntimeError("Creación de migraciones solo disponible en modo DEBUG")
    
    try:
        logger.info(f"📝 Creando migración: {message}")
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, message=message, autogenerate=True)
        logger.info("✅ Migración creada exitosamente")
    except Exception as e:
        logger.error(f"❌ Error creando migración: {e}")
        raise