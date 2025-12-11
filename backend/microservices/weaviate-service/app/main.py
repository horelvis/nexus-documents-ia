"""
Weaviate Microservice with Emma AI Integration
Provides advanced RAG capabilities using Weaviate + Emma AI (PlanningFlow orchestration)
"""
import warnings

# Suppress httpx deprecation warning from litellm (uses data= instead of content=)
warnings.filterwarnings(
    "ignore",
    message="Use 'content=<...>' to upload raw bytes/text content.",
    category=DeprecationWarning,
    module="httpx._models"
)

# Suppress pydantic v2 deprecation warnings (class Config -> model_config)
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

from app.core.config import settings
from app.core.security import verify_api_key
from app.api import weaviate_router, emma_router, public_knowledge_router
from app.api.agents import router as agents_router
from app.cag.api.cag import router as cag_router
from app.cag.api.vector import router as cag_vector_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce verbosity of agent framework logs
logging.getLogger("autogen_core.events").setLevel(logging.WARNING)
logging.getLogger("autogen_core").setLevel(logging.WARNING)
logging.getLogger("autogen_agentchat").setLevel(logging.WARNING)
logging.getLogger("agent_framework").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("🚀 Starting Weaviate Service with Emma AI...")
    logger.info(f"🔧 Service Port: {settings.service_port}")
    logger.info(f"🗄️ Weaviate URL: {settings.weaviate_url}")
    logger.info(f"🤖 PlanningFlow enabled: {settings.agents_enabled}")

    # Initialize connections
    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.initialize()
        logger.info("✅ Weaviate connection established")

        # Initialize Emma AI (PlanningFlow orchestration)
        if settings.agents_enabled:
            try:
                from app.services.emma_service import emma_service
                await emma_service.initialize()
                logger.info("✅ Emma AI initialized (PlanningFlow orchestration)")
            except Exception as emma_error:
                logger.warning(f"⚠️ Emma AI initialization skipped: {emma_error}")

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
    title="Weaviate Service with Emma AI",
    description="Advanced RAG service using Weaviate vector database and Emma AI (PlanningFlow orchestration)",
    version="2.0.0",
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
app.include_router(emma_router, prefix="/emma", tags=["emma"])
app.include_router(agents_router, tags=["agents"])  # OpenManus-style orchestration
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
        "version": "2.0.0",
        "weaviate_url": settings.weaviate_url,
        "agents_enabled": settings.agents_enabled
    }

# Service info
@app.get("/info")
async def service_info():
    """Service information and capabilities"""
    return {
        "service": "weaviate-service",
        "description": "Advanced RAG with Weaviate + AutoGen multi-agent orchestration",
        "capabilities": [
            "Vector storage and retrieval",
            "Semantic search",
            "Multi-agent orchestration (AutoGen)",
            "RAG Pipeline (7 layers)",
            "Dynamic data visualization",
            "Multi-provider LLM support"
        ],
        "agents": [
            "SearchAgent",
            "AnalystAgent",
            "ContractAgent",
            "ComplianceAgent",
            "SummarizerAgent"
        ],
        "workflows": [
            "Sequential (RoundRobinGroupChat)",
            "GroupChat (SelectorGroupChat)",
            "Swarm (Handoffs)",
            "PlanningFlow (OpenManus-style)"
        ],
        "endpoints": {
            "weaviate": "/weaviate/*",
            "emma": "/emma/* (chatbot)",
            "agents": "/agents/* (orchestration)",
            "cag": "/cag/*",
            "health": "/health",
            "docs": "/docs" if settings.debug else None
        }
    }

# Agent status endpoint
@app.get("/agents/status")
async def agents_status():
    """AutoGen agents status"""
    try:
        from app.agents import get_orchestrator, agent_config
        orchestrator = get_orchestrator()
        return {
            "status": "available" if agent_config.enabled else "disabled",
            "config": {
                "enabled": agent_config.enabled,
                "default_workflow": agent_config.default_workflow.value,
                "max_turns": agent_config.max_turns,
                "timeout_seconds": agent_config.timeout_seconds,
                "fallback_to_rag": agent_config.fallback_to_rag,
                "model_provider": agent_config.model_provider,
                "ollama_model": agent_config.ollama_model
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug
    )
