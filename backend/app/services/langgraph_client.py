"""
LangGraph Client Service - Interface to communicate with LangGraph microservice
Provides state-based graph workflows with enhanced capabilities over LangChain
"""
import asyncio
import logging
import httpx
from typing import List, Dict, Any, Optional, AsyncGenerator
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.core.config import settings

logger = logging.getLogger(__name__)


# Helper function to determine if an exception should be retried
def should_retry_exception(exception: BaseException) -> bool:
    if isinstance(exception, (httpx.NetworkError, httpx.TimeoutException)):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code >= 500  # Retry on 5xx errors
    return False


class LangGraphClient:
    """Client for LangGraph microservice with state-based workflows"""

    def __init__(self, http_client: httpx.AsyncClient, tenant_id: str = None, user_id: str = None):
        self.http_client = http_client
        self.base_url = getattr(settings, 'LANGGRAPH_SERVICE_URL', 'http://langgraph-service:8007')
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.api_key = getattr(settings, 'LANGGRAPH_API_KEY', 'langgraph-secret-key-12345')
    
    def _get_auth_headers(self, tenant_id: str = None, user_id: str = None) -> dict:
        """Get authentication headers for microservice requests"""
        headers = {
            "X-API-Key": self.api_key,
            "X-Tenant-ID": tenant_id or self.tenant_id or getattr(settings, 'DEFAULT_TENANT', 'default')
        }
        
        user_id_to_use = user_id or self.user_id
        if user_id_to_use:
            headers["X-User-ID"] = user_id_to_use
            
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(should_retry_exception)
    )
    async def run_graph(
        self,
        graph_type: str,
        input_data: Dict[str, Any],
        tenant_id: str = None,
        user_id: str = None,
        config: Dict[str, Any] = None,
        thread_id: str = None,
        checkpoint_id: str = None
    ) -> Dict[str, Any]:
        """
        Run a graph to completion
        
        Args:
            graph_type: Type of graph to run (tag_generation, document_processing, rag)
            input_data: Input data for the graph
            tenant_id: Tenant ID for multi-tenancy
            user_id: User ID for tracking
            config: Additional configuration for graph execution
            thread_id: Thread ID for conversation continuity
            checkpoint_id: Resume from specific checkpoint
            
        Returns:
            Graph execution result
        """
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            request_data = {
                "graph_type": graph_type,
                "input_data": input_data,
                "tenant_id": tenant_id or self.tenant_id,
                "config": config or {},
                "mode": "run"
            }
            
            if user_id:
                request_data["user_id"] = user_id
            if thread_id:
                request_data["thread_id"] = thread_id
            if checkpoint_id:
                request_data["checkpoint_id"] = checkpoint_id
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/graphs/run",
                json=request_data,
                headers=headers,
                timeout=60.0  # Longer timeout for graph execution
            )
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "failed":
                raise Exception(f"Graph execution failed: {result.get('error', 'Unknown error')}")
                
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error running graph: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error running graph {graph_type}: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(should_retry_exception)
    )
    async def generate_tags(
        self,
        text: str,
        max_tags: int = 5,
        tag_type: str = "general",
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Generate tags from text using LangGraph
        
        Args:
            text: Text to generate tags from
            max_tags: Maximum number of tags to generate
            tag_type: Type of tags (general, technical, business)
            tenant_id: Tenant ID
            user_id: User ID
            
        Returns:
            Dictionary with tags, confidence scores, and reasoning
        """
        input_data = {
            "text": text,
            "max_tags": max_tags,
            "tag_type": tag_type
        }
        
        result = await self.run_graph(
            graph_type="tag_generation",
            input_data=input_data,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        return result.get("result", {})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(should_retry_exception)
    )
    async def process_document(
        self,
        document_id: str,
        content: str,
        filename: str,
        tenant_id: str = None,
        user_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process document with intelligent chunking and quality checks
        
        Args:
            document_id: Unique document identifier
            content: Document content
            filename: Document filename
            tenant_id: Tenant ID
            user_id: User ID
            metadata: Additional metadata
            
        Returns:
            Processing result with chunks and metadata
        """
        input_data = {
            "document_id": document_id,
            "content": content,
            "filename": filename,
            "tenant_id": tenant_id or self.tenant_id,
            "user_id": user_id,
            "metadata": metadata or {}
        }
        
        result = await self.run_graph(
            graph_type="document_processing",
            input_data=input_data,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        return result.get("result", {})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(should_retry_exception)
    )
    async def rag_query(
        self,
        query: str,
        tenant_id: str = None,
        user_id: str = None,
        max_results: int = 5,
        filters: Dict[str, Any] = None,
        include_sources: bool = True
    ) -> Dict[str, Any]:
        """
        Execute RAG query with enhanced search and generation
        
        Args:
            query: User query
            tenant_id: Tenant ID
            user_id: User ID
            max_results: Maximum search results
            filters: Search filters
            include_sources: Include source documents
            
        Returns:
            Answer with sources and confidence
        """
        input_data = {
            "query": query,
            "tenant_id": tenant_id or self.tenant_id,
            "user_id": user_id,
            "max_results": max_results,
            "filters": filters or {},
            "include_sources": include_sources
        }
        
        result = await self.run_graph(
            graph_type="rag",
            input_data=input_data,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        return result.get("result", {})

    async def stream_graph(
        self,
        graph_type: str,
        input_data: Dict[str, Any],
        tenant_id: str = None,
        user_id: str = None,
        config: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream graph execution events
        
        Args:
            graph_type: Type of graph to run
            input_data: Input data for the graph
            tenant_id: Tenant ID
            user_id: User ID
            config: Additional configuration
            
        Yields:
            Stream events from graph execution
        """
        try:
            headers = self._get_auth_headers(tenant_id, user_id)
            
            request_data = {
                "graph_type": graph_type,
                "input_data": input_data,
                "tenant_id": tenant_id or self.tenant_id,
                "config": config or {},
                "mode": "stream"
            }
            
            if user_id:
                request_data["user_id"] = user_id
            
            async with self.http_client.stream(
                "POST",
                f"{self.base_url}/api/v1/graphs/stream",
                json=request_data,
                headers=headers,
                timeout=60.0
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield {"event": "data", "data": line}
                        
        except Exception as e:
            logger.error(f"Error streaming graph {graph_type}: {str(e)}")
            yield {"event": "error", "data": str(e)}
    
    async def stream_graph_execution(
        self,
        request_data: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream graph execution events in a format compatible with SSE
        
        Args:
            request_data: Complete request including graph_type, input_data, tenant_id, etc.
            
        Yields:
            Events from graph execution
        """
        try:
            headers = self._get_auth_headers(
                request_data.get("tenant_id"), 
                request_data.get("user_id")
            )
            
            request_data["mode"] = "stream"
            
            async with self.http_client.stream(
                "POST",
                f"{self.base_url}/api/v1/graphs/stream",
                json=request_data,
                headers=headers,
                timeout=300.0  # 5 minutes for complex workflows
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line and line.startswith("data: "):
                        try:
                            import json
                            event_data = json.loads(line[6:])  # Skip "data: " prefix
                            yield event_data
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse event: {line}")
                            continue
                        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error streaming graph: {e.response.status_code} - {e.response.text}")
            yield {"type": "error", "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Error streaming graph execution: {str(e)}")
            yield {"type": "error", "error": str(e)}

    async def get_graph_types(self) -> List[str]:
        """Get list of available graph types"""
        try:
            headers = self._get_auth_headers()
            response = await self.http_client.get(
                f"{self.base_url}/api/v1/graphs/types",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting graph types: {str(e)}")
            return []

    async def get_graph_structure(self, graph_type: str) -> Dict[str, Any]:
        """Get structure of a specific graph type"""
        try:
            headers = self._get_auth_headers()
            response = await self.http_client.get(
                f"{self.base_url}/api/v1/graphs/structure/{graph_type}",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting graph structure: {str(e)}")
            return {}

    async def health_check(self) -> bool:
        """Check if LangGraph service is healthy"""
        try:
            response = await self.http_client.get(
                f"{self.base_url}/health",
                timeout=5.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("status") == "healthy"
        except Exception as e:
            logger.error(f"LangGraph health check failed: {str(e)}")
            return False