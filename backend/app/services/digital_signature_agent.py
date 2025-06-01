"""
Digital Signature Agent - AI Agent for signature workflow management
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, AsyncGenerator
from uuid import UUID
from sqlalchemy.orm import Session

from app.services.agent_service import AgentService
from app.services.signature_service import SignatureService
from app.services.langchain_client import LangChainClient
from app.db.models import Agent, AgentConversation, AgentMessage
from app.schemas.agent import SignatureRequestCreate, SignerCreate

logger = logging.getLogger(__name__)


class DigitalSignatureAgent:
    """Agente especializado en firma digital"""
    
    def __init__(self, db: Session, agent_id: UUID, tenant_id: UUID):
        self.db = db
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.agent_service = AgentService(db)
        self.signature_service = SignatureService(db)
        
        # Obtener configuración del agente
        self.agent = self.agent_service.get_agent(agent_id, tenant_id)
        if not self.agent:
            raise ValueError("Agent not found")
        
        self.config = self.agent.configuration
        
        # Herramientas disponibles
        self.tools = {
            "create_signature_request": self._create_signature_request,
            "get_signature_status": self._get_signature_status,
            "list_signature_requests": self._list_signature_requests,
            "send_signature_request": self._send_signature_request,
            "cancel_signature_request": self._cancel_signature_request,
            "download_signed_document": self._download_signed_document,
            "search_documents": self._search_documents,
            "calculate": self._calculate
        }
    
    async def process_message(
        self, 
        message: str, 
        conversation_id: UUID, 
        user_id: UUID,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Procesar mensaje del usuario con streaming"""
        
        try:
            # Registrar mensaje del usuario
            user_message = self.agent_service.add_message(
                MessageCreate(
                    conversation_id=conversation_id,
                    role="user",
                    content=message,
                    metadata=context or {}
                ),
                self.tenant_id,
                user_id
            )
            
            # Obtener historial de conversación
            conversation_history = self._get_conversation_history(conversation_id, user_id)
            
            # Preparar contexto para el LLM
            system_prompt = self._build_system_prompt()
            
            # Procesar con LangChain
            async with LangChainClient() as client:
                # Determinar si necesita usar herramientas
                tool_analysis = await self._analyze_tool_usage(client, message, conversation_history)
                
                if tool_analysis.get("needs_tools", False):
                    # Ejecutar herramientas necesarias
                    async for response in self._execute_tools_workflow(
                        client, message, conversation_history, tool_analysis, user_id
                    ):
                        yield response
                else:
                    # Respuesta directa del LLM
                    async for response in self._generate_direct_response(
                        client, message, conversation_history, system_prompt
                    ):
                        yield response
                        
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error processing your request: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    def _build_system_prompt(self) -> str:
        """Construir prompt del sistema para el agente"""
        return f"""Eres un asistente especializado en firma digital y gestión de documentos.

Tu función es ayudar a los usuarios a:
- Crear solicitudes de firma digital
- Gestionar el estado de las firmas
- Consultar documentos y su estado
- Realizar cálculos relacionados con firmas (fechas, plazos, etc.)

Configuración del agente:
- Tenant ID: {self.tenant_id}
- Configuración: {json.dumps(self.config, indent=2)}

Herramientas disponibles:
- create_signature_request: Crear nueva solicitud de firma
- get_signature_status: Consultar estado de firma
- list_signature_requests: Listar solicitudes existentes
- send_signature_request: Enviar solicitud a firmantes
- cancel_signature_request: Cancelar solicitud
- download_signed_document: Descargar documento firmado
- search_documents: Buscar documentos en el sistema
- calculate: Realizar cálculos matemáticos

Instrucciones:
1. Siempre sé claro y profesional
2. Explica los pasos del proceso de firma
3. Proporciona información detallada sobre el estado
4. Sugiere mejores prácticas para firma digital
5. Si necesitas información adicional, pídela específicamente

Responde en español y adapta tu comunicación al contexto empresarial."""
    
    async def _analyze_tool_usage(
        self, 
        client: LangChainClient, 
        message: str, 
        history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analizar si el mensaje requiere uso de herramientas"""
        
        analysis_prompt = f"""Analiza el siguiente mensaje y determina si necesita usar herramientas específicas:

Mensaje del usuario: "{message}"

Herramientas disponibles:
- create_signature_request: Para crear solicitudes de firma
- get_signature_status: Para consultar estado de firmas
- list_signature_requests: Para listar solicitudes
- send_signature_request: Para enviar solicitudes
- cancel_signature_request: Para cancelar
- download_signed_document: Para descargar documentos firmados
- search_documents: Para buscar documentos
- calculate: Para cálculos matemáticos

Responde en JSON con:
{{
    "needs_tools": true/false,
    "tools_needed": ["tool1", "tool2"],
    "reasoning": "explicación de por qué"
}}"""
        
        try:
            response = await client.generate_response(
                query=analysis_prompt,
                max_tokens=200
            )
            
            # Intentar parsear como JSON
            analysis_text = response.get("answer", "{}")
            analysis = json.loads(analysis_text)
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing tool usage: {str(e)}")
            return {"needs_tools": False, "tools_needed": [], "reasoning": "Error in analysis"}
    
    async def _execute_tools_workflow(
        self, 
        client: LangChainClient, 
        message: str, 
        history: List[Dict[str, Any]], 
        tool_analysis: Dict[str, Any],
        user_id: UUID
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar flujo de trabajo con herramientas"""
        
        tools_needed = tool_analysis.get("tools_needed", [])
        
        yield {
            "type": "message",
            "content": f"Entendido. Voy a {tool_analysis.get('reasoning', 'procesar tu solicitud')}...",
            "metadata": {"tools_to_use": tools_needed}
        }
        
        # Ejecutar herramientas
        tool_results = {}
        for tool_name in tools_needed:
            if tool_name in self.tools:
                try:
                    yield {
                        "type": "tool_call",
                        "content": f"Ejecutando: {tool_name}",
                        "metadata": {"tool": tool_name, "status": "running"}
                    }
                    
                    # Extraer parámetros del mensaje (simplificado)
                    params = await self._extract_tool_parameters(client, message, tool_name)
                    
                    # Ejecutar herramienta
                    result = await self.tools[tool_name](params, user_id)
                    tool_results[tool_name] = result
                    
                    yield {
                        "type": "tool_call",
                        "content": f"✅ {tool_name} ejecutado correctamente",
                        "metadata": {"tool": tool_name, "status": "completed", "result": result}
                    }
                    
                except Exception as e:
                    error_msg = f"Error ejecutando {tool_name}: {str(e)}"
                    tool_results[tool_name] = {"error": str(e)}
                    
                    yield {
                        "type": "tool_call",
                        "content": f"❌ {error_msg}",
                        "metadata": {"tool": tool_name, "status": "error", "error": str(e)}
                    }
        
        # Generar respuesta final con resultados
        final_prompt = f"""Basándote en los resultados de las herramientas ejecutadas, genera una respuesta completa para el usuario.

Mensaje original: "{message}"
Resultados de herramientas: {json.dumps(tool_results, indent=2, default=str)}

Proporciona una respuesta clara, informativa y útil."""
        
        async for response in self._generate_direct_response(client, final_prompt, history):
            yield response
    
    async def _extract_tool_parameters(
        self, 
        client: LangChainClient, 
        message: str, 
        tool_name: str
    ) -> Dict[str, Any]:
        """Extraer parámetros para una herramienta específica"""
        
        param_schemas = {
            "create_signature_request": {
                "title": "string",
                "document_name": "string", 
                "signers": "array of {name, email}",
                "message": "optional string"
            },
            "get_signature_status": {
                "request_id": "UUID or identifier"
            },
            "list_signature_requests": {
                "status": "optional status filter",
                "limit": "optional number"
            },
            "search_documents": {
                "query": "search query string"
            },
            "calculate": {
                "expression": "mathematical expression"
            }
        }
        
        schema = param_schemas.get(tool_name, {})
        
        extraction_prompt = f"""Extrae los parámetros necesarios para la herramienta '{tool_name}' del siguiente mensaje:

Mensaje: "{message}"

Esquema de parámetros esperados:
{json.dumps(schema, indent=2)}

Responde solo con un JSON válido con los parámetros extraídos. Si falta información, usa valores por defecto razonables o null."""
        
        try:
            response = await client.generate_response(
                query=extraction_prompt,
                max_tokens=300
            )
            
            params_text = response.get("answer", "{}")
            return json.loads(params_text)
            
        except Exception as e:
            logger.error(f"Error extracting parameters: {str(e)}")
            return {}
    
    async def _generate_direct_response(
        self, 
        client: LangChainClient, 
        message: str, 
        history: List[Dict[str, Any]], 
        system_prompt: str = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Generar respuesta directa del LLM"""
        
        # Construir contexto
        context_messages = []
        if system_prompt:
            context_messages.append(f"Sistema: {system_prompt}")
        
        for msg in history[-10:]:  # Últimos 10 mensajes
            context_messages.append(f"{msg['role']}: {msg['content']}")
        
        context_messages.append(f"Usuario: {message}")
        
        full_prompt = "\n\n".join(context_messages)
        
        try:
            response = await client.generate_response(
                query=full_prompt,
                max_tokens=1000
            )
            
            answer = response.get("answer", "Lo siento, no pude generar una respuesta.")
            
            yield {
                "type": "message",
                "content": answer,
                "metadata": {
                    "sources": response.get("sources", []),
                    "response_type": "direct"
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating direct response: {str(e)}")
            yield {
                "type": "error",
                "content": "Error generando respuesta. Por favor, intenta de nuevo.",
                "metadata": {"error": str(e)}
            }
    
    def _get_conversation_history(
        self, 
        conversation_id: UUID, 
        user_id: UUID,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Obtener historial de conversación"""
        messages = self.agent_service.get_messages(
            conversation_id, self.tenant_id, user_id, limit=limit
        )
        
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata,
                "created_at": msg.created_at
            }
            for msg in messages
        ]
    
    # =====================================
    # HERRAMIENTAS ESPECÍFICAS
    # =====================================
    
    async def _create_signature_request(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Crear solicitud de firma"""
        try:
            # Obtener proveedor por defecto
            default_provider = self.signature_service.get_default_provider(self.tenant_id)
            if not default_provider:
                return {"error": "No hay proveedor de firma configurado"}
            
            # Preparar datos de firmantes
            signers_data = []
            for signer in params.get("signers", []):
                signers_data.append(SignerCreate(
                    name=signer.get("name", ""),
                    email=signer.get("email", ""),
                    phone=signer.get("phone"),
                    order=signer.get("order", 1),
                    authentication_method=signer.get("authentication_method", "email")
                ))
            
            if not signers_data:
                return {"error": "Se requiere al menos un firmante"}
            
            # Crear solicitud
            request_data = SignatureRequestCreate(
                provider_id=default_provider.id,
                title=params.get("title", "Documento para firma"),
                message=params.get("message", "Por favor, firma este documento"),
                document_name=params.get("document_name", "documento.pdf"),
                signers=signers_data,
                signature_type=params.get("signature_type", "sequential"),
                callback_url=params.get("callback_url"),
                success_url=params.get("success_url"),
                error_url=params.get("error_url"),
                metadata=params.get("metadata", {})
            )
            
            signature_request = self.signature_service.create_signature_request(
                request_data, self.tenant_id, user_id
            )
            
            return {
                "success": True,
                "request_id": str(signature_request.id),
                "status": signature_request.status,
                "title": signature_request.title,
                "signers_count": len(signature_request.signers),
                "created_at": signature_request.created_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating signature request: {str(e)}")
            return {"error": f"Error creando solicitud: {str(e)}"}
    
    async def _get_signature_status(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Obtener estado de solicitud de firma"""
        try:
            request_id = params.get("request_id")
            if not request_id:
                return {"error": "ID de solicitud requerido"}
            
            request = self.signature_service.get_signature_request(
                UUID(request_id), self.tenant_id
            )
            
            if not request:
                return {"error": "Solicitud no encontrada"}
            
            # Actualizar estado desde proveedor
            updated_request = self.signature_service.update_signature_status(
                UUID(request_id), self.tenant_id
            )
            
            signers_status = [
                {
                    "name": signer.name,
                    "email": signer.email,
                    "status": signer.status,
                    "signed_at": signer.signed_at.isoformat() if signer.signed_at else None
                }
                for signer in updated_request.signers
            ]
            
            return {
                "request_id": str(updated_request.id),
                "title": updated_request.title,
                "status": updated_request.status,
                "created_at": updated_request.created_at.isoformat(),
                "sent_at": updated_request.sent_at.isoformat() if updated_request.sent_at else None,
                "completed_at": updated_request.completed_at.isoformat() if updated_request.completed_at else None,
                "signers": signers_status
            }
            
        except Exception as e:
            logger.error(f"Error getting signature status: {str(e)}")
            return {"error": f"Error consultando estado: {str(e)}"}
    
    async def _list_signature_requests(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Listar solicitudes de firma"""
        try:
            status_filter = params.get("status")
            limit = params.get("limit", 10)
            
            requests = self.signature_service.get_signature_requests(
                tenant_id=self.tenant_id,
                user_id=user_id,
                status=status_filter,
                limit=limit
            )
            
            requests_data = []
            for request in requests:
                requests_data.append({
                    "request_id": str(request.id),
                    "title": request.title,
                    "status": request.status,
                    "signers_count": len(request.signers),
                    "created_at": request.created_at.isoformat(),
                    "document_name": request.document_name
                })
            
            return {
                "success": True,
                "requests": requests_data,
                "total": len(requests_data),
                "status_filter": status_filter
            }
            
        except Exception as e:
            logger.error(f"Error listing signature requests: {str(e)}")
            return {"error": f"Error listando solicitudes: {str(e)}"}
    
    async def _send_signature_request(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Enviar solicitud de firma"""
        try:
            request_id = params.get("request_id")
            if not request_id:
                return {"error": "ID de solicitud requerido"}
            
            success = self.signature_service.send_signature_request(
                UUID(request_id), self.tenant_id
            )
            
            if success:
                return {
                    "success": True,
                    "message": "Solicitud enviada correctamente",
                    "request_id": request_id
                }
            else:
                return {"error": "Error enviando solicitud"}
            
        except Exception as e:
            logger.error(f"Error sending signature request: {str(e)}")
            return {"error": f"Error enviando solicitud: {str(e)}"}
    
    async def _cancel_signature_request(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Cancelar solicitud de firma"""
        # TODO: Implementar cancelación
        return {"error": "Función de cancelación no implementada aún"}
    
    async def _download_signed_document(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Descargar documento firmado"""
        try:
            request_id = params.get("request_id")
            if not request_id:
                return {"error": "ID de solicitud requerido"}
            
            document_bytes = self.signature_service.download_signed_document(
                UUID(request_id), self.tenant_id
            )
            
            if document_bytes:
                # En una implementación real, aquí se guardaría el archivo
                # y se devolvería una URL de descarga
                return {
                    "success": True,
                    "message": "Documento descargado correctamente",
                    "size_bytes": len(document_bytes),
                    "download_url": f"/api/v1/signatures/{request_id}/download"
                }
            else:
                return {"error": "Documento no disponible o no completado"}
            
        except Exception as e:
            logger.error(f"Error downloading document: {str(e)}")
            return {"error": f"Error descargando documento: {str(e)}"}
    
    async def _search_documents(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Buscar documentos"""
        try:
            query = params.get("query", "")
            if not query:
                return {"error": "Consulta de búsqueda requerida"}
            
            # Usar el servicio de vectores para búsqueda semántica
            async with LangChainClient() as client:
                results = await client.search_similar(
                    tenant_id=str(self.tenant_id),
                    query=query,
                    limit=5
                )
            
            documents = []
            for result in results:
                documents.append({
                    "content_preview": result.get("content", "")[:200] + "...",
                    "metadata": result.get("metadata", {}),
                    "similarity_score": result.get("score", 0.0)
                })
            
            return {
                "success": True,
                "query": query,
                "documents": documents,
                "total_found": len(documents)
            }
            
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            return {"error": f"Error buscando documentos: {str(e)}"}
    
    async def _calculate(self, params: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Realizar cálculos matemáticos"""
        try:
            expression = params.get("expression", "")
            if not expression:
                return {"error": "Expresión matemática requerida"}
            
            # Evaluación segura de expresiones matemáticas básicas
            # Solo permitir operaciones seguras
            allowed_chars = set("0123456789+-*/().= ")
            if not all(c in allowed_chars for c in expression):
                return {"error": "Expresión contiene caracteres no permitidos"}
            
            try:
                # Evaluación simple (en producción usar un evaluador más seguro)
                result = eval(expression.replace("=", "=="))
                return {
                    "success": True,
                    "expression": expression,
                    "result": result
                }
            except:
                return {"error": "Expresión matemática inválida"}
            
        except Exception as e:
            logger.error(f"Error in calculation: {str(e)}")
            return {"error": f"Error en cálculo: {str(e)}"}