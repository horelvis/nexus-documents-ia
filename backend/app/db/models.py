import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Table, Float, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from sqlalchemy.sql import func
from app.db.base_class import Base

# Intermediary Tables for Many-to-Many relationships
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True)
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True)
)

# Tabla de asociación para relaciones many-to-many
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id")),
    Column("tag_id", Integer, ForeignKey("tags.id"))
)

# Tabla de asociación para las lecturas de documentos
# CORRECCIÓN: Cambiar tipos String por UUID(as_uuid=True) para compatibilidad
document_views = Table(
    "document_views",
    Base.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),  # Cambio: UUID en lugar de String
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),  # Cambio: UUID en lugar de String
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False),  # Cambio: UUID en lugar de String
    Column("viewed_at", DateTime, default=func.now(), nullable=False),
    Column("view_duration_seconds", Integer, nullable=True),
    Column("is_complete_view", Boolean, default=False),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False),  # Cambio: UUID en lugar de String
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    clerk_user_id = Column(String, nullable=True, unique=True)  # New field
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relaciones
    tenant = relationship("Tenant", back_populates="users")
    image = relationship("UserImage", back_populates="user", uselist=False, cascade="all, delete-orphan")
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserImage(Base):
    __tablename__ = "user_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    alt_text = Column(String, nullable=True)
    content_type = Column(String, nullable=False)
    blob = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="image")


class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    users = relationship("User", secondary=user_roles, back_populates="roles")
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity = Column(String, nullable=False)  # e.g., 'document', 'user', 'tenant'
    action = Column(String, nullable=False)  # e.g., 'create', 'read', 'update', 'delete'
    access = Column(String, nullable=False)  # e.g., 'own', 'tenant', 'all'
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    __table_args__ = (UniqueConstraint('action', 'entity', 'access', name='uq_action_entity_access'),)


class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    prices = relationship("Price", back_populates="plan", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="plan")


class Price(Base):
    __tablename__ = "prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    amount = Column(Integer, nullable=False)  # Amount in cents
    currency = Column(String, nullable=False)  # e.g., 'usd', 'eur'
    interval = Column(String, nullable=False)  # e.g., 'month', 'year'
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    plan = relationship("Plan", back_populates="prices")
    subscriptions = relationship("Subscription", back_populates="price")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    price_id = Column(UUID(as_uuid=True), ForeignKey("prices.id"), nullable=False)
    status = Column(String, nullable=False)  # e.g., 'active', 'canceled', 'past_due'
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    cancel_at_period_end = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="subscription")
    plan = relationship("Plan", back_populates="subscriptions")
    price = relationship("Price", back_populates="subscriptions")


class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    bucket_name = Column(String, nullable=False)
    is_active = Column(Boolean(), default=True)
    settings = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relaciones
    users = relationship("User", back_populates="tenant")
    documents = relationship("Document", back_populates="tenant")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    indexed = Column(Integer, default=0)  # See IndexingStatus enum in app.schemas.enums
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    
    # Relaciones
    tenant = relationship("Tenant", back_populates="documents")
    creator = relationship("User")
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    # Nuevas relaciones
    metrics = relationship("DocumentMetrics", back_populates="document", uselist=False, cascade="all, delete-orphan")
    views = relationship("User", secondary=document_views, backref="viewed_documents")
    
    # Método de ayuda para incrementar métricas
    def increment_metric(self, metric_name, session, amount=1):
        if not self.metrics:
            self.metrics = DocumentMetrics(document_id=self.id, tenant_id=self.tenant_id)
            session.add(self.metrics)
        
        current_value = getattr(self.metrics, metric_name, 0)
        setattr(self.metrics, metric_name, current_value + amount)
        
        if metric_name == "view_count":
            self.metrics.last_viewed_at = func.now()
        
        # Actualizar relevance_score basado en todas las métricas
        self._update_relevance_score()
        
    def _update_relevance_score(self):
        # Fórmula simple para calcular relevancia: se puede ajustar según necesidades
        view_weight = 1.0
        download_weight = 3.0
        share_weight = 2.0
        query_weight = 1.5
        recency_weight = 2.0  # Para favorecer documentos vistos recientemente
        
        base_score = (
            self.metrics.view_count * view_weight +
            self.metrics.download_count * download_weight +
            self.metrics.share_count * share_weight +
            self.metrics.query_count * query_weight
        )
        
        # Factor de recencia: favorece documentos vistos recientemente
        recency_factor = 1.0
        if self.metrics.last_viewed_at:
            days_since_view = (datetime.now() - self.metrics.last_viewed_at).days
            if days_since_view < 30:  # Documentos vistos en el último mes
                recency_factor = 1 + ((30 - days_since_view) / 30) * recency_weight
        
        self.metrics.relevance_score = base_score * recency_factor


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String, nullable=True)  # ID en la base de datos vectorial
    
    # Relaciones
    document = relationship("Document", back_populates="chunks")


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relaciones
    tenant = relationship("Tenant")
    documents = relationship("Document", secondary=document_tags, back_populates="tags")


# Tabla para métricas de documentos
class DocumentMetrics(Base):
    __tablename__ = "document_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    view_count = Column(Integer, default=0)
    download_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    query_count = Column(Integer, default=0)  # Número de consultas sobre este documento
    
    relevance_score = Column(Float, default=0.0)  # Puntuación calculada de relevancia
    last_viewed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    document = relationship("Document", back_populates="metrics")
    tenant = relationship("Tenant")


# =====================================
# SISTEMA DE AGENTES MULTI-TENANT
# =====================================

class Agent(Base):
    """Modelo para agentes AI del sistema"""
    __tablename__ = "agents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=False)  # 'digital_signature', 'document_analyzer', etc.
    
    # Multi-tenant
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Configuración del agente
    configuration = Column(JSONB, nullable=False, default={})  # Configuración específica del tipo
    tools = Column(ARRAY(String), nullable=False, default=[])  # Lista de herramientas disponibles
    
    # Estado y permisos
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=False)  # Si otros usuarios del tenant pueden usarlo
    
    # Metadatos
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    tenant = relationship("Tenant")
    creator = relationship("User")
    conversations = relationship("AgentConversation", back_populates="agent")
    executions = relationship("AgentExecution", back_populates="agent")
    
    __table_args__ = (
        UniqueConstraint('name', 'tenant_id', name='uq_agent_name_tenant'),
    )


class AgentConversation(Base):
    """Conversaciones con agentes"""
    __tablename__ = "agent_conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    title = Column(String(200), nullable=True)
    context = Column(JSONB, nullable=False, default={})  # Contexto persistente
    
    # Estado
    is_active = Column(Boolean, default=True)
    
    # Metadatos
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    agent = relationship("Agent", back_populates="conversations")
    user = relationship("User")
    tenant = relationship("Tenant")
    messages = relationship("AgentMessage", back_populates="conversation")


class AgentMessage(Base):
    """Mensajes en conversaciones con agentes"""
    __tablename__ = "agent_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("agent_conversations.id"), nullable=False)
    
    # Contenido del mensaje
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    message_metadata = Column(JSONB, nullable=False, default={})  # Attachments, tool calls, etc.
    
    # Metadatos
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relaciones
    conversation = relationship("AgentConversation", back_populates="messages")


class AgentExecution(Base):
    """Ejecuciones de agentes para auditoría"""
    __tablename__ = "agent_executions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    # Detalles de ejecución
    task_type = Column(String(100), nullable=False)  # Tipo de tarea ejecutada
    input_data = Column(JSONB, nullable=False)  # Datos de entrada
    output_data = Column(JSONB, nullable=True)  # Resultado
    
    # Estado y métricas
    status = Column(String(20), nullable=False, default='pending')  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    
    # Metadatos
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relaciones
    agent = relationship("Agent", back_populates="executions")
    user = relationship("User")
    tenant = relationship("Tenant")


class AgentTool(Base):
    """Herramientas disponibles para agentes"""
    __tablename__ = "agent_tools"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    
    # Configuración de la herramienta
    tool_type = Column(String(50), nullable=False)  # 'internal', 'external_api', 'custom'
    configuration_schema = Column(JSONB, nullable=False)  # JSON Schema para configuración
    
    # Permisos
    requires_admin = Column(Boolean, default=False)
    is_tenant_specific = Column(Boolean, default=False)
    
    # Metadatos
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


# =====================================
# SISTEMA DE FIRMA DIGITAL
# =====================================

class SignatureProvider(Base):
    """Proveedores de firma digital por tenant"""
    __tablename__ = "signature_providers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    # Configuración del proveedor
    provider_name = Column(String(50), nullable=False)  # 'docusign', 'yousign', 'signaturit'
    display_name = Column(String(100), nullable=False)
    
    # Credenciales encriptadas
    encrypted_credentials = Column(LargeBinary, nullable=False)  # Credenciales cifradas
    
    # Estado
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    
    # Configuración específica
    configuration = Column(JSONB, nullable=False, default={})
    
    # Metadatos
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    tenant = relationship("Tenant")
    signature_requests = relationship("SignatureRequest", back_populates="provider")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider_name', name='uq_tenant_provider'),
    )


class SignatureRequest(Base):
    """Solicitudes de firma digital"""
    __tablename__ = "signature_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("signature_providers.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Identificadores externos
    external_id = Column(String(255), nullable=True)  # ID en el proveedor externo
    
    # Información del documento
    document_name = Column(String(255), nullable=False)
    document_content = Column(LargeBinary, nullable=True)  # Contenido del documento
    document_url = Column(String(500), nullable=True)  # URL del documento
    
    # Configuración de firma
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    signature_type = Column(String(20), default='sequential')  # sequential, parallel
    
    # Estado
    status = Column(String(30), default='draft')  # draft, sent, in_progress, completed, declined, expired
    
    # URLs y configuración
    callback_url = Column(String(500), nullable=True)
    success_url = Column(String(500), nullable=True)
    error_url = Column(String(500), nullable=True)
    
    # Metadatos
    metadata = Column(JSONB, nullable=False, default={})
    
    # Fechas
    created_at = Column(DateTime, default=func.now(), nullable=False)
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    # Relaciones
    tenant = relationship("Tenant")
    provider = relationship("SignatureProvider", back_populates="signature_requests")
    creator = relationship("User")
    signers = relationship("SignatureRequestSigner", back_populates="request")
    events = relationship("SignatureEvent", back_populates="request")


class SignatureRequestSigner(Base):
    """Firmantes de una solicitud de firma"""
    __tablename__ = "signature_request_signers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("signature_requests.id"), nullable=False)
    
    # Información del firmante
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    
    # Configuración de firma
    order = Column(Integer, nullable=False, default=1)
    authentication_method = Column(String(20), default='email')  # email, sms, code
    
    # URLs personalizadas
    success_url = Column(String(500), nullable=True)
    error_url = Column(String(500), nullable=True)
    
    # Estado
    status = Column(String(20), default='pending')  # pending, sent, opened, signed, declined
    
    # Identificadores externos
    external_id = Column(String(255), nullable=True)
    signing_url = Column(String(500), nullable=True)
    
    # Metadatos
    signed_at = Column(DateTime, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Relaciones
    request = relationship("SignatureRequest", back_populates="signers")


class SignatureEvent(Base):
    """Eventos de auditoría para firmas"""
    __tablename__ = "signature_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("signature_requests.id"), nullable=False)
    
    # Información del evento
    event_type = Column(String(50), nullable=False)  # created, sent, opened, signed, completed, etc.
    description = Column(Text, nullable=True)
    
    # Datos del evento
    event_data = Column(JSONB, nullable=False, default={})
    
    # Metadatos
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relaciones
    request = relationship("SignatureRequest", back_populates="events")