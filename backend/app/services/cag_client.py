"""
CAG (Corrective Agent Generation) Service Client
Real agent-based processing for the virtual assistant
"""
import logging
import httpx
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class CAGClient:
    """Client for interacting with the CAG microservice"""
    
    def __init__(self):
        # Use docker service name for container-to-container communication
        self.base_url = "http://docker-cag-service-1:8008"
        self.timeout = httpx.Timeout(30.0, connect=5.0)
        self.api_key = settings.MICROSERVICES_API_KEY
        
    async def process_with_agent(
        self,
        message: str,
        context: Dict[str, Any],
        agent_type: str = "virtual_assistant",
        tools: List[str] = None
    ) -> Dict[str, Any]:
        """
        Process a message using the CAG service with real agent capabilities
        
        Args:
            message: User message to process
            context: Context including user info, history, etc.
            agent_type: Type of agent to use
            tools: List of tools the agent can use
            
        Returns:
            Agent response with reasoning, actions, and final answer
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Use the query endpoint for conversational interactions
                request_data = {
                    "query": message,
                    "tenant_id": context.get("tenant_id"),
                    "user_id": context.get("user_id"),
                    "context": {
                        "conversation_id": context.get("conversation_id"),
                        "message_history": context.get("message_history", []),
                        "working_memory": context.get("working_memory", {}),
                        "is_welcome": context.get("is_welcome", False),  # Pass welcome flag directly
                        "agent_type": agent_type,
                        "tools": tools or [
                            "search_documents",
                            "analyze_document", 
                            "get_statistics",
                            "extract_entities"
                        ]
                    },
                    "model": "gemma3:12b-it-qat",
                    "temperature": 0.7,
                    "max_iterations": 5
                }
                
                # Call CAG service query endpoint for conversational processing
                response = await client.post(
                    f"{self.base_url}/api/v1/cag/query",
                    json=request_data,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Check if CAG actually failed even with HTTP 200
                    cag_success = result.get("success", False)
                    cag_error = result.get("error")
                    
                    if not cag_success or cag_error:
                        # CAG failed, return error to trigger fallback
                        logger.warning(f"CAG reported failure: {cag_error}")
                        return {
                            "error": cag_error or "CAG processing failed",
                            "fallback": True,
                            "response": None,
                            "metadata": result.get("metadata", {})
                        }
                    
                    # Transform successful CAG response to match expected format
                    return {
                        "response": result.get("response") or result.get("answer", ""),
                        "success": True,
                        "quality_score": result.get("quality_score", 0),
                        "confidence": result.get("confidence", 0.7),
                        "iterations": result.get("iterations", 1),
                        "context_chunks_used": result.get("context_chunks_used", 0),
                        "tools_used": result.get("tools_used", []),
                        "reasoning_steps": result.get("iterations", 1),
                        "suggestions": result.get("suggestions", []),
                        "metadata": result.get("metadata", {}),
                        "error": None  # Clear error for successful responses
                    }
                else:
                    logger.error(f"CAG service error: {response.status_code} - {response.text}")
                    return {
                        "error": f"CAG service error: {response.status_code}",
                        "fallback": True,
                        "response": "Lo siento, no pude procesar tu solicitud con el agente. Intentando método alternativo..."
                    }
                    
        except httpx.TimeoutException:
            logger.error("CAG service timeout")
            return {
                "error": "CAG service timeout",
                "fallback": True,
                "response": "El servicio está tardando más de lo esperado. Por favor, intenta de nuevo."
            }
        except Exception as e:
            logger.error(f"CAG client error: {e}")
            return {
                "error": str(e),
                "fallback": True,
                "response": "Error al conectar con el servicio de agentes."
            }
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a specific tool through the CAG service
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Execution context
            
        Returns:
            Tool execution results
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                request_data = {
                    "tool": tool_name,
                    "parameters": parameters,
                    "context": context
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/tools/execute",
                    json=request_data,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Tool execution error: {response.status_code}")
                    return {"error": f"Tool execution failed: {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"error": str(e)}
    
    async def get_agent_capabilities(self) -> Dict[str, Any]:
        """Get available agent capabilities and tools"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Use health endpoint to check if service is available
                response = await client.get(
                    f"{self.base_url}/api/v1/cag/health",
                    headers={"X-API-Key": self.api_key}
                )
                
                if response.status_code == 200:
                    # Return predefined capabilities since CAG doesn't have a capabilities endpoint
                    return {
                        "status": "healthy",
                        "capabilities": [
                            "document_analysis",
                            "query_processing",
                            "embeddings_generation",
                            "contextual_search",
                            "agent_reasoning"
                        ],
                        "tools": [
                            "search_documents",
                            "analyze_document",
                            "extract_entities",
                            "generate_summary"
                        ]
                    }
                else:
                    return {"error": f"Service unhealthy: {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"Error checking CAG service: {e}")
            return {"error": str(e)}