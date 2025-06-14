"""
API endpoints for Agent Registry - Dynamic agent management
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
import uuid

from app.api.dependencies import get_db, get_current_active_user, require_admin
from app.db.models import User, AgentDefinition, AgentDeployment, AgentStatus
from app.schemas.agent_registry import (
    AgentDefinitionCreate,
    AgentDefinitionUpdate,
    AgentDefinitionResponse,
    AgentDeploymentCreate,
    AgentDeploymentResponse,
    LangflowImportRequest,
    LangflowImportResponse
)
from app.services.langflow_import_service import LangflowImportService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/definitions", response_model=List[AgentDefinitionResponse])
async def list_agent_definitions(
    skip: int = 0,
    limit: int = 100,
    include_private: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List available agent definitions"""
    query = db.query(AgentDefinition).filter(
        AgentDefinition.status == AgentStatus.ACTIVE
    )
    
    if not include_private:
        # Show only public agents or tenant-specific ones
        query = query.filter(
            db.or_(
                AgentDefinition.is_public == True,
                AgentDefinition.tenant_id == current_user.tenant_id
            )
        )
    
    definitions = query.offset(skip).limit(limit).all()
    return definitions


@router.post("/definitions", response_model=AgentDefinitionResponse)
async def create_agent_definition(
    agent_def: AgentDefinitionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new agent definition (admin only)"""
    
    # Check if name already exists
    existing = db.query(AgentDefinition).filter(
        AgentDefinition.name == agent_def.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent with name '{agent_def.name}' already exists"
        )
    
    db_agent = AgentDefinition(
        **agent_def.dict(),
        created_by=current_user.id,
        tenant_id=current_user.tenant_id if not agent_def.is_public else None
    )
    
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    
    logger.info(f"Created agent definition: {db_agent.name}")
    return db_agent


@router.put("/definitions/{agent_id}", response_model=AgentDefinitionResponse)
async def update_agent_definition(
    agent_id: str,
    agent_update: AgentDefinitionUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update an agent definition (admin only)"""
    
    agent = db.query(AgentDefinition).filter(
        AgentDefinition.id == agent_id
    ).first()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent definition not found"
        )
    
    # Check permissions
    if agent.tenant_id and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify agent from another tenant"
        )
    
    update_data = agent_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)
    
    db.commit()
    db.refresh(agent)
    
    logger.info(f"Updated agent definition: {agent.name}")
    return agent


@router.delete("/definitions/{agent_id}")
async def delete_agent_definition(
    agent_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete an agent definition (admin only)"""
    
    agent = db.query(AgentDefinition).filter(
        AgentDefinition.id == agent_id
    ).first()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent definition not found"
        )
    
    # Check permissions
    if agent.tenant_id and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete agent from another tenant"
        )
    
    # Soft delete by setting status
    agent.status = AgentStatus.DEPRECATED
    db.commit()
    
    logger.info(f"Deleted agent definition: {agent.name}")
    return {"message": "Agent definition deleted successfully"}


@router.post("/deploy", response_model=AgentDeploymentResponse)
async def deploy_agent(
    deployment: AgentDeploymentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deploy an agent for the current tenant"""
    
    # Verify agent definition exists
    agent_def = db.query(AgentDefinition).filter(
        AgentDefinition.id == deployment.agent_definition_id,
        AgentDefinition.status == AgentStatus.ACTIVE
    ).first()
    
    if not agent_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent definition not found or not active"
        )
    
    # Check if already deployed
    existing = db.query(AgentDeployment).filter(
        AgentDeployment.agent_definition_id == deployment.agent_definition_id,
        AgentDeployment.tenant_id == current_user.tenant_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent already deployed for this tenant"
        )
    
    # Create deployment
    db_deployment = AgentDeployment(
        agent_definition_id=deployment.agent_definition_id,
        tenant_id=current_user.tenant_id,
        custom_config=deployment.custom_config or {},
        custom_prompt=deployment.custom_prompt,
        deployed_by=current_user.id
    )
    
    db.add(db_deployment)
    db.commit()
    db.refresh(db_deployment)
    
    logger.info(f"Deployed agent {agent_def.name} for tenant {current_user.tenant_id}")
    return db_deployment


@router.get("/deployments", response_model=List[AgentDeploymentResponse])
async def list_deployments(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List agent deployments for current tenant"""
    
    deployments = db.query(AgentDeployment).filter(
        AgentDeployment.tenant_id == current_user.tenant_id,
        AgentDeployment.is_enabled == True
    ).all()
    
    return deployments


@router.put("/deployments/{deployment_id}/toggle")
async def toggle_deployment(
    deployment_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Enable/disable an agent deployment"""
    
    deployment = db.query(AgentDeployment).filter(
        AgentDeployment.id == deployment_id,
        AgentDeployment.tenant_id == current_user.tenant_id
    ).first()
    
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )
    
    deployment.is_enabled = not deployment.is_enabled
    db.commit()
    
    status_text = "enabled" if deployment.is_enabled else "disabled"
    logger.info(f"Agent deployment {deployment_id} {status_text}")
    
    return {
        "message": f"Deployment {status_text} successfully",
        "is_enabled": deployment.is_enabled
    }


@router.post("/import/langflow", response_model=LangflowImportResponse)
async def import_from_langflow(
    import_request: LangflowImportRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Import agent from Langflow export JSON (admin only)"""
    
    # Validate the Langflow export
    if not LangflowImportService.validate_langflow_export(import_request.langflow_data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Langflow export format"
        )
    
    try:
        # Import the agent
        agent = await LangflowImportService.import_from_langflow(
            db=db,
            langflow_json=import_request.langflow_data,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            is_public=import_request.is_public
        )
        
        # Auto-deploy if requested
        deployment = None
        if import_request.auto_deploy:
            deployment = AgentDeployment(
                agent_definition_id=agent.id,
                tenant_id=current_user.tenant_id,
                deployed_by=current_user.id,
                is_enabled=True
            )
            db.add(deployment)
            db.commit()
            db.refresh(deployment)
        
        return LangflowImportResponse(
            agent=agent,
            deployment=deployment,
            message=f"Successfully imported agent '{agent.display_name}' from Langflow"
        )
        
    except Exception as e:
        logger.error(f"Error importing from Langflow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import from Langflow: {str(e)}"
        )


@router.post("/import/langflow-url", response_model=LangflowImportResponse)
async def import_from_langflow_url(
    flow_url: str,
    is_public: bool = False,
    auto_deploy: bool = True,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Import agent from Langflow URL (admin only)"""
    
    try:
        # Import from URL
        agent = await LangflowImportService.import_from_langflow_url(
            db=db,
            flow_url=flow_url,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            is_public=is_public
        )
        
        # Auto-deploy if requested
        deployment = None
        if auto_deploy:
            deployment = AgentDeployment(
                agent_definition_id=agent.id,
                tenant_id=current_user.tenant_id,
                deployed_by=current_user.id,
                is_enabled=True
            )
            db.add(deployment)
            db.commit()
            db.refresh(deployment)
        
        return LangflowImportResponse(
            agent=agent,
            deployment=deployment,
            message=f"Successfully imported agent '{agent.display_name}' from Langflow URL"
        )
        
    except Exception as e:
        logger.error(f"Error importing from Langflow URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import from Langflow URL: {str(e)}"
        )