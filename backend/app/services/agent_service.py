"""
Agent Management Service
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc

from app.db.models import (
    Agent, AgentConversation, AgentMessage, AgentExecution, 
    AgentTool, User, Tenant
)
from app.schemas.agent import (
    AgentCreate, AgentUpdate, ConversationCreate, MessageCreate,
    ExecutionCreate, AgentStats
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentService:
    """Servicio para gestión de agentes AI"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # =====================================
    # AGENT MANAGEMENT
    # =====================================
    
    def create_agent(
        self, 
        agent_data: AgentCreate, 
        tenant_id: UUID, 
        user_id: UUID
    ) -> Agent:
        """Crear un nuevo agente"""
        try:
            # Verificar que el nombre no exista en el tenant
            existing = self.db.query(Agent).filter(
                and_(
                    Agent.name == agent_data.name,
                    Agent.tenant_id == tenant_id
                )
            ).first()
            
            if existing:
                raise ValueError(f"Agent with name '{agent_data.name}' already exists in this tenant")
            
            # Validar herramientas
            available_tools = self._get_available_tools(tenant_id)
            invalid_tools = set(agent_data.tools) - set(available_tools.keys())
            if invalid_tools:
                raise ValueError(f"Invalid tools: {invalid_tools}")
            
            # Crear agente
            agent = Agent(
                name=agent_data.name,
                description=agent_data.description,
                type=agent_data.type,
                tenant_id=tenant_id,
                created_by=user_id,
                configuration=agent_data.configuration,
                tools=agent_data.tools,
                is_active=agent_data.is_active,
                is_public=agent_data.is_public
            )
            
            self.db.add(agent)
            self.db.commit()
            self.db.refresh(agent)
            
            logger.info(f"Created agent {agent.id} for tenant {tenant_id}")
            return agent
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating agent: {str(e)}")
            raise
    
    def get_agent(self, agent_id: UUID, tenant_id: UUID) -> Optional[Agent]:
        """Obtener un agente por ID"""
        return self.db.query(Agent).filter(
            and_(
                Agent.id == agent_id,
                Agent.tenant_id == tenant_id
            )
        ).first()
    
    def get_agents(
        self, 
        tenant_id: UUID, 
        user_id: Optional[UUID] = None,
        agent_type: Optional[str] = None,
        is_active: Optional[bool] = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[Agent]:
        """Obtener agentes del tenant"""
        query = self.db.query(Agent).filter(Agent.tenant_id == tenant_id)
        
        if is_active is not None:
            query = query.filter(Agent.is_active == is_active)
        
        if agent_type:
            query = query.filter(Agent.type == agent_type)
        
        if user_id:
            # Mostrar agentes públicos o creados por el usuario
            query = query.filter(
                or_(
                    Agent.is_public == True,
                    Agent.created_by == user_id
                )
            )
        
        return query.order_by(desc(Agent.created_at)).offset(offset).limit(limit).all()
    
    def update_agent(
        self, 
        agent_id: UUID, 
        agent_data: AgentUpdate, 
        tenant_id: UUID,
        user_id: UUID
    ) -> Optional[Agent]:
        """Actualizar un agente"""
        try:
            agent = self.get_agent(agent_id, tenant_id)
            if not agent:
                return None
            
            # Verificar permisos (solo el creador o admin puede editar)
            if agent.created_by != user_id:
                # TODO: Verificar si es admin del tenant
                raise PermissionError("Only the agent creator can modify it")
            
            # Actualizar campos
            update_data = agent_data.dict(exclude_unset=True)
            
            if 'tools' in update_data:
                available_tools = self._get_available_tools(tenant_id)
                invalid_tools = set(update_data['tools']) - set(available_tools.keys())
                if invalid_tools:
                    raise ValueError(f"Invalid tools: {invalid_tools}")
            
            for field, value in update_data.items():
                setattr(agent, field, value)
            
            self.db.commit()
            self.db.refresh(agent)
            
            logger.info(f"Updated agent {agent_id}")
            return agent
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating agent: {str(e)}")
            raise
    
    def delete_agent(self, agent_id: UUID, tenant_id: UUID, user_id: UUID) -> bool:
        """Eliminar un agente"""
        try:
            agent = self.get_agent(agent_id, tenant_id)
            if not agent:
                return False
            
            # Verificar permisos
            if agent.created_by != user_id:
                raise PermissionError("Only the agent creator can delete it")
            
            # Marcar como inactivo en lugar de eliminar
            agent.is_active = False
            self.db.commit()
            
            logger.info(f"Deleted agent {agent_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting agent: {str(e)}")
            raise
    
    # =====================================
    # CONVERSATION MANAGEMENT
    # =====================================
    
    def create_conversation(
        self, 
        conversation_data: ConversationCreate, 
        tenant_id: UUID, 
        user_id: UUID
    ) -> AgentConversation:
        """Crear una nueva conversación"""
        try:
            # Verificar que el agente existe y es accesible
            agent = self.get_agent(conversation_data.agent_id, tenant_id)
            if not agent:
                raise ValueError("Agent not found")
            
            if not agent.is_public and agent.created_by != user_id:
                raise PermissionError("Agent is private")
            
            conversation = AgentConversation(
                agent_id=conversation_data.agent_id,
                user_id=user_id,
                tenant_id=tenant_id,
                title=conversation_data.title,
                context=conversation_data.context
            )
            
            self.db.add(conversation)
            self.db.commit()
            self.db.refresh(conversation)
            
            logger.info(f"Created conversation {conversation.id}")
            return conversation
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating conversation: {str(e)}")
            raise
    
    def get_conversation(
        self, 
        conversation_id: UUID, 
        tenant_id: UUID, 
        user_id: UUID
    ) -> Optional[AgentConversation]:
        """Obtener una conversación"""
        return self.db.query(AgentConversation).filter(
            and_(
                AgentConversation.id == conversation_id,
                AgentConversation.tenant_id == tenant_id,
                AgentConversation.user_id == user_id
            )
        ).first()
    
    def get_conversations(
        self, 
        tenant_id: UUID, 
        user_id: UUID,
        agent_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[AgentConversation]:
        """Obtener conversaciones del usuario"""
        query = self.db.query(AgentConversation).filter(
            and_(
                AgentConversation.tenant_id == tenant_id,
                AgentConversation.user_id == user_id,
                AgentConversation.is_active == True
            )
        )
        
        if agent_id:
            query = query.filter(AgentConversation.agent_id == agent_id)
        
        return query.order_by(desc(AgentConversation.updated_at)).offset(offset).limit(limit).all()
    
    # =====================================
    # MESSAGE MANAGEMENT
    # =====================================
    
    def add_message(
        self, 
        message_data: MessageCreate, 
        tenant_id: UUID, 
        user_id: UUID
    ) -> AgentMessage:
        """Añadir mensaje a conversación"""
        try:
            # Verificar que la conversación existe y pertenece al usuario
            conversation = self.get_conversation(
                message_data.conversation_id, 
                tenant_id, 
                user_id
            )
            if not conversation:
                raise ValueError("Conversation not found")
            
            message = AgentMessage(
                conversation_id=message_data.conversation_id,
                role=message_data.role,
                content=message_data.content,
                message_metadata=message_data.metadata
            )
            
            self.db.add(message)
            
            # Actualizar timestamp de conversación
            conversation.updated_at = func.now()
            
            self.db.commit()
            self.db.refresh(message)
            
            return message
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding message: {str(e)}")
            raise
    
    def get_messages(
        self, 
        conversation_id: UUID, 
        tenant_id: UUID, 
        user_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[AgentMessage]:
        """Obtener mensajes de conversación"""
        # Verificar acceso a conversación
        conversation = self.get_conversation(conversation_id, tenant_id, user_id)
        if not conversation:
            return []
        
        return self.db.query(AgentMessage).filter(
            AgentMessage.conversation_id == conversation_id
        ).order_by(AgentMessage.created_at).offset(offset).limit(limit).all()
    
    # =====================================
    # EXECUTION MANAGEMENT
    # =====================================
    
    def create_execution(
        self, 
        execution_data: ExecutionCreate, 
        tenant_id: UUID, 
        user_id: UUID
    ) -> AgentExecution:
        """Crear una nueva ejecución"""
        try:
            # Verificar acceso al agente
            agent = self.get_agent(execution_data.agent_id, tenant_id)
            if not agent:
                raise ValueError("Agent not found")
            
            if not agent.is_public and agent.created_by != user_id:
                raise PermissionError("Agent is private")
            
            execution = AgentExecution(
                agent_id=execution_data.agent_id,
                user_id=user_id,
                tenant_id=tenant_id,
                task_type=execution_data.task_type,
                input_data=execution_data.input_data,
                status='pending'
            )
            
            self.db.add(execution)
            self.db.commit()
            self.db.refresh(execution)
            
            logger.info(f"Created execution {execution.id}")
            return execution
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating execution: {str(e)}")
            raise
    
    def update_execution_status(
        self, 
        execution_id: UUID, 
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Actualizar estado de ejecución"""
        try:
            execution = self.db.query(AgentExecution).filter(
                AgentExecution.id == execution_id
            ).first()
            
            if not execution:
                return False
            
            execution.status = status
            if output_data:
                execution.output_data = output_data
            if error_message:
                execution.error_message = error_message
            
            if status in ['completed', 'failed']:
                execution.completed_at = func.now()
                if execution.started_at:
                    # Calcular tiempo de ejecución
                    time_diff = datetime.now() - execution.started_at
                    execution.execution_time_ms = int(time_diff.total_seconds() * 1000)
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating execution status: {str(e)}")
            raise
    
    # =====================================
    # TOOLS & UTILITIES
    # =====================================
    
    def _get_available_tools(self, tenant_id: UUID) -> Dict[str, AgentTool]:
        """Obtener herramientas disponibles para el tenant"""
        tools = self.db.query(AgentTool).filter(
            or_(
                AgentTool.is_tenant_specific == False,
                and_(
                    AgentTool.is_tenant_specific == True,
                    # TODO: Verificar configuraciones específicas del tenant
                )
            )
        ).all()
        
        return {tool.name: tool for tool in tools}
    
    def get_agent_stats(self, agent_id: UUID, tenant_id: UUID) -> Optional[AgentStats]:
        """Obtener estadísticas de un agente"""
        agent = self.get_agent(agent_id, tenant_id)
        if not agent:
            return None
        
        # Obtener estadísticas
        total_conversations = self.db.query(func.count(AgentConversation.id)).filter(
            AgentConversation.agent_id == agent_id
        ).scalar() or 0
        
        total_messages = self.db.query(func.count(AgentMessage.id)).join(
            AgentConversation
        ).filter(
            AgentConversation.agent_id == agent_id
        ).scalar() or 0
        
        total_executions = self.db.query(func.count(AgentExecution.id)).filter(
            AgentExecution.agent_id == agent_id
        ).scalar() or 0
        
        # Tiempo promedio de respuesta
        avg_time = self.db.query(func.avg(AgentExecution.execution_time_ms)).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == 'completed'
            )
        ).scalar()
        
        # Tasa de éxito
        completed_executions = self.db.query(func.count(AgentExecution.id)).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == 'completed'
            )
        ).scalar() or 0
        
        success_rate = (completed_executions / total_executions) if total_executions > 0 else 0.0
        
        # Último uso
        last_used = self.db.query(func.max(AgentExecution.started_at)).filter(
            AgentExecution.agent_id == agent_id
        ).scalar()
        
        return AgentStats(
            total_conversations=total_conversations,
            total_messages=total_messages,
            total_executions=total_executions,
            avg_response_time_ms=avg_time,
            success_rate=success_rate,
            last_used_at=last_used
        )