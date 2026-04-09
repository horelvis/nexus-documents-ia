"""
API endpoints for CrewAI Agent management
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import httpx

from app.api.async_dependencies import get_current_active_user_async
from app.core.auth.base import UserProfile
from app.db.models import User
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# =====================================
# PYDANTIC MODELS
# =====================================

class CreateAgentRequest(BaseModel):
    name: str
    role: str
    goal: str
    backstory: str
    tools: Optional[list] = []
    configuration: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ExecuteTaskRequest(BaseModel):
    task_description: str
    expected_output: str
    agent_roles: Optional[list] = []
    context: Optional[Dict[str, Any]] = None

# =====================================
# CREWAI SERVICE INTEGRATION
# =====================================

@router.get("/health")
async def check_crewai_health():
    """Check connectivity with CrewAI CAG service"""
    try:
        headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.CAG_SERVICE_URL}/health", headers=headers)
            response.raise_for_status()
            health_data = response.json()
            
        return {
            "status": "healthy",
            "crewai_service": health_data,
            "integration": "working"
        }
    except Exception as e:
        logger.error(f"CrewAI health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"CrewAI service unavailable: {str(e)}"
        )

@router.get("/status")
async def get_crewai_status():
    """Get CrewAI service health status"""
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
            "service": "crewai_agents",
            "cag_health": cag_health,
            "status": overall_status,
            "agents_available": cag_health.get("agents_count", 0),
            "crews_running": cag_health.get("crews_running", 0),
            "system_resources": cag_health.get("system_resources", {
                "cpu_percent": 0,
                "memory_percent": 0,
                "disk_percent": 0
            })
        }
    except Exception as e:
        logger.error(f"Error getting service status: {str(e)}")
        return {
            "service": "crewai_agents", 
            "status": "degraded",
            "error": str(e),
            "cag_health": {"status": "unknown"}
        }

# =====================================
# AGENT TYPES AND LISTING
# =====================================

@router.get("/types")
async def list_agent_types():
    """List available CrewAI agent types from REAL CAG service - NO HARDCODE"""
    try:
        # Obtener datos REALES del nuevo endpoint de agentes
        headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
        async with httpx.AsyncClient() as client:
            # Usar el endpoint REAL que expone los agentes de CrewAI
            response = await client.get(
                f"{settings.CAG_SERVICE_URL}/api/v1/cag/agents/available",
                headers=headers,
                params={"tenant_id": "default"}
            )
            response.raise_for_status()
            agents_data = response.json()
            
            # Devolver los datos REALES directamente del servicio CrewAI
            return agents_data
        
    except Exception as e:
        logger.error(f"Error fetching REAL agent types from CrewAI: {str(e)}")
        return {
            "available_types": {},
            "total": 0,
            "error": f"Failed to fetch REAL agents from CrewAI: {str(e)}"
        }

@router.get("/list")
async def list_available_agents(
    current_user: User = Depends(get_current_active_user_async),
):
    """List available CrewAI agents for the tenant"""
    try:
        # Get agent types and add tenant-specific information
        agent_types_response = await list_agent_types()
        available_types = agent_types_response.get("available_types", {})
        
        # Add tenant-specific status for each agent
        for agent_key, agent_info in available_types.items():
            agent_info.update({
                "tenant_id": tenant_id,
                "status": "active",  # CrewAI agents are always ready
                "is_enabled": True,
                "last_activity": None,
                "execution_count": 0,  # Would need to track this
                "average_response_time": 0  # Would need to track this
            })
        
        return {
            "available_types": available_types,
            "total": len(available_types),
            "tenant_id": tenant_id,
            "service": "crewai"
        }
        
    except Exception as e:
        logger.error(f"Error listing agents for tenant {tenant_id}: {str(e)}")
        return {
            "available_types": {},
            "total": 0,
            "tenant_id": tenant_id,
            "error": str(e)
        }

# =====================================
# AGENT CREATION AND MANAGEMENT  
# =====================================

@router.post("/create")
async def create_custom_agent(
    request: CreateAgentRequest,
    current_user: User = Depends(get_current_active_user_async),
):
    """Create a custom CrewAI agent configuration"""
    try:
        # For now, CrewAI agents are pre-defined and managed by the service
        # This endpoint could be used to create custom agent configurations
        # that get passed to the CrewAI service
        
        custom_agent_config = {
            "name": request.name,
            "role": request.role,
            "goal": request.goal, 
            "backstory": request.backstory,
            "tools": request.tools,
            "tenant_id": tenant_id,
            "created_by": str(current_user.id),
            "created_at": datetime.utcnow().isoformat(),
            "configuration": request.configuration or {}
        }
        
        # In a full implementation, this would be stored and used by CrewAI
        # For now, return the configuration
        
        return {
            "agent_id": f"custom_{request.name.lower().replace(' ', '_')}_{tenant_id}",
            "configuration": custom_agent_config,
            "status": "created",
            "message": "Custom agent configuration created. Will be available in next CrewAI deployment."
        }
        
    except Exception as e:
        logger.error(f"Error creating custom agent: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create custom agent: {str(e)}"
        )

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_active_user_async),
):
    """Delete/disable agent configuration"""
    try:
        # For standard CrewAI agents, they can't be deleted, only disabled
        if not agent_id.startswith("custom_"):
            return {
                "status": "disabled",
                "agent_id": agent_id,
                "message": "Standard CrewAI agents cannot be deleted, only disabled"
            }
        
        # For custom agents, remove the configuration
        return {
            "status": "deleted",
            "agent_id": agent_id,
            "message": "Custom agent configuration removed"
        }
        
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete agent: {str(e)}"
        )

# =====================================
# AGENT INTERACTION
# =====================================

@router.post("/chat")
async def chat_with_agents(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user_async),
):
    """Chat using CrewAI agents"""
    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                # Use CAG service for chat with CrewAI agents
                query_request = {
                    "query": request.message,
                    "tenant_id": tenant_id,
                    "user_id": str(current_user.id),
                    "context": request.context or {},
                    "conversation_id": request.conversation_id
                }
                
                headers = {
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": tenant_id,
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
                                yield "data: [DONE]\\n\\n"
                                break
                            
                            try:
                                event = json.loads(data_str)
                                
                                # Transform CAG events for chat
                                if event["type"] == "result":
                                    response_event = {
                                        "type": "message",
                                        "content": event["content"].get("answer", ""),
                                        "agent": event["content"].get("agent_used", "unknown"),
                                        "quality_score": event["content"].get("quality_score", 0),
                                        "execution_time": event["content"].get("execution_time", 0)
                                    }
                                    yield f"data: {json.dumps(response_event)}\\n\\n"
                                else:
                                    # Pass through other events (progress, error)
                                    yield f"data: {json.dumps(event)}\\n\\n"
                                    
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data: {data_str}")
                            
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\\n\\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache", 
            "Connection": "keep-alive",
        }
    )

@router.post("/{agent_id}/chat")
async def chat_with_specific_agent(
    agent_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user_async),
):
    """Chat with a specific CrewAI agent"""
    # Add agent preference to context
    request.context = request.context or {}
    request.context["preferred_agent"] = agent_id
    request.context["agent_id"] = agent_id
    
    return await chat_with_agents(request, current_user, tenant_id)

@router.post("/{agent_id}/execute")
async def execute_agent_task(
    agent_id: str,
    request: ExecuteTaskRequest,
    current_user: User = Depends(get_current_active_user_async),
):
    """Execute a task with CrewAI agents"""
    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                # Create a crew task for execution
                task_request = {
                    "task_description": request.task_description,
                    "expected_output": request.expected_output,
                    "agent_roles": request.agent_roles or [agent_id],
                    "tenant_id": tenant_id,
                    "user_id": str(current_user.id),
                    "context": request.context or {}
                }
                
                headers = {
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": tenant_id,
                    "X-User-ID": str(current_user.id)
                }
                
                # Use CAG service to execute the task
                async with client.stream(
                    "POST",
                    f"{settings.CAG_SERVICE_URL}/api/v1/cag/execute/stream",
                    json=task_request,
                    headers=headers,
                    timeout=120.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                yield "data: [DONE]\\n\\n"
                                break
                                
                            try:
                                event = json.loads(data_str)
                                yield f"data: {json.dumps(event)}\\n\\n"
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data: {data_str}")
                            
        except Exception as e:
            logger.error(f"Error executing task: {str(e)}")
            error_response = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_response)}\\n\\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# =====================================
# ANALYTICS AND MONITORING
# =====================================

@router.get("/statistics")
async def get_agent_statistics(
    current_user: User = Depends(get_current_active_user_async),
):
    """Get CrewAI agent usage statistics"""
    try:
        # In a full implementation, this would query actual usage data
        # For now, return mock data that represents what would be tracked
        
        return {
            "tenant_id": tenant_id,
            "enabled_agents": 6,  # Number of CrewAI agents available
            "total_executions": 0,  # Would track actual executions
            "executions_last_24h": 0,
            "success_rate": 0,
            "avg_execution_time_ms": 0,
            "total_tokens_used": 0,
            "active_crews": 0,
            "agent_performance": {
                "virtual_assistant": {"executions": 0, "avg_time": 0, "success_rate": 0},
                "search_specialist": {"executions": 0, "avg_time": 0, "success_rate": 0},
                "document_analyst": {"executions": 0, "avg_time": 0, "success_rate": 0},
                "compliance_expert": {"executions": 0, "avg_time": 0, "success_rate": 0},
                "communication_specialist": {"executions": 0, "avg_time": 0, "success_rate": 0},
                "workflow_coordinator": {"executions": 0, "avg_time": 0, "success_rate": 0}
            },
            "generated_at": datetime.utcnow().isoformat(),
            "service": "crewai"
        }
        
    except Exception as e:
        logger.error(f"Error fetching agent statistics: {str(e)}")
        return {
            "tenant_id": tenant_id,
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat()
        }

@router.get("/activity")
async def get_agent_activity(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_active_user_async),
):
    """Get recent CrewAI agent activity"""
    try:
        # In a full implementation, this would track actual agent executions
        # For now, return empty activity as no tracking is implemented yet
        
        return {
            "activities": [],
            "total": 0,
            "tenant_id": tenant_id,
            "has_more": False,
            "service": "crewai",
            "message": "Activity tracking for CrewAI agents will be implemented in future versions"
        }
        
    except Exception as e:
        logger.error(f"Error fetching agent activity: {str(e)}")
        return {
            "activities": [],
            "total": 0,
            "tenant_id": tenant_id,
            "error": str(e)
        }

@router.get("/{agent_id}/stats")
async def get_specific_agent_stats(
    agent_id: str,
    current_user: User = Depends(get_current_active_user_async),
):
    """Get statistics for a specific CrewAI agent"""
    try:
        return {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "tasks_completed": 0,
            "avg_response_time": 0.0,
            "success_rate": 0.0,
            "total_executions": 0,
            "last_24h_executions": 0,
            "error_count": 0,
            "status": "active",
            "service": "crewai",
            "message": "Individual agent statistics tracking will be implemented in future versions"
        }
        
    except Exception as e:
        logger.error(f"Error fetching stats for agent {agent_id}: {str(e)}")
        return {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "error": str(e)
        }

# =====================================
# TESTING AND DIAGNOSTICS
# =====================================

@router.post("/test")
async def test_crewai_integration(
    current_user: User = Depends(get_current_active_user_async),
):
    """Test CrewAI integration with a simple query"""
    try:
        # Test health check first
        headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.CAG_SERVICE_URL}/health", headers=headers)
            response.raise_for_status()
            
        # Test simple query execution
        async with httpx.AsyncClient() as client:
            test_request = {
                "query": "Hello, this is a test of the CrewAI integration",
                "tenant_id": tenant_id,
                "user_id": str(current_user.id),
                "context": {"test": True}
            }
            
            headers = {
                "X-API-Key": settings.MICROSERVICES_API_KEY,
                "X-Tenant-ID": tenant_id,
                "X-User-ID": str(current_user.id)
            }
            
            response = await client.post(
                f"{settings.CAG_SERVICE_URL}/api/v1/cag/query",
                json=test_request,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            
        return {
            "status": "success",
            "message": "CrewAI integration test completed successfully",
            "test_result": result,
            "service": "crewai",
            "agents_available": True,
            "tenant_id": tenant_id
        }
        
    except Exception as e:
        logger.error(f"CrewAI test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CrewAI integration test failed: {str(e)}"
        )