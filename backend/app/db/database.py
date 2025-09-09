"""
Database connection management with proper pooling and error handling
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Base para modelos SQLAlchemy
Base = declarative_base()

# Configuración de pool de conexiones
POOL_CONFIG = {
    "poolclass": QueuePool,
    "pool_size": 10,  # Número máximo de conexiones en el pool
    "max_overflow": 20,  # Conexiones adicionales permitidas
    "pool_timeout": 30,  # Timeout para obtener conexión del pool
    "pool_recycle": 3600,  # Reciclar conexiones cada hora
    "pool_pre_ping": True,  # Verificar conexión antes de usar
    "echo": settings.DEBUG,  # Log SQL queries in debug mode
}

# Configuración específica para producción
if not settings.DEBUG:
    POOL_CONFIG.update({
        "pool_size": 20,
        "max_overflow": 30,
        "pool_timeout": 60,
    })

# Crear motor de base de datos con configuración optimizada
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    **POOL_CONFIG
)

# Configurar logging de conexiones
@event.listens_for(engine, "connect")
def connect_event(connection, connection_record):
    """Log successful database connections"""
    logger.debug("🔗 Database connection established")

@event.listens_for(engine, "checkout")
def checkout_event(connection, connection_record, connection_proxy):
    """Log connection checkout from pool"""
    logger.debug("📤 Connection checked out from pool")

@event.listens_for(engine, "checkin")
def checkin_event(connection, connection_record, connection_proxy):
    """Log connection checkin to pool"""
    logger.debug("📥 Connection checked in to pool")

@event.listens_for(engine, "close")
def close_event(connection, connection_record):
    """Log connection close"""
    logger.debug("🔌 Database connection closed")

# Crear fábrica de sesiones con configuración optimizada
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Mejor rendimiento
)

def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection for database sessions.
    Provides a database session with proper error handling and cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"❌ Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

@contextmanager
def get_db_context():
    """
    Context manager for database sessions.
    Useful for background tasks and utilities.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"❌ Database context error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

async def get_async_db():
    """
    Async version of database session provider.
    For use with async endpoints.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    # Crear motor async si no existe
    if not hasattr(get_async_db, '_async_engine'):
        # Convertir URI síncrona a asíncrona
        async_uri = settings.SQLALCHEMY_DATABASE_URI.replace("postgresql://", "postgresql+asyncpg://")

        get_async_db._async_engine = create_async_engine(
            async_uri,
            **POOL_CONFIG
        )

        get_async_db._async_session = async_sessionmaker(
            get_async_db._async_engine,
            expire_on_commit=False
        )

    session = get_async_db._async_session()
    try:
        yield session
    except Exception as e:
        logger.error(f"❌ Async database session error: {str(e)}")
        await session.rollback()
        raise
    finally:
        await session.close()

def test_connection() -> bool:
    """
    Test database connection and return status.
    Useful for health checks.
    """
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        logger.info("✅ Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection test failed: {str(e)}")
        return False

def get_connection_stats():
    """
    Get database connection pool statistics.
    Useful for monitoring and debugging.
    """
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checkedin": pool.checkedin(),
        "checkedout": pool.checkedout(),
        "invalid": pool.invalid(),
        "overflow": pool.overflow(),
        "timeout": pool.timeout(),
    }