"""
Ollama Microservice - FastAPI wrapper for Ollama LLM
"""
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.llm import router as llm_router
from app.core.config import settings

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