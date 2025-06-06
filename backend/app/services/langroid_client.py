# app/services/langroid_client.py

import httpx
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import json
from app.core.config import settings

logger = logging.getLogger(__name__)

class LangroidClient:
    """Cliente para comunicarse con el microservicio Langroid"""
    
    def __init__(self):
        self.base_url = settings.LANGROID_SERVICE_URL
        self.timeout = 30.0
    
    def _get_security_headers(self, tenant_id: str = None, user_id: str = None) -> Dict[str, str]:
        """Obtener headers de seguridad para requests al microservicio"""
        headers = {
            "X-API-Key": settings.API_KEY,
            "Content-Type": "application/json"
        }
        
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if user_id:
            headers["X-User-ID"] = user_id
            
        return headers
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str,
        tenant_id: str = None,
        user_id: str = None,
        **kwargs
    ) -> httpx.Response:
        """Realizar una request HTTP al microservicio con headers de seguridad"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}{endpoint}"
            
            # Agregar headers de seguridad
            security_headers = {
                "X-API-Key": settings.API_KEY
            }
            
            if tenant_id:
                security_headers["X-Tenant-ID"] = tenant_id
            if user_id:
                security_headers["X-User-ID"] = user_id
            
            # Combinar headers
            if "headers" in kwargs:
                kwargs["headers"].update(security_headers)
            else:
                kwargs["headers"] = security_headers
            
            logger.info(f"🌐 {method.upper()} {url} (Tenant: {tenant_id}, User: {user_id})")
            
            response = await client.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )
            
            if response.status_code >= 400:
                logger.error(f"❌ Langroid service error: {response.status_code} - {response.text}")
                response.raise_for_status()
            
            return response
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar el estado del microservicio"""
        response = await self._make_request("GET", "/health")
        return response.json()
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Obtener estado detallado del servicio"""
        response = await self._make_request("GET", "/status")
        return response.json()
    
    # =====================================
    # AGENT MANAGEMENT
    # =====================================
    
    async def create_agent(
        self, 
        agent_type: str, 
        tenant_id: str, 
        user_id: str, 
        configuration: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Crear un nuevo agente"""
        data = {
            "agent_type": agent_type,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "configuration": configuration or {}
        }
        
        response = await self._make_request(
            "POST", "/agents/create", 
            tenant_id=tenant_id, 
            user_id=user_id,
            json=data
        )
        return response.json()
    
    async def delete_agent(self, agent_id: str, tenant_id: str) -> Dict[str, Any]:
        """Eliminar un agente"""
        response = await self._make_request(
            "DELETE", 
            f"/agents/{agent_id}",
            tenant_id=tenant_id,
            params={"tenant_id": tenant_id}
        )
        return response.json()
    
    async def list_agents(self, tenant_id: str) -> Dict[str, Any]:
        """Listar agentes de un tenant"""
        response = await self._make_request(
            "GET", 
            "/agents/list",
            tenant_id=tenant_id,
            params={"tenant_id": tenant_id}
        )
        return response.json()
    
    # =====================================
    # AGENT INTERACTION
    # =====================================
    
    async def chat_with_agent(
        self, 
        agent_id: str, 
        tenant_id: str, 
        message: str,
        user_id: str = None,
        conversation_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chat con un agente (streaming)"""
        data = {
            "message": message,
            "conversation_id": conversation_id,
            "context": context or {}
        }
        
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/agents/{agent_id}/chat"
            
            # Headers de seguridad
            headers = self._get_security_headers(tenant_id, user_id)
            
            async with client.stream(
                "POST",
                url,
                json=data,
                headers=headers,
                params={"tenant_id": tenant_id},
                timeout=60.0
            ) as response:
                if response.status_code >= 400:
                    logger.error(f"❌ Chat error: {response.status_code}")
                    response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in stream: {line}")
    
    async def execute_agent_task(
        self, 
        agent_id: str, 
        tenant_id: str, 
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar una tarea con un agente (streaming)"""
        data = {
            "task_type": task_type,
            "parameters": parameters,
            "context": context or {}
        }
        
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/agents/{agent_id}/execute"
            
            async with client.stream(
                "POST",
                url,
                json=data,
                params={"tenant_id": tenant_id},
                timeout=120.0
            ) as response:
                if response.status_code >= 400:
                    logger.error(f"❌ Task execution error: {response.status_code}")
                    response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in stream: {line}")
    
    # =====================================
    # DIGITAL SIGNATURE
    # =====================================
    
    async def create_signature_request(
        self,
        tenant_id: str,
        user_id: str,
        title: str,
        document_name: str,
        signers: List[Dict[str, Any]],
        message: Optional[str] = None,
        signature_type: str = "sequential"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Crear una solicitud de firma digital (streaming)"""
        data = {
            "title": title,
            "document_name": document_name,
            "signers": signers,
            "message": message,
            "signature_type": signature_type
        }
        
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/signature-agent/create-request"
            
            async with client.stream(
                "POST",
                url,
                json=data,
                params={"tenant_id": tenant_id, "user_id": user_id},
                timeout=120.0
            ) as response:
                if response.status_code >= 400:
                    logger.error(f"❌ Signature request error: {response.status_code}")
                    response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in stream: {line}")
    
    async def get_signature_status(
        self,
        request_id: str,
        tenant_id: str,
        user_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Obtener estado de una solicitud de firma (streaming)"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/signature-agent/status/{request_id}"
            
            async with client.stream(
                "GET",
                url,
                params={"tenant_id": tenant_id, "user_id": user_id},
                timeout=60.0
            ) as response:
                if response.status_code >= 400:
                    logger.error(f"❌ Signature status error: {response.status_code}")
                    response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in stream: {line}")
    
    # =====================================
    # DOCUMENT ANALYSIS
    # =====================================
    
    async def analyze_document(
        self,
        document_content: str,
        analysis_type: str = "general",
        tenant_id: str = "",
        user_id: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Analizar documento con agentes (streaming)"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/document/analyze"
            
            data = {
                "document_content": document_content,
                "analysis_type": analysis_type,
                "tenant_id": tenant_id,
                "user_id": user_id
            }
            
            async with client.stream(
                "POST",
                url,
                json=data,
                timeout=120.0
            ) as response:
                if response.status_code >= 400:
                    logger.error(f"❌ Document analysis error: {response.status_code}")
                    response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in stream: {line}")

# Instancia singleton
langroid_client = LangroidClient()