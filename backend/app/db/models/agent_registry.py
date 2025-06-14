"""
Agent Registry Models - Dynamic agent configuration and management
"""
from sqlalchemy import Column, String, Text, JSON, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from app.db.base import Base


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TESTING = "testing"
    DEPRECATED = "deprecated"


class AgentType(str, enum.Enum):
    CONVERSATIONAL = "conversational"
    ANALYTICAL = "analytical"
    WORKFLOW = "workflow"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class AgentDefinition(Base):
    """Dynamic agent definitions that can be created/modified at runtime"""
    __tablename__ = "agent_definitions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Basic info
    name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(200), nullable=False)
    description = Column(Text)
    icon = Column(String(50))  # Icon name or emoji
    color = Column(String(20))  # UI color theme
    
    # Classification
    agent_type = Column(Enum(AgentType), default=AgentType.CUSTOM)
    category = Column(String(50))  # e.g., "financial", "legal", "general"
    tags = Column(JSON, default=list)  # Searchable tags
    
    # Configuration
    base_class = Column(String(100), default="EnhancedLangroidAgent")
    system_prompt = Column(Text, nullable=False)
    capabilities = Column(JSON, default=dict)  # What the agent can do
    parameters = Column(JSON, default=dict)  # Configurable parameters
    
    # UI Configuration
    ui_config = Column(JSON, default=dict)  # How to display in frontend
    quick_actions = Column(JSON, default=list)  # Suggested actions/questions
    filters = Column(JSON, default=dict)  # Custom filters for this agent
    
    # Access Control
    is_public = Column(Boolean, default=True)  # Available to all tenants
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    required_permissions = Column(JSON, default=list)  # Required user permissions
    required_subscription = Column(String(50))  # Minimum subscription tier
    
    # Versioning
    version = Column(String(20), default="1.0.0")
    status = Column(Enum(AgentStatus), default=AgentStatus.ACTIVE)
    
    # Metadata
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    creator = relationship("User", back_populates="created_agents")
    deployments = relationship("AgentDeployment", back_populates="definition")
    templates = relationship("AgentTemplate", back_populates="agent_definition")


class AgentDeployment(Base):
    """Track agent deployments per tenant"""
    __tablename__ = "agent_deployments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # References
    agent_definition_id = Column(UUID(as_uuid=True), ForeignKey("agent_definitions.id"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    
    # Deployment config
    is_enabled = Column(Boolean, default=True)
    custom_config = Column(JSON, default=dict)  # Tenant-specific overrides
    custom_prompt = Column(Text)  # Optional prompt override
    
    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_used = Column(DateTime)
    
    # Metadata
    deployed_at = Column(DateTime, default=datetime.utcnow)
    deployed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    definition = relationship("AgentDefinition", back_populates="deployments")
    tenant = relationship("Tenant", back_populates="agent_deployments")
    deployer = relationship("User")


class AgentTemplate(Base):
    """Pre-built agent templates for common use cases"""
    __tablename__ = "agent_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Template info
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50))
    
    # Template content
    agent_definition_id = Column(UUID(as_uuid=True), ForeignKey("agent_definitions.id"))
    template_config = Column(JSON, default=dict)
    sample_queries = Column(JSON, default=list)
    
    # Metadata
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    agent_definition = relationship("AgentDefinition", back_populates="templates")


class AgentPlugin(Base):
    """Extensible plugin system for agents"""
    __tablename__ = "agent_plugins"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Plugin info
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    version = Column(String(20))
    
    # Plugin code/config
    plugin_type = Column(String(50))  # "tool", "analyzer", "integration"
    configuration = Column(JSON, default=dict)
    code_reference = Column(String(200))  # Module path or URL
    
    # Compatibility
    compatible_agents = Column(JSON, default=list)  # Agent types/names
    required_dependencies = Column(JSON, default=list)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)