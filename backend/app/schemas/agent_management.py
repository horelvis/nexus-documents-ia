"""
Pydantic schemas for Agent Management
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.db.agent_models import AgentType, AgentExecutionMode

# =====================================
# AGENT DEFINITION SCHEMAS
# =====================================

class AgentDefinitionBase(BaseModel):
    agent_type: AgentType
    name: str
    description: Optional[str] = None
    category: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    required_permissions: List[str] = Field(default_factory=list)
    execution_mode: AgentExecutionMode = AgentExecutionMode.CONFIRMATION_REQUIRED
    requires_context: bool = True
    supports_streaming: bool = True
    max_tokens: int = 2000
    timeout_seconds: int = 300

class AgentDefinitionResponse(AgentDefinitionBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True

# =====================================
# AGENT CONFIGURATION SCHEMAS
# =====================================

class AgentConfigurationBase(BaseModel):
    is_enabled: bool = False
    custom_name: Optional[str] = None
    custom_description: Optional[str] = None
    custom_settings: Dict[str, Any] = Field(default_factory=dict)
    execution_mode_override: Optional[AgentExecutionMode] = None
    requires_approval: bool = False
    allowed_users: List[UUID] = Field(default_factory=list)
    max_executions_per_day: int = 100
    max_executions_per_user_per_day: int = 10

class AgentConfigurationCreate(AgentConfigurationBase):
    agent_definition_id: UUID

class AgentConfigurationUpdate(BaseModel):
    custom_name: Optional[str] = None
    custom_description: Optional[str] = None
    custom_settings: Optional[Dict[str, Any]] = None
    execution_mode_override: Optional[AgentExecutionMode] = None
    requires_approval: Optional[bool] = None
    allowed_users: Optional[List[UUID]] = None
    max_executions_per_day: Optional[int] = None
    max_executions_per_user_per_day: Optional[int] = None

class AgentConfigurationResponse(AgentConfigurationBase):
    id: UUID
    agent_definition_id: UUID
    enabled_by: Optional[UUID] = None
    enabled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Include the definition details
    definition: Optional[AgentDefinitionResponse] = None
    
    class Config:
        orm_mode = True

class AgentActivationRequest(BaseModel):
    """Request to activate an agent with optional configuration"""
    custom_name: Optional[str] = None
    custom_description: Optional[str] = None
    execution_mode_override: Optional[AgentExecutionMode] = None
    requires_approval: Optional[bool] = None
    allowed_users: Optional[List[UUID]] = None
    max_executions_per_day: Optional[int] = None
    max_executions_per_user_per_day: Optional[int] = None

# =====================================
# AGENT EXECUTION SCHEMAS
# =====================================
