import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.api.storage import router as storage_router, limiter

# Configurar logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="Storage Microservice",
    description="Microservicio para gestión de almacenamiento en Google Cloud Storage",
    version=settings.SERVICE_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware para loggear requests"""
    start_time = time.time()
    
    # Skip logging for health checks (Docker health check spam)
    is_health_check = request.url.path in ["/health", "/healthz"]
    
    # Log request (skip health checks)
    if not is_health_check:
        logger.info(f"Request: {request.method} {request.url}")
        
        # Headers importantes para debugging (sin exponer secrets)
        tenant_id = request.headers.get("X-Tenant-ID", "unknown")
        user_id = request.headers.get("X-User-ID", "system")
        
        logger.debug(f"Tenant: {tenant_id}, User: {user_id}")
    
    response = await call_next(request)
    
    # Log response (skip health checks)
    if not is_health_check:
        process_time = time.time() - start_time
        logger.info(
            f"Response: {response.status_code} "
            f"({process_time:.3f}s) "
            f"for {request.method} {request.url.path}"
        )
    
    return response

# Incluir routers
app.include_router(storage_router, prefix="/api/v1")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled"
    }

# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación"""
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Testing mode: {settings.TESTING}")
    logger.info(f"GCS Project: {settings.GCS_PROJECT_ID}")
    logger.info(f"Base bucket: {settings.GCS_BUCKET_NAME}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Evento de cierre de la aplicación"""
    logger.info(f"Shutting down {settings.SERVICE_NAME}")

if __name__ == "__main__":
    import uvicorn
    import time
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=settings.DEBUG,
        log_level="info"
    )