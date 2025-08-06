"""
Virtual Assistant API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime
import json

from app.db.async_database import get_async_db
from app.db.models import User, Document, Tenant
from app.api.dependencies import get_current_user
from app.services.llm_service import LLMService
from app.services.async_document_service import AsyncDocumentService
from app.services.search_service import SearchService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    """Chat message request model"""
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    conversation_id: str
    metadata: Optional[Dict[str, Any]] = None
    suggestions: Optional[list[str]] = None


class AssistantService:
    """Virtual assistant service for handling chat interactions"""
    
    def __init__(self):
        self.llm_service = LLMService()
        
    async def process_message(
        self,
        message: str,
        user: User,
        tenant_id: str,
        db: AsyncSession,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a user message and generate an assistant response
        
        Args:
            message: User's message
            user: Current user
            tenant_id: Tenant ID
            db: Database session
            conversation_id: Optional conversation ID for context
            
        Returns:
            Response dictionary with assistant's reply and metadata
        """
        try:
            # Analyze message intent
            intent = await self._analyze_intent(message)
            
            # Generate contextual response based on intent
            if intent == "document_search":
                response = await self._handle_document_search(message, user, tenant_id, db)
            elif intent == "document_upload":
                response = await self._handle_document_upload_query(message, user)
            elif intent == "signature_request":
                response = await self._handle_signature_query(message, user)
            elif intent == "share_document":
                response = await self._handle_share_query(message, user)
            elif intent == "analytics":
                response = await self._handle_analytics_query(message, user, tenant_id, db)
            else:
                response = await self._handle_general_query(message, user)
            
            # Generate suggestions for next actions
            suggestions = await self._generate_suggestions(message, intent)
            
            return {
                "response": response,
                "conversation_id": conversation_id or self._generate_conversation_id(),
                "metadata": {
                    "intent": intent,
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_id": user.id,
                },
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error processing assistant message: {e}")
            return {
                "response": "Lo siento, hubo un error procesando tu mensaje. ¿Podrías reformularlo?",
                "conversation_id": conversation_id or self._generate_conversation_id(),
                "metadata": {"error": str(e)},
                "suggestions": [
                    "Ver mis documentos",
                    "Buscar un documento",
                    "Subir un nuevo documento"
                ]
            }
    
    async def _analyze_intent(self, message: str) -> str:
        """Analyze user message to determine intent"""
        message_lower = message.lower()
        
        # Document search keywords
        if any(word in message_lower for word in ["buscar", "encontrar", "search", "find", "documento"]):
            return "document_search"
        
        # Upload keywords
        if any(word in message_lower for word in ["subir", "cargar", "upload", "añadir", "agregar"]):
            return "document_upload"
        
        # Signature keywords
        if any(word in message_lower for word in ["firma", "firmar", "signature", "sign"]):
            return "signature_request"
        
        # Share keywords
        if any(word in message_lower for word in ["compartir", "share", "enviar", "send"]):
            return "share_document"
        
        # Analytics keywords
        if any(word in message_lower for word in ["estadística", "analytics", "reporte", "informe", "análisis"]):
            return "analytics"
        
        return "general"
    
    async def _handle_document_search(
        self, message: str, user: User, tenant_id: str, db: AsyncSession
    ) -> str:
        """Handle document search queries"""
        try:
            # Extract search terms
            search_service = SearchService(db)
            
            # Perform search
            results = await search_service.search_documents(
                query=message,
                tenant_id=tenant_id,
                user_id=user.id,
                limit=5
            )
            
            if results:
                response = "He encontrado los siguientes documentos:\n\n"
                for i, doc in enumerate(results, 1):
                    response += f"{i}. **{doc.get('filename', 'Sin nombre')}**\n"
                    response += f"   Tipo: {doc.get('document_type', 'General')}\n"
                    response += f"   Fecha: {doc.get('created_at', '')[:10]}\n\n"
                response += "¿Te gustaría ver alguno de estos documentos?"
            else:
                response = "No encontré documentos que coincidan con tu búsqueda. ¿Podrías ser más específico?"
                
            return response
            
        except Exception as e:
            logger.error(f"Error in document search: {e}")
            return "Hubo un problema al buscar documentos. Por favor, intenta de nuevo."
    
    async def _handle_document_upload_query(self, message: str, user: User) -> str:
        """Handle document upload queries"""
        return (
            "Para subir un documento, puedes:\n\n"
            "1. **Hacer clic en el botón '+ Subir Documento'** en la barra superior\n"
            "2. **Arrastrar y soltar** archivos directamente en la pantalla\n"
            "3. **Usar el atajo de teclado** Ctrl+U (o Cmd+U en Mac)\n\n"
            "Formatos soportados: PDF, Word, Excel, PowerPoint, imágenes y más.\n"
            "Tamaño máximo: 10 MB por archivo."
        )
    
    async def _handle_signature_query(self, message: str, user: User) -> str:
        """Handle signature-related queries"""
        return (
            "Para solicitar una firma digital:\n\n"
            "1. **Selecciona el documento** que necesitas firmar\n"
            "2. **Haz clic en 'Solicitar Firma'** en las opciones del documento\n"
            "3. **Añade los firmantes** con sus correos electrónicos\n"
            "4. **Marca las áreas de firma** en el documento\n"
            "5. **Envía la solicitud**\n\n"
            "Los firmantes recibirán un email con el enlace para firmar."
        )
    
    async def _handle_share_query(self, message: str, user: User) -> str:
        """Handle document sharing queries"""
        return (
            "Para compartir un documento:\n\n"
            "1. **Selecciona el documento** que deseas compartir\n"
            "2. **Haz clic en 'Compartir'** en las opciones\n"
            "3. **Ingresa el email** del destinatario\n"
            "4. **Configura los permisos** (ver, editar, descargar)\n"
            "5. **Establece la expiración** (opcional)\n\n"
            "El destinatario recibirá un enlace seguro para acceder al documento."
        )
    
    async def _handle_analytics_query(
        self, message: str, user: User, tenant_id: str, db: AsyncSession
    ) -> str:
        """Handle analytics and reporting queries"""
        try:
            # Get basic stats
            doc_service = AsyncDocumentService(db)
            stats = await doc_service.get_tenant_statistics(tenant_id)
            
            response = "📊 **Resumen de tu cuenta:**\n\n"
            response += f"• Total de documentos: {stats.get('total_documents', 0)}\n"
            response += f"• Documentos este mes: {stats.get('documents_this_month', 0)}\n"
            response += f"• Espacio usado: {stats.get('storage_used', '0 MB')}\n"
            response += f"• Documentos compartidos: {stats.get('shared_documents', 0)}\n"
            response += f"• Firmas pendientes: {stats.get('pending_signatures', 0)}\n\n"
            response += "¿Necesitas información más detallada sobre algo específico?"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return "No pude obtener las estadísticas en este momento. Por favor, visita la página de Analytics."
    
    async def _handle_general_query(self, message: str, user: User) -> str:
        """Handle general queries"""
        return (
            "Soy tu asistente virtual y puedo ayudarte con:\n\n"
            "📄 **Documentos**: Buscar, subir, organizar\n"
            "✍️ **Firmas**: Solicitar y gestionar firmas digitales\n"
            "🤝 **Compartir**: Enviar documentos de forma segura\n"
            "📊 **Análisis**: Ver estadísticas y reportes\n"
            "🔍 **Búsqueda**: Encontrar información específica\n\n"
            "¿Qué te gustaría hacer?"
        )
    
    async def _generate_suggestions(self, message: str, intent: str) -> list[str]:
        """Generate contextual suggestions based on user's intent"""
        if intent == "document_search":
            return [
                "Ver todos mis documentos",
                "Filtrar por tipo de documento",
                "Buscar por fecha"
            ]
        elif intent == "document_upload":
            return [
                "Subir múltiples archivos",
                "Organizar documentos en carpetas",
                "Ver documentos recientes"
            ]
        elif intent == "signature_request":
            return [
                "Ver solicitudes pendientes",
                "Configurar plantilla de firma",
                "Ver historial de firmas"
            ]
        elif intent == "share_document":
            return [
                "Ver documentos compartidos conmigo",
                "Gestionar permisos",
                "Crear enlace público"
            ]
        else:
            return [
                "Ver mis documentos",
                "Subir un documento",
                "Buscar información",
                "Ver estadísticas"
            ]
    
    def _generate_conversation_id(self) -> str:
        """Generate a unique conversation ID"""
        from uuid import uuid4
        return str(uuid4())


# Initialize service
assistant_service = AssistantService()


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> ChatResponse:
    """
    Chat with the virtual assistant
    
    The assistant can help with:
    - Document search and management
    - Digital signature requests
    - Document sharing
    - Analytics and reports
    - General platform guidance
    """
    try:
        # Get tenant ID from context or user
        tenant_id = request.context.get("tenant_id") if request.context else current_user.tenant_id
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant ID is required"
            )
        
        # Process message
        result = await assistant_service.process_message(
            message=request.message,
            user=current_user,
            tenant_id=tenant_id,
            db=db,
            conversation_id=request.conversation_id
        )
        
        return ChatResponse(**result)
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing chat message"
        )


@router.get("/suggestions")
async def get_suggestions(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get contextual suggestions for the user
    """
    return {
        "suggestions": [
            {
                "id": "upload",
                "text": "Subir un documento",
                "icon": "upload",
                "action": "/documents/upload"
            },
            {
                "id": "search",
                "text": "Buscar documentos",
                "icon": "search",
                "action": "/search"
            },
            {
                "id": "signatures",
                "text": "Ver firmas pendientes",
                "icon": "signature",
                "action": "/signatures"
            },
            {
                "id": "analytics",
                "text": "Ver estadísticas",
                "icon": "chart",
                "action": "/analytics"
            }
        ]
    }


@router.get("/help/{topic}")
async def get_help_content(
    topic: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get help content for a specific topic
    """
    help_topics = {
        "upload": {
            "title": "Cómo subir documentos",
            "content": "Guía para subir y organizar documentos...",
            "video_url": None,
            "related": ["organize", "search", "share"]
        },
        "signature": {
            "title": "Firmas digitales",
            "content": "Cómo solicitar y gestionar firmas digitales...",
            "video_url": None,
            "related": ["providers", "templates", "tracking"]
        },
        "share": {
            "title": "Compartir documentos",
            "content": "Opciones para compartir documentos de forma segura...",
            "video_url": None,
            "related": ["permissions", "expiration", "tracking"]
        }
    }
    
    if topic not in help_topics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Help topic not found"
        )
    
    return help_topics[topic]