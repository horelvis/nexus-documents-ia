"""
Langroid Client Service - Interface to communicate with Langroid microservice
"""
import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, AsyncGenerator
from uuid import UUID
import httpx
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class LangroidClient:
    """Client for communicating with Langroid microservice"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'LANGROID_SERVICE_URL', 'http://langroid-service:8002')
        self.timeout = 60.0
        self.http_client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.http_client:
            await self.http_client.aclose()
    
    def _get_headers(self, tenant_id: str, user_id: str) -> Dict[str, str]:
        """Get headers for requests"""
        return {
            "X-Tenant-ID": str(tenant_id),
            "X-User-ID": str(user_id),
            "Content-Type": "application/json"
        }
    
    # =====================================
    # AGENT MANAGEMENT
    # =====================================
    
    async def create_agent(
        self,
        agent_type: str,
        tenant_id: UUID,
        user_id: UUID,
        configuration: Dict[str, Any] = None
    ) -> str:
        """Create a new Langroid agent"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "agent_type": agent_type,
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "configuration": configuration or {}
            }
            
            response = await self.http_client.post(
                "/agents/create",
                json=payload,
                headers=self._get_headers(str(tenant_id), str(user_id))
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result["agent_id"]
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating agent: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}")
            raise
    
    async def delete_agent(
        self,
        agent_id: str,
        tenant_id: UUID,
        user_id: UUID
    ) -> bool:
        """Delete a Langroid agent"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            response = await self.http_client.delete(
                f"/agents/{agent_id}",
                params={"tenant_id": str(tenant_id)},
                headers=self._get_headers(str(tenant_id), str(user_id))
            )
            
            response.raise_for_status()
            return True
            
        except httpx.HTTPError as e:
            if e.response.status_code == 404:
                return False
            logger.error(f"HTTP error deleting agent: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting agent: {str(e)}")
            raise
    
    async def list_agents(
        self,
        tenant_id: UUID,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """List all agents for a tenant"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            response = await self.http_client.get(
                "/agents/list",
                params={"tenant_id": str(tenant_id)},
                headers=self._get_headers(str(tenant_id), str(user_id))
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result["agents"]
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error listing agents: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error listing agents: {str(e)}")
            raise
    
    # =====================================
    # AGENT INTERACTION
    # =====================================
    
    async def chat_with_agent(
        self,
        agent_id: str,
        tenant_id: UUID,
        user_id: UUID,
        message: str,
        conversation_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chat with an agent and stream responses"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "message": message,
                "conversation_id": conversation_id,
                "context": context or {}
            }
            
            async with self.http_client.stream(
                "POST",
                f"/agents/{agent_id}/chat",
                json=payload,
                params={"tenant_id": str(tenant_id)},
                headers=self._get_headers(str(tenant_id), str(user_id))
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in agent chat: {str(e)}")
            yield {
                "type": "error",
                "content": f"Connection error: {str(e)}",
                "metadata": {"error_type": "http_error"}
            }
        except Exception as e:
            logger.error(f"Error in agent chat: {str(e)}")
            yield {
                "type": "error",
                "content": f"Unexpected error: {str(e)}",
                "metadata": {"error_type": "unexpected_error"}
            }
    
    async def execute_agent_task(
        self,
        agent_id: str,
        tenant_id: UUID,
        user_id: UUID,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a task with an agent and stream responses"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "task_type": task_type,
                "parameters": parameters,
                "context": context or {}
            }
            
            async with self.http_client.stream(
                "POST",
                f"/agents/{agent_id}/execute",
                json=payload,
                params={"tenant_id": str(tenant_id)},
                headers=self._get_headers(str(tenant_id), str(user_id))
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error executing agent task: {str(e)}")
            yield {
                "type": "error",
                "content": f"Connection error: {str(e)}",
                "metadata": {"error_type": "http_error"}
            }
        except Exception as e:
            logger.error(f"Error executing agent task: {str(e)}")
            yield {
                "type": "error",
                "content": f"Unexpected error: {str(e)}",
                "metadata": {"error_type": "unexpected_error"}
            }
    
    # =====================================
    # DIGITAL SIGNATURE SPECIFIC
    # =====================================
    
    async def create_signature_request_with_agent(
        self,
        tenant_id: UUID,
        user_id: UUID,
        title: str,
        document_name: str,
        signers: List[Dict[str, Any]],
        message: Optional[str] = None,
        signature_type: str = "sequential"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Create signature request using Langroid agent"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "title": title,
                "document_name": document_name,
                "signers": signers,
                "message": message,
                "signature_type": signature_type
            }
            
            async with self.http_client.stream(
                "POST",
                "/signature-agent/create-request",
                json=payload,
                params={
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id)
                },
                headers=self._get_headers(str(tenant_id), str(user_id))
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            yield data
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating signature request: {str(e)}")
            yield {
                "type": "error",
                "content": f"Connection error: {str(e)}",
                "metadata": {"error_type": "http_error"}
            }
        except Exception as e:
            logger.error(f"Error creating signature request: {str(e)}")
            yield {
                "type": "error",
                "content": f"Unexpected error: {str(e)}",
                "metadata": {"error_type": "unexpected_error"}
            }
    
    async def get_signature_status_with_agent(
        self,
        request_id: str,
        tenant_id: UUID,
        user_id: UUID
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Get signature status using Langroid agent"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            async with self.http_client.stream(
                "GET",
                f"/signature-agent/status/{request_id}",
                params={
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id)
                },
                headers=self._get_headers(str(tenant_id), str(user_id))
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            yield data
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting signature status: {str(e)}")
            yield {
                "type": "error",
                "content": f"Connection error: {str(e)}",
                "metadata": {"error_type": "http_error"}
            }
        except Exception as e:
            logger.error(f"Error getting signature status: {str(e)}")
            yield {
                "type": "error",
                "content": f"Unexpected error: {str(e)}",
                "metadata": {"error_type": "unexpected_error"}
            }
    
    # =====================================
    # DOCUMENT PROCESSING
    # =====================================
    
    async def analyze_document_with_agent(
        self,
        document_content: str,
        analysis_type: str = "general",
        tenant_id: UUID = None,
        user_id: UUID = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Analyze document using Langroid agent"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "document_content": document_content,
                "analysis_type": analysis_type,
                "tenant_id": str(tenant_id) if tenant_id else "",
                "user_id": str(user_id) if user_id else ""
            }
            
            headers = {}
            if tenant_id and user_id:
                headers = self._get_headers(str(tenant_id), str(user_id))
            
            async with self.http_client.stream(
                "POST",
                "/document/analyze",
                json=payload,
                headers=headers
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            yield data
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error analyzing document: {str(e)}")
            yield {
                "type": "error",
                "content": f"Connection error: {str(e)}",
                "metadata": {"error_type": "http_error"}
            }
        except Exception as e:
            logger.error(f"Error analyzing document: {str(e)}")
            yield {
                "type": "error",
                "content": f"Unexpected error: {str(e)}",
                "metadata": {"error_type": "unexpected_error"}
            }
    
    # =====================================
    # HEALTH CHECK
    # =====================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of Langroid service"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            response = await self.http_client.get("/health")
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get detailed service status"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            response = await self.http_client.get("/status")
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Status check failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }