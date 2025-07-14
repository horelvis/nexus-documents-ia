# Actualización para app/main.py

import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
import time
from app.api.api import api_router as v1_api_router # Import the central v1 router
from app.api.docs import router as docs_router  # Importar el router de documentación
from app.core.config import settings
from app.core.logging import setup_logging, enable_auth_debug, disable_auth_debug

from contextlib import asynccontextmanager

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
    
    # Crear tablas si no existen
    try:
        logger.info("🔧 Verificando estructura de base de datos...")
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
    except Exception as e:
        logger.error(f"❌ Error en configuración de BD: {e}")
        if not settings.DEBUG:
            logger.error("💥 Aplicación no puede iniciar sin BD")
            raise
        else:
            logger.warning("⚠️ Continuando en modo DEBUG a pesar del error de BD")
    
    logger.info(f"📝 Documentation available at: {settings.API_PREFIX}/docs")
    yield
    # Shutdown:
    logger.info("🛑 Application shutdown...")

# Crear aplicación FastAPI con metadatos mejorados
app = FastAPI(
    lifespan=lifespan, # Add lifespan handler
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
app.openapi = custom_openapi

# Configurar archivos estáticos (logos, favicons, etc.)
import os
static_dir = "app/static"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning(f"Static directory '{static_dir}' not found, skipping static files mount")

# Configurar CORS - Solución simple para IPs dinámicas
if settings.ALLOW_ALL_CORS and settings.DEBUG:
    # SOLO para desarrollo - permitir todos los orígenes
    logger.warning("⚠️ ALLOW_ALL_CORS enabled - permitting all origins (DEVELOPMENT ONLY)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # No se puede usar credentials con origins="*"
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("✅ CORS middleware configured (all origins)")
else:
    cors_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    logger.info(f"🌐 Configuring CORS with origins: {cors_origins}")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("✅ CORS middleware configured")

# Middleware para logging detallado
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Handle OPTIONS requests early (CORS preflight)
    if request.method == "OPTIONS":
        logger.info(f"🔄 OPTIONS: {request.url.path}")
        logger.info(f"🌐 Origin: {request.headers.get('origin')}")
        logger.info(f"🔍 Request headers: {dict(request.headers)}")
        
        response = await call_next(request)
        process_time = time.time() - start_time
        
        logger.info(f"📨 Response headers: {dict(response.headers)}")
        logger.info(f"✅ OPTIONS completed: {response.status_code} ({process_time:.3f}s)")
        
        if response.status_code != 200:
            logger.error(f"❌ OPTIONS failed with {response.status_code}")
        
        return response
    
    # Obtener información de la request
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    auth_header = request.headers.get("authorization")
    user_id = request.headers.get("x-user-id")
    content_type = request.headers.get("content-type")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    
    # Skip logging for health checks (Docker health check spam)
    is_health_check = request.url.path in ["/health", "/healthz"]
    
    # Log inicial de la request (skip health checks)
    if not is_health_check:
        logger.info(f"📨 {request.method} {request.url.path} from {client_ip}")
    
    # Log headers adicionales para debugging de auth
    if request.url.path.startswith("/api/v1/auth"):
        logger.info(f"🔍 Auth endpoint: {request.url.path}")
        logger.info(f"🔗 Origin: {origin or 'None'}")
        logger.info(f"🎫 Auth header: {'Yes' if auth_header else 'No'}")
        
        if auth_header and len(auth_header.split(' ')) == 2:
            auth_type, token = auth_header.split(' ')
            logger.info(f"🔐 Token: {auth_type} {token[:20]}...")
        
        # Log todas las headers para debugging completo cuando hay problema
        logger.debug(f"📋 All headers: {dict(request.headers)}")
    
    try:
        # Procesar la solicitud
        response = await call_next(request)
        
        # Calcular tiempo de procesamiento
        process_time = time.time() - start_time
        
        # Añadir cabecera de tiempo de procesamiento
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log de respuesta exitosa (skip health checks)
        if not is_health_check:
            logger.info(f"✅ {response.status_code} {request.method} {request.url.path} ({process_time:.3f}s)")
        
        # Log adicional para endpoints de auth con errores
        if request.url.path.startswith("/api/v1/auth") and response.status_code >= 400:
            if response.status_code == 401:
                logger.error("🚫 Unauthorized - token validation failed")
            elif response.status_code == 403:
                logger.error("🚫 Forbidden - user authenticated but not authorized")
            elif response.status_code == 400:
                logger.error("⚠️ Bad Request - missing or malformed token")
        
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        # Log errors (skip health checks)
        if not is_health_check:
            logger.error(f"❌ {request.method} {request.url.path} failed: {str(e)} ({process_time:.3f}s)")
        
        # Log adicional para excepciones en auth endpoints
        if request.url.path.startswith("/api/v1/auth"):
            logger.error(f"💥 Auth exception: {type(e).__name__}")
            if hasattr(e, 'status_code'):
                logger.error(f"📋 HTTP {e.status_code}: {getattr(e, 'detail', 'No detail')}")
        
        raise

# Incluir router de documentación personalizada
app.include_router(
    docs_router,
    prefix=settings.API_PREFIX,
    tags=["documentation"]
)

# Include the central v1 API router
app.include_router(v1_api_router, prefix=settings.API_PREFIX)

# Ruta de estado
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# Ruta simple para probar CORS
@app.get("/cors-test", tags=["health"])
async def cors_test(request: Request):
    return {
        "status": "ok",
        "origin": request.headers.get("origin"),
        "method": request.method,
        "cors_configured": len(settings.BACKEND_CORS_ORIGINS) > 0,
        "allowed_origins": [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    }

# Test endpoint directo para auth
@app.get("/direct-auth-test", tags=["debug"])
async def direct_auth_test():
    from app.api.dependencies import get_current_user
    from app.db.database import get_db
    
    logger.info("🔧 [DIRECT_TEST] Direct auth test endpoint called")
    return {"status": "direct_endpoint_working", "message": "This endpoint works without router"}

# Ruta de test de conectividad
@app.get("/test-connection", tags=["health"])
async def test_connection(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    headers = dict(request.headers)
    
    logger.info(f"🔍 Connection test from {client_ip}")
    logger.info(f"🔍 Headers received: {headers}")
    
    return {
        "status": "connected",
        "client_ip": client_ip,
        "headers": headers,
        "cors_origins": [str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        "api_prefix": settings.API_PREFIX,
        "server_host": str(settings.SERVER_HOST)
    }

# Ruta de debug para listar endpoints
@app.get("/debug/routes", tags=["debug"])
async def list_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else []
            })
    return {"routes": routes}

# Debug endpoint para controlar logging
@app.post("/debug/logging/auth/enable", tags=["debug"])
async def enable_debug_logging():
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️
    Activa logging DEBUG para componentes de autenticación.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug logging endpoints only available in development mode"
        )
    
    enable_auth_debug()
    return {"status": "success", "message": "Debug logging enabled for authentication"}

@app.post("/debug/logging/auth/disable", tags=["debug"])
async def disable_debug_logging():
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️ 
    Desactiva logging DEBUG para componentes de autenticación.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug logging endpoints only available in development mode"
        )
    
    disable_auth_debug()
    return {"status": "success", "message": "Debug logging disabled for authentication"}

@app.get("/debug/logging/status", tags=["debug"])
async def get_logging_status():
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️
    Muestra el estado actual del logging.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug logging endpoints only available in development mode"
        )
    
    import logging
    auth_loggers = [
        "app.api.dependencies",
        "app.services.auth_service", 
        "app.api.v1.auth",
        "app.main"
    ]
    
    logger_status = {}
    for logger_name in auth_loggers:
        logger = logging.getLogger(logger_name)
        logger_status[logger_name] = {
            "level": logging.getLevelName(logger.level),
            "effective_level": logging.getLevelName(logger.getEffectiveLevel())
        }
    
    return {
        "debug_mode": settings.DEBUG,
        "loggers": logger_status
    }

# Debug endpoint para verificar estructura de tabla
@app.get("/debug/check-users-table", tags=["debug"])
async def check_users_table():
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️
    Verifica la estructura de la tabla users.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoint only available in development mode"
        )
    
    try:
        from app.db.database import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            # Obtener todas las columnas de la tabla users
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name='users'
                ORDER BY ordinal_position
            """))
            
            columns = []
            for row in result.fetchall():
                columns.append({
                    "name": row[0],
                    "type": row[1], 
                    "nullable": row[2],
                    "default": row[3]
                })
            
            # Verificar específicamente onboarding_completed
            onboarding_exists = any(col["name"] == "onboarding_completed" for col in columns)
            
            return {
                "status": "success",
                "table_exists": len(columns) > 0,
                "onboarding_completed_exists": onboarding_exists,
                "total_columns": len(columns),
                "columns": columns
            }
            
    except Exception as e:
        logger.error(f"❌ Error checking users table: {str(e)}")
        return {
            "status": "error",
            "message": f"Error checking users table: {str(e)}"
        }

# Debug endpoint para forzar adición de columna
@app.post("/debug/force-add-onboarding-column", tags=["debug"])
async def force_add_onboarding_column():
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️
    Fuerza la adición de la columna onboarding_completed.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoint only available in development mode"
        )
    
    try:
        from app.db.migrations import manual_add_onboarding_column
        
        success = manual_add_onboarding_column()
        
        if success:
            return {
                "status": "success",
                "message": "Columna onboarding_completed procesada exitosamente"
            }
        else:
            return {
                "status": "error", 
                "message": "No se pudo agregar la columna onboarding_completed"
            }
            
    except Exception as e:
        logger.error(f"❌ Error forcing column addition: {str(e)}")
        return {
            "status": "error",
            "message": f"Error forcing column addition: {str(e)}"
        }

# Debug endpoint para crear migraciones
@app.post("/debug/create-migration", tags=["debug"])
async def create_migration_endpoint(message: str):
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️
    Crea una nueva migración con Alembic.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Migration creation endpoint only available in development mode"
        )
    
    try:
        from app.db.migrations import create_migration
        create_migration(message)
        return {
            "status": "success",
            "message": f"Migration '{message}' created successfully (DEVELOPMENT ONLY)",
            "warning": "This endpoint should NOT be used in production"
        }
    except Exception as e:
        logger.error(f"❌ Migration creation failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Migration creation failed: {str(e)}"
        }


@app.post("/debug/init-db", tags=["debug"], include_in_schema=False)
async def init_database():
    """
    ⚠️ SOLO PARA DESARROLLO ⚠️
    Inicializar la base de datos con tablas y datos iniciales.
    Este endpoint NO debe usarse en producción por razones de seguridad.
    """
    # Verificar que estamos en modo desarrollo
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Database initialization endpoint only available in development mode"
        )
    
    try:
        from app.db.models import Base
        from app.db.database import engine, SessionLocal
        from app.services.auth_service import AuthService
        from app.db.models import Tenant, User
        import uuid
        
        logger.warning("🚨 DEVELOPMENT ONLY: Initializing database via API endpoint")
        
        # Crear todas las tablas
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created")
        
        # Crear datos iniciales
        db = SessionLocal()
        try:
            # Crear tenant por defecto
            tenant = db.query(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT).first()
            if not tenant:
                tenant = Tenant(
                    id=uuid.uuid4(),
                    name=settings.DEFAULT_TENANT,
                    description="Default tenant",
                    bucket_name=f"nexus-{settings.DEFAULT_TENANT}"
                )
                db.add(tenant)
                db.flush()
                logger.info(f"✅ Default tenant created: {tenant.id}")
            
            # Crear usuario admin
            admin_user = db.query(User).filter(User.email == "admin@example.com").first()
            if not admin_user:
                admin_user = User(
                    id=uuid.uuid4(),
                    email="admin@example.com",
                    hashed_password=AuthService.get_password_hash("admin123"),
                    full_name="Admin User",
                    is_superuser=True,
                    is_active=True,
                    tenant_id=tenant.id
                )
                db.add(admin_user)
                logger.info("✅ Admin user created")
            
            db.commit()
            
        finally:
            db.close()
        
        return {
            "status": "success",
            "message": "Database initialized successfully (DEVELOPMENT ONLY)",
            "tenant_id": str(tenant.id) if tenant else None,
            "warning": "This endpoint should NOT be used in production"
        }
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Database initialization failed: {str(e)}"
        }

# Manejadores de errores específicos
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"🚫 Validation error on {request.url.path}: {str(exc)}")
    logger.error(f"🔍 Validation errors: {exc.errors()}")
    
    if settings.DEBUG:
        logger.error(f"🔍 Request method: {request.method}")
        logger.error(f"🔍 Request headers: {dict(request.headers)}")
        logger.error(f"🔍 Request body: {await request.body() if hasattr(request, 'body') else 'N/A'}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "path": str(request.url.path),
            "debug_info": "Validation error - check logs for details" if settings.DEBUG else None
        }
    )

# Manejador de errores global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"💥 Unhandled exception on {request.url.path}: {str(exc)}")
    
    # En DEBUG mode, mostrar más información
    if settings.DEBUG:
        logger.error(f"🔍 Request method: {request.method}")
        logger.error(f"🔍 Request headers: {dict(request.headers)}")
        logger.error(f"🔍 Exception type: {type(exc)}")
        import traceback
        logger.error(f"📚 Full traceback: {traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "path": str(request.url.path),
            "debug_info": str(exc) if settings.DEBUG else None
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)