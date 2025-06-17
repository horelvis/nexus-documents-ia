from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import sys
from contextlib import asynccontextmanager

# main.py
from app.patch.fix_crewai_litellm import apply_patch

apply_patch()

from app.core.config import settings
from app.api import graphs as graph_routes
from app.core.langgraph_manager import LangGraphManager


# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
    level=settings.log_level
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    
    # Initialize LangGraph manager
    try:
        manager = LangGraphManager()
        await manager.initialize()
        logger.info("LangGraph manager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize LangGraph manager: {e}")
        raise
    
    yield
    
    # Cleanup
    logger.info(f"Shutting down {settings.service_name}")


app = FastAPI(
    title="LangGraph Service",
    description="Microservice for LangGraph-based workflows and state management",
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
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if LangGraph manager is initialized
        manager = LangGraphManager()
        is_healthy = await manager.health_check()
        
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "service": settings.service_name,
            "checks": {
                "langgraph": is_healthy
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": settings.service_name,
                "error": str(e)
            }
        )


# Include routers
app.include_router(
    graph_routes.router,
    prefix="/api/v1/graphs",
    tags=["graphs"]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug
    )