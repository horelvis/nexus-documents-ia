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
from app.db.database import engine

logger = logging.getLogger(__name__)

def _redact_database_url(database_url: str | None) -> str:
    """
    Redact credentials from database URLs for safe logging.

    Example:
        postgresql://user:pass@host:5432/db -> postgresql://host:5432/db
    """
    if not database_url:
        return "N/A"
    try:
        parsed = urlparse(database_url)
        scheme = parsed.scheme or "db"
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        db = parsed.path.lstrip("/") if parsed.path else ""
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
    """
    Validate database connectivity on startup.

    NOTE: This function only validates connectivity. It does NOT:
    - Create tables (use: alembic upgrade head)
    - Run migrations (use: alembic upgrade head)

    Schema changes should be applied during deployment, not at runtime,
    to avoid race conditions in scaled environments with multiple replicas.

    Run migrations before starting the application:
        cd backend && alembic upgrade head
    """
    try:
        logger.info("🔧 Validating database connectivity...")

        # Import models to register them with SQLAlchemy
        import app.db.models  # noqa: F401

        # Test connection with pre-ping for resilience
        logger.info("🧪 Testing database connection...")
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")

        # Log connection pool status
        pool = engine.pool
        logger.info(
            f"📊 Connection pool: size={pool.size()} "
            f"checked_in={pool.checkedin()} overflow={pool.overflow()}"
        )

        # Initialize default tenant for single-tenant mode
        await _ensure_default_tenant()

    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error(f"🔍 Database: {_redact_database_url(settings.SQLALCHEMY_DATABASE_URI)}")
        logger.warning(
            "⚠️ Continuing without database - API will have limited functionality. "
            "Ensure the database is running and run 'alembic upgrade head' to initialize schema."
        )


async def _ensure_default_tenant() -> None:
    """
    Ensure the default tenant exists in single-tenant mode.

    In SINGLE_TENANT_MODE, this function creates the default tenant on first startup
    if it doesn't already exist. All users will be auto-assigned to this tenant.

    This is idempotent - safe to run multiple times.
    """
    if not settings.SINGLE_TENANT_MODE:
        logger.info("🏢 Multi-tenant mode: skipping default tenant initialization")
        return

    try:
        from uuid import UUID
        from sqlalchemy.orm import Session
        from app.db.models import Tenant
        from app.db.database import SessionLocal

        tenant_id = UUID(settings.DEFAULT_TENANT_ID)
        tenant_name = settings.DEFAULT_TENANT_NAME
        tenant_slug = settings.DEFAULT_TENANT_SLUG

        with SessionLocal() as db:
            # Check if tenant already exists
            existing = db.query(Tenant).filter(Tenant.id == tenant_id).first()

            if existing:
                logger.info(f"🏢 Single-tenant mode: using existing tenant '{existing.name}' ({existing.id})")
            else:
                # Create the default tenant with all required fields
                bucket_name = f"nouxcube-{str(tenant_id).replace('-', '')[:12]}"
                tenant = Tenant(
                    id=tenant_id,
                    name=tenant_name,
                    slug=tenant_slug,
                    bucket_name=bucket_name,
                    is_active=True,
                    auto_classification_enabled=True,
                    auto_classification_k=7,
                    auto_classification_min_confidence=0.6,
                    site_enabled=False,
                    settings={
                        "deployment_mode": "single_tenant",
                        "created_by": "system_initialization"
                    }
                )
                db.add(tenant)
                db.commit()
                logger.info(f"🏢 Single-tenant mode: created default tenant '{tenant_name}' ({tenant_id})")
                logger.info(f"   Bucket: {bucket_name}")

        logger.info(f"🔧 SINGLE_TENANT_MODE=true | Tenant ID: {tenant_id}")

    except Exception as e:
        logger.warning(f"⚠️ Could not initialize default tenant: {e}")


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
        # NouxCubeIA - API de Gestión Documental Potenciada por IA 🧠

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
