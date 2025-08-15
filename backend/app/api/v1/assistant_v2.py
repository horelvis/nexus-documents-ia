"""
Virtual Assistant API v2 - Agent-based implementation
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import json
import asyncio
import logging

from app.db.async_database import get_async_db
from app.db.models import User, Document, Tenant
from app.api.dependencies import get_current_user
from app.services.cag_client import CAGClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant/v2", tags=["assistant-v2"])


def extract_regional_context(request: Request) -> Dict[str, str]:
    """Extraer configuración regional del request del usuario"""
    context = {}
    
    # Extraer Accept-Language header
    accept_language = request.headers.get("accept-language", "")
    if accept_language:
        # Formato: "es-ES,es;q=0.9,en;q=0.8"
        languages = accept_language.split(",")
        if languages:
            primary_lang = languages[0].split(";")[0].strip()
            
            # Separar idioma y país
            if "-" in primary_lang:
                locale, country = primary_lang.split("-", 1)
                context["locale"] = locale.lower()
                context["country"] = country.lower()
                context["accept_language"] = primary_lang.lower()
            else:
                context["locale"] = primary_lang.lower()
                context["accept_language"] = primary_lang.lower()
                # Mapear idioma a país por defecto
                lang_to_country = {
                    "es": "es", "en": "us", "fr": "fr", "de": "de", 
                    "it": "it", "pt": "pt", "ca": "es", "eu": "es"
                }
                context["country"] = lang_to_country.get(primary_lang.lower(), "us")
    
    # Headers adicionales que algunos navegadores/aplicaciones envían
    country_header = request.headers.get("cf-ipcountry") or request.headers.get("x-country")
    if country_header:
        context["country"] = country_header.lower()
    
    # Valores por defecto si no se encuentra nada
    if not context.get("locale"):
        context["locale"] = "es"
    if not context.get("country"):
        context["country"] = "es"
        
    return context


class ChatMessage(BaseModel):
    """Chat message request model"""
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    stream: bool = Field(default=False, description="Enable streaming response")


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    conversation_id: str
    actions_taken: List[Dict[str, Any]]
    suggestions: List[str]
    confidence: float
    metadata: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False


class ConversationMemory:
    """Simple in-memory conversation storage (replace with Redis in production)"""
    _conversations: Dict[str, List[Dict[str, Any]]] = {}
    
    @classmethod
    def get_history(cls, conversation_id: str) -> List[Dict[str, Any]]:
        return cls._conversations.get(conversation_id, [])
    
    @classmethod
    def add_message(cls, conversation_id: str, message: Dict[str, Any]):
        if conversation_id not in cls._conversations:
            cls._conversations[conversation_id] = []
        cls._conversations[conversation_id].append(message)
        
        # Keep only last 20 messages per conversation
        if len(cls._conversations[conversation_id]) > 20:
            cls._conversations[conversation_id] = cls._conversations[conversation_id][-20:]
    
    @classmethod
    def clear_conversation(cls, conversation_id: str):
        if conversation_id in cls._conversations:
            del cls._conversations[conversation_id]


# Initialize CAG client for real agent processing
cag_client = CAGClient()


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> ChatResponse:
    """
    Chat with the AI agent-based virtual assistant
    
    This endpoint uses an advanced agent with:
    - Tool use capabilities (search, analyze, share, etc.)
    - Conversation memory
    - Multi-step reasoning
    - Action planning and execution
    """
    try:
        # Get or create conversation ID
        conversation_id = request.conversation_id or _generate_conversation_id()
        
        # Get tenant ID
        tenant_id = request.context.get("tenant_id") if request.context else current_user.tenant_id
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant ID is required"
            )
        
        # Check if this is a welcome message request
        is_welcome = request.context and request.context.get("is_welcome", False)
        
        # Get conversation history
        message_history = ConversationMemory.get_history(conversation_id)
        
        # For welcome messages, enhance the message to be more specific
        actual_message = chat_request.message
        if is_welcome and "SYSTEM:" in chat_request.message:
            # Get basic stats for personalized welcome
            try:
                from sqlalchemy import select, func
                from app.db.models import Document, SignatureRequest
                
                # Get document count
                doc_query = select(func.count(Document.id)).where(Document.tenant_id == tenant_id)
                doc_result = await db.execute(doc_query)
                document_count = doc_result.scalar() or 0
                
                # Get pending signatures
                sig_query = select(func.count(SignatureRequest.id)).where(
                    SignatureRequest.tenant_id == tenant_id,
                    SignatureRequest.status == "pending"
                )
                sig_result = await db.execute(sig_query)
                pending_signatures = sig_result.scalar() or 0
                
                actual_message = f"Generate a personalized welcome message for {current_user.full_name or 'this user'}. They have {document_count} documents and {pending_signatures} pending signatures."
                
            except Exception as e:
                logger.warning(f"Could not get stats for welcome: {e}")
                actual_message = f"Generate a personalized welcome message for {current_user.full_name or 'this user'}"
        
        # Prepare context for CAG/CrewAI
        cag_context = {
            "tenant_id": str(tenant_id),  # Convert UUID to string
            "user_id": str(current_user.id),  # Convert UUID to string
            "conversation_id": conversation_id,
            "message_history": message_history[-5:],  # Last 5 messages
            "is_welcome": is_welcome,
            "user_email": current_user.email,
            "user_name": current_user.full_name or "Usuario"
        }
        
        # Process with CrewAI via CAG service
        logger.info(f"Processing with CAG - Message: {actual_message[:100]}")
        logger.info(f"CAG Context: {cag_context}")
        
        cag_response = await cag_client.process_with_agent(
            message=actual_message,
            context=cag_context,
            agent_type="virtual_assistant",
            tools=["search_documents", "analyze_document", "get_statistics", "signature_request", "document_sharing"]
        )
        
        logger.info(f"CAG Response: {cag_response}")
        
        # Extract response from CAG
        if cag_response.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent processing error: {cag_response['error']}"
            )
        
        response_message = cag_response.get("response", "I'm sorry, I couldn't process your request.")
        actions_taken = cag_response.get("actions", [])
        suggestions = cag_response.get("suggestions", ["Ask about your documents", "Check signatures", "Get statistics"])
        confidence = cag_response.get("confidence", 0.8)
        
        # Store in conversation memory
        ConversationMemory.add_message(conversation_id, {
            "role": "user",
            "content": chat_request.message,
            "timestamp": datetime.utcnow().isoformat()
        })
        ConversationMemory.add_message(conversation_id, {
            "role": "assistant",
            "content": response_message,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": cag_response.get("metadata", {})
        })
        
        return ChatResponse(
            response=response_message,
            conversation_id=conversation_id,
            actions_taken=actions_taken,
            suggestions=suggestions,
            confidence=confidence,
            metadata=cag_response.get("metadata", {}),
            requires_confirmation=cag_response.get("requires_confirmation", False)
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Agent chat error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}"
        )


@router.post("/chat/stream")
async def chat_with_agent_stream(
    chat_request: ChatMessage,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Stream chat responses from the agent
    
    Returns a Server-Sent Events stream for real-time responses
    """
    conversation_id = chat_request.conversation_id or _generate_conversation_id()
    tenant_id = chat_request.context.get("tenant_id") if chat_request.context else current_user.tenant_id
    
    # Extraer configuración regional del request HTTP
    regional_context = extract_regional_context(request)
    
    async def generate():
        try:
            # Send initial acknowledgment
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id})}\n\n"
            
            # Get conversation history
            message_history = ConversationMemory.get_history(conversation_id)
            
            # Prepare context for CAG/CrewAI
            cag_context = {
                "tenant_id": str(tenant_id),  # Convert UUID to string
                "user_id": str(current_user.id),  # Convert UUID to string
                "conversation_id": conversation_id,
                "message_history": message_history[-5:],
                "user_email": current_user.email,
                "user_name": current_user.full_name or "Usuario",
                # Agregar configuración regional para SerperDevTool dinámico
                **regional_context
            }
            
            # Process with CrewAI via CAG service
            cag_response = await cag_client.process_with_agent(
                message=chat_request.message,
                context=cag_context,
                agent_type="virtual_assistant",
                tools=["search_documents", "analyze_document", "get_statistics", "signature_request"]
            )
            
            if cag_response.get("error"):
                yield f"data: {json.dumps({'type': 'error', 'error': cag_response['error']})}\n\n"
                return
                
            agent_message = cag_response.get("response", "No response generated")
            
            # Stream the response in chunks
            words = agent_message.split()
            current_chunk = ""
            
            for i, word in enumerate(words):
                current_chunk += word + " "
                
                # Send chunk every 5 words or at the end
                if (i + 1) % 5 == 0 or i == len(words) - 1:
                    yield f"data: {json.dumps({'type': 'content', 'content': current_chunk})}\n\n"
                    current_chunk = ""
                    await asyncio.sleep(0.05)  # Small delay for streaming effect
            
            # Send metadata and suggestions
            metadata_data = {
                'type': 'metadata',
                'actions': cag_response.get("actions", []),
                'suggestions': cag_response.get("suggestions", []),
                'confidence': cag_response.get("confidence", 0.8)
            }
            yield f"data: {json.dumps(metadata_data)}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
            # Store in memory
            ConversationMemory.add_message(conversation_id, {
                "role": "user",
                "content": chat_request.message,
                "timestamp": datetime.utcnow().isoformat()
            })
            ConversationMemory.add_message(conversation_id, {
                "role": "assistant",
                "content": agent_message,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/conversation/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get conversation history
    """
    history = ConversationMemory.get_history(conversation_id)
    
    return {
        "conversation_id": conversation_id,
        "messages": history,
        "message_count": len(history)
    }


@router.delete("/conversation/{conversation_id}")
async def clear_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Clear conversation history
    """
    ConversationMemory.clear_conversation(conversation_id)
    
    return {
        "status": "success",
        "message": "Conversation cleared"
    }


@router.post("/feedback")
async def submit_feedback(
    conversation_id: str,
    message_id: str,
    feedback: str,
    rating: Optional[int] = None,
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Submit feedback for a specific message
    """
    # In production, store this in database
    logger.info(f"Feedback received - User: {current_user.id}, Conversation: {conversation_id}, Rating: {rating}")
    
    return {
        "status": "success",
        "message": "Feedback received"
    }


@router.get("/capabilities")
async def get_agent_capabilities(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get agent capabilities and available tools
    """
    return {
        "capabilities": [
            {
                "name": "search_documents",
                "description": "Buscar documentos por contenido o metadatos",
                "parameters": ["query", "filters", "date_range"]
            },
            {
                "name": "analyze_document",
                "description": "Analizar contenido y extraer información clave",
                "parameters": ["document_id", "analysis_type"]
            },
            {
                "name": "create_signature_request",
                "description": "Preparar solicitud de firma digital",
                "parameters": ["document_id", "signers", "deadline"]
            },
            {
                "name": "share_document",
                "description": "Compartir documentos con permisos específicos",
                "parameters": ["document_id", "recipients", "permissions"]
            },
            {
                "name": "get_statistics",
                "description": "Obtener estadísticas y métricas del sistema",
                "parameters": ["metric_type", "date_range"]
            },
            {
                "name": "extract_entities",
                "description": "Extraer entidades como nombres, fechas, cantidades",
                "parameters": ["document_id", "entity_types"]
            }
        ],
        "supported_languages": ["es", "en"],
        "max_context_length": 20,
        "streaming_available": True
    }


def _generate_conversation_id() -> str:
    """Generate unique conversation ID"""
    from uuid import uuid4
    return str(uuid4())