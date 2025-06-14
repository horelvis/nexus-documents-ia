"""
API endpoints for Agent management - Proxy to Langroid microservice
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from app.api.dependencies import get_current_active_user, require_subscription_permission, require_admin
from app.db.models import User
from app.services.langroid_client import langroid_client

logger = logging.getLogger(__name__)
router = APIRouter()

# =====================================
# PYDANTIC MODELS
# =====================================

class CreateAgentRequest(BaseModel):
    agent_type: str
    configuration: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ExecuteTaskRequest(BaseModel):
    task_type: str
    parameters: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None

class SignatureRequest(BaseModel):
    title: str
    document_name: str
    signers: list
    message: Optional[str] = None
    signature_type: str = "sequential"

class DocumentAnalysisRequest(BaseModel):
    document_content: str
    analysis_type: str = "general"

# =====================================
# HEALTH AND STATUS
# =====================================

@router.get("/health")
async def check_langroid_health():
    """Verificar conectividad con Langroid service"""
    try:
        health_status = await langroid_client.health_check()
        return {
            "status": "healthy",
            "langroid_service": health_status,
            "integration": "working"
        }
    except Exception as e:
        logger.error(f"Langroid health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Langroid service unavailable: {str(e)}"
        )

@router.get("/status")
async def get_service_status():
    """Obtener estado detallado del servicio Langroid"""
    try:
        service_status = await langroid_client.get_service_status()
        return service_status
    except Exception as e:
        logger.error(f"Error getting service status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service status unavailable: {str(e)}"
        )

# =====================================
# AGENT MANAGEMENT
# =====================================

@router.post("/create")
async def create_agent(
    request: CreateAgentRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Crear un nuevo agente en Langroid"""
    try:
        result = await langroid_client.create_agent(
            agent_type=request.agent_type,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            configuration=request.configuration or {}
        )
        return result
    except Exception as e:
        logger.error(f"Error creating agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating agent: {str(e)}"
        )

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Eliminar un agente en Langroid"""
    try:
        result = await langroid_client.delete_agent(
            agent_id=agent_id,
            tenant_id=str(current_user.tenant_id)
        )
        return result
    except Exception as e:
        logger.error(f"Error deleting agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting agent: {str(e)}"
        )

@router.get("/list")
async def list_agents(
    current_user: User = Depends(get_current_active_user)
):
    """Listar agentes del tenant"""
    try:
        result = await langroid_client.list_agents(
            tenant_id=str(current_user.tenant_id)
        )
        return result
    except Exception as e:
        logger.error(f"Error listing agents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing agents: {str(e)}"
        )

# =====================================
# AGENT INTERACTION
# =====================================

@router.post("/{agent_id}/chat")
async def chat_with_agent(
    agent_id: str,
    request: ChatRequest,
    current_user: User = Depends(require_subscription_permission("can_use_agents"))
):
    """Chat con un agente (streaming)"""
    async def event_stream():
        try:
            async for response in langroid_client.chat_with_agent(
                agent_id=agent_id,
                tenant_id=str(current_user.tenant_id),
                message=request.message,
                user_id=str(current_user.id),
                conversation_id=request.conversation_id,
                context=request.context or {}
            ):
                yield f"data: {json.dumps(response)}\n\n"
        except Exception as e:
            logger.error(f"Error in chat stream: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.post("/{agent_id}/execute")
async def execute_agent_task(
    agent_id: str,
    request: ExecuteTaskRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Ejecutar una tarea con un agente (streaming)"""
    async def event_stream():
        try:
            async for response in langroid_client.execute_agent_task(
                agent_id=agent_id,
                tenant_id=str(current_user.tenant_id),
                task_type=request.task_type,
                parameters=request.parameters,
                context=request.context or {}
            ):
                yield f"data: {json.dumps(response)}\n\n"
        except Exception as e:
            logger.error(f"Error in task execution stream: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# =====================================
# DIGITAL SIGNATURE
# =====================================

@router.post("/signature/create-request")
async def create_signature_request(
    request: SignatureRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Crear una solicitud de firma digital (streaming)"""
    async def event_stream():
        try:
            async for response in langroid_client.create_signature_request(
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id),
                title=request.title,
                document_name=request.document_name,
                signers=request.signers,
                message=request.message,
                signature_type=request.signature_type
            ):
                yield f"data: {json.dumps(response)}\n\n"
        except Exception as e:
            logger.error(f"Error in signature request stream: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.get("/signature/{request_id}/status")
async def get_signature_status(
    request_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Obtener estado de una solicitud de firma (streaming)"""
    async def event_stream():
        try:
            async for response in langroid_client.get_signature_status(
                request_id=request_id,
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id)
            ):
                yield f"data: {json.dumps(response)}\n\n"
        except Exception as e:
            logger.error(f"Error in signature status stream: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# =====================================
# DOCUMENT ANALYSIS
# =====================================

@router.post("/document/analyze")
async def analyze_document(
    request: DocumentAnalysisRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Analizar documento con agentes (streaming)"""
    async def event_stream():
        try:
            async for response in langroid_client.analyze_document(
                document_content=request.document_content,
                analysis_type=request.analysis_type,
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id)
            ):
                yield f"data: {json.dumps(response)}\n\n"
        except Exception as e:
            logger.error(f"Error in document analysis stream: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# =====================================
# TEST ENDPOINTS
# =====================================

@router.post("/import/langflow")
async def import_langflow_agent(
    langflow_data: Dict[str, Any],
    current_user: User = Depends(require_admin)
):
    """Import agent from Langflow JSON and save to agents directory"""
    import json
    from pathlib import Path
    
    try:
        # Validate it's a Langflow export
        if "data" not in langflow_data or "nodes" not in langflow_data.get("data", {}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Langflow export format"
            )
        
        # Get agent name
        agent_name = langflow_data.get("name", "unnamed_agent").replace(" ", "_").lower()
        
        # Save to agents directory (this would be mounted in production)
        agents_dir = Path("/app/agents")
        agents_dir.mkdir(exist_ok=True)
        
        # Save the JSON file
        agent_file = agents_dir / f"{agent_name}.json"
        with open(agent_file, 'w') as f:
            json.dump(langflow_data, f, indent=2)
        
        logger.info(f"Imported Langflow agent: {agent_name}")
        
        return {
            "status": "success",
            "message": f"Agent '{agent_name}' imported successfully",
            "agent_name": agent_name,
            "file_path": str(agent_file)
        }
        
    except Exception as e:
        logger.error(f"Error importing Langflow agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import agent: {str(e)}"
        )

@router.post("/test")
async def test_langroid_integration(
    current_user: User = Depends(get_current_active_user)
):
    """Probar integración completa con Langroid"""
    try:
        # Crear agente de prueba
        agent_result = await langroid_client.create_agent(
            agent_type="generic",
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            configuration={"test_mode": True}
        )
        
        agent_id = agent_result.get("agent_id")
        
        if not agent_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create test agent"
            )
        
        # Probar ejecución
        test_results = []
        async for response in langroid_client.execute_agent_task(
            agent_id=agent_id,
            tenant_id=str(current_user.tenant_id),
            task_type="test_task",
            parameters={"message": "Hello from integration test"},
            context={}
        ):
            test_results.append(response)
        
        # Limpiar agente
        await langroid_client.delete_agent(
            agent_id=agent_id,
            tenant_id=str(current_user.tenant_id)
        )
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "test_results": test_results,
            "message": "Langroid integration test completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Langroid test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Integration test failed: {str(e)}"
        )