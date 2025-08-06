"""
API endpoints for Agent Management
Handles agent configuration, activation, and tenant-specific settings
"""
import logging
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import (
    get_current_active_user_async, 
    get_current_tenant_admin_async
)
from app.db.async_database import get_async_db
from app.db.models import User, Tenant
from app.db.agent_models import (
    AgentDefinition, AgentConfiguration, AgentExecution,
    AgentType, AgentExecutionMode
)
from app.schemas.agent_management import (
    AgentDefinitionResponse, AgentConfigurationResponse,
    AgentConfigurationCreate, AgentConfigurationUpdate,
    AgentExecutionResponse, AgentActivationRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()

# =====================================
# AGENT DEFINITIONS (READ-ONLY)
# =====================================

@router.get("/definitions", response_model=List[AgentDefinitionResponse])
async def list_agent_definitions(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """List all available agent definitions in the system"""
    query = select(AgentDefinition).where(AgentDefinition.is_active == True)
    result = await db.execute(query)
    definitions = result.scalars().all()
    
    return definitions

@router.get("/definitions/{agent_type}", response_model=AgentDefinitionResponse)
async def get_agent_definition(
    agent_type: AgentType,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Get details of a specific agent definition"""
    query = select(AgentDefinition).where(
        and_(
            AgentDefinition.agent_type == agent_type,
            AgentDefinition.is_active == True
        )
    )
    result = await db.execute(query)
    definition = result.scalar_one_or_none()
    
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent definition {agent_type} not found"
        )
    
    return definition

# =====================================
# AGENT CONFIGURATIONS (TENANT-SPECIFIC)
# =====================================

@router.get("/configurations", response_model=List[AgentConfigurationResponse])
async def list_tenant_agent_configurations(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
):
    """List all agent configurations for the current tenant"""
    query = (
        select(AgentConfiguration)
        .options(selectinload(AgentConfiguration.definition))
        .where(AgentConfiguration.tenant_id == current_user.tenant_id)
    )
    result = await db.execute(query)
    configurations = result.scalars().all()
    
    return configurations

@router.get("/configurations/{agent_type}", response_model=AgentConfigurationResponse)
async def get_tenant_agent_configuration(
    agent_type: AgentType,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
):
    """Get configuration for a specific agent type in the current tenant"""
    return await _get_tenant_agent_configuration(agent_type, db, current_user)

async def _get_tenant_agent_configuration(
    agent_type: AgentType,
    db: AsyncSession,
    current_user: User
):
    """Get configuration for a specific agent type in the current tenant"""
    # First get the agent definition
    def_query = select(AgentDefinition).where(
        AgentDefinition.agent_type == agent_type
    )
    def_result = await db.execute(def_query)
    definition = def_result.scalar_one_or_none()
    
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent type {agent_type} not found"
        )
    
    # Get tenant configuration
    config_query = (
        select(AgentConfiguration)
        .options(selectinload(AgentConfiguration.definition))
        .where(
            and_(
                AgentConfiguration.tenant_id == current_user.tenant_id,
                AgentConfiguration.agent_definition_id == definition.id
            )
        )
    )
    config_result = await db.execute(config_query)
    configuration = config_result.scalar_one_or_none()
    
    if not configuration:
        # Create default configuration if it doesn't exist
        configuration = AgentConfiguration(
            tenant_id=current_user.tenant_id,
            agent_definition_id=definition.id,
            is_enabled=False,
            custom_settings={},
            max_executions_per_day=100,
            max_executions_per_user_per_day=10
        )
        db.add(configuration)
        await db.commit()
        await db.refresh(configuration)
        
        # Load the definition relationship
        await db.refresh(configuration, ['definition'])
    
    return configuration

# =====================================
# AGENT ACTIVATION/DEACTIVATION (ADMIN ONLY)
# =====================================

@router.post("/configurations/{agent_type}/activate")
async def activate_agent(
    agent_type: AgentType,
    request: AgentActivationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_admin: User = Depends(get_current_tenant_admin_async),
):
    """Activate an agent for the tenant (admin only)"""
    # Get or create configuration
    configuration = await _get_tenant_agent_configuration(
        agent_type, db, current_admin
    )
    
    # Update configuration
    configuration.is_enabled = True
    configuration.enabled_by = current_admin.id
    configuration.enabled_at = datetime.utcnow()
    
    if request.custom_name:
        configuration.custom_name = request.custom_name
    if request.custom_description:
        configuration.custom_description = request.custom_description
    if request.execution_mode_override:
        configuration.execution_mode_override = request.execution_mode_override
    if request.requires_approval is not None:
        configuration.requires_approval = request.requires_approval
    if request.allowed_users:
        configuration.allowed_users = request.allowed_users
    if request.max_executions_per_day:
        configuration.max_executions_per_day = request.max_executions_per_day
    if request.max_executions_per_user_per_day:
        configuration.max_executions_per_user_per_day = request.max_executions_per_user_per_day
    
    await db.commit()
    await db.refresh(configuration)
    
    logger.info(
        f"Agent {agent_type} activated for tenant {current_admin.tenant_id} "
        f"by admin {current_admin.email}"
    )
    
    return {
        "message": f"Agent {agent_type} activated successfully",
        "configuration": configuration
    }

@router.post("/configurations/{agent_type}/deactivate")
async def deactivate_agent(
    agent_type: AgentType,
    db: AsyncSession = Depends(get_async_db),
    current_admin: User = Depends(get_current_tenant_admin_async),
):
    """Deactivate an agent for the tenant (admin only)"""
    configuration = await _get_tenant_agent_configuration(
        agent_type, db, current_admin
    )
    
    configuration.is_enabled = False
    configuration.enabled_by = None
    configuration.enabled_at = None
    
    await db.commit()
    
    logger.info(
        f"Agent {agent_type} deactivated for tenant {current_user.tenant_id} "
        f"by admin {current_admin.email}"
    )
    
    return {
        "message": f"Agent {agent_type} deactivated successfully"
    }

# =====================================
# AGENT CONFIGURATION UPDATES (ADMIN ONLY)
# =====================================

@router.put("/configurations/{agent_type}", response_model=AgentConfigurationResponse)
async def update_agent_configuration(
    agent_type: AgentType,
    update_data: AgentConfigurationUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_admin: User = Depends(get_current_tenant_admin_async),
):
    """Update agent configuration for the tenant (admin only)"""
    configuration = await _get_tenant_agent_configuration(
        agent_type, db, current_admin
    )
    
    # Update fields if provided
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(configuration, field, value)
    
    configuration.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(configuration)
    
    logger.info(
        f"Agent {agent_type} configuration updated for tenant {current_user.tenant_id} "
        f"by admin {current_admin.email}"
    )
    
    return configuration

# =====================================
# AGENT EXECUTION HISTORY
# =====================================

@router.get("/executions", response_model=List[AgentExecutionResponse])
async def list_agent_executions(
    agent_type: Optional[AgentType] = None,
    user_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
):
    """List agent executions for the tenant"""
    query = (
        select(AgentExecution)
        .options(
            selectinload(AgentExecution.configuration)
            .selectinload(AgentConfiguration.definition)
        )
        .where(AgentExecution.tenant_id == current_user.tenant_id)
    )
    
    # Apply filters
    if agent_type:
        query = query.join(AgentConfiguration).join(AgentDefinition).where(
            AgentDefinition.agent_type == agent_type
        )
    
    if user_id:
        # Only admins can filter by user_id
        if not current_user.is_tenant_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can filter by user"
            )
        query = query.where(AgentExecution.user_id == user_id)
    elif not current_user.is_tenant_admin:
        # Non-admins can only see their own executions
        query = query.where(AgentExecution.user_id == current_user.id)
    
    if status:
        query = query.where(AgentExecution.status == status)
    
    # Order by creation date descending
    query = query.order_by(AgentExecution.created_at.desc())
    
    # Apply pagination
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    executions = result.scalars().all()
    
    return executions

@router.get("/executions/{execution_id}", response_model=AgentExecutionResponse)
async def get_agent_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
):
    """Get details of a specific agent execution"""
    query = (
        select(AgentExecution)
        .options(
            selectinload(AgentExecution.configuration)
            .selectinload(AgentConfiguration.definition),
            selectinload(AgentExecution.logs)
        )
        .where(
            and_(
                AgentExecution.id == execution_id,
                AgentExecution.tenant_id == current_user.tenant_id
            )
        )
    )
    
    # Non-admins can only see their own executions
    if not current_user.is_tenant_admin:
        query = query.where(AgentExecution.user_id == current_user.id)
    
    result = await db.execute(query)
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    return execution

# =====================================
# AGENT USAGE STATISTICS (ADMIN ONLY)
# =====================================

@router.get("/statistics/usage")
async def get_agent_usage_statistics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_async_db),
    current_admin: User = Depends(get_current_tenant_admin_async),
):
    """Get agent usage statistics for the tenant (admin only)"""
    # Base query
    query = select(
        AgentDefinition.agent_type,
        AgentDefinition.name,
        func.count(AgentExecution.id).label('execution_count'),
        func.avg(AgentExecution.execution_time_ms).label('avg_execution_time'),
        func.sum(AgentExecution.tokens_used).label('total_tokens')
    ).select_from(
        AgentExecution
    ).join(
        AgentConfiguration
    ).join(
        AgentDefinition
    ).where(
        AgentExecution.tenant_id == current_user.tenant_id
    )
    
    # Apply date filters
    if start_date:
        query = query.where(AgentExecution.created_at >= start_date)
    if end_date:
        query = query.where(AgentExecution.created_at <= end_date)
    
    # Group by agent type
    query = query.group_by(AgentDefinition.agent_type, AgentDefinition.name)
    
    result = await db.execute(query)
    statistics = result.all()
    
    return {
        "tenant_id": str(current_user.tenant_id),
        "start_date": start_date,
        "end_date": end_date,
        "agent_statistics": [
            {
                "agent_type": stat.agent_type,
                "name": stat.name,
                "execution_count": stat.execution_count,
                "avg_execution_time_ms": float(stat.avg_execution_time) if stat.avg_execution_time else 0,
                "total_tokens_used": stat.total_tokens or 0
            }
            for stat in statistics
        ]
    }