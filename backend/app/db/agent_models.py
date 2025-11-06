"""
Agent Management Models
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.db.base_class import Base


class AgentType(str, enum.Enum):
    """Types of agents available in the system"""
    DOCUMENT_ANALYZER = "document_analyzer"
    CONTRACT_INTELLIGENCE = "contract_intelligence"
    COMPLIANCE_CHECKER = "compliance_checker"
    SIGNATURE_AGENT = "signature_agent"
    FINANCIAL_ANALYZER = "financial_analyzer"
    LEGAL_ADVISOR = "legal_advisor"
    RAG_ASSISTANT = "rag_assistant"


class AgentExecutionMode(str, enum.Enum):
    """How the agent executes"""
    AUTOMATIC = "automatic"  # Runs without user confirmation
    CONFIRMATION_REQUIRED = "confirmation_required"  # Requires user confirmation
    SCHEDULED = "scheduled"  # Runs on schedule


class AgentDefinition(Base):
    """
    Master table of all available agents in the system
    This defines what agents exist, not their configuration per tenant
    """
    __tablename__ = "agent_definitions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type = Column(SQLEnum(AgentType), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # document, legal, financial, etc
    
    # Agent capabilities
    capabilities = Column(JSONB, default={})  # What the agent can do
    required_permissions = Column(JSONB, default=[])  # Permissions needed
    
    # Execution settings
    execution_mode = Column(SQLEnum(AgentExecutionMode), default=AgentExecutionMode.CONFIRMATION_REQUIRED)
    requires_context = Column(Boolean, default=True)  # Needs document/context
    supports_streaming = Column(Boolean, default=True)
    
    # Resource limits
    max_tokens = Column(Integer, default=2000)
    timeout_seconds = Column(Integer, default=300)
    
    # System fields
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    configurations = relationship("AgentConfiguration", back_populates="definition")


class AgentConfiguration(Base):
    """
    Per-tenant configuration of agents
    Controls which agents are available and how they're configured for each tenant
    """
    __tablename__ = "agent_configurations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    agent_definition_id = Column(UUID(as_uuid=True), ForeignKey("agent_definitions.id"), nullable=False)
    
    # Activation control
    is_enabled = Column(Boolean, default=False)  # Admin must explicitly enable
    enabled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    enabled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Per-tenant customization
    custom_name = Column(String(100), nullable=True)  # Override default name
    custom_description = Column(Text, nullable=True)
    custom_settings = Column(JSONB, default={})  # Tenant-specific settings
    
    # Execution overrides
    execution_mode_override = Column(SQLEnum(AgentExecutionMode), nullable=True)
    requires_approval = Column(Boolean, default=False)  # Admin approval for each execution
    allowed_users = Column(JSONB, default=[])  # Empty = all users, otherwise list of user IDs
    
    # Usage limits per tenant
    max_executions_per_day = Column(Integer, default=100)
    max_executions_per_user_per_day = Column(Integer, default=10)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    definition = relationship("AgentDefinition", back_populates="configurations")
    executions = relationship("AgentExecution", back_populates="configuration")


class AgentExecution(Base):
    """
    Track every agent execution for audit and billing
    """
    __tablename__ = "agent_executions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    configuration_id = Column(UUID(as_uuid=True), ForeignKey("agent_configurations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Execution details
    execution_type = Column(String(50), nullable=False)  # chat, analyze, process, etc
    input_data = Column(JSONB, default={})
    output_data = Column(JSONB, default={})
    
    # Context
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)  # For chat continuity
    
    # Status tracking
    status = Column(String(20), default="pending")  # pending, running, completed, failed, cancelled
    error_message = Column(Text, nullable=True)
    
    # Approval workflow (if required)
    requires_approval = Column(Boolean, default=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_notes = Column(Text, nullable=True)
    
    # Performance metrics
    tokens_used = Column(Integer, default=0)
    execution_time_ms = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    configuration = relationship("AgentConfiguration", back_populates="executions")


class AgentExecutionLog(Base):
    """
    Detailed logs for agent executions
    """
    __tablename__ = "agent_execution_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("agent_executions.id"), nullable=False)
    
    log_level = Column(String(20), nullable=False)  # info, warning, error, debug
    message = Column(Text, nullable=False)
    log_metadata = Column(JSONB, default={})
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    execution = relationship("AgentExecution", backref="logs")