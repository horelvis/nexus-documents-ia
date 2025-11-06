#!/usr/bin/env python3
"""
Intermediate FastAPI app - adding complexity gradually
"""

import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import real settings but skip database
try:
    from app.core.config import settings
    logger.info("✅ Real settings imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import real settings: {e}")
    # Fallback to basic settings
    class Settings:
        API_PREFIX: str = "/api/v1"
        SERVER_NAME: str = "NexusDocs360 API"
        DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
        BACKEND_CORS_ORIGINS = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://pre.nexusdocs360.app",
            "https://pre-api.nexusdocs360.app"
        ]
    settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Application startup...")
    logger.info(f"📍 Server starting...")
    logger.info(f"🔧 API Prefix: {settings.API_PREFIX}")
    logger.info(f"🌐 CORS Origins: {settings.BACKEND_CORS_ORIGINS}")
    
    # Try to import core modules (without DB)
    try:
        logger.info("🔧 Testing core imports...")
        # Import logging setup
        from app.core.logging import setup_logging
        setup_logging()
        logger.info("✅ Logging setup imported")
        
        # Initialize database using environment-aware proxy
        try:
            logger.info("🔧 Initializing database with environment detection...")
            
            from app.db.database_proxy import db_proxy
            
            # Initialize database connection (auto-detects environment)
            if db_proxy.initialize():
                logger.info("✅ Database proxy initialized")
                
                # Create tables
                if db_proxy.create_tables():
                    logger.info("✅ Database tables ready")
                else:
                    logger.warning("⚠️ Table creation failed, but connection works")
            else:
                logger.warning("⚠️ Database proxy initialization failed")
                
        except Exception as db_e:
            logger.error(f"❌ Database initialization failed: {db_e}")
            logger.warning("⚠️ Continuing without database - API will have limited functionality")
        
        # Skip API routers that might cause import issues
        logger.info("⚠️ SKIPPING API routers for stability")
        # # Try to import API routers (without DB-dependent ones)
        # try:
        #     logger.info("🔧 Testing API router imports...")
        #     # This will test if the router imports work
        #     from app.api.api import api_router
        #     logger.info("✅ API routers imported successfully")
        #     
        #     # Add the router to the app
        #     app.include_router(api_router, prefix=settings.API_PREFIX)
        #     logger.info("✅ API routers registered")
        #     
        # except Exception as router_e:
        #     logger.error(f"❌ Error importing API routers: {router_e}")
        #     logger.warning("⚠️ Continuing without API routers")
        
    except Exception as e:
        logger.error(f"❌ Error in core imports: {e}")
        logger.warning("⚠️ Continuing with basic configuration")
    
    logger.info("✅ Startup completed")
    yield
    # Shutdown
    logger.info("⏹️ Application shutdown...")

# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.SERVER_NAME,
    version="1.0.0",
    lifespan=lifespan,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic endpoints
@app.get("/")
async def root():
    return {"message": "NexusDocs360 API is running", "status": "ok", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}

@app.get(f"{settings.API_PREFIX}/health")
async def health_v1():
    return {"status": "healthy", "version": "1.0.0", "api_prefix": settings.API_PREFIX}

@app.get("/debug")
async def debug():
    # Check database status
    db_status = "unknown"
    try:
        from app.db.database_proxy import db_proxy
        if db_proxy.health_check():
            db_status = "healthy"
        else:
            db_status = "unhealthy"
    except:
        db_status = "error"
        
    return {
        "environment": {
            "DEBUG": settings.DEBUG,
            "PORT": os.getenv("PORT", "8000"),
            "API_PREFIX": settings.API_PREFIX,
            "K_SERVICE": os.getenv("K_SERVICE", "not_set"),
            "ENVIRONMENT": os.getenv("ENVIRONMENT", "unknown")
        },
        "database": {
            "status": db_status,
            "environment": os.getenv("K_SERVICE") and "cloud_run" or "local"
        },
        "status": "debug_mode_active"
    }

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"💥 Unhandled exception on {request.url.path}: {str(exc)}")
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
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)