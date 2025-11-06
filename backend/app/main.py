"""
Refactored main application module - clean and modular
"""
import logging

from app.api.api import api_router as v1_api_router
from app.api.docs import router as docs_router
from app.core.app_config import create_application, configure_static_files
from app.core.basic_routes import basic_router
from app.core.config import settings
from app.core.debug_routes import debug_router
from app.core.error_handlers import register_error_handlers
from app.core.middlewares import configure_middlewares
from app.core.openapi_config import custom_openapi

# Create FastAPI application
app = create_application()

<<<<<<< HEAD
# Configurar logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    logger.info("🚀 Application startup...")
    logger.info(f"📍 Server URL: {settings.SERVER_HOST}:{settings.SERVER_PORT if hasattr(settings, 'SERVER_PORT') else '8000'}")
    logger.info(f"🔧 API Prefix: {settings.API_PREFIX}")
    logger.info(f"🌐 CORS Origins: {settings.BACKEND_CORS_ORIGINS}")
    logger.info(f"🗄️ Database URL: {settings.SQLALCHEMY_DATABASE_URI}")
    
    # Crear tablas si no existen - con reintentos para producción
    max_retries = 3
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔧 Verificando estructura de base de datos... (intento {attempt + 1}/{max_retries})")
            from app.db.base_class import Base
            from app.db.database import engine
            import app.db.models  # Importar módulo para registrar los modelos
            
            # Crear todas las tablas desde los modelos
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Estructura de base de datos verificada/creada")
            
            # Auto-upgrade de la base de datos (solo para registrar versión de Alembic)
            logger.info("🔧 Registrando versión de Alembic...")
            from app.db.migrations import auto_upgrade_database
            auto_upgrade_database()
            logger.info("✅ Versión de Alembic registrada")
            break  # Éxito, salir del loop
        except Exception as e:
            logger.error(f"❌ Error en configuración de BD (intento {attempt + 1}): {e}")
            if attempt == max_retries - 1:  # Último intento
                if not settings.DEBUG:
                    logger.warning("⚠️ Continuando sin BD - la aplicación intentará conectar más tarde")
                else:
                    logger.warning("⚠️ Continuando en modo DEBUG a pesar del error de BD")
            else:
                logger.info(f"⏳ Reintentando en {retry_delay} segundos...")
                import asyncio
                await asyncio.sleep(retry_delay)
    
    logger.info(f"📝 Documentation available at: {settings.API_PREFIX}/docs")
    yield
    # Shutdown:
    logger.info("🛑 Application shutdown...")

# Crear aplicación FastAPI con metadatos mejorados
app = FastAPI(
    lifespan=lifespan, # Add lifespan handler
    title=settings.SERVER_NAME,
    description="""
    # Sistema de Gestión Documental con Búsqueda Semántica
    
    Esta API permite gestionar documentos, realizar búsquedas semánticas y chatear con tus documentos.
    
    ## Características principales:
    
    * **Gestión de documentos**: Sube, descarga, categoriza y elimina documentos
    * **Búsqueda semántica**: Encuentra documentos por similitud conceptual
    * **Procesamiento inteligente**: Extracción de texto, generación de resúmenes y sugerencia de etiquetas
    * **Multi-tenant**: Aislamiento de datos por organización
    * **Autenticación segura**: JWT para todas las operaciones
    
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

# Definir una función personalizada para generar el esquema OpenAPI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Establecer explícitamente la versión de OpenAPI
    openapi_schema["openapi"] = "3.0.2"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Asignar la función personalizada
=======
# Configure custom OpenAPI schema
>>>>>>> feature/architecture-improvements
app.openapi = custom_openapi

# Configure static files
configure_static_files(app)

# Configure middlewares (CORS, logging, etc.)
configure_middlewares(app)

# Register error handlers
register_error_handlers(app)

# Include routers
app.include_router(
    docs_router,
    prefix=settings.API_PREFIX,
    tags=["documentation"]
)

app.include_router(v1_api_router, prefix=settings.API_PREFIX)
app.include_router(basic_router)

# Include debug routes only in development
if settings.DEBUG:
    app.include_router(debug_router)

# Store reference for OpenAPI generation
settings._app = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)