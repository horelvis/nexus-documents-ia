"""
Ollama Microservice - FastAPI wrapper for Ollama LLM
"""
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.llm import router as llm_router
from app.core.config import settings
from app.services.ollama_service import OllamaService

# Create FastAPI application
app = FastAPI(
    title="Ollama Microservice",
    description="FastAPI wrapper for Ollama LLM operations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(llm_router, prefix="/api/v1", tags=["llm"])

@app.on_event("startup")
async def startup_event():
    """Startup event to ensure required models are available"""
    logger.info("🚀 Starting Ollama Microservice startup...")
    
    # Initialize Ollama service
    ollama_service = OllamaService()
    
    # Required models for the system
    required_models = [
        settings.EMBEDDING_MODEL,  # nomic-embed-text
        settings.DEFAULT_MODEL     # llama3.2 or other default LLM
    ]
    
    for model in required_models:
        try:
            logger.info(f"🔍 Checking if model '{model}' is available...")
            success = await ollama_service.ensure_model_loaded(model)
            if success:
                logger.info(f"✅ Model '{model}' is ready")
            else:
                logger.warning(f"⚠️ Failed to ensure model '{model}' is ready")
        except Exception as e:
            logger.error(f"❌ Error ensuring model '{model}': {e}")
    
    logger.info("🎉 Ollama Microservice startup complete!")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ollama-microservice"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Ollama Microservice API",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    logger.info("Starting Ollama Microservice...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )