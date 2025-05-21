# Actualización para app/main.py

import logging
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import time
from app.api.v1 import auth, documents, search, admin, tenants
from app.api.docs import router as docs_router  # Importar el router de documentación
from app.core.config import settings
from app.core.logging import setup_logging

# Configurar logging
setup_logging()
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI con metadatos mejorados
app = FastAPI(
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
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
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

# Middleware para logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Procesar la solicitud
    response = await call_next(request)
    
    # Calcular tiempo de procesamiento
    process_time = time.time() - start_time
    
    # Añadir cabecera de tiempo de procesamiento
    response.headers["X-Process-Time"] = str(process_time)
    
    # Loggear la solicitud
    logger.info(
        f"Request: {request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.4f}s"
    )
    
    return response

# Incluir router de documentación personalizada
app.include_router(
    docs_router,
    prefix=settings.API_V1_STR,
    tags=["documentation"]
)

# Rutas de la API v1
app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_STR}/auth",
    tags=["auth"]
)

app.include_router(
    documents.router,
    prefix=f"{settings.API_V1_STR}/documents",
    tags=["documents"]
)

app.include_router(
    search.router,
    prefix=f"{settings.API_V1_STR}/search",
    tags=["search"]
)

app.include_router(
    admin.router,
    prefix=f"{settings.API_V1_STR}/admin",
    tags=["admin"]
)

app.include_router(
    tenants.router,
    prefix=f"{settings.API_V1_STR}/tenants",
    tags=["tenants"]
)

# Ruta de estado
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# Manejador de errores global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)