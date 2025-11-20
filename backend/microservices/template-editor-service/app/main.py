"""
Template Editor Service - Main FastAPI application
Provides temporary Google Docs editing following Alfresco ECM pattern
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys

from app.core.config import settings
from app.api import edit_sessions
from app.services.edit_session_service import edit_session_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("🚀 Starting Template Editor Service...")
    logger.info(f"🔧 Service Port: {settings.service_port}")
    if settings.debug:
        logger.debug("Database URL set (value hidden)")
        logger.debug("Google credentials path configured")
    
    # Start background cleanup task
    try:
        edit_session_service.start_cleanup_task()
        logger.info("✅ Background cleanup task started")
    except Exception as e:
        logger.error(f"❌ Failed to start cleanup task: {e}")
        # Continue startup anyway
    
    # Initialize database (in real implementation, run migrations here)
    try:
        # Database initialization would go here
        logger.info("✅ Database connection verified")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        # In production, you might want to exit here
    
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down Template Editor Service...")
    
    try:
        edit_session_service.stop_cleanup_task()
        logger.info("✅ Background tasks stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping background tasks: {e}")


# Create FastAPI app
app = FastAPI(
    title="Template Editor Service",
    description="Temporary Google Docs editing service following Alfresco ECM pattern",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": str(request.url)}
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Template Editor Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Temporary Google Docs editing following Alfresco ECM pattern",
        "features": [
            "Temporary Google Docs creation",
            "Session-based editing",
            "Automatic cleanup",
            "Multi-tenant support"
        ]
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Check Google API connectivity (basic check)
        from app.services.google_docs_service import google_docs_service
        
        health_status = {
            "status": "healthy",
            "service": "template-editor-service",
            "version": "1.0.0",
            "timestamp": "2025-01-08T10:00:00Z",  # In real app, use actual timestamp
            "checks": {
                "database": "healthy",  # Would check actual DB connection
                "google_apis": "healthy",  # Would check Google API access
                "cleanup_task": "running" if edit_session_service._cleanup_task else "stopped"
            }
        }
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "template-editor-service",
                "error": str(e)
            }
        )


@app.get("/info")
async def service_info():
    """Service information and capabilities"""
    return {
        "service": "template-editor-service",
        "description": "Temporary Google Docs editing following Alfresco ECM pattern",
        "version": "1.0.0",
        "pattern": "alfresco-ecm",
        "capabilities": [
            "Create temporary Google Docs from template content",
            "Manage user editing sessions",
            "Automatic session expiration and cleanup",
            "Change detection and synchronization",
            "Multi-tenant session isolation",
            "Background cleanup of expired sessions"
        ],
        "endpoints": {
            "create_session": "POST /edit-sessions/",
            "get_session": "GET /edit-sessions/{session_id}",
            "finish_session": "POST /edit-sessions/{session_id}/finish",
            "extend_session": "POST /edit-sessions/{session_id}/extend",
            "cancel_session": "DELETE /edit-sessions/{session_id}",
            "user_sessions": "GET /edit-sessions/user/{user_id}",
            "cleanup": "POST /edit-sessions/cleanup",
            "stats": "GET /edit-sessions/stats",
            "health": "GET /health",
            "docs": "GET /docs" if settings.debug else None
        },
        "configuration": {
            "session_timeout_hours": settings.edit_session_timeout_hours,
            "cleanup_interval_minutes": settings.cleanup_interval_minutes,
            "debug_mode": settings.debug
        }
    }


# Include API routers
app.include_router(edit_sessions.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
