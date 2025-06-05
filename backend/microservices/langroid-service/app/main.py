"""
Langroid Microservice - FastAPI application for advanced agent workflows
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, AsyncGenerator
import json
import asyncio
from datetime import datetime

from app.core.config import settings
from app.services.langroid_agent_service import LangroidAgentService
from app.services.digital_signature_langroid_agent import DigitalSignatureLangroidAgent

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

# Global service instances
agent_service: Optional[LangroidAgentService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    global agent_service
    
    # Startup
    logger.info("Starting Langroid Service...")
    agent_service = LangroidAgentService()
    await agent_service.initialize()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Langroid Service...")
    if agent_service:
        await agent_service.cleanup()


app = FastAPI(
    title="Langroid Microservice",
    description="Advanced agent workflows using Langroid framework",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================
# API MODELS
# =====================================

class AgentConfig(BaseModel):
    """Agent configuration"""
    agent_type: str
    tenant_id: str
    user_id: str
    configuration: Dict[str, Any] = {}


class AgentMessage(BaseModel):
    """Agent message"""
    message: str
    conversation_id: Optional[str] = None
    context: Dict[str, Any] = {}


class AgentExecuteTask(BaseModel):
    """Agent task execution"""
    task_type: str
    parameters: Dict[str, Any]
    context: Dict[str, Any] = {}


class SignatureRequestConfig(BaseModel):
    """Digital signature request configuration"""
    title: str
    document_name: str
    signers: List[Dict[str, Any]]
    message: Optional[str] = None
    signature_type: str = "sequential"


class StreamingEvent(BaseModel):
    """Streaming event response"""
    type: str
    content: str
    metadata: Dict[str, Any] = {}
    timestamp: str = datetime.now().isoformat()


# =====================================
# HEALTH AND STATUS
# =====================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "langroid-service",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/status")
async def service_status():
    """Service status with detailed information"""
    global agent_service
    
    status = {
        "service": "langroid-service",
        "status": "ready" if agent_service else "initializing",
        "active_agents": len(agent_service.active_agents) if agent_service else 0,
        "supported_agent_types": [
            "digital_signature",
            "document_analyzer", 
            "rag_assistant",
            "generic"
        ],
        "models": {
            "llm": settings.DEFAULT_LLM_MODEL,
            "embedding": settings.DEFAULT_EMBEDDING_MODEL
        }
    }
    
    return status


# =====================================
# AGENT MANAGEMENT
# =====================================

@app.post("/agents/create")
async def create_agent(config: AgentConfig):
    """Create a new agent instance"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        agent_id = await agent_service.create_agent(
            agent_type=config.agent_type,
            tenant_id=config.tenant_id,
            user_id=config.user_id,
            configuration=config.configuration
        )
        
        return {
            "agent_id": agent_id,
            "agent_type": config.agent_type,
            "status": "created",
            "tenant_id": config.tenant_id
        }
        
    except Exception as e:
        logger.error(f"Error creating agent: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, tenant_id: str):
    """Delete an agent instance"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        success = await agent_service.delete_agent(agent_id, tenant_id)
        if success:
            return {"status": "deleted", "agent_id": agent_id}
        else:
            raise HTTPException(status_code=404, detail="Agent not found")
            
    except Exception as e:
        logger.error(f"Error deleting agent: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents/list")
async def list_agents(tenant_id: str):
    """List all agents for a tenant"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        agents = await agent_service.list_agents(tenant_id)
        return {"agents": agents, "total": len(agents)}
        
    except Exception as e:
        logger.error(f"Error listing agents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================
# AGENT INTERACTION
# =====================================

@app.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, message: AgentMessage, tenant_id: str):
    """Send a message to an agent and get streaming response"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    async def generate_response():
        try:
            async for event in agent_service.chat_with_agent(
                agent_id=agent_id,
                tenant_id=tenant_id,
                message=message.message,
                conversation_id=message.conversation_id,
                context=message.context
            ):
                yield f"data: {json.dumps(event.dict())}\n\n"
                
        except Exception as e:
            error_event = StreamingEvent(
                type="error",
                content=str(e),
                metadata={"error_type": type(e).__name__}
            )
            yield f"data: {json.dumps(error_event.dict())}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/agents/{agent_id}/execute")
async def execute_agent_task(agent_id: str, task: AgentExecuteTask, tenant_id: str):
    """Execute a specific task with an agent"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    async def generate_response():
        try:
            async for event in agent_service.execute_agent_task(
                agent_id=agent_id,
                tenant_id=tenant_id,
                task_type=task.task_type,
                parameters=task.parameters,
                context=task.context
            ):
                yield f"data: {json.dumps(event.dict())}\n\n"
                
        except Exception as e:
            error_event = StreamingEvent(
                type="error",
                content=str(e),
                metadata={"error_type": type(e).__name__}
            )
            yield f"data: {json.dumps(error_event.dict())}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# =====================================
# DIGITAL SIGNATURE SPECIFIC ENDPOINTS
# =====================================

@app.post("/signature-agent/create-request")
async def create_signature_request(
    config: SignatureRequestConfig,
    tenant_id: str,
    user_id: str,
    background_tasks: BackgroundTasks
):
    """Create a digital signature request using Langroid agent"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        # Create temporary signature agent
        agent_id = await agent_service.create_agent(
            agent_type="digital_signature",
            tenant_id=tenant_id,
            user_id=user_id,
            configuration={}
        )
        
        async def generate_response():
            try:
                async for event in agent_service.execute_agent_task(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    task_type="create_signature_request",
                    parameters=config.dict(),
                    context={"user_id": user_id}
                ):
                    yield f"data: {json.dumps(event.dict())}\n\n"
                    
            finally:
                # Clean up agent in background
                background_tasks.add_task(
                    agent_service.delete_agent, agent_id, tenant_id
                )
        
        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Error creating signature request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signature-agent/status/{request_id}")
async def get_signature_status(request_id: str, tenant_id: str, user_id: str):
    """Get signature request status using Langroid agent"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        # Create temporary signature agent
        agent_id = await agent_service.create_agent(
            agent_type="digital_signature",
            tenant_id=tenant_id,
            user_id=user_id,
            configuration={}
        )
        
        async def generate_response():
            try:
                async for event in agent_service.execute_agent_task(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    task_type="get_signature_status",
                    parameters={"request_id": request_id},
                    context={"user_id": user_id}
                ):
                    yield f"data: {json.dumps(event.dict())}\n\n"
                    
            finally:
                # Clean up agent
                await agent_service.delete_agent(agent_id, tenant_id)
        
        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting signature status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================
# DOCUMENT PROCESSING
# =====================================

@app.post("/document/analyze")
async def analyze_document(
    document_content: str,
    analysis_type: str = "general",
    tenant_id: str = "",
    user_id: str = ""
):
    """Analyze document using Langroid agents"""
    global agent_service
    
    if not agent_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        # Create temporary document analyzer agent
        agent_id = await agent_service.create_agent(
            agent_type="document_analyzer",
            tenant_id=tenant_id,
            user_id=user_id,
            configuration={"analysis_type": analysis_type}
        )
        
        async def generate_response():
            try:
                async for event in agent_service.execute_agent_task(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    task_type="analyze_document",
                    parameters={
                        "document_content": document_content,
                        "analysis_type": analysis_type
                    },
                    context={"user_id": user_id}
                ):
                    yield f"data: {json.dumps(event.dict())}\n\n"
                    
            finally:
                # Clean up agent
                await agent_service.delete_agent(agent_id, tenant_id)
        
        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Error analyzing document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)