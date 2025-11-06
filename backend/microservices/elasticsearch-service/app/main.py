"""Elasticsearch Microservice - Main Application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.api.elasticsearch import router as elasticsearch_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Elasticsearch Microservice",
    description="Microservice for Elasticsearch operations - hybrid search and analytics",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    elasticsearch_router,
    prefix="/api/v1/elasticsearch",
    tags=["elasticsearch"]
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        from elasticsearch import Elasticsearch

        # Test Elasticsearch connection
        client = Elasticsearch([settings.ELASTICSEARCH_URL])
        info = client.info()

        return {
            "status": "healthy",
            "service": "elasticsearch-microservice",
            "elasticsearch_connected": True,
            "elasticsearch_version": info["version"]["number"],
            "debug_mode": settings.DEBUG
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "elasticsearch-microservice",
            "elasticsearch_connected": False,
            "error": str(e)
        }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Elasticsearch Microservice",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )