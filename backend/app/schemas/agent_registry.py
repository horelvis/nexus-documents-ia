"""
Pydantic schemas for Agent Registry
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID

from app.db.models import AgentStatus, AgentType


# Agent Definition Schemas
class AgentDefinitionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    
    agent_type: AgentType = AgentType.CUSTOM
    category: Optional[str] = Field(None, max_length=50)
    tags: List[str] = Field(default_factory=list)
    
    base_class: str = Field(default="EnhancedLangroidAgent", max_length=100)
    system_prompt: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    
    ui_config: Dict[str, Any] = Field(default_factory=dict)
    quick_actions: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    
    is_public: bool = True
    required_permissions: List[str] = Field(default_factory=list)
    required_subscription: Optional[str] = None
    
    version: str = Field(default="1.0.0", max_length=20)
    status: AgentStatus = AgentStatus.ACTIVE


class AgentDefinitionCreate(AgentDefinitionBase):
    pass


class AgentDefinitionUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    
    category: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None
    
    system_prompt: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    
    ui_config: Optional[Dict[str, Any]] = None
    quick_actions: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    
    required_permissions: Optional[List[str]] = None
    required_subscription: Optional[str] = None
    
    version: Optional[str] = Field(None, max_length=20)
    status: Optional[AgentStatus] = None


class AgentDefinitionResponse(AgentDefinitionBase):
    id: UUID
    tenant_id: Optional[UUID]
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


# Agent Deployment Schemas
class AgentDeploymentBase(BaseModel):
    agent_definition_id: UUID
    custom_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    custom_prompt: Optional[str] = None


class AgentDeploymentCreate(AgentDeploymentBase):
    pass


class AgentDeploymentResponse(AgentDeploymentBase):
    id: UUID
    tenant_id: UUID
    is_enabled: bool
    usage_count: int
    last_used: Optional[datetime]
    deployed_at: datetime
    deployed_by: UUID
    
    # Include agent definition info
    definition: Optional[AgentDefinitionResponse] = None
    
    class Config:
        orm_mode = True


# Agent Template Schemas
class AgentTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    template_config: Dict[str, Any] = Field(default_factory=dict)
    sample_queries: List[str] = Field(default_factory=list)
    is_featured: bool = False


class AgentTemplateCreate(AgentTemplateBase):
    agent_definition_id: UUID


class AgentTemplateResponse(AgentTemplateBase):
    id: UUID
    agent_definition_id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True


# Agent Plugin Schemas  
class AgentPluginBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    version: str = Field(..., max_length=20)
    plugin_type: str = Field(..., max_length=50)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    code_reference: Optional[str] = Field(None, max_length=200)
    compatible_agents: List[str] = Field(default_factory=list)
    required_dependencies: List[str] = Field(default_factory=list)


class AgentPluginCreate(AgentPluginBase):
    pass


class AgentPluginResponse(AgentPluginBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


# Langflow Import Schemas
class LangflowImportRequest(BaseModel):
    langflow_data: Dict[str, Any] = Field(..., description="Langflow export JSON")
    is_public: bool = Field(default=False, description="Make agent available to all tenants")
    auto_deploy: bool = Field(default=True, description="Automatically deploy after import")


class LangflowImportResponse(BaseModel):
    agent: AgentDefinitionResponse
    deployment: Optional[AgentDeploymentResponse] = None
    message: str