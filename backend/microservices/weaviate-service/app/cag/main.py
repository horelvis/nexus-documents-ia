"""CAG Service - Main FastAPI application"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import sys

from .core.config import settings
from .api import cag, vector
from .services.cag_service import cag_service

# Configure Loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.log_level
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("Starting CAG Service...")
    
    # Initialize service
    try:
        await cag_service.initialize()
        logger.info("CAG Service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize CAG Service: {e}")
        raise
    
    yield
    
    # Cleanup
    logger.info("Shutting down CAG Service...")


# Create FastAPI app
app = FastAPI(
    title="CAG Service",
    description="Contextual Augmented Generation Service for intelligent document processing",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "CAG Service",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return await cag_service.health_check()


# Include routers
app.include_router(cag.router)
app.include_router(vector.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
        log_config=None  # Use Loguru instead
    )