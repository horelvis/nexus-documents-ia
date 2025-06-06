"""
Schemas for Agent system
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


# =====================================
# AGENT SCHEMAS
# =====================================

class AgentToolSchema(BaseModel):
    """Schema for agent tools"""
    name: str
    description: str
    tool_type: str
    configuration_schema: Dict[str, Any]
    requires_admin: bool = False
    is_tenant_specific: bool = False


class AgentBase(BaseModel):
    """Base schema for agents"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    type: str = Field(..., min_length=1, max_length=50)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    tools: List[str] = Field(default_factory=list)
    is_active: bool = True
    is_public: bool = False


class AgentCreate(AgentBase):
    """Schema for creating agents"""
    pass


class AgentUpdate(BaseModel):
    """Schema for updating agents"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None
    tools: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class AgentResponse(AgentBase):
    """Schema for agent responses"""
    id: UUID
    tenant_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =====================================
# CONVERSATION SCHEMAS
# =====================================

class ConversationBase(BaseModel):
    """Base schema for conversations"""
    title: Optional[str] = Field(None, max_length=200)
    context: Dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(ConversationBase):
    """Schema for creating conversations"""
    agent_id: UUID


class ConversationResponse(ConversationBase):
    """Schema for conversation responses"""
    id: UUID
    agent_id: UUID
    user_id: UUID
    tenant_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =====================================
# MESSAGE SCHEMAS
# =====================================

class MessageBase(BaseModel):
    """Base schema for messages"""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageCreate(MessageBase):
    """Schema for creating messages"""
    conversation_id: UUID


class MessageResponse(MessageBase):
    """Schema for message responses"""
    id: UUID
    conversation_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# =====================================
# EXECUTION SCHEMAS
# =====================================

class ExecutionBase(BaseModel):
    """Base schema for executions"""
    task_type: str = Field(..., min_length=1, max_length=100)
    input_data: Dict[str, Any]


class ExecutionCreate(ExecutionBase):
    """Schema for creating executions"""
    agent_id: UUID


class ExecutionResponse(ExecutionBase):
    """Schema for execution responses"""
    id: UUID
    agent_id: UUID
    user_id: UUID
    tenant_id: UUID
    output_data: Optional[Dict[str, Any]] = None
    status: str
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =====================================
# DIGITAL SIGNATURE SCHEMAS
# =====================================

class SignatureProviderBase(BaseModel):
    """Base schema for signature providers"""
    provider_name: str = Field(..., regex="^(docusign|yousign|signaturit)$")
    display_name: str = Field(..., min_length=1, max_length=100)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_default: bool = False


class SignatureProviderCreate(SignatureProviderBase):
    """Schema for creating signature providers"""
    credentials: Dict[str, Any]  # Will be encrypted before storage


class SignatureProviderUpdate(BaseModel):
    """Schema for updating signature providers"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    configuration: Optional[Dict[str, Any]] = None
    credentials: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class SignatureProviderResponse(SignatureProviderBase):
    """Schema for signature provider responses"""
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =====================================
# SIGNATURE REQUEST SCHEMAS
# =====================================

class SignerBase(BaseModel):
    """Base schema for signers"""
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    phone: Optional[str] = Field(None, max_length=20)
    order: int = Field(default=1, ge=1)
    authentication_method: str = Field(default='email', regex='^(email|sms|code)$')
    success_url: Optional[str] = None
    error_url: Optional[str] = None


class SignerCreate(SignerBase):
    """Schema for creating signers"""
    pass


class SignerResponse(SignerBase):
    """Schema for signer responses"""
    id: UUID
    request_id: UUID
    status: str
    external_id: Optional[str] = None
    signing_url: Optional[str] = None
    signed_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    class Config:
        from_attributes = True


class SignatureRequestBase(BaseModel):
    """Base schema for signature requests"""
    title: str = Field(..., min_length=1, max_length=200)
    message: Optional[str] = None
    document_name: str = Field(..., min_length=1, max_length=255)
    signature_type: str = Field(default='sequential', regex='^(sequential|parallel)$')
    callback_url: Optional[str] = None
    success_url: Optional[str] = None
    error_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SignatureRequestCreate(SignatureRequestBase):
    """Schema for creating signature requests"""
    provider_id: UUID
    signers: List[SignerCreate] = Field(..., min_items=1)
    document_content: Optional[bytes] = None
    document_url: Optional[str] = None


class SignatureRequestUpdate(BaseModel):
    """Schema for updating signature requests"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    message: Optional[str] = None
    callback_url: Optional[str] = None
    success_url: Optional[str] = None
    error_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SignatureRequestResponse(SignatureRequestBase):
    """Schema for signature request responses"""
    id: UUID
    tenant_id: UUID
    provider_id: UUID
    created_by: UUID
    external_id: Optional[str] = None
    document_url: Optional[str] = None
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    signers: List[SignerResponse] = []

    class Config:
        from_attributes = True


# =====================================
# AGENT CHAT SCHEMAS
# =====================================

class ChatRequest(BaseModel):
    """Schema for chat requests"""
    message: str = Field(..., min_length=1)
    conversation_id: Optional[UUID] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Schema for chat responses"""
    message: str
    conversation_id: UUID
    agent_id: UUID
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentExecutionRequest(BaseModel):
    """Schema for agent execution requests"""
    task_type: str
    parameters: Dict[str, Any]
    context: Dict[str, Any] = Field(default_factory=dict)


class StreamingChatResponse(BaseModel):
    """Schema for streaming chat responses"""
    type: str = Field(..., regex='^(message|tool_call|completion|error)$')
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =====================================
# STATISTICS SCHEMAS
# =====================================

class AgentStats(BaseModel):
    """Schema for agent statistics"""
    total_conversations: int
    total_messages: int
    total_executions: int
    avg_response_time_ms: Optional[float] = None
    success_rate: float
    last_used_at: Optional[datetime] = None


class TenantAgentStats(BaseModel):
    """Schema for tenant-wide agent statistics"""
    total_agents: int
    active_agents: int
    total_conversations: int
    total_executions: int
    most_used_agents: List[Dict[str, Any]] = []