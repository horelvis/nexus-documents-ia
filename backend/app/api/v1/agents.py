"""
API endpoints for Agent management - Proxy to LangGraph microservice
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import httpx

from app.api.dependencies import get_current_active_user, get_current_active_superuser, require_agent_permission
from app.db.models import User
from app.core.config import settings

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
    document_id: Optional[str] = None
    analysis_type: str = "general"

# =====================================
# HEALTH AND STATUS
# =====================================

@router.get("/health")
async def check_langgraph_health():
    """Check connectivity with LangGraph service"""
    try:
        headers = {"X-API-Key": settings.LANGGRAPH_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.LANGGRAPH_SERVICE_URL}/health", headers=headers)
            response.raise_for_status()
            health_data = response.json()
            
        return {
            "status": "healthy",
            "langgraph_service": health_data,
            "integration": "working"
        }
    except Exception as e:
        logger.error(f"LangGraph health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LangGraph service unavailable: {str(e)}"
        )

@router.get("/status")
async def get_service_status():
    """Get detailed service status from LangGraph"""
    try:
        headers = {"X-API-Key": settings.LANGGRAPH_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/status", headers=headers)
            response.raise_for_status()
            
        return response.json()
    except Exception as e:
        logger.error(f"Error getting service status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service status unavailable: {str(e)}"
        )

# =====================================
# AGENT TYPES AND LISTING
# =====================================

@router.get("/types")
async def list_agent_types():
    """List available agent types from LangGraph"""
    try:
        headers = {"X-API-Key": settings.LANGGRAPH_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/types", headers=headers)
            response.raise_for_status()
            
        graph_types = response.json()
        
        # Map LangGraph types to agent types
        agent_types = {
            "document_analyzer": {
                "name": "Document Analyzer",
                "description": "Analyzes and categorizes documents",
                "capabilities": ["classification", "extraction", "analysis"],
                "source": "langgraph"
            },
            "rag_assistant": {
                "name": "RAG Assistant",
                "description": "Retrieval-augmented generation for Q&A",
                "capabilities": ["search", "qa", "context_retrieval"],
                "source": "langgraph"
            },
            "digital_signature": {
                "name": "Digital Signature Agent",
                "description": "Manages signature workflows",
                "capabilities": ["signature_management", "tracking"],
                "source": "langgraph"
            }
        }
        
        # Add graph types as agent types
        for graph_type in graph_types.get("available_graphs", []):
            if graph_type not in agent_types:
                agent_types[graph_type] = {
                    "name": graph_type.replace("_", " ").title(),
                    "description": f"LangGraph {graph_type} workflow",
                    "capabilities": ["workflow", "automation"],
                    "source": "langgraph"
                }
        
        return {"available_types": agent_types, "total": len(agent_types)}
        
    except Exception as e:
        logger.error(f"Error listing agent types: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agent types: {str(e)}"
        )

@router.get("/list")
async def list_agents(current_user: User = Depends(get_current_active_user)):
    """List available agents/graphs for the tenant"""
    # Since LangGraph doesn't persist agents, return available types
    return await list_agent_types()

# =====================================
# DOCUMENT ANALYSIS
# =====================================

@router.post("/document/analyze")
async def analyze_document(
    request: DocumentAnalysisRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Analyze document using LangGraph document analysis workflow"""
    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                # Use document_analysis_crew graph
                stream_request = {
                    "graph_type": "document_analysis_crew",
                    "input_data": {
                        "document_id": request.document_id or "temp-doc",
                        "document_content": request.document_content,
                        "tenant_id": str(current_user.tenant_id),
                        "user_id": str(current_user.id)
                    },
                    "tenant_id": str(current_user.tenant_id),
                    "user_id": str(current_user.id),
                    "mode": "stream"
                }
                
                headers = {
                    "X-API-Key": getattr(settings, 'LANGGRAPH_API_KEY', 'langgraph-secret-key-12345'),
                    "X-Tenant-ID": str(current_user.tenant_id),
                    "X-User-ID": str(current_user.id)
                }
                
                # Stream from LangGraph
                async with client.stream(
                    "POST",
                    f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/stream",
                    json=stream_request,
                    headers=headers,
                    timeout=120.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                
                                # Transform LangGraph events to our format
                                if data.get("type") == "node_start":
                                    node_name = data.get("node", "")
                                    progress_map = {
                                        "classify_document": 20,
                                        "select_specialist_agents": 30,
                                        "extract_entities": 40,
                                        "execute_specialist_crew": 50,
                                        "analyze_compliance": 60,
                                        "synthesize_findings": 80,
                                        "generate_recommendations": 90
                                    }
                                    progress = progress_map.get(node_name, 50)
                                    
                                    yield f"data: {json.dumps({'type': 'progress', 'content': f'Processing: {node_name}', 'progress': progress})}\n\n"
                                
                                elif data.get("type") == "result":
                                    # Final result from LangGraph
                                    result_data = data.get("data", {})
                                    
                                    result = {
                                        "type": "result",
                                        "content": {
                                            "document_type": result_data.get("document_type", "general"),
                                            "is_signable": result_data.get("requires_signature", False),
                                            "required_agents": result_data.get("agents_used", ["document_analyzer"]),
                                            "confidence": result_data.get("confidence_scores", {}).get("overall", 0.85),
                                            "execution_type": "sequential",
                                            "analysis": result_data.get("analysis", {}),
                                            "recommendations": result_data.get("recommendations", []),
                                            "action_items": result_data.get("action_items", []),
                                            "extracted_data": result_data.get("extracted_data", {}),
                                            "compliance_status": result_data.get("compliance_status", {}),
                                            "risk_assessment": result_data.get("risk_assessment", {}),
                                            "analysis_timestamp": datetime.utcnow().isoformat()
                                        }
                                    }
                                    
                                    yield f"data: {json.dumps(result)}\n\n"
                                
                                else:
                                    # Pass through other events
                                    yield f"data: {json.dumps(data)}\n\n"
                                    
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data: {line}")
                    
                    yield f"data: [DONE]\n\n"
                    
        except Exception as e:
            logger.error(f"Error in document analysis: {str(e)}")
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
# AGENT INTERACTION (Chat/Execute)
# =====================================

@router.post("/chat")
async def chat_with_agent(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Chat using RAG or conversational graphs"""
    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                # Use RAG graph for chat
                stream_request = {
                    "graph_type": "rag",
                    "input_data": {
                        "question": request.message,
                        "conversation_id": request.conversation_id,
                        "context": request.context or {}
                    },
                    "tenant_id": str(current_user.tenant_id),
                    "user_id": str(current_user.id),
                    "mode": "stream"
                }
                
                headers = {
                    "X-API-Key": getattr(settings, 'LANGGRAPH_API_KEY', 'langgraph-secret-key-12345'),
                    "X-Tenant-ID": str(current_user.tenant_id),
                    "X-User-ID": str(current_user.id)
                }
                
                async with client.stream(
                    "POST",
                    f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/stream",
                    json=stream_request,
                    headers=headers,
                    timeout=60.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            yield line + "\n\n"
                            
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
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
# BACKWARD COMPATIBILITY
# =====================================

@router.post("/create")
async def create_agent(
    request: CreateAgentRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Create agent - for backward compatibility"""
    # LangGraph doesn't create persistent agents, return mock response
    return {
        "agent_id": f"{request.agent_type}_{current_user.tenant_id}",
        "agent_type": request.agent_type,
        "status": "created",
        "tenant_id": str(current_user.tenant_id),
        "message": "Using LangGraph workflows - agents are created on-demand"
    }

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete agent - for backward compatibility"""
    return {
        "status": "deleted",
        "agent_id": agent_id,
        "message": "LangGraph workflows are stateless - nothing to delete"
    }

@router.post("/{agent_id}/chat")
async def chat_with_specific_agent(
    agent_id: str,
    request: ChatRequest,
    current_user: User = Depends(require_agent_permission)
):
    """Chat with specific agent - routes to appropriate graph"""
    # Map agent IDs to graph types
    graph_mapping = {
        "document_analyzer": "document_analysis_crew",
        "rag_assistant": "rag",
        "digital_signature": "document_processing"
    }
    
    graph_type = graph_mapping.get(agent_id.split("_")[0], "rag")
    
    # Redirect to general chat with appropriate graph
    request.context = request.context or {}
    request.context["graph_type"] = graph_type
    request.context["agent_id"] = agent_id
    
    return await chat_with_agent(request, current_user)

@router.post("/{agent_id}/execute")
async def execute_agent_task(
    agent_id: str,
    request: ExecuteTaskRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Execute task with agent - uses appropriate graph"""
    async def event_stream():
        try:
            # Map task types to graphs
            graph_mapping = {
                "analyze_document": "document_analysis_crew",
                "answer_question": "rag",
                "process_document": "document_processing",
                "multi_agent_task": "multi_agent_workflow"
            }
            
            graph_type = graph_mapping.get(request.task_type, "document_processing")
            
            async with httpx.AsyncClient() as client:
                stream_request = {
                    "graph_type": graph_type,
                    "input_data": {
                        **request.parameters,
                        "task_type": request.task_type,
                        "context": request.context or {}
                    },
                    "tenant_id": str(current_user.tenant_id),
                    "user_id": str(current_user.id),
                    "mode": "stream"
                }
                
                headers = {
                    "X-API-Key": getattr(settings, 'LANGGRAPH_API_KEY', 'langgraph-secret-key-12345'),
                    "X-Tenant-ID": str(current_user.tenant_id),
                    "X-User-ID": str(current_user.id)
                }
                
                async with client.stream(
                    "POST",
                    f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/stream",
                    json=stream_request,
                    headers=headers,
                    timeout=120.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            yield line + "\n\n"
                            
        except Exception as e:
            logger.error(f"Error executing task: {str(e)}")
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

@router.post("/test")
async def test_agent_integration(
    current_user: User = Depends(get_current_active_user)
):
    """Test LangGraph integration"""
    try:
        # Test health check
        headers = {"X-API-Key": settings.LANGGRAPH_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.LANGGRAPH_SERVICE_URL}/health", headers=headers)
            response.raise_for_status()
            
        # Test simple graph execution
        async with httpx.AsyncClient() as client:
            test_request = {
                "graph_type": "tag_generation",
                "input_data": {
                    "content": "Test document for integration testing"
                },
                "tenant_id": str(current_user.tenant_id),
                "user_id": str(current_user.id),
                "mode": "run"
            }
            
            headers = {
                "X-API-Key": getattr(settings, 'LANGGRAPH_API_KEY', 'langgraph-secret-key-12345'),
                "X-Tenant-ID": str(current_user.tenant_id),
                "X-User-ID": str(current_user.id)
            }
            
            response = await client.post(
                f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/run",
                json=test_request,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            
        return {
            "status": "success",
            "message": "LangGraph integration test completed successfully",
            "test_result": result,
            "service": "langgraph"
        }
        
    except Exception as e:
        logger.error(f"LangGraph test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Integration test failed: {str(e)}"
        )

# =====================================
# AGENT STATISTICS & ACTIVITY
# =====================================

@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get statistics for a specific agent/graph"""
    # LangGraph doesn't track persistent stats, return placeholder
    return {
        "agent_id": agent_id,
        "tasks_completed": 0,
        "avg_response_time": 0.0,
        "success_rate": 0.0,
        "total_executions": 0,
        "last_24h_executions": 0,
        "error_count": 0,
        "avg_execution_time": 0.0,
        "created_at": datetime.utcnow().isoformat(),
        "last_activity": None,
        "message": "Statistics tracked at graph execution level"
    }

@router.get("/activity")
async def get_agent_activity(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_active_user)
):
    """Get recent agent activity"""
    # Would need to implement activity tracking in LangGraph
    return {
        "activities": [],
        "total": 0,
        "tenant_id": str(current_user.tenant_id),
        "message": "Activity tracking available through graph execution history"
    }