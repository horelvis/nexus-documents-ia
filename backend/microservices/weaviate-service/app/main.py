"""
Weaviate Microservice with Elysia Integration
Provides advanced RAG capabilities using Weaviate + Elysia decision trees
"""
import warnings

# Suppress httpx deprecation warning from litellm (uses data= instead of content=)
# This is a known issue in litellm: https://github.com/BerriAI/litellm/issues
warnings.filterwarnings(
    "ignore",
    message="Use 'content=<...>' to upload raw bytes/text content.",
    category=DeprecationWarning,
    module="httpx._models"
)

# Suppress pydantic v2 deprecation warnings (class Config -> model_config)
# These will be fixed in future but are not breaking changes
try:
    from pydantic import PydanticDeprecatedSince20
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
except ImportError:
    pass
warnings.filterwarnings(
    "ignore",
    message=".*class-based `config` is deprecated.*",
    category=DeprecationWarning
)

# Suppress FastAPI regex deprecation warning
warnings.filterwarnings(
    "ignore",
    message="`regex` has been deprecated.*",
    category=DeprecationWarning
)

# Suppress Click shell_completion deprecation from spacy
warnings.filterwarnings(
    "ignore",
    message=".*Importing 'parser.split_arg_string' is deprecated.*",
    category=DeprecationWarning
)

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time

# Fix for asyncio loop compatibility with Elysia
try:
    import nest_asyncio
    import asyncio
    
    # Only apply patch if not using uvloop
    loop = asyncio.get_event_loop()
    if 'uvloop' not in str(type(loop)):
        nest_asyncio.apply()
        logging.getLogger(__name__).info("✅ Applied nest_asyncio patch")
    else:
        logging.getLogger(__name__).info("⚠️ Using uvloop, skipping nest_asyncio patch")
except ImportError:
    logging.getLogger(__name__).warning("⚠️ nest_asyncio not available")
except Exception as e:
    logging.getLogger(__name__).warning(f"⚠️ Could not apply nest_asyncio patch: {e}")

from app.core.config import settings
from app.core.security import verify_api_key
from app.api import weaviate_router, elysia_router, public_knowledge_router
from app.cag.api.cag import router as cag_router
from app.cag.api.vector import router as cag_vector_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("🚀 Starting Weaviate Service with Elysia...")
    logger.info(f"🔧 Service Port: {settings.service_port}")
    logger.info(f"🗄️ Weaviate URL: {settings.weaviate_url}")
    logger.info(f"🧠 Elysia enabled: {settings.elysia_enabled}")
    
    # Initialize connections
    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.initialize()
        logger.info("✅ Weaviate connection established")
        
        if settings.elysia_enabled:
            from app.services.elysia_service import elysia_service
            # Force re-initialization to ensure proper state
            if not elysia_service.tree or not elysia_service.tools_registered:
                await elysia_service.initialize()
            logger.info("✅ Elysia framework initialized")

        # Initialize integrated CAG engine
        try:
            from app.cag.services.cag_service import cag_service
            await cag_service.initialize()
            logger.info("✅ CAG engine initialized inside weaviate-service")
        except Exception as cag_error:
            logger.error(f"❌ Failed to initialize integrated CAG engine: {cag_error}")
            raise cag_error
            
    except Exception as e:
        logger.error(f"❌ Service initialization failed: {e}")
        # Continue startup but log error
    
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down Weaviate Service...")
    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.cleanup()
        logger.info("✅ Weaviate connections closed")
    except:
        pass

# Create FastAPI app
app = FastAPI(
    title="Weaviate Service with Elysia",
    description="Advanced RAG service using Weaviate vector database and Elysia decision trees",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if not settings.request_logging_enabled:
        return await call_next(request)

    start_time = time.time()
    
    # Skip health check spam
    if request.url.path != "/health":
        logger.info(f"📨 {request.method} {request.url.path}")
    
    response = await call_next(request)
    process_time = time.time() - start_time
    
    if request.url.path != "/health":
        logger.info(f"✅ {response.status_code} completed in {process_time:.3f}s")
    
    return response

# Include routers
app.include_router(weaviate_router, prefix="/weaviate", tags=["weaviate"])
app.include_router(elysia_router, prefix="/elysia", tags=["elysia"])
app.include_router(public_knowledge_router, tags=["public-knowledge"])
app.include_router(cag_router)
app.include_router(cag_vector_router)

# Health check
@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "weaviate-service",
        "version": "1.0.0",
        "weaviate_url": settings.weaviate_url,
        "elysia_enabled": settings.elysia_enabled
    }

# Service info
@app.get("/info")
async def service_info():
    """Service information and capabilities"""
    return {
        "service": "weaviate-service",
        "description": "Advanced RAG with Weaviate + Elysia decision trees",
        "capabilities": [
            "Vector storage and retrieval",
            "Semantic search",
            "Decision tree-based tool selection",
            "Dynamic data visualization",
            "Multi-agent coordination",
            "Feedback learning"
        ],
        "endpoints": {
            "weaviate": "/weaviate/*",
            "elysia": "/elysia/*",
            "health": "/health",
            "docs": "/docs" if settings.debug else None
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=settings.service_port,
        reload=settings.debug
    )
