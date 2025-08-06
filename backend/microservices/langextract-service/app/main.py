"""
LangExtract Microservice
Provides structured document extraction using LangExtract with multiple LLM providers
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys

from .core.config import settings
from .api import extraction
from .schemas.extraction import HealthResponse

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"Default provider: {settings.default_provider}")
    logger.info(f"Ollama endpoint: {settings.ollama_host}")
    
    # Test Ollama connection
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_host}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                logger.info(f"✅ Ollama connected. Available models: {len(models)}")
                for model in models[:3]:  # Show first 3 models
                    logger.info(f"  - {model.get('name', 'unknown')}")
            else:
                logger.warning(f"⚠️  Ollama connection issue: {response.status_code}")
    except Exception as e:
        logger.warning(f"⚠️  Could not connect to Ollama: {e}")
        logger.info("Will use fallback extraction methods if needed")
    
    yield
    
    logger.info(f"Shutting down {settings.service_name}")


# Create FastAPI app
app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    description="Document extraction service using LangExtract with multiple LLM providers",
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

# Include routers
app.include_router(extraction.router)


@app.get("/", response_model=dict)
async def root():
    """Root endpoint"""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": [
            "/health",
            "/api/v1/extraction/extract",
            "/api/v1/extraction/stats",
            "/docs"
        ]
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Check available providers
        providers = ["ollama"]  # Always available
        
        if settings.gemini_api_key:
            providers.append("gemini")
        
        if settings.openai_api_key:
            providers.append("openai")
        
        return HealthResponse(
            status="healthy",
            service=settings.service_name,
            version=settings.service_version,
            providers=providers,
            default_provider=settings.default_provider
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8009,
        reload=True,
        log_level="info"
    )