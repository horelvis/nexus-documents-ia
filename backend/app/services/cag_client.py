"""
CAG (Corrective Agent Generation) Service Client
Real agent-based processing for the virtual assistant
"""
import logging
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError

logger = logging.getLogger(__name__)


class CAGClient(BaseHTTPClient):
    """Client for interacting with the CAG microservice"""
    
    def __init__(self):
        # Use configured service URL (now served by weaviate-service)
        base_url = settings.CAG_SERVICE_URL.rstrip("/")
        super().__init__(
            service_name="cag",
            base_url=base_url,
            timeout_type="ai",
        )
        self.default_model = settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.SGLANG_MODEL

    async def query(
        self,
        *,
        query: str,
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
            "user_id": str(user_id),
            "context": payload_context,
            "model": model or self.default_model,
            "temperature": temperature,
            "max_iterations": max_iterations,
        }

        try:
            result = await self.post_json(
                "/api/v1/cag/query",
                json=payload,
                user_id=str(user_id),
            )
        except HTTPClientError as exc:
            logger.error("CAG query upstream error: %s", exc)
            return {"success": False, "error": exc.message, "status_code": exc.status_code}

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
            llm_model = settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.SGLANG_MODEL
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

        except HTTPClientError as exc:
            logger.error("CAG client upstream error: %s", exc)
            return {
                "error": exc.message,
                "fallback": True,
                "response": "El servicio de agentes no está disponible ahora mismo.",
            }
        except Exception as exc:
            logger.error("CAG client error: %s", exc)
            return {
                "error": str(exc),
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
            request_data = {"tool": tool_name, "parameters": parameters, "context": context}
            return await self.post_json("/api/v1/tools/execute", json=request_data)
        except HTTPClientError as exc:
            logger.error("Tool execution upstream error: %s", exc)
            return {"error": exc.message, "status_code": exc.status_code}
        except Exception as exc:
            logger.error("Tool execution error: %s", exc)
            return {"error": str(exc)}
    
    async def get_agent_capabilities(self) -> Dict[str, Any]:
        """Get available agent capabilities and tools"""
        try:
            response = await self.get("/api/v1/cag/health")
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "capabilities": [
                        "document_analysis",
                        "query_processing",
                        "embeddings_generation",
                        "contextual_search",
                        "agent_reasoning",
                    ],
                    "tools": [
                        "search_documents",
                        "analyze_document",
                        "extract_entities",
                        "generate_summary",
                    ],
                }
            return {"error": f"Service unhealthy: {response.status_code}"}
        except HTTPClientError as exc:
            logger.error("Error checking CAG service: %s", exc)
            return {"error": exc.message}
        except Exception as exc:
            logger.error("Error checking CAG service: %s", exc)
            return {"error": str(exc)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of CAG service"""
        try:
            response = await self.get("/health", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy", "service": "cag"}
            return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except HTTPClientError as exc:
            logger.error("CAG health check failed: %s", exc)
            return {"status": "unhealthy", "error": exc.message}
        except Exception as exc:
            logger.error("CAG health check failed: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}
    
    async def search_documents(self, search_request: Dict[str, Any]) -> Dict[str, Any]:
        """Search documents using CAG service"""
        try:
            return await self.post_json("/api/v1/cag/search", json=search_request)
        except HTTPClientError as exc:
            logger.error("CAG search error: %s", exc)
            return {"error": exc.message, "results": []}
        except Exception as exc:
            logger.error("CAG search error: %s", exc)
            return {"error": str(exc), "results": []}
    
    async def add_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add document to CAG service"""
        try:
            return await self.post_json("/api/v1/cag/documents", json=document_data)
        except HTTPClientError as exc:
            logger.error("CAG add document error: %s", exc)
            raise
        except Exception as exc:
            logger.error("CAG add document error: %s", exc)
            raise


# Global client instance
cag_client = CAGClient()
