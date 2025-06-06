# microservices/langroid-service/app/schemas/agent.py

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum

# =====================================
# ENUMS
# =====================================

class AgentType(str, Enum):
    """Tipos de agentes disponibles"""
    GENERIC = "generic"
    DOCUMENT_ANALYZER = "document_analyzer" 
    DIGITAL_SIGNATURE = "digital_signature"
    RAG_ASSISTANT = "rag_assistant"
    CONTRACT_ANALYZER = "contract_analyzer"

class AgentStatus(str, Enum):
    """Estados del agente"""
    INACTIVE = "inactive"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"

class MessageRole(str, Enum):
    """Roles de mensajes"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

# =====================================
# AGENT SCHEMAS
# =====================================

class AgentBase(BaseModel):
    """Base schema for agents"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    agent_type: AgentType
    configuration: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

class AgentCreate(AgentBase):
    """Schema for creating agents"""
    tenant_id: str
    created_by: str

class AgentUpdate(BaseModel):
    """Schema for updating agents"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    configuration: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class Agent(AgentBase):
    """Schema for agent responses"""
    id: str
    tenant_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    status: AgentStatus
    last_activity: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

# =====================================
# MESSAGE SCHEMAS
# =====================================

class MessageBase(BaseModel):
    """Base schema for messages"""
    role: MessageRole
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MessageCreate(MessageBase):
    """Schema for creating messages"""
    conversation_id: str
    agent_id: str

class Message(MessageBase):
    """Schema for message responses"""
    id: str
    conversation_id: str
    agent_id: str
    created_at: datetime
    
    model_config = {"from_attributes": True}

# =====================================
# CONVERSATION SCHEMAS
# =====================================

class ConversationBase(BaseModel):
    """Base schema for conversations"""
    title: Optional[str] = Field(None, max_length=255)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ConversationCreate(ConversationBase):
    """Schema for creating conversations"""
    agent_id: str

class Conversation(ConversationBase):
    """Schema for conversation responses"""
    id: str
    agent_id: str
    tenant_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    
    model_config = {"from_attributes": True}

# =====================================
# EXECUTION SCHEMAS
# =====================================

class AgentExecutionRequest(BaseModel):
    """Schema for agent execution requests"""
    task_type: str
    parameters: Dict[str, Any]
    context: Dict[str, Any] = Field(default_factory=dict)

class StreamingChatResponse(BaseModel):
    """Schema for streaming chat responses"""
    type: str = Field(..., pattern='^(message|tool_call|completion|error)$')
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

# =====================================
# DIGITAL SIGNATURE SCHEMAS
# =====================================

class SignatureProviderBase(BaseModel):
    """Base schema for signature providers"""
    provider_name: str = Field(..., pattern="^(docusign|yousign|signaturit)$")
    display_name: str = Field(..., min_length=1, max_length=100)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_default: bool = False

class SignatureProviderCreate(SignatureProviderBase):
    """Schema for creating signature providers"""
    pass

class SignatureProviderUpdate(BaseModel):
    """Schema for updating signature providers"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    configuration: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

class SignatureProvider(SignatureProviderBase):
    """Schema for signature provider responses"""
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

class SignerBase(BaseModel):
    """Base schema for signers"""
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    phone: Optional[str] = Field(None, max_length=20)
    order: int = Field(default=1, ge=1)
    authentication_method: str = Field(default='email', pattern='^(email|sms|code)$')
    success_url: Optional[str] = None
    error_url: Optional[str] = None

class SignerCreate(SignerBase):
    """Schema for creating signers"""
    pass

class Signer(SignerBase):
    """Schema for signer responses"""
    id: str
    signature_request_id: str
    status: str
    signed_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}

class SignatureRequestBase(BaseModel):
    """Base schema for signature requests"""
    title: str = Field(..., min_length=1, max_length=200)
    message: Optional[str] = None
    document_name: str = Field(..., min_length=1, max_length=255)
    signature_type: str = Field(default='sequential', pattern='^(sequential|parallel)$')
    callback_url: Optional[str] = None
    success_url: Optional[str] = None
    error_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SignatureRequestCreate(SignatureRequestBase):
    """Schema for creating signature requests"""
    document_id: str
    signers: List[SignerCreate]
    provider_id: Optional[str] = None

class SignatureRequest(SignatureRequestBase):
    """Schema for signature request responses"""
    id: str
    document_id: str
    provider_id: str
    tenant_id: str
    created_by: str
    external_id: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    signers: List[Signer] = []
    
    model_config = {"from_attributes": True}

# =====================================
# STATISTICS SCHEMAS
# =====================================

class AgentStatistics(BaseModel):
    """Schema for agent statistics"""
    total_agents: int
    active_agents: int
    total_conversations: int
    total_messages: int
    agents_by_type: Dict[str, int]
    recent_activity: List[Dict[str, Any]]

class UsageStatistics(BaseModel):
    """Schema for usage statistics"""
    period: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    avg_response_time: float
    most_used_agents: List[Dict[str, Any]]