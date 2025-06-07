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
from app.core.logging import setup_logging

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
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Configurar CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Middleware para logging detallado
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Handle OPTIONS requests early (CORS preflight)
    if request.method == "OPTIONS":
        logger.info(f"🔄 [CORS] OPTIONS preflight request: {request.url.path}")
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"✅ [CORS] OPTIONS completed: {response.status_code} - Time: {process_time:.4f}s")
        return response
    
    # Obtener información de la request
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    auth_header = request.headers.get("authorization")
    user_id = request.headers.get("x-user-id")
    content_type = request.headers.get("content-type")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    
    # Log inicial de la request
    logger.info(
        f"📨 [REQUEST] Incoming request: {request.method} {request.url.path} "
        f"from {client_ip} - User-Agent: {user_agent[:50]}... "
        f"Auth: {'Bearer ***' if auth_header else 'None'} "
        f"User-ID: {user_id or 'None'}"
    )
    
    # Log headers adicionales para debugging de auth
    if request.url.path.startswith("/api/v1/auth"):
        logger.info(f"🔍 [AUTH_REQUEST] Request to auth endpoint: {request.url.path}")
        logger.info(f"📋 [AUTH_REQUEST] Content-Type: {content_type or 'None'}")
        logger.info(f"🌐 [AUTH_REQUEST] Origin: {origin or 'None'}")
        logger.info(f"🔗 [AUTH_REQUEST] Referer: {referer or 'None'}")
        logger.info(f"🎫 [AUTH_REQUEST] Auth header present: {'Yes' if auth_header else 'No'}")
        
        if auth_header:
            # Log solo el tipo de token y longitud por seguridad
            auth_parts = auth_header.split(' ')
            if len(auth_parts) == 2:
                auth_type, token = auth_parts
                logger.info(f"🔐 [AUTH_REQUEST] Auth type: {auth_type}")
                logger.info(f"🔐 [AUTH_REQUEST] Token length: {len(token)}")
                logger.info(f"🔐 [AUTH_REQUEST] Token prefix: {token[:20]}..." if len(token) > 20 else f"🔐 [AUTH_REQUEST] Full token: {token}")
            else:
                logger.warning(f"⚠️ [AUTH_REQUEST] Invalid auth header format: {len(auth_parts)} parts")
        
        # Log query parameters if any
        if request.query_params:
            logger.info(f"❓ [AUTH_REQUEST] Query params: {dict(request.query_params)}")
            
        # Log todas las headers para debugging completo
        logger.info(f"📋 [AUTH_REQUEST] All headers: {dict(request.headers)}")
    
    try:
        # Procesar la solicitud
        response = await call_next(request)
        
        # Calcular tiempo de procesamiento
        process_time = time.time() - start_time
        
        # Añadir cabecera de tiempo de procesamiento
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log de respuesta exitosa
        logger.info(
            f"✅ [RESPONSE] Request completed: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Time: {process_time:.4f}s - "
            f"Client: {client_ip}"
        )
        
        # Log adicional para endpoints de auth
        if request.url.path.startswith("/api/v1/auth"):
            logger.info(f"🔍 [AUTH_RESPONSE] Auth endpoint response: {response.status_code}")
            logger.info(f"📋 [AUTH_RESPONSE] Response headers: {dict(response.headers)}")
            
            # Log especial para respuestas de error
            if response.status_code >= 400:
                logger.error(f"❌ [AUTH_RESPONSE] Auth failed with status: {response.status_code}")
                if response.status_code == 401:
                    logger.error(f"🚫 [AUTH_RESPONSE] Unauthorized - likely token validation failed")
                elif response.status_code == 403:
                    logger.error(f"🚫 [AUTH_RESPONSE] Forbidden - user authenticated but not authorized")
                elif response.status_code == 400:
                    logger.error(f"⚠️ [AUTH_RESPONSE] Bad Request - likely missing or malformed token")
            else:
                logger.info(f"✅ [AUTH_RESPONSE] Auth successful")
        
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"❌ [EXCEPTION] Request failed: {request.method} {request.url.path} - "
            f"Error: {str(e)} - "
            f"Time: {process_time:.4f}s - "
            f"Client: {client_ip}"
        )
        
        # Log adicional para excepciones en auth endpoints
        if request.url.path.startswith("/api/v1/auth"):
            logger.error(f"💥 [AUTH_EXCEPTION] Exception in auth endpoint: {str(e)}")
            logger.error(f"🐛 [AUTH_EXCEPTION] Exception type: {type(e)}")
            
            # Log específico para HTTPExceptions
            if hasattr(e, 'status_code'):
                logger.error(f"📋 [AUTH_EXCEPTION] HTTP status: {e.status_code}")
                logger.error(f"📋 [AUTH_EXCEPTION] HTTP detail: {getattr(e, 'detail', 'No detail')}")
            
            import traceback
            logger.error(f"📚 [AUTH_EXCEPTION] Full traceback: {traceback.format_exc()}")
        
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

# NOTA: Este endpoint es SOLO para desarrollo y debería removerse en producción
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

# Manejador de errores global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "path": str(request.url.path)
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)