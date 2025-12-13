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
        # Use configured service URL (now served by weaviate-service)
        self.base_url = settings.CAG_SERVICE_URL.rstrip("/")
        self.timeout = httpx.Timeout(30.0, connect=5.0)
        self.api_key = settings.MICROSERVICES_API_KEY
        self.default_model = (
            settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.OLLAMA_MODEL
        )

    async def query(
        self,
        *,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_iterations: int = 4,
    ) -> Dict[str, Any]:
        """Execute a generic /api/v1/cag/query call."""
        payload_context = context.copy() if context else {}
        payload = {
            "query": query,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "context": payload_context,
            "model": model or self.default_model,
            "temperature": temperature,
            "max_iterations": max_iterations,
        }

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/cag/query",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            logger.error("CAG query HTTP error: %s", exc)
            return {"success": False, "error": str(exc)}

        if response.status_code != 200:
            logger.error("CAG query failed: %s - %s", response.status_code, response.text)
            return {
                "success": False,
                "error": f"CAG service error: {response.status_code}",
                "status_code": response.status_code,
            }

        result = response.json()
        metadata = result.get("metadata") or {}
        metadata.setdefault("engine", "elysia")
        result["metadata"] = metadata
        return result
        
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
            llm_model = (
                settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.OLLAMA_MODEL
            )
            tenant_id = context.get("tenant_id") or settings.DEFAULT_TENANT
            user_id = context.get("user_id") or "virtual_assistant"
            agent_context = {
                "conversation_id": context.get("conversation_id"),
                "message_history": context.get("message_history", []),
                "working_memory": context.get("working_memory", {}),
                "is_welcome": context.get("is_welcome", False),
                "agent_type": agent_type,
                "tools": tools
                or [
                    "search_documents",
                    "analyze_document",
                    "get_statistics",
                    "extract_entities",
                ],
            }

            result = await self.query(
                query=message,
                tenant_id=tenant_id,
                user_id=user_id,
                context=agent_context,
                model=llm_model,
                temperature=0.7,
                max_iterations=5,
            )

            metadata = result.get("metadata", {}) or {}
            documents = metadata.get("documents", [])
            decision_path = metadata.get("decision_path", [])
            tools_used = metadata.get("tools_used", [])
            cag_success = result.get("success", False)
            cag_error = result.get("error")

            if not cag_success or cag_error:
                logger.warning("CAG reported failure: %s", cag_error)
                return {
                    "error": cag_error or "CAG processing failed",
                    "fallback": True,
                    "response": None,
                    "metadata": metadata,
                }

            return {
                "response": result.get("response") or result.get("answer", ""),
                "success": True,
                "quality_score": result.get("quality_score", 0),
                "confidence": result.get("confidence", 0.7),
                "iterations": result.get("iterations", 1),
                "context_chunks_used": result.get("context_chunks_used", 0),
                "tools_used": tools_used,
                "decision_path": decision_path,
                "reasoning_steps": result.get("iterations", 1),
                "suggestions": result.get("suggestions", []),
                "metadata": metadata,
                "documents": documents,
                "engine": metadata.get("engine"),
                "agents_used": metadata.get("agents_used", []),
                "error": None,
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
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of CAG service"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={"X-API-Key": self.api_key}
                )
                
                if response.status_code == 200:
                    return {"status": "healthy", "service": "cag"}
                else:
                    return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"CAG health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    async def search_documents(self, search_request: Dict[str, Any]) -> Dict[str, Any]:
        """Search documents using CAG service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/cag/search",
                    json=search_request,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"CAG search error: {response.status_code}")
                    return {"error": f"Search failed: {response.status_code}", "results": []}
                    
        except Exception as e:
            logger.error(f"CAG search error: {e}")
            return {"error": str(e), "results": []}
    
    async def add_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add document to CAG service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/cag/documents",
                    json=document_data,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"CAG add document error: {response.status_code}")
                    raise Exception(f"Failed to add document: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"CAG add document error: {e}")
            raise


# Global client instance
cag_client = CAGClient()
