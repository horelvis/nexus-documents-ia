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
    tenant_id: UUID
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

class AgentExecutionBase(BaseModel):
    execution_type: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    document_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None

class AgentExecutionCreate(AgentExecutionBase):
    agent_type: AgentType

class AgentExecutionResponse(AgentExecutionBase):
    id: UUID
    tenant_id: UUID
    configuration_id: UUID
    user_id: UUID
    output_data: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    error_message: Optional[str] = None
    requires_approval: bool = False
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    tokens_used: int = 0
    execution_time_ms: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Include configuration details
    configuration: Optional[AgentConfigurationResponse] = None
    
    class Config:
        orm_mode = True

# =====================================
# AGENT EXECUTION LOG SCHEMAS
# =====================================

class AgentExecutionLogResponse(BaseModel):
    id: UUID
    execution_id: UUID
    log_level: str
    message: str
    log_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    
    class Config:
        orm_mode = True

# =====================================
# AGENT STATISTICS SCHEMAS
# =====================================

class AgentUsageStatistics(BaseModel):
    agent_type: AgentType
    name: str
    execution_count: int
    avg_execution_time_ms: float
    total_tokens_used: int

class TenantAgentStatistics(BaseModel):
    tenant_id: UUID
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    agent_statistics: List[AgentUsageStatistics]