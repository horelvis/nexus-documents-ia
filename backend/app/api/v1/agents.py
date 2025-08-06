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

from app.api.async_dependencies import get_current_active_user_async, get_current_active_superuser_async, require_agent_permission_async
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
async def check_cag_health():
    """Check connectivity with CAG service"""
    try:
        headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.CAG_SERVICE_URL}/health", headers=headers)
            response.raise_for_status()
            health_data = response.json()
            
        return {
            "status": "healthy",
            "cag_service": health_data,
            "integration": "working"
        }
    except Exception as e:
        logger.error(f"CAG health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"CAG service unavailable: {str(e)}"
        )

@router.get("/status")
async def get_service_status():
    """Get service health status from CAG"""
    try:
        # Check CAG service health
        cag_health = {"status": "unknown"}
        try:
            headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.CAG_SERVICE_URL}/health", headers=headers)
                if response.status_code == 200:
                    cag_health = response.json()
        except Exception as e:
            logger.warning(f"CAG health check failed: {e}")
        
        # Determine overall status
        overall_status = "operational"
        if cag_health.get("status") != "healthy":
            overall_status = "degraded"
        
        return {
            "service": "agents",
            "cag_health": cag_health,
            "status": overall_status,
            "system_resources": {
                "cpu_percent": 25.0,  # Mock data for now
                "memory_percent": 45.0,
                "disk_percent": 60.0
            }
        }
    except Exception as e:
        logger.error(f"Error getting service status: {str(e)}")
        # Return degraded status instead of error
        return {
            "service": "agents",
            "status": "degraded",
            "error": str(e),
            "cag_health": {"status": "unknown"},
            "system_resources": {
                "cpu_percent": 0,
                "memory_percent": 0,
                "disk_percent": 0
            }
        }

# =====================================
# AGENT TYPES AND LISTING
# =====================================

@router.get("/types")
async def list_agent_types():
    """List available agent types - CAG-based agents"""
    try:
        # Define CAG-based agent types
        agent_types = {
            "document_analyzer": {
                "name": "Document Analyzer",
                "description": "Analyzes and categorizes documents using CAG",
                "capabilities": ["classification", "extraction", "analysis", "summarization"],
                "source": "cag"
            },
            "rag_assistant": {
                "name": "RAG Assistant",
                "description": "CAG-powered retrieval and Q&A",
                "capabilities": ["search", "qa", "context_retrieval", "multi-turn_conversation"],
                "source": "cag"
            },
            "digital_signature": {
                "name": "Digital Signature Agent",
                "description": "Manages signature workflows",
                "capabilities": ["signature_management", "tracking", "validation"],
                "source": "cag"
            },
            "legal_compliance": {
                "name": "Legal Compliance Agent",
                "description": "Validates legal requirements and compliance",
                "capabilities": ["compliance_check", "risk_assessment", "regulatory_validation"],
                "source": "cag"
            },
            "financial_analysis": {
                "name": "Financial Analysis Agent",
                "description": "Analyzes financial documents and metrics",
                "capabilities": ["financial_metrics", "trend_analysis", "reporting"],
                "source": "cag"
            },
            "contract_analyzer": {
                "name": "Contract Analyzer",
                "description": "Analyzes contracts and legal agreements",
                "capabilities": ["clause_extraction", "risk_identification", "comparison"],
                "source": "cag"
            }
        }
        
        return {"available_types": agent_types, "total": len(agent_types)}
        
    except Exception as e:
        logger.error(f"Error listing agent types: {str(e)}")
        # Return default CAG agents even if there's an error
        return {
            "available_types": {
                "document_analyzer": {
                    "name": "Document Analyzer",
                    "description": "Analyzes and categorizes documents using CAG",
                    "capabilities": ["classification", "extraction", "analysis"],
                    "source": "cag"
                },
                "rag_assistant": {
                    "name": "RAG Assistant",
                    "description": "CAG-powered retrieval and Q&A",
                    "capabilities": ["search", "qa", "context_retrieval"],
                    "source": "cag"
                }
            },
            "total": 2
        }

@router.get("/list")
async def list_agents(current_user: User = Depends(get_current_active_user_async)):
    """List available agents/graphs for the tenant"""
    # Since LangGraph doesn't persist agents, return available types
    return await list_agent_types()

# =====================================
# DOCUMENT ANALYSIS
# =====================================

@router.post("/document/analyze")
async def analyze_document(
    request: DocumentAnalysisRequest,
    current_user: User = Depends(get_current_active_user_async)
):
    """Analyze document using LangGraph document analysis workflow"""
    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                # Use CAG service for document analysis
                analysis_request = {
                    "document_content": request.document_content,
                    "document_id": request.document_id or "temp-doc",
                    "tenant_id": str(current_user.tenant_id),
                    "user_id": str(current_user.id),
                    "analysis_type": request.analysis_type
                }
                
                headers = {
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": str(current_user.tenant_id),
                    "X-User-ID": str(current_user.id)
                }
                
                # Use streaming CAG endpoint
                async with client.stream(
                    "POST",
                    f"{settings.CAG_SERVICE_URL}/api/v1/cag/analyze/stream",
                    json=analysis_request,
                    headers=headers,
                    timeout=120.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            
                            try:
                                event = json.loads(data_str)
                                
                                # Transform CAG events to expected format
                                if event["type"] == "result":
                                    # Transform to document analysis result
                                    result = {
                                        "type": "result",
                                        "content": {
                                            "document_type": event["content"].get("analysis_type", "general"),
                                            "is_signable": False,
                                            "required_agents": ["document_analyzer"],
                                            "confidence": event["content"].get("quality_score", 0.85),
                                            "execution_type": "cag",
                                            "analysis": {
                                                "summary": event["content"].get("analysis", ""),
                                                "quality_score": event["content"].get("quality_score", 0),
                                                "execution_time": event["content"].get("execution_time", 0)
                                            },
                                            "recommendations": [],
                                            "action_items": [],
                                            "extracted_data": {},
                                            "compliance_status": {},
                                            "risk_assessment": {},
                                            "analysis_timestamp": datetime.utcnow().isoformat()
                                        }
                                    }
                                    yield f"data: {json.dumps(result)}\n\n"
                                else:
                                    # Pass through other events (progress, error)
                                    yield f"data: {json.dumps(event)}\n\n"
                                    
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data: {data_str}")
                    
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
    current_user: User = Depends(get_current_active_user_async)
):
    """Chat using RAG or conversational graphs"""
    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                # Use CAG service for chat
                query_request = {
                    "query": request.message,
                    "tenant_id": str(current_user.tenant_id),
                    "user_id": str(current_user.id),
                    "context": request.context or {}
                }
                
                headers = {
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": str(current_user.tenant_id),
                    "X-User-ID": str(current_user.id)
                }
                
                # Use streaming CAG endpoint
                async with client.stream(
                    "POST",
                    f"{settings.CAG_SERVICE_URL}/api/v1/cag/query/stream",
                    json=query_request,
                    headers=headers,
                    timeout=60.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            
                            try:
                                event = json.loads(data_str)
                                
                                # Transform CAG events for chat
                                if event["type"] == "result":
                                    # Transform to chat response
                                    response_event = {
                                        "type": "response",
                                        "content": event["content"].get("answer", ""),
                                        "quality_score": event["content"].get("quality_score", 0),
                                        "iterations": event["content"].get("iterations", 0)
                                    }
                                    yield f"data: {json.dumps(response_event)}\n\n"
                                else:
                                    # Pass through other events (progress, error)
                                    yield f"data: {json.dumps(event)}\n\n"
                                    
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data: {data_str}")
                            
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
    current_user: User = Depends(get_current_active_user_async)
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
    current_user: User = Depends(get_current_active_user_async)
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
    current_user: User = Depends(require_agent_permission_async)
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
    current_user: User = Depends(get_current_active_user_async)
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
    current_user: User = Depends(get_current_active_user_async)
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
    current_user: User = Depends(get_current_active_user_async)
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
    current_user: User = Depends(get_current_active_user_async)
):
    """Get recent agent activity"""
    # Would need to implement activity tracking in LangGraph
    return {
        "activities": [],
        "total": 0,
        "tenant_id": str(current_user.tenant_id),
        "message": "Activity tracking available through graph execution history"
    }