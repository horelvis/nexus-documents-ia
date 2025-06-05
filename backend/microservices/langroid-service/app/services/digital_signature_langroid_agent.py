"""
Digital Signature Langroid Agent - Advanced signature workflow management with Langroid
"""
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator
from uuid import UUID
import httpx

import langroid as lr
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tools.orchestration import AgentDoneTool
from langroid.language_models.base import LLMMessage, Role
from langroid.pydantic_v1 import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


# =====================================
# SIGNATURE TOOLS
# =====================================

class CreateSignatureRequestTool(lr.agent.ToolMessage):
    """Tool for creating signature requests"""
    request: str = "create_signature_request"
    title: str = Field(..., description="Title of the signature request")
    document_name: str = Field(..., description="Name of the document to be signed")
    signers: List[Dict[str, Any]] = Field(..., description="List of signers with name and email")
    message: Optional[str] = Field(None, description="Message for signers")
    signature_type: str = Field(default="sequential", description="Type of signature workflow")

    def handle(self) -> str:
        """Handle the signature request creation"""
        return f"Creating signature request: {self.title} with {len(self.signers)} signers"


class GetSignatureStatusTool(lr.agent.ToolMessage):
    """Tool for checking signature status"""
    request: str = "get_signature_status"
    request_id: str = Field(..., description="ID of the signature request to check")

    def handle(self) -> str:
        """Handle the status check"""
        return f"Checking status for request: {self.request_id}"


class ListSignatureRequestsTool(lr.agent.ToolMessage):
    """Tool for listing signature requests"""
    request: str = "list_signature_requests"
    status: Optional[str] = Field(None, description="Filter by status")
    limit: int = Field(default=10, description="Maximum number of requests to return")

    def handle(self) -> str:
        """Handle the list requests"""
        return f"Listing signature requests (limit: {self.limit}, status: {self.status})"


class SendSignatureRequestTool(lr.agent.ToolMessage):
    """Tool for sending signature requests"""
    request: str = "send_signature_request"
    request_id: str = Field(..., description="ID of the signature request to send")

    def handle(self) -> str:
        """Handle sending the request"""
        return f"Sending signature request: {self.request_id}"


class SearchDocumentsTool(lr.agent.ToolMessage):
    """Tool for searching documents"""
    request: str = "search_documents"
    query: str = Field(..., description="Search query")
    limit: int = Field(default=5, description="Maximum number of results")

    def handle(self) -> str:
        """Handle document search"""
        return f"Searching documents for: {self.query}"


# =====================================
# DIGITAL SIGNATURE AGENT
# =====================================

class DigitalSignatureLangroidAgent(ChatAgent):
    """Advanced Digital Signature Agent using Langroid framework"""
    
    def __init__(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        llm_config: lr.language_models.ollama_chat.OllamaChatConfig,
        vector_config: lr.vector_store.qdrantdb.QdrantDBConfig = None,
        config: Dict[str, Any] = None
    ):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.config = config or {}
        
        # Configure agent
        agent_config = ChatAgentConfig(
            name="DigitalSignatureAgent",
            llm=llm_config,
            vecdb=vector_config,
            system_message=self._build_system_message(),
            use_tools=True,
            use_functions_api=True
        )
        
        super().__init__(agent_config)
        
        # Register tools
        self.enable_message(CreateSignatureRequestTool)
        self.enable_message(GetSignatureStatusTool)
        self.enable_message(ListSignatureRequestsTool)
        self.enable_message(SendSignatureRequestTool)
        self.enable_message(SearchDocumentsTool)
        self.enable_message(AgentDoneTool)
        
        # HTTP client for backend communication
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        logger.info(f"Created DigitalSignatureLangroidAgent {agent_id} for tenant {tenant_id}")
    
    def _build_system_message(self) -> str:
        """Build system message for the agent"""
        return f"""You are an advanced digital signature assistant powered by Langroid.

IDENTITY & ROLE:
- Agent ID: {self.agent_id}
- Tenant: {self.tenant_id}
- Specialized in digital signature workflows and document management

CAPABILITIES:
- Create and manage digital signature requests
- Monitor signature status and progress
- Send reminders and notifications
- Search and analyze documents
- Provide guidance on signature best practices

AVAILABLE TOOLS:
1. CreateSignatureRequestTool: Create new signature requests
2. GetSignatureStatusTool: Check status of existing requests
3. ListSignatureRequestsTool: List signature requests with filters
4. SendSignatureRequestTool: Send requests to signers
5. SearchDocumentsTool: Search document collections

BEHAVIOR GUIDELINES:
- Always be professional and clear in communications
- Explain each step of the signature process
- Provide detailed status updates
- Suggest improvements for signature workflows
- Ask for clarification when information is incomplete
- Use tools proactively to gather information

SECURITY:
- Respect tenant boundaries and permissions
- Validate all inputs before processing
- Protect sensitive signature data
- Follow audit and compliance requirements

Respond in Spanish and adapt your communication to business contexts.
When users ask about signatures, proactively use the appropriate tools to help them."""
    
    async def chat_stream(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chat with the agent and stream responses"""
        
        try:
            yield {
                "type": "message",
                "content": "Analizando tu solicitud...",
                "metadata": {"status": "processing", "agent_id": self.agent_id}
            }
            
            # Analyze the message to determine if tools are needed
            needs_tools = await self._analyze_message_for_tools(message)
            
            if needs_tools["requires_tools"]:
                # Execute tool workflow
                async for response in self._execute_tool_workflow(
                    message, needs_tools, context
                ):
                    yield response
            else:
                # Direct conversation
                async for response in self._direct_conversation(message, context):
                    yield response
                    
        except Exception as e:
            logger.error(f"Error in chat_stream: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error procesando tu solicitud: {str(e)}",
                "metadata": {"error": str(e), "agent_id": self.agent_id}
            }
    
    async def execute_task_stream(
        self,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute specific task with streaming"""
        
        try:
            yield {
                "type": "task_progress",
                "content": f"Ejecutando tarea: {task_type}",
                "metadata": {
                    "task_type": task_type,
                    "agent_id": self.agent_id,
                    "progress": 10
                }
            }
            
            # Execute based on task type
            if task_type == "create_signature_request":
                async for response in self._execute_create_signature_request(parameters):
                    yield response
                    
            elif task_type == "get_signature_status":
                async for response in self._execute_get_signature_status(parameters):
                    yield response
                    
            elif task_type == "list_signature_requests":
                async for response in self._execute_list_signature_requests(parameters):
                    yield response
                    
            elif task_type == "send_signature_request":
                async for response in self._execute_send_signature_request(parameters):
                    yield response
                    
            elif task_type == "search_documents":
                async for response in self._execute_search_documents(parameters):
                    yield response
                    
            else:
                yield {
                    "type": "error",
                    "content": f"Tipo de tarea no soportado: {task_type}",
                    "metadata": {"task_type": task_type, "agent_id": self.agent_id}
                }
                
        except Exception as e:
            logger.error(f"Error executing task {task_type}: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error ejecutando tarea: {str(e)}",
                "metadata": {"task_type": task_type, "error": str(e)}
            }
    
    # =====================================
    # TOOL ANALYSIS AND EXECUTION
    # =====================================
    
    async def _analyze_message_for_tools(self, message: str) -> Dict[str, Any]:
        """Analyze message to determine required tools"""
        
        # Keywords that indicate tool usage
        tool_keywords = {
            "create_signature_request": ["crear", "nueva solicitud", "firmar documento", "enviar para firma"],
            "get_signature_status": ["estado", "status", "cómo va", "progreso", "firmado"],
            "list_signature_requests": ["listar", "mostrar", "solicitudes", "historial"],
            "send_signature_request": ["enviar", "mandar", "notificar"],
            "search_documents": ["buscar", "encontrar", "documento", "archivo"]
        }
        
        message_lower = message.lower()
        suggested_tools = []
        
        for tool, keywords in tool_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                suggested_tools.append(tool)
        
        return {
            "requires_tools": len(suggested_tools) > 0,
            "suggested_tools": suggested_tools,
            "confidence": 0.8 if suggested_tools else 0.1,
            "reasoning": f"Detected keywords for tools: {suggested_tools}"
        }
    
    async def _execute_tool_workflow(
        self,
        message: str,
        tool_analysis: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute workflow with tools"""
        
        suggested_tools = tool_analysis["suggested_tools"]
        
        yield {
            "type": "message",
            "content": f"Voy a ayudarte con: {', '.join(suggested_tools)}",
            "metadata": {"tools_to_use": suggested_tools}
        }
        
        # For now, we'll execute the first suggested tool
        # In a more advanced implementation, you could chain multiple tools
        if suggested_tools:
            primary_tool = suggested_tools[0]
            
            # Extract parameters from message (simplified)
            parameters = await self._extract_parameters_from_message(message, primary_tool)
            
            # Execute the tool
            async for response in self.execute_task_stream(primary_tool, parameters, context):
                yield response
    
    async def _extract_parameters_from_message(
        self, 
        message: str, 
        tool_name: str
    ) -> Dict[str, Any]:
        """Extract parameters from natural language message"""
        
        # This is a simplified implementation
        # In production, you'd use more sophisticated NLP or LLM-based extraction
        
        parameters = {}
        message_lower = message.lower()
        
        if tool_name == "create_signature_request":
            # Look for common patterns
            if "título" in message_lower or "title" in message_lower:
                # Extract title (simplified)
                parameters["title"] = "Documento para firma digital"
            
            parameters.setdefault("title", "Solicitud de firma")
            parameters.setdefault("document_name", "documento.pdf")
            parameters.setdefault("signers", [])
            parameters.setdefault("message", "Por favor, firma este documento")
            
        elif tool_name == "get_signature_status":
            # Would extract request ID from message
            parameters["request_id"] = "placeholder-id"
            
        elif tool_name == "search_documents":
            # Extract search query
            parameters["query"] = message
            parameters["limit"] = 5
        
        return parameters
    
    # =====================================
    # TASK IMPLEMENTATIONS
    # =====================================
    
    async def _execute_create_signature_request(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute signature request creation"""
        
        try:
            yield {
                "type": "task_progress",
                "content": "Creando solicitud de firma...",
                "metadata": {"progress": 30}
            }
            
            # Call backend service
            backend_url = f"http://backend:8000/api/v1/signatures/requests"
            
            request_data = {
                "title": parameters.get("title", "Solicitud de firma"),
                "document_name": parameters.get("document_name", "documento.pdf"),
                "signers": parameters.get("signers", []),
                "message": parameters.get("message", "Por favor, firma este documento"),
                "signature_type": parameters.get("signature_type", "sequential")
            }
            
            # Simulate backend call (in production, make actual HTTP request)
            await asyncio.sleep(1)  # Simulate processing time
            
            # Mock response
            mock_response = {
                "success": True,
                "request_id": f"sr_{self.agent_id}_{int(datetime.now().timestamp())}",
                "title": request_data["title"],
                "status": "draft",
                "signers_count": len(request_data["signers"]),
                "created_at": datetime.now().isoformat()
            }
            
            yield {
                "type": "task_result",
                "content": "✅ Solicitud de firma creada exitosamente",
                "metadata": {
                    "progress": 100,
                    "result": mock_response,
                    "task_type": "create_signature_request"
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error creando solicitud: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_get_signature_status(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute signature status check"""
        
        try:
            request_id = parameters.get("request_id")
            
            yield {
                "type": "task_progress", 
                "content": f"Consultando estado de {request_id}...",
                "metadata": {"progress": 50}
            }
            
            # Simulate backend call
            await asyncio.sleep(0.5)
            
            # Mock response
            mock_status = {
                "request_id": request_id,
                "title": "Contrato de servicios",
                "status": "pending_signatures",
                "created_at": "2024-01-15T10:30:00Z",
                "signers": [
                    {
                        "name": "Juan Pérez",
                        "email": "juan@example.com",
                        "status": "signed",
                        "signed_at": "2024-01-15T11:30:00Z"
                    },
                    {
                        "name": "María García",
                        "email": "maria@example.com", 
                        "status": "pending",
                        "signed_at": None
                    }
                ]
            }
            
            yield {
                "type": "task_result",
                "content": "📄 Estado de firma consultado",
                "metadata": {
                    "progress": 100,
                    "result": mock_status,
                    "task_type": "get_signature_status"
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error consultando estado: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_list_signature_requests(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute signature requests listing"""
        
        try:
            yield {
                "type": "task_progress",
                "content": "Obteniendo lista de solicitudes...",
                "metadata": {"progress": 40}
            }
            
            # Simulate backend call
            await asyncio.sleep(0.5)
            
            # Mock response
            mock_requests = {
                "success": True,
                "requests": [
                    {
                        "request_id": "sr_001",
                        "title": "Contrato de servicios",
                        "status": "completed",
                        "signers_count": 2,
                        "created_at": "2024-01-15T10:30:00Z"
                    },
                    {
                        "request_id": "sr_002",
                        "title": "Acuerdo de confidencialidad",
                        "status": "pending_signatures",
                        "signers_count": 1,
                        "created_at": "2024-01-16T09:15:00Z"
                    }
                ],
                "total": 2
            }
            
            yield {
                "type": "task_result",
                "content": "📋 Lista de solicitudes obtenida",
                "metadata": {
                    "progress": 100,
                    "result": mock_requests,
                    "task_type": "list_signature_requests"
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error listando solicitudes: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_send_signature_request(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute signature request sending"""
        
        try:
            request_id = parameters.get("request_id")
            
            yield {
                "type": "task_progress",
                "content": f"Enviando solicitud {request_id}...",
                "metadata": {"progress": 60}
            }
            
            # Simulate backend call
            await asyncio.sleep(1)
            
            mock_response = {
                "success": True,
                "message": "Solicitud enviada correctamente",
                "request_id": request_id,
                "sent_at": datetime.now().isoformat()
            }
            
            yield {
                "type": "task_result",
                "content": "📤 Solicitud enviada a los firmantes",
                "metadata": {
                    "progress": 100,
                    "result": mock_response,
                    "task_type": "send_signature_request"
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error enviando solicitud: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_search_documents(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute document search"""
        
        try:
            query = parameters.get("query", "")
            
            yield {
                "type": "task_progress",
                "content": f"Buscando documentos: '{query}'...",
                "metadata": {"progress": 50}
            }
            
            # Simulate search
            await asyncio.sleep(0.5)
            
            mock_results = {
                "success": True,
                "query": query,
                "documents": [
                    {
                        "content_preview": "Contrato de prestación de servicios entre...",
                        "metadata": {"title": "Contrato servicios", "type": "pdf"},
                        "similarity_score": 0.95
                    },
                    {
                        "content_preview": "Acuerdo de confidencialidad para...",
                        "metadata": {"title": "NDA", "type": "docx"},
                        "similarity_score": 0.87
                    }
                ],
                "total_found": 2
            }
            
            yield {
                "type": "task_result",
                "content": "🔍 Búsqueda completada",
                "metadata": {
                    "progress": 100,
                    "result": mock_results,
                    "task_type": "search_documents"
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error buscando documentos: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _direct_conversation(
        self, 
        message: str, 
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle direct conversation without tools"""
        
        try:
            # Use Langroid's chat functionality
            response = self.llm_response(message)
            
            yield {
                "type": "message",
                "content": response.content,
                "metadata": {
                    "conversation_type": "direct",
                    "agent_id": self.agent_id,
                    "context": context
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": "Lo siento, no pude procesar tu mensaje. ¿Podrías reformularlo?",
                "metadata": {"error": str(e)}
            }
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'http_client'):
                await self.http_client.aclose()
            logger.info(f"Cleaned up DigitalSignatureLangroidAgent {self.agent_id}")
        except Exception as e:
            logger.error(f"Error cleaning up agent: {str(e)}")