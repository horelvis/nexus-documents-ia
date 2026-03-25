"""
LangExtract Microservice
Provides structured document extraction using LangExtract with multiple LLM providers
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys
import logging
import warnings

# Silence absl and langextract warnings
logging.getLogger("absl").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="langextract")

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
    provider = (settings.default_provider or "ollama").lower()
    model = settings.llm_model  # Required - no fallback
    logger.info(f"Default provider: {provider} | model: {model}")
    
    if provider == "ollama":
        ollama_endpoint = (settings.ollama_host or "http://ollama:11434").rstrip("/")
        logger.info(f"Ollama endpoint: {ollama_endpoint}")
        # Test Ollama connection
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_endpoint}/api/tags")
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
    elif provider == "openai":
        api_base = (settings.llm_api_base or "https://api.openai.com/v1").rstrip("/")
        logger.info(f"OpenAI endpoint: {api_base}")
        if not (settings.openai_api_key or settings.llm_api_key):
            logger.warning("⚠️  OpenAI provider selected but no API key configured")
    elif provider == "gemini":
        api_base = (settings.llm_api_base or "https://generativelanguage.googleapis.com").rstrip("/")
        logger.info(f"Gemini endpoint: {api_base}")
        if not (settings.gemini_api_key or settings.llm_api_key):
            logger.warning("⚠️  Gemini provider selected but no API key configured")
    elif provider in ("anthropic", "claude"):
        logger.info(f"🤖 Using Anthropic Claude provider")
        logger.info(f"   Model: {settings.llm_model}")
        if not settings.llm_api_key:
            logger.error("❌ Anthropic provider selected but LLM_API_KEY not configured")
            raise ValueError("LLM_API_KEY is required for Anthropic provider")
    elif provider in ("sglang", "vllm"):
        # SGLang uses OpenAI-compatible API
        api_base = (settings.llm_api_base or "http://sglang:8000/v1").rstrip("/")
        logger.info(f"🚀 Using SGLang provider (OpenAI-compatible API)")
        logger.info(f"   Endpoint: {api_base}")
        logger.info(f"   Model: {settings.llm_model}")
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{api_base}/models", timeout=10.0)
                if response.status_code == 200:
                    models = response.json().get("data", [])
                    logger.info(f"✅ SGLang connected. Available models: {len(models)}")
                    for m in models[:3]:
                        logger.info(f"  - {m.get('id', 'unknown')}")
                else:
                    logger.warning(f"⚠️  SGLang connection issue: {response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️  Could not connect to SGLang: {e}")
            logger.info("Will use fallback extraction methods if needed")
    else:
        logger.error(f"❌ Unknown provider '{provider}'. Valid providers: ollama, openai, gemini, anthropic, sglang")
        raise ValueError(f"Invalid LLM_PROVIDER: {provider}")
    
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
