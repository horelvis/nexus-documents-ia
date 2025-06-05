"""
API endpoints for Agent management
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User
from app.services.agent_service import AgentService
from app.schemas.agent import (
    AgentCreate, AgentUpdate, AgentResponse,
    ConversationCreate, ConversationResponse,
    MessageCreate, MessageResponse,
    ExecutionCreate, ExecutionResponse,
    ChatRequest, ChatResponse, StreamingChatResponse,
    AgentExecutionRequest, AgentStats, TenantAgentStats
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================
# AGENT MANAGEMENT
# =====================================

@router.post("/", response_model=AgentResponse)
async def create_agent(
    agent_data: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Crear un nuevo agente (solo administradores)"""
    
    # TODO: Verificar que el usuario es administrador del tenant
    if not current_user.is_superuser:
        # Por ahora, solo superusuarios pueden crear agentes
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create agents"
        )
    
    try:
        agent_service = AgentService(db)
        agent = agent_service.create_agent(
            agent_data, 
            current_user.tenant_id, 
            current_user.id
        )
        return agent
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating agent"
        )


@router.get("/", response_model=List[AgentResponse])
async def get_agents(
    agent_type: Optional[str] = None,
    is_active: Optional[bool] = True,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener agentes del tenant"""
    
    try:
        agent_service = AgentService(db)
        agents = agent_service.get_agents(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            agent_type=agent_type,
            is_active=is_active,
            limit=limit,
            offset=offset
        )
        return agents
        
    except Exception as e:
        logger.error(f"Error getting agents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving agents"
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener un agente específico"""
    
    try:
        agent_service = AgentService(db)
        agent = agent_service.get_agent(agent_id, current_user.tenant_id)
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        # Verificar acceso (público o creado por el usuario)
        if not agent.is_public and agent.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to private agent"
            )
        
        return agent
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving agent"
        )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Actualizar un agente"""
    
    try:
        agent_service = AgentService(db)
        agent = agent_service.update_agent(
            agent_id, 
            agent_data, 
            current_user.tenant_id,
            current_user.id
        )
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        return agent
        
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating agent"
        )


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Eliminar un agente"""
    
    try:
        agent_service = AgentService(db)
        success = agent_service.delete_agent(
            agent_id, 
            current_user.tenant_id,
            current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        return {"message": "Agent deleted successfully"}
        
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    except Exception as e:
        logger.error(f"Error deleting agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting agent"
        )


# =====================================
# CONVERSATION MANAGEMENT
# =====================================

@router.post("/{agent_id}/conversations", response_model=ConversationResponse)
async def create_conversation(
    agent_id: UUID,
    conversation_data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Crear una nueva conversación con un agente"""
    
    try:
        # Verificar que agent_id coincida
        if conversation_data.agent_id != agent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent ID mismatch"
            )
        
        agent_service = AgentService(db)
        conversation = agent_service.create_conversation(
            conversation_data,
            current_user.tenant_id,
            current_user.id
        )
        return conversation
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to agent"
        )
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating conversation"
        )


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    agent_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener conversaciones del usuario"""
    
    try:
        agent_service = AgentService(db)
        conversations = agent_service.get_conversations(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            agent_id=agent_id,
            limit=limit,
            offset=offset
        )
        return conversations
        
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving conversations"
        )


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener mensajes de una conversación"""
    
    try:
        agent_service = AgentService(db)
        messages = agent_service.get_messages(
            conversation_id,
            current_user.tenant_id,
            current_user.id,
            limit=limit,
            offset=offset
        )
        return messages
        
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving messages"
        )


# =====================================
# CHAT INTERFACE
# =====================================

@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat_with_agent(
    agent_id: UUID,
    chat_request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Chat síncrono con un agente"""
    
    try:
        # Verificar acceso al agente
        agent_service = AgentService(db)
        agent = agent_service.get_agent(agent_id, current_user.tenant_id)
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        if not agent.is_public and agent.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to private agent"
            )
        
        # Obtener o crear conversación
        conversation_id = chat_request.conversation_id
        if not conversation_id:
            conversation_data = ConversationCreate(
                agent_id=agent_id,
                title=f"Chat - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            conversation = agent_service.create_conversation(
                conversation_data,
                current_user.tenant_id,
                current_user.id
            )
            conversation_id = conversation.id
        
        # Usar Langroid para todos los agentes
        from app.services.langroid_client import LangroidClient
        
        async with LangroidClient() as client:
            # Crear agente temporal en Langroid
            langroid_agent_id = await client.create_agent(
                agent_type=agent.type,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                configuration=agent.configuration or {}
            )
            
            # Recopilar respuestas del chat
            responses = []
            async for response in client.chat_with_agent(
                agent_id=langroid_agent_id,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                message=chat_request.message,
                conversation_id=str(conversation_id),
                context=chat_request.context
            ):
                responses.append(response)
            
            # Limpiar agente temporal
            await client.delete_agent(langroid_agent_id, current_user.tenant_id, current_user.id)
            
            # Devolver respuesta consolidada
            if responses:
                last_response = responses[-1]
                return ChatResponse(
                    message=last_response.get("content", "Chat completado"),
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    metadata={
                        "responses": responses,
                        "response_count": len(responses),
                        "langroid_agent_id": langroid_agent_id
                    }
                )
            
            return ChatResponse(
                message="No se pudo procesar la solicitud",
                conversation_id=conversation_id,
                agent_id=agent_id,
                metadata={}
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing chat"
        )


@router.post("/{agent_id}/chat/stream")
async def chat_with_agent_stream(
    agent_id: UUID,
    chat_request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Chat con streaming SSE"""
    
    async def event_stream():
        try:
            # Verificar acceso al agente
            agent_service = AgentService(db)
            agent = agent_service.get_agent(agent_id, current_user.tenant_id)
            
            if not agent:
                yield f"data: {{'type': 'error', 'content': 'Agent not found'}}\n\n"
                return
            
            if not agent.is_public and agent.created_by != current_user.id:
                yield f"data: {{'type': 'error', 'content': 'Access denied'}}\n\n"
                return
            
            # Obtener o crear conversación
            conversation_id = chat_request.conversation_id
            if not conversation_id:
                conversation_data = ConversationCreate(
                    agent_id=agent_id,
                    title=f"Chat - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                conversation = agent_service.create_conversation(
                    conversation_data,
                    current_user.tenant_id,
                    current_user.id
                )
                conversation_id = conversation.id
                
                # Enviar ID de conversación
                yield f"data: {{'type': 'conversation_id', 'content': '{conversation_id}'}}\n\n"
            
            # Usar Langroid para todos los agentes
            from app.services.langroid_client import LangroidClient
            
            async with LangroidClient() as client:
                # Crear agente temporal en Langroid
                langroid_agent_id = await client.create_agent(
                    agent_type=agent.type,
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    configuration=agent.configuration or {}
                )
                
                yield f"data: {{'type': 'langroid_agent_created', 'content': 'Agent created', 'agent_id': '{langroid_agent_id}'}}\n\n"
                
                # Streaming del chat
                async for response in client.chat_with_agent(
                    agent_id=langroid_agent_id,
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    message=chat_request.message,
                    conversation_id=str(conversation_id),
                    context=chat_request.context
                ):
                    import json
                    yield f"data: {json.dumps(response)}\n\n"
                
                # Limpiar agente temporal
                await client.delete_agent(langroid_agent_id, current_user.tenant_id, current_user.id)
            
            # Señal de finalización
            yield f"data: {{'type': 'completion', 'content': 'Stream completed'}}\n\n"
            
        except Exception as e:
            logger.error(f"Error in streaming chat: {str(e)}")
            import json
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )


# =====================================
# AGENT EXECUTION
# =====================================

@router.post("/{agent_id}/execute/stream")
async def execute_agent_streaming(
    agent_id: UUID,
    execution_request: AgentExecutionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Ejecutar agente con streaming de resultados"""
    
    from app.services.agent_execution_service import AgentExecutionService
    
    async def event_stream():
        try:
            execution_service = AgentExecutionService(db)
            
            async for result in execution_service.execute_agent_streaming(
                agent_id=agent_id,
                task_type=execution_request.task_type,
                parameters=execution_request.parameters,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                context=execution_request.context
            ):
                import json
                yield f"data: {json.dumps(result)}\n\n"
            
            # Señal de finalización
            yield f"data: {json.dumps({'type': 'stream_end', 'content': 'Execution completed'})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in streaming execution: {str(e)}")
            import json
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )

@router.post("/{agent_id}/execute", response_model=ExecutionResponse)
async def execute_agent(
    agent_id: UUID,
    execution_request: AgentExecutionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Ejecutar un agente con parámetros específicos"""
    
    try:
        agent_service = AgentService(db)
        
        # Crear ejecución
        execution_data = ExecutionCreate(
            agent_id=agent_id,
            task_type=execution_request.task_type,
            input_data={
                "parameters": execution_request.parameters,
                "context": execution_request.context
            }
        )
        
        execution = agent_service.create_execution(
            execution_data,
            current_user.tenant_id,
            current_user.id
        )
        
        # Ejecutar en background
        background_tasks.add_task(
            _execute_agent_task,
            db,
            execution.id,
            agent_id,
            current_user.tenant_id,
            current_user.id,
            execution_request
        )
        
        return execution
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to agent"
        )
    except Exception as e:
        logger.error(f"Error executing agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error executing agent"
        )


@router.get("/{agent_id}/executions", response_model=List[ExecutionResponse])
async def get_agent_executions(
    agent_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener ejecuciones de un agente"""
    
    try:
        # TODO: Implementar obtención de ejecuciones
        return []
        
    except Exception as e:
        logger.error(f"Error getting executions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving executions"
        )


# =====================================
# LANGROID INTEGRATION TEST
# =====================================

@router.get("/langroid/health")
async def check_langroid_health():
    """Verificar conectividad con Langroid service"""
    
    try:
        from app.services.langroid_client import LangroidClient
        
        async with LangroidClient() as client:
            health_status = await client.health_check()
            return {
                "status": "healthy",
                "langroid_service": health_status,
                "integration": "working"
            }
            
    except Exception as e:
        logger.error(f"Langroid health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Langroid service unavailable: {str(e)}"
        )

@router.post("/langroid/test-agent")
async def test_langroid_agent(
    current_user: User = Depends(get_current_active_user)
):
    """Crear un agente de prueba en Langroid"""
    
    try:
        from app.services.langroid_client import LangroidClient
        
        async with LangroidClient() as client:
            # Crear agente de prueba
            agent_id = await client.create_agent(
                agent_type="generic",
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                configuration={"test_mode": True}
            )
            
            # Probar ejecución
            test_results = []
            async for response in client.execute_agent_task(
                agent_id=agent_id,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                task_type="test_task",
                parameters={"message": "Hello from integration test"}
            ):
                test_results.append(response)
            
            # Limpiar agente
            await client.delete_agent(agent_id, current_user.tenant_id, current_user.id)
            
            return {
                "status": "success",
                "agent_id": agent_id,
                "test_results": test_results,
                "message": "Langroid integration test completed successfully"
            }
            
    except Exception as e:
        logger.error(f"Langroid test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Langroid test failed: {str(e)}"
        )

# =====================================
# STATISTICS
# =====================================

@router.get("/{agent_id}/stats", response_model=AgentStats)
async def get_agent_stats(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener estadísticas de un agente"""
    
    try:
        agent_service = AgentService(db)
        stats = agent_service.get_agent_stats(agent_id, current_user.tenant_id)
        
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving statistics"
        )


@router.get("/stats/tenant", response_model=TenantAgentStats)
async def get_tenant_agent_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtener estadísticas de agentes del tenant"""
    
    try:
        # TODO: Implementar estadísticas del tenant
        return TenantAgentStats(
            total_agents=0,
            active_agents=0,
            total_conversations=0,
            total_executions=0,
            most_used_agents=[]
        )
        
    except Exception as e:
        logger.error(f"Error getting tenant stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving tenant statistics"
        )


# =====================================
# BACKGROUND TASKS
# =====================================

async def _execute_agent_task(
    db: Session,
    execution_id: UUID,
    agent_id: UUID,
    tenant_id: UUID,
    user_id: UUID,
    execution_request: AgentExecutionRequest
):
    """Ejecutar agente en background"""
    
    try:
        agent_service = AgentService(db)
        
        # Marcar como iniciado
        agent_service.update_execution_status(execution_id, "running")
        
        # Simular ejecución (implementar lógica específica según el agente)
        import asyncio
        await asyncio.sleep(2)  # Simular trabajo
        
        # Marcar como completado con resultados
        output_data = {
            "result": "Execution completed successfully",
            "task_type": execution_request.task_type,
            "parameters": execution_request.parameters
        }
        
        agent_service.update_execution_status(
            execution_id, 
            "completed", 
            output_data=output_data
        )
        
    except Exception as e:
        logger.error(f"Error in background execution: {str(e)}")
        agent_service.update_execution_status(
            execution_id,
            "failed",
            error_message=str(e)
        )