"""
Application configuration and setup utilities
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.env_validator import validate_environment
from app.core.logging import setup_logging
from app.core.security_validator import validate_security_on_startup
from app.core.structured_logging import setup_structured_logging
from app.core.alerting import initialize_alerting, start_alert_evaluation
from app.core.health_checks import initialize_health_checks, start_health_check_monitoring
from app.db.base_class import Base
from app.db.database import engine
from app.db.migrations import auto_upgrade_database

logger = logging.getLogger(__name__)

def _redact_database_url(database_url: str | None) -> str:
    if not database_url:
        return "N/A"
    try:
        parsed = urlparse(database_url)
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        db = parsed.path.lstrip("/") if parsed.path else ""
        scheme = parsed.scheme or "db"
        return f"{scheme}://{host}{port}/{db}"
    except Exception:
        return "[unparseable]"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events"""
    # Startup
    logger.info("🚀 Application startup...")

    # Security validation
    logger.info("🔒 Running security validation...")
    security_result = validate_security_on_startup()

    # Initialize monitoring systems
    logger.info("📊 Initializing monitoring systems...")
    setup_structured_logging()
    initialize_alerting()
    initialize_health_checks()

    logger.info(f"📍 Server URL: {settings.SERVER_HOST}:{settings.SERVER_PORT if hasattr(settings, 'SERVER_PORT') else '8000'}")
    logger.info(f"🔧 API Prefix: {settings.API_PREFIX}")
    logger.info(f"🌐 CORS Origins: {settings.BACKEND_CORS_ORIGINS}")
    logger.info(f"🗄️ Database: {_redact_database_url(settings.SQLALCHEMY_DATABASE_URI)}")

    # Database initialization
    await _initialize_database()

    # Start background monitoring tasks
    logger.info("🔄 Starting background monitoring tasks...")
    alert_task = asyncio.create_task(start_alert_evaluation())
    health_task = asyncio.create_task(start_health_check_monitoring())

    logger.info(f"📝 Documentation available at: {settings.API_PREFIX}/docs")
    logger.info(f"🔒 Security Score: {security_result['security_score']}/100")
    logger.info("✅ All systems initialized and monitoring active")

    yield
    # Shutdown
    logger.info("🛑 Application shutdown...")

    # Cancel background tasks
    alert_task.cancel()
    health_task.cancel()

    try:
        await alert_task
        await health_task
    except asyncio.CancelledError:
        pass

    logger.info("🔄 Background monitoring tasks stopped")


async def _initialize_database() -> None:
    """Initialize database with robust error handling"""
    try:
        logger.info("🔧 Initializing database...")
        logger.info(f"🔗 Database: {_redact_database_url(settings.SQLALCHEMY_DATABASE_URI)}")

        # Import models to register them
        import app.db.models  # noqa: F401

        # Configure engine for Cloud Run
        engine_configured = engine.execution_options(
            pool_pre_ping=True,
            pool_recycle=300
        )

        # Test connection first
        logger.info("🧪 Testing database connection...")
        from sqlalchemy import text
        with engine_configured.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")

        if settings.DB_AUTO_MIGRATE:
            # Create tables (dev/bootstrap convenience; prefer Alembic in production)
            Base.metadata.create_all(bind=engine_configured)
            logger.info("✅ Database structure verified/created")

            # Try Alembic migration (non-fatal)
            try:
                logger.info("🔧 Running Alembic migrations...")
                auto_upgrade_database()
                logger.info("✅ Alembic migrations completed")
            except Exception as alembic_e:
                logger.warning(f"⚠️ Alembic migration failed (continuing): {alembic_e}")
        else:
            logger.info("⏭️ DB_AUTO_MIGRATE disabled; skipping create_all/migrations")

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error(f"🔍 Database: {_redact_database_url(settings.SQLALCHEMY_DATABASE_URI)}")
        logger.warning("⚠️ Continuing without database - API will have limited functionality")


def configure_static_files(app: FastAPI) -> None:
    """Configure static file serving"""
    static_dir = "app/static"
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        logger.warning(f"Static directory '{static_dir}' not found, skipping static files mount")


def create_application() -> FastAPI:
    """Create and configure FastAPI application"""
    # Ensure critical environment variables are present before bootstrapping
    validate_environment()

    # Setup logging
    setup_logging()

    # Create FastAPI app with metadata
    app = FastAPI(
        lifespan=lifespan,
        title=settings.SERVER_NAME,
        description="""
        # NexusDocs360 - API de Gestión Documental Potenciada por IA 🧠

        La primera plataforma donde la Inteligencia Artificial transforma radicalmente la gestión documental empresarial.

        ## 🤖 Capacidades de IA Integradas:

        * **Procesamiento Cognitivo**: IA que comprende, analiza y genera insights automáticamente
        * **Agentes Especializados**: Legal, Financiero, Compliance - cada uno experto en su dominio
        * **Chat Inteligente**: Conversa con tus documentos en lenguaje natural
        * **Extracción Automática**: 99% de precisión en datos estructurados y no estructurados
        * **Predicción y Recomendaciones**: IA que anticipa necesidades y sugiere acciones
        * **Multimodal AI**: Procesa texto, imágenes, tablas con igual eficacia

        ## 🚀 Powered by:
        GPT-4 | Claude | Llama 3.2 | LangChain | Qdrant | Vision AI

        Para más información, consulta el [repositorio del proyecto](https://github.com/tuorganizacion/doc-management).
        """,
        version="1.0.0",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        docs_url=None,  # Desactivamos la ruta por defecto de Swagger
        redoc_url=None,  # Desactivamos la ruta por defecto de ReDoc
        openapi_tags=[
            {
                "name": "auth",
                "description": "Operaciones de autenticación y gestión de usuarios"
            },
            {
                "name": "documents",
                "description": "Gestión y procesamiento de documentos"
            },
            {
                "name": "search",
                "description": "Búsqueda semántica y consultas basadas en documentos"
            },
            {
                "name": "chat",
                "description": "Interacción conversacional con los documentos"
            },
            {
                "name": "admin",
                "description": "Operaciones administrativas (solo superusuarios)"
            },
            {
                "name": "tenants",
                "description": "Gestión de organizaciones (tenants)"
            },
            {
                "name": "storage",
                "description": "Operaciones de almacenamiento directo"
            },
            {
                "name": "langgraph",
                "description": "Flujos de trabajo avanzados con grafos y estado persistente"
            }
        ]
    )

    return app
