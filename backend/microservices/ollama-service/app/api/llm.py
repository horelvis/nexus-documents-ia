"""
LLM API endpoints for Ollama operations
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from loguru import logger

from app.services.ollama_service import OllamaService
from app.core.config import settings

router = APIRouter()
ollama_service = OllamaService()

# Request/Response models
class ChatRequest(BaseModel):
    model: str = Field(..., description="Model name to use")
    messages: List[Dict[str, str]] = Field(..., description="Chat messages")
    temperature: float = Field(default=settings.DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    max_tokens: int = Field(default=settings.DEFAULT_MAX_TOKENS, gt=0)
    top_p: float = Field(default=settings.DEFAULT_TOP_P, ge=0.0, le=1.0)
    stream: bool = Field(default=False, description="Enable streaming response")

class GenerateRequest(BaseModel):
    model: str = Field(..., description="Model name to use")
    prompt: str = Field(..., description="Input prompt")
    temperature: float = Field(default=settings.DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    max_tokens: int = Field(default=settings.DEFAULT_MAX_TOKENS, gt=0)
    top_p: float = Field(default=settings.DEFAULT_TOP_P, ge=0.0, le=1.0)
    stream: bool = Field(default=False, description="Enable streaming response")

class ModelPullRequest(BaseModel):
    model: str = Field(..., description="Model name to pull")

class ModelInfo(BaseModel):
    name: str
    size: int
    digest: str
    modified_at: str

class ChatResponse(BaseModel):
    model: str
    response: str
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    eval_count: Optional[int] = None

@router.get("/models", response_model=List[ModelInfo])
async def list_models():
    """List available models"""
    try:
        models = await ollama_service.list_models()
        return models
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/pull")
async def pull_model(request: ModelPullRequest, background_tasks: BackgroundTasks):
    """Pull a model from Ollama registry"""
    try:
        background_tasks.add_task(ollama_service.pull_model, request.model)
        return {"message": f"Started pulling model {request.model}", "status": "in_progress"}
    except Exception as e:
        logger.error(f"Error pulling model {request.model}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/models/{model_name}")
async def delete_model(model_name: str):
    """Delete a model"""
    try:
        success = await ollama_service.delete_model(model_name)
        if success:
            return {"message": f"Model {model_name} deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    except Exception as e:
        logger.error(f"Error deleting model {model_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with a model"""
    try:
        response = await ollama_service.chat(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            stream=request.stream
        )
        return response
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=ChatResponse)
async def generate(request: GenerateRequest):
    """Generate text with a model"""
    try:
        response = await ollama_service.generate(
            model=request.model,
            prompt=request.prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            stream=request.stream
        )
        return response
    except Exception as e:
        logger.error(f"Error in generate: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/{model_name}/info")
async def get_model_info(model_name: str):
    """Get information about a specific model"""
    try:
        info = await ollama_service.get_model_info(model_name)
        if info:
            return info
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    except Exception as e:
        logger.error(f"Error getting model info for {model_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_status():
    """Get Ollama service status"""
    try:
        status = await ollama_service.get_status()
        return status
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/ensure-required")
async def ensure_required_models():
    """Ensure all required models are available"""
    try:
        required_models = [settings.EMBEDDING_MODEL, settings.DEFAULT_MODEL]
        results = {}
        
        for model in required_models:
            logger.info(f"Ensuring model {model} is available...")
            success = await ollama_service.ensure_model_loaded(model)
            results[model] = "available" if success else "failed"
            
        return {
            "message": "Required models check completed",
            "results": results,
            "required_models": required_models
        }
    except Exception as e:
        logger.error(f"Error ensuring required models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/check-embedding")
async def check_embedding_model():
    """Check if embedding model is available"""
    try:
        model_name = settings.EMBEDDING_MODEL
        info = await ollama_service.get_model_info(model_name)
        
        return {
            "model": model_name,
            "available": info is not None,
            "info": info
        }
    except Exception as e:
        logger.error(f"Error checking embedding model: {e}")
        raise HTTPException(status_code=500, detail=str(e))