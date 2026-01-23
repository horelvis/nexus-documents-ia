"""
Virtual Assistant Agent Service
Uses CrewAI through CAG service - NO reinventamos la rueda!
All agent capabilities provided by CrewAI framework
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models import User, Document, IndexedDocument, Tenant, DocumentShare, SignatureRequest
from app.services.async_document_service import AsyncDocumentService
from app.services.search_service import SearchService
from app.services.vector_service_direct import VectorServiceDirect
from app.services.cag_client import CAGClient

logger = logging.getLogger(__name__)


class AgentCapability(Enum):
    """Agent capabilities/tools available"""
    SEARCH_DOCUMENTS = "search_documents"
    ANALYZE_DOCUMENT = "analyze_document"
    CREATE_SIGNATURE_REQUEST = "create_signature_request"
    SHARE_DOCUMENT = "share_document"
    GET_STATISTICS = "get_statistics"
    EXTRACT_ENTITIES = "extract_entities"
    SUMMARIZE_DOCUMENT = "summarize_document"
    COMPARE_DOCUMENTS = "compare_documents"
    GENERAL_KNOWLEDGE = "general_knowledge"


@dataclass
class AgentContext:
    """Context for agent operations"""
    user: User
    tenant_id: str
    db_session: AsyncSession
    conversation_id: str
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    working_memory: Dict[str, Any] = field(default_factory=dict)
    tools_used: List[str] = field(default_factory=list)


@dataclass
class AgentResponse:
    """Structured agent response"""
    message: str
    actions_taken: List[Dict[str, Any]]
    suggestions: List[str]
    confidence: float
    metadata: Dict[str, Any]
    requires_confirmation: bool = False


class VirtualAssistantAgent:
    """
    Advanced Virtual Assistant Agent with reasoning and tool-use capabilities
    """
    
    def __init__(self):
        self.cag_client = CAGClient()  # Primary agent service
        self.vector_service = None  # Initialized when needed
        self.capabilities = list(AgentCapability)
        self.max_reasoning_steps = 5
        self.use_cag = True  # Flag to use CAG service
        
    async def _initialize_services(self, db: AsyncSession):
        """Initialize async services"""
        if not self.vector_service:
            self.vector_service = VectorServiceDirect()
            
    async def process_request(
        self,
        message: str,
        context: AgentContext
    ) -> AgentResponse:
        """
        Process user request using agent reasoning and tools
        
        Args:
            message: User's message
            context: Agent context with user info and history
            
        Returns:
            Structured agent response
        """
        try:
            await self._initialize_services(context.db_session)
            
            # Check if this is a welcome message request
            is_welcome = context.working_memory.get("is_welcome", False) or message.startswith("SYSTEM: Generate a personalized welcome message")
            
            logger.info(f"Processing message: {message[:100]}")
            logger.info(f"Is welcome message: {is_welcome}")
            logger.info(f"Working memory: {context.working_memory}")
            
            if is_welcome:
                logger.info("Generating personalized welcome message")
                
                # Get user stats for personalization
                stats = await self._get_user_stats(context)
                
                # Get additional dashboard info if available
                doc_info = f"Tienes {stats.get('total_documents', 0)} documentos" if stats.get('total_documents', 0) > 0 else "Aún no tienes documentos"
                activity_info = "Trabajaste en documentos hoy" if stats.get('recent_activity', '').startswith('Worked on documents today') else ""
                
                # Create a personalized context for welcome message
                welcome_context = f"""
                El usuario tiene {stats.get('total_documents', 0)} documentos en su biblioteca.
                {activity_info if activity_info else f"Última actividad: {stats.get('recent_activity', 'Sin actividad reciente')}"}
                Se unió: {stats.get('days_since_joined', 'recientemente')}.
                """
                
                # Generate personalized welcome through CAG
                welcome_query = f"""
                Genera un mensaje de bienvenida cálido y personalizado en español.
                
                Información del usuario:
                {welcome_context}
                
                Instrucciones:
                - Sé amigable y personal
                - Si el usuario tiene documentos, menciona cuántos tiene
                - Si trabajó hoy, felicítalo por su productividad
                - Si es nuevo (0 documentos), dale la bienvenida y sugiere empezar
                - Sugiere 2-3 acciones relevantes basadas en su historial
                - Mantén el mensaje conciso (2-3 oraciones)
                - USA ESPAÑOL
                
                Ejemplo si tiene documentos: "¡Bienvenido de vuelta! Veo que tienes 15 documentos en tu biblioteca y has estado trabajando activamente. ¿Quieres buscar algún documento específico o subir uno nuevo?"
                
                Ejemplo si es nuevo: "¡Bienvenido a tu asistente de documentos! Veo que es tu primera vez aquí. Te puedo ayudar a subir tu primer documento o explorar las funciones disponibles."
                """
                
                # Process through CAG for dynamic response
                message = welcome_query
            
            # Add message to history
            context.message_history.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Use CAG service with CrewAI for agent processing
            if self.use_cag:
                logger.info("Processing with CrewAI CAG service...")
                
                # Prepare context for CrewAI CAG - ensure all values are JSON serializable
                # Convert UUID to string and ensure working_memory is serializable
                serializable_working_memory = {}
                for key, value in context.working_memory.items():
                    if isinstance(value, UUID):
                        # Convert UUID to string
                        serializable_working_memory[key] = str(value)
                    elif hasattr(value, '__dict__'):
                        # If it's an object, try to get its dict representation
                        serializable_working_memory[key] = str(value)
                    elif isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        serializable_working_memory[key] = value
                    else:
                        # Convert to string for any other type
                        serializable_working_memory[key] = str(value)
                
                # Also ensure message_history is serializable
                serializable_history = []
                for msg in context.message_history[-10:]:  # Last 10 messages
                    serializable_msg = {}
                    for key, value in msg.items():
                        if isinstance(value, UUID):
                            serializable_msg[key] = str(value)
                        elif isinstance(value, datetime):
                            serializable_msg[key] = value.isoformat()
                        elif isinstance(value, (str, int, float, bool, list, dict, type(None))):
                            serializable_msg[key] = value
                        else:
                            serializable_msg[key] = str(value)
                    serializable_history.append(serializable_msg)
                
                cag_context = {
                    "tenant_id": str(context.tenant_id) if context.tenant_id else None,
                    "user_id": str(context.user.id) if context.user else None,
                    "conversation_id": str(context.conversation_id) if context.conversation_id else None,
                    "message_history": serializable_history,
                    "working_memory": serializable_working_memory,
                    "db_session": None  # CrewAI will manage its own connections
                }
                
                # Process with CrewAI agents (6 specialized agents working together)
                # CrewAI provides: Search, Analysis, Compliance, Response, Signature, Financial agents
                logger.info(f"Sending to CAG with context: {cag_context}")
                cag_response = await self.cag_client.process_with_agent(
                    message=message,
                    context=cag_context,
                    agent_type="virtual_assistant",  # CrewAI will orchestrate multiple agents
                    tools=["search_documents", "analyze_document", "get_statistics", "extract_entities", "signature_request"]
                )
                
                logger.info(f"CAG response: {cag_response}")
                
                # Check if CAG succeeded
                if not cag_response.get("error"):
                    # Extract response from CAG
                    final_message = cag_response.get("response", "")
                    actions_taken = cag_response.get("actions", [])
                    suggestions = cag_response.get("suggestions", [])
                    confidence = cag_response.get("confidence", 0.85)
                    
                    # Process any document results to add links
                    if cag_response.get("documents"):
                        final_message = await self._format_document_response(
                            cag_response["documents"],
                            final_message,
                            context
                        )
                    
                    # Update context
                    context.message_history.append({
                        "role": "assistant",
                        "content": final_message,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actions": actions_taken
                    })
                    
                    return AgentResponse(
                        message=final_message,
                        actions_taken=actions_taken,
                        suggestions=suggestions,
                        confidence=confidence,
                        metadata={
                            "agent": "CrewAI",
                            "engine": cag_response.get("engine", "crewai"),
                            "agents_used": cag_response.get("agents_used", []),
                            "tools_used": cag_response.get("tools_used", []),
                            "reasoning_steps": cag_response.get("reasoning_steps", 0),
                            "conversation_id": context.conversation_id
                        },
                        requires_confirmation=False
                    )
                else:
                    # Smart fallback - handle common queries locally when CAG fails
                    error_msg = cag_response.get('error', 'Unknown error')
                    logger.warning(f"CAG service error: {error_msg}, attempting local fallback")
                    
                    # Special handling for welcome messages - provide a warm, natural fallback
                    if is_welcome:
                        try:
                            # Get basic stats for personalized welcome
                            stats = await self._get_user_stats(context)
                            
                            # Generate personalized welcome message
                            if stats.get('total_documents', 0) > 0:
                                welcome_msg = f"¡Hola de nuevo! 👋 Veo que tienes {stats['total_documents']} documentos en tu biblioteca. "
                                if "today" in stats.get('recent_activity', ''):
                                    welcome_msg += "¡Qué bien que hayas estado trabajando hoy! "
                                welcome_msg += "¿En qué puedo ayudarte hoy?"
                                
                                suggestions = [
                                    f"Buscar entre mis {stats['total_documents']} documentos",
                                    "Ver estadísticas detalladas", 
                                    "Revisar documentos recientes"
                                ]
                            else:
                                welcome_msg = "¡Bienvenido a tu asistente de documentos! 🎉 Veo que es tu primera vez aquí. Estoy aquí para ayudarte a organizar y gestionar tus documentos de manera inteligente. ¿Te gustaría empezar subiendo tu primer documento?"
                                
                                suggestions = [
                                    "Subir mi primer documento",
                                    "Explorar las funciones disponibles",
                                    "Conocer las capacidades del asistente"
                                ]
                            
                            return AgentResponse(
                                message=welcome_msg,
                                actions_taken=[{"action": "welcome_fallback", "success": True, "result": stats}],
                                suggestions=suggestions,
                                confidence=0.85,
                                metadata={"fallback": True, "agent": "welcome_fallback", "stats": stats},
                                requires_confirmation=False
                            )
                            
                        except Exception as welcome_error:
                            logger.error(f"Welcome fallback error: {welcome_error}")
                            return AgentResponse(
                                message="¡Bienvenido! 😊 Soy tu asistente virtual de documentos. Aunque estoy teniendo algunas dificultades técnicas en este momento, estoy aquí para ayudarte con la gestión de tus documentos.",
                                actions_taken=[],
                                suggestions=["Intentar de nuevo", "Explorar funciones", "Contactar soporte"],
                                confidence=0.6,
                                metadata={"fallback": True, "agent": "simple_welcome_fallback"},
                                requires_confirmation=False
                            )
                    
                    return AgentResponse(
                        message="Lo siento, tengo dificultades para procesar tu solicitud en este momento. ¿Podrías reformularla o intentarlo de nuevo?",
                        actions_taken=[],
                        suggestions=["Buscar documentos", "Ver estadísticas", "Revisar firmas pendientes"],
                        confidence=0.3,
                        metadata={
                            "error": error_msg,
                            "agent": "final_fallback",
                            "conversation_id": context.conversation_id
                        },
                        requires_confirmation=False
                    )
            
        except Exception as e:
            logger.error(f"Agent processing error: {e}")
            return AgentResponse(
                message="Lo siento, encontré un problema al procesar tu solicitud. ¿Podrías reformularla?",
                actions_taken=[],
                suggestions=["Intenta ser más específico", "Pregunta sobre documentos", "Solicita ayuda"],
                confidence=0.2,
                metadata={"error": str(e)}
            )
    
    async def _analyze_intent(self, message: str, context: AgentContext) -> Dict[str, Any]:
        """Lightweight heuristic analysis used only during fallbacks."""
        return await self._analyze_intent_simple(message, context)
    
    async def _plan_actions(self, intent_analysis: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Plan actions based on intent analysis
        """
        intent = intent_analysis.get("primary_intent", "general")
        entities = intent_analysis.get("entities", {})
        is_confirmation = intent_analysis.get("is_confirmation", False)
        
        action_plan = {
            "steps": [],
            "reasoning": ""
        }
        
        # Handle confirmations first
        if is_confirmation or intent == "confirmation":
            # Look at the last assistant message to determine what was offered
            last_assistant_msg = None
            for msg in reversed(context.message_history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "")
                    break
            
            # Default to showing documents and statistics when confirming initial greeting
            if "documentos" in last_assistant_msg.lower() or "estadísticas" in last_assistant_msg.lower():
                action_plan["steps"].append({
                    "action": AgentCapability.SEARCH_DOCUMENTS,
                    "parameters": {"query": [], "filters": {}}
                })
                action_plan["steps"].append({
                    "action": AgentCapability.GET_STATISTICS,
                    "parameters": {}
                })
                action_plan["reasoning"] = "User confirmed, showing documents and statistics"
                return action_plan
        
        # Build action plan based on intent
        if "buscar" in intent.lower() or "search" in intent.lower() or intent == "search_documents":
            action_plan["steps"].append({
                "action": AgentCapability.SEARCH_DOCUMENTS,
                "parameters": {
                    "query": entities.get("document_names", []),
                    "filters": entities
                }
            })
            
        elif "analizar" in intent.lower() or "analyze" in intent.lower():
            # First search for documents, then analyze
            if entities.get("document_names"):
                action_plan["steps"].append({
                    "action": AgentCapability.SEARCH_DOCUMENTS,
                    "parameters": {"query": entities["document_names"]}
                })
            action_plan["steps"].append({
                "action": AgentCapability.ANALYZE_DOCUMENT,
                "parameters": entities
            })
            
        elif "firma" in intent.lower() or "signature" in intent.lower():
            action_plan["steps"].append({
                "action": AgentCapability.CREATE_SIGNATURE_REQUEST,
                "parameters": entities
            })
            
        elif "compartir" in intent.lower() or "share" in intent.lower():
            action_plan["steps"].append({
                "action": AgentCapability.SHARE_DOCUMENT,
                "parameters": entities
            })
            
        elif "estadistica" in intent.lower() or "statistics" in intent.lower():
            action_plan["steps"].append({
                "action": AgentCapability.GET_STATISTICS,
                "parameters": {}
            })
            
        else:
            # Default to general knowledge
            action_plan["steps"].append({
                "action": AgentCapability.GENERAL_KNOWLEDGE,
                "parameters": {"query": intent_analysis}
            })
        
        action_plan["reasoning"] = f"Based on intent '{intent}', planned {len(action_plan['steps'])} actions"
        return action_plan
    
    async def _execute_actions(self, action_plan: Dict[str, Any], context: AgentContext) -> List[Dict[str, Any]]:
        """
        Execute planned actions
        """
        results = []
        
        for step in action_plan.get("steps", []):
            action = step.get("action")
            parameters = step.get("parameters", {})
            
            try:
                if action == AgentCapability.SEARCH_DOCUMENTS:
                    result = await self._search_documents(parameters, context)
                    
                elif action == AgentCapability.ANALYZE_DOCUMENT:
                    result = await self._analyze_document(parameters, context)
                    
                elif action == AgentCapability.GET_STATISTICS:
                    result = await self._get_statistics(context)
                    
                elif action == AgentCapability.CREATE_SIGNATURE_REQUEST:
                    result = await self._prepare_signature_request(parameters, context)
                    
                elif action == AgentCapability.SHARE_DOCUMENT:
                    result = await self._prepare_share_document(parameters, context)
                    
                else:
                    result = await self._general_knowledge(parameters, context)
                
                results.append({
                    "action": action.value if isinstance(action, AgentCapability) else action,
                    "success": True,
                    "result": result
                })
                
                context.tools_used.append(action.value if isinstance(action, AgentCapability) else str(action))
                
            except Exception as e:
                logger.error(f"Action execution error for {action}: {e}")
                results.append({
                    "action": action.value if isinstance(action, AgentCapability) else action,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    async def _search_documents(self, parameters: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Search for documents using vector search
        """
        query = " ".join(parameters.get("query", []))
        if not query:
            query = " ".join(parameters.get("filters", {}).get("document_names", []))
        
        if not query:
            return {"error": "No search query provided"}
        
        # Perform vector search
        search_results = await self.vector_service.search_documents(
            query=query,
            tenant_id=context.tenant_id,
            limit=5
        )
        
        # Get document details
        documents = []
        for result in search_results:
            doc_query = select(Document).where(
                Document.id == result["document_id"],
                Document.tenant_id == context.tenant_id
            )
            doc_result = await context.db_session.execute(doc_query)
            doc = doc_result.scalar_one_or_none()
            
            if doc:
                documents.append({
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "title": doc.title or doc.filename,
                    "summary": doc.summary,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "relevance_score": result.get("score", 0),
                    "tenant_id": context.tenant_id  # Include for link generation
                })
        
        # Store in working memory for follow-up actions
        context.working_memory["found_documents"] = documents
        
        return {
            "documents_found": len(documents),
            "documents": documents
        }
    
    async def _analyze_document(self, parameters: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Analyze document content
        """
        # Get documents from working memory or search
        documents = context.working_memory.get("found_documents", [])
        
        if not documents:
            return {"error": "No documents to analyze"}
        
        # Analyze first document
        doc = documents[0]
        
        # Get full document content if needed
        doc_service = AsyncDocumentService(context.db_session)
        
        analysis = {
            "document": doc["filename"],
            "summary": doc.get("summary", ""),
            "key_points": [],
            "entities": [],
            "recommendations": []
        }
        
        if doc.get("summary"):
            analysis["detailed_analysis"] = doc.get("summary")
        
        return analysis
    
    async def _get_statistics(self, context: AgentContext) -> Dict[str, Any]:
        """
        Get tenant statistics.

        Combines counts from both Document (uploads) and IndexedDocument (connectors).
        """
        from datetime import timedelta

        tenant_uuid = UUID(context.tenant_id) if isinstance(context.tenant_id, str) else context.tenant_id

        # Document count from Document table (direct uploads)
        doc_count_query = select(func.count(Document.id)).where(
            Document.tenant_id == tenant_uuid
        )
        doc_count_result = await context.db_session.execute(doc_count_query)
        doc_uploads = doc_count_result.scalar() or 0

        # Document count from IndexedDocument table (connector documents)
        idx_count_query = select(func.count(IndexedDocument.id)).where(
            IndexedDocument.tenant_id == tenant_uuid
        )
        idx_count_result = await context.db_session.execute(idx_count_query)
        idx_documents = idx_count_result.scalar() or 0

        total_documents = doc_uploads + idx_documents

        # Recent documents (last 30 days) - from both tables
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        recent_docs_query = select(func.count(Document.id)).where(
            Document.tenant_id == tenant_uuid,
            Document.created_at >= thirty_days_ago
        )
        recent_docs_result = await context.db_session.execute(recent_docs_query)
        recent_docs = recent_docs_result.scalar() or 0

        recent_idx_query = select(func.count(IndexedDocument.id)).where(
            IndexedDocument.tenant_id == tenant_uuid,
            IndexedDocument.created_at >= thirty_days_ago
        )
        recent_idx_result = await context.db_session.execute(recent_idx_query)
        recent_idx = recent_idx_result.scalar() or 0

        recent_documents = recent_docs + recent_idx

        # Shared documents (only from Document table - IndexedDocument uses different sharing)
        shared_query = select(func.count(DocumentShare.id)).join(
            Document, DocumentShare.document_id == Document.id
        ).where(Document.tenant_id == tenant_uuid)
        shared_result = await context.db_session.execute(shared_query)
        shared_documents = shared_result.scalar() or 0

        # Pending signatures
        signatures_query = select(func.count(SignatureRequest.id)).where(
            SignatureRequest.tenant_id == tenant_uuid,
            SignatureRequest.status == "pending"
        )
        signatures_result = await context.db_session.execute(signatures_query)
        pending_signatures = signatures_result.scalar() or 0

        # Calculate storage estimate
        doc_size_query = select(func.coalesce(func.sum(Document.file_size), 0)).where(
            Document.tenant_id == tenant_uuid
        )
        doc_size_result = await context.db_session.execute(doc_size_query)
        doc_storage = doc_size_result.scalar() or 0

        idx_size_query = select(func.coalesce(func.sum(IndexedDocument.size_bytes), 0)).where(
            IndexedDocument.tenant_id == tenant_uuid
        )
        idx_size_result = await context.db_session.execute(idx_size_query)
        idx_storage = idx_size_result.scalar() or 0

        total_storage_mb = (doc_storage + idx_storage) / (1024 * 1024)

        return {
            "total_documents": total_documents,
            "recent_documents": recent_documents,
            "shared_documents": shared_documents,
            "pending_signatures": pending_signatures,
            "storage_used": f"{total_storage_mb:.1f} MB",
            "breakdown": {
                "uploads": doc_uploads,
                "connectors": idx_documents
            }
        }
    
    async def _prepare_signature_request(self, parameters: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Prepare signature request information
        """
        documents = context.working_memory.get("found_documents", [])
        
        if not documents:
            return {
                "status": "need_document_selection",
                "message": "Primero necesitas seleccionar un documento para firmar",
                "instructions": [
                    "Busca el documento que necesitas firmar",
                    "Selecciona el documento",
                    "Indica los firmantes"
                ]
            }
        
        return {
            "status": "ready_to_create",
            "document": documents[0],
            "next_steps": [
                "Añadir correos de los firmantes",
                "Definir orden de firma",
                "Establecer fecha límite",
                "Enviar solicitud"
            ]
        }
    
    async def _prepare_share_document(self, parameters: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Prepare document sharing information
        """
        documents = context.working_memory.get("found_documents", [])
        
        if not documents:
            return {
                "status": "need_document_selection",
                "message": "Primero necesitas seleccionar un documento para compartir"
            }
        
        return {
            "status": "ready_to_share",
            "document": documents[0],
            "sharing_options": [
                "Enlace público (cualquiera con el enlace)",
                "Usuarios específicos (por email)",
                "Compartir con el equipo"
            ],
            "permission_levels": ["Ver", "Comentar", "Editar"]
        }
    
    async def _general_knowledge(self, parameters: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Handle general knowledge queries
        """
        return {
            "type": "general_assistance",
            "available_actions": [
                "Buscar documentos",
                "Subir nuevos documentos",
                "Solicitar firmas",
                "Compartir documentos",
                "Ver estadísticas",
                "Configurar notificaciones"
            ]
        }
    
    async def _generate_response(
        self,
        intent_analysis: Dict[str, Any],
        action_results: List[Dict[str, Any]],
        context: AgentContext
    ) -> Dict[str, str]:
        """Generate a lightweight natural language response based on action results."""
        successful_actions = [r for r in action_results if r.get("success")]
        if not successful_actions:
            return {
                "message": self._generate_fallback_response(action_results),
                "confidence": 0.4,
                "requires_confirmation": False
            }
        
        results_summary = self._format_action_results(successful_actions)
        message = (
            "He completado las siguientes acciones:\n"
            f"{results_summary or 'Sin resultados detallados.'}"
        )
        return {
            "message": message,
            "confidence": 0.75,
            "requires_confirmation": False
        }
    
    async def _generate_suggestions(
        self,
        intent_analysis: Dict[str, Any],
        action_results: List[Dict[str, Any]],
        context: AgentContext
    ) -> List[str]:
        """
        Generate contextual suggestions for next actions
        """
        suggestions = []
        
        # Based on successful actions
        for result in action_results:
            if result.get("success"):
                action = result.get("action")
                
                if action == AgentCapability.SEARCH_DOCUMENTS.value:
                    docs = result.get("result", {}).get("documents", [])
                    if docs:
                        suggestions.extend([
                            f"Ver detalles de {docs[0]['filename']}",
                            "Compartir este documento",
                            "Solicitar firma para este documento"
                        ])
                    else:
                        suggestions.append("Buscar con otros términos")
                        
                elif action == AgentCapability.GET_STATISTICS.value:
                    suggestions.extend([
                        "Ver documentos recientes",
                        "Exportar reporte detallado",
                        "Configurar alertas"
                    ])
        
        # Default suggestions if none generated
        if not suggestions:
            suggestions = [
                "Buscar documentos",
                "Ver estadísticas",
                "Subir nuevo documento",
                "Obtener ayuda"
            ]
        
        return suggestions[:4]  # Limit to 4 suggestions
    
    def _format_history(self, messages: List[Dict[str, Any]]) -> str:
        """Format message history for context"""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted.append(f"{role.capitalize()}: {content}")
        return "\n".join(formatted)
    
    def _format_action_results(self, results: List[Dict[str, Any]]) -> str:
        """Format action results for LLM"""
        formatted = []
        for result in results:
            action = result.get("action", "unknown")
            data = result.get("result", {})
            
            if action == AgentCapability.SEARCH_DOCUMENTS.value:
                docs = data.get("documents", [])
                if docs:
                    formatted.append(f"Encontré {len(docs)} documento(s):")
                    for doc in docs[:5]:  # Show up to 5 documents
                        doc_id = doc.get('id', '')
                        tenant_id = doc.get('tenant_id', '')
                        filename = doc.get('filename', 'Sin nombre')
                        title = doc.get('title', filename)
                        summary = doc.get('summary', '')[:200] + '...' if doc.get('summary') else 'Sin resumen disponible'
                        relevance = doc.get('relevance_score', 0)
                        
                        # Format with markdown link - correct path structure
                        formatted.append(f"\n📄 **[{title}](/{tenant_id}/documents/{doc_id}/preview)**")
                        formatted.append(f"   *Archivo:* {filename}")
                        if summary:
                            formatted.append(f"   *Resumen:* {summary}")
                        formatted.append(f"   *Relevancia:* {relevance:.0%}")
                else:
                    formatted.append("No encontré documentos con esos criterios")
                    
            elif action == AgentCapability.GET_STATISTICS.value:
                formatted.append("Estadísticas del sistema:")
                formatted.append(f"  - Total documentos: {data.get('total_documents', 0)}")
                formatted.append(f"  - Documentos recientes: {data.get('recent_documents', 0)}")
                formatted.append(f"  - Compartidos: {data.get('shared_documents', 0)}")
                formatted.append(f"  - Firmas pendientes: {data.get('pending_signatures', 0)}")
                
            else:
                formatted.append(f"Acción {action}: {json.dumps(data, indent=2)}")
        
        return "\n".join(formatted)
    
    def _generate_fallback_response(self, action_results: List[Dict[str, Any]]) -> str:
        """Generate fallback response when LLM fails"""
        if not action_results:
            return "No pude procesar tu solicitud. ¿Podrías ser más específico?"
        
        successful = [r for r in action_results if r.get("success")]
        if successful:
            return "He completado las acciones solicitadas. ¿Hay algo más en lo que pueda ayudarte?"
        else:
            return "Encontré algunos problemas al procesar tu solicitud. Por favor, intenta de nuevo."
    
    async def _get_user_stats(self, context: AgentContext) -> Dict[str, Any]:
        """Get user statistics for personalization"""
        try:
            db = context.db_session
            user = context.user
            
            # Get document count
            doc_count = await db.execute(
                select(func.count(Document.id)).where(
                    Document.created_by == user.id,
                    Document.tenant_id == context.tenant_id
                )
            )
            total_documents = doc_count.scalar() or 0
            
            # Get recent activity
            recent_doc = await db.execute(
                select(Document).where(
                    Document.created_by == user.id,
                    Document.tenant_id == context.tenant_id
                ).order_by(Document.updated_at.desc()).limit(1)
            )
            recent = recent_doc.scalar_one_or_none()
            
            recent_activity = "No recent activity"
            if recent:
                days_ago = (datetime.utcnow() - recent.updated_at).days
                if days_ago == 0:
                    recent_activity = "Worked on documents today"
                elif days_ago == 1:
                    recent_activity = "Worked on documents yesterday"
                else:
                    recent_activity = f"Last activity {days_ago} days ago"
            
            # Calculate days since joined (using created_at if available)
            days_since_joined = "recently"
            if hasattr(user, 'created_at') and user.created_at:
                days = (datetime.utcnow() - user.created_at).days
                if days == 0:
                    days_since_joined = "today"
                elif days < 7:
                    days_since_joined = f"{days} days ago"
                elif days < 30:
                    weeks = days // 7
                    days_since_joined = f"{weeks} weeks ago"
                else:
                    months = days // 30
                    days_since_joined = f"{months} months ago"
            
            return {
                "total_documents": total_documents,
                "recent_activity": recent_activity,
                "days_since_joined": days_since_joined,
                "last_login": "today",
                "has_documents": total_documents > 0
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {
                "total_documents": 0,
                "recent_activity": "No recent activity",
                "days_since_joined": "recently",
                "last_login": "today",
                "has_documents": False
            }
    
    async def _format_document_response(
        self,
        documents: List[Dict[str, Any]],
        message: str,
        context: AgentContext
    ) -> str:
        """Format document results with clickable links"""
        if not documents:
            return message
        
        # Add document links to the message
        doc_section = "\n\n📚 **Documentos encontrados:**\n"
        for doc in documents[:5]:
            doc_id = doc.get('id', '')
            title = doc.get('title', doc.get('filename', 'Sin título'))
            summary = doc.get('summary', '')[:150] + '...' if doc.get('summary') else ''
            
            # Create markdown link
            doc_section += f"\n📄 **[{title}](/{context.tenant_id}/documents/{doc_id}/preview)**"
            if summary:
                doc_section += f"\n   {summary}"
        
        # Append to message if not already included
        if "](/documents/" not in message and documents:
            message += doc_section
        
        return message
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM"""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(response)
        except:
            # Fallback parsing
            return {
                "primary_intent": "general",
                "entities": {},
                "parameters": {},
                "confidence": 0.5
            }

    async def _analyze_intent_simple(self, message: str, context: AgentContext) -> Dict[str, Any]:
        """
        Simple intent analysis for fallback scenarios
        """
        lower_msg = message.lower()
        if any(word in lower_msg for word in ["firma", "firmar", "signature", "sign"]):
            return {"primary_intent": "signature_request", "entities": {}, "confidence": 0.8}
        if any(word in lower_msg for word in ["buscar", "search", "encontrar"]):
            return {"primary_intent": "search_documents", "entities": {}, "confidence": 0.8}
        if any(word in lower_msg for word in ["estadísticas", "stats", "números"]):
            return {"primary_intent": "get_statistics", "entities": {}, "confidence": 0.8}
        return {"primary_intent": "general", "entities": {}, "confidence": 0.5}


# Singleton instance
assistant_agent = VirtualAssistantAgent()
