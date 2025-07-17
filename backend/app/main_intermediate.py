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

# Basic settings
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
    logger.info("✅ Basic startup completed")
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
    return {
        "environment": {
            "DEBUG": settings.DEBUG,
            "PORT": os.getenv("PORT", "8000"),
            "API_PREFIX": settings.API_PREFIX
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