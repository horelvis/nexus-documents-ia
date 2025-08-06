"""
Virtual Assistant API v2 - Agent-based implementation
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
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
from app.services.virtual_assistant_agent import (
    VirtualAssistantAgent,
    AgentContext,
    AgentResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant/v2", tags=["assistant-v2"])


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


# Initialize agent
agent = VirtualAssistantAgent()


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
        
        # Create agent context with welcome flag
        working_memory = {"is_welcome": is_welcome} if is_welcome else {}
        
        context = AgentContext(
            user=current_user,
            tenant_id=tenant_id,
            db_session=db,
            conversation_id=conversation_id,
            message_history=message_history,
            working_memory=working_memory,
            tools_used=[]
        )
        
        # Process request with agent
        agent_response: AgentResponse = await agent.process_request(
            message=request.message,
            context=context
        )
        
        # Store in conversation memory
        ConversationMemory.add_message(conversation_id, {
            "role": "user",
            "content": request.message,
            "timestamp": datetime.utcnow().isoformat()
        })
        ConversationMemory.add_message(conversation_id, {
            "role": "assistant",
            "content": agent_response.message,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": agent_response.metadata
        })
        
        return ChatResponse(
            response=agent_response.message,
            conversation_id=conversation_id,
            actions_taken=agent_response.actions_taken,
            suggestions=agent_response.suggestions,
            confidence=agent_response.confidence,
            metadata=agent_response.metadata,
            requires_confirmation=agent_response.requires_confirmation
        )
        
    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}"
        )


@router.post("/chat/stream")
async def chat_with_agent_stream(
    request: ChatMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Stream chat responses from the agent
    
    Returns a Server-Sent Events stream for real-time responses
    """
    conversation_id = request.conversation_id or _generate_conversation_id()
    tenant_id = request.context.get("tenant_id") if request.context else current_user.tenant_id
    
    async def generate():
        try:
            # Send initial acknowledgment
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id})}\n\n"
            
            # Get conversation history
            message_history = ConversationMemory.get_history(conversation_id)
            
            # Create agent context
            context = AgentContext(
                user=current_user,
                tenant_id=tenant_id,
                db_session=db,
                conversation_id=conversation_id,
                message_history=message_history,
                working_memory={},
                tools_used=[]
            )
            
            # Process with agent
            agent_response = await agent.process_request(
                message=request.message,
                context=context
            )
            
            # Stream the response in chunks
            words = agent_response.message.split()
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
                'actions': agent_response.actions_taken,
                'suggestions': agent_response.suggestions,
                'confidence': agent_response.confidence
            }
            yield f"data: {json.dumps(metadata_data)}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
            # Store in memory
            ConversationMemory.add_message(conversation_id, {
                "role": "user",
                "content": request.message,
                "timestamp": datetime.utcnow().isoformat()
            })
            ConversationMemory.add_message(conversation_id, {
                "role": "assistant",
                "content": agent_response.message,
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