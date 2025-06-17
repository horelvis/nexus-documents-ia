import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Table, Float, LargeBinary, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from sqlalchemy.sql import func
from app.db.base_class import Base

# =====================================
# TABLAS DE ASOCIACIÓN (Many-to-Many)
# =====================================

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

document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True)
)

# =====================================
# TABLAS DE AUDITORÍA SEPARADAS
# =====================================

class RoleAssignmentAudit(Base):
    """Auditoría de asignaciones/remociones de roles"""
    __tablename__ = "role_assignment_audits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True)  # 'assigned', 'removed'
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    user = relationship("User", foreign_keys=[user_id])
    role = relationship("Role")
    assigner = relationship("User", foreign_keys=[assigned_by])
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_role_audits_user_action', 'user_id', 'action'),
        Index('idx_role_audits_tenant_created', 'tenant_id', 'created_at'),
    )


class PermissionAssignmentAudit(Base):
    """Auditoría de asignaciones/remociones de permisos a roles"""
    __tablename__ = "permission_assignment_audits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    action = Column(String(20), nullable=False, index=True)  # 'assigned', 'removed'
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    role = relationship("Role")
    permission = relationship("Permission")
    assigner = relationship("User")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_permission_audits_role_action', 'role_id', 'action'),
        Index('idx_permission_audits_tenant_created', 'tenant_id', 'created_at'),
    )


class DocumentTagAudit(Base):
    """Auditoría de asignaciones/remociones de tags a documentos"""
    __tablename__ = "document_tag_audits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True)  # 'tagged', 'untagged'
    tagged_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    document = relationship("Document")
    tag = relationship("Tag")
    tagger = relationship("User")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_tag_audits_document_action', 'document_id', 'action'),
        Index('idx_tag_audits_tenant_created', 'tenant_id', 'created_at'),
    )


# =====================================
# MODELOS PRINCIPALES
# =====================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    clerk_user_id = Column(String(255), nullable=True, unique=True, index=True)
    stripe_customer_id = Column(String(255), nullable=True, unique=True, index=True)
    
    # Subscription info cached from Stripe
    subscription_plan = Column(String(50), nullable=True, default="free")
    subscription_status = Column(String(50), nullable=True, default="active")
    
    # Team member info
    is_team_member = Column(Boolean(), default=False, nullable=False)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    
    is_active = Column(Boolean(), default=True, nullable=False)
    is_superuser = Column(Boolean(), default=False, nullable=False)
    onboarding_completed = Column(Boolean(), default=False, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    
    last_login_at = Column(DateTime, nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    tenant = relationship("Tenant", back_populates="users")
    image = relationship("UserImage", back_populates="user", uselist=False, cascade="all, delete-orphan")
    # profile eliminado - datos se obtienen de Clerk y Stripe
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    created_documents = relationship("Document", foreign_keys="Document.created_by", back_populates="creator")
    document_views = relationship("DocumentView", back_populates="user", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_users_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_users_email_active', 'email', 'is_active'),
    )


class UserImage(Base):
    __tablename__ = "user_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    alt_text = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=False)
    blob = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="image")


# UserProfile eliminado - Los datos de perfil se obtienen de Clerk y Stripe
# No necesitamos duplicar datos entre servicios externos y nuestra DB


class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    is_system_role = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    users = relationship("User", secondary=user_roles, back_populates="roles")
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        UniqueConstraint('name', 'tenant_id', name='uq_role_name_tenant'),
        Index('idx_roles_tenant_system', 'tenant_id', 'is_system_role'),
    )


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    access = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=True)
    conditions = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    __table_args__ = (
        UniqueConstraint('entity', 'action', 'access', 'resource_id', name='uq_permission_full'),
        Index('idx_permissions_entity_action', 'entity', 'action'),
    )


class TeamInvitation(Base):
    __tablename__ = "team_invitations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invitation_code = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)  # Optional: specific email to invite
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean(), default=False, nullable=False)
    used_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="team_invitations")
    inviter = relationship("User", foreign_keys=[invited_by], backref="sent_invitations")
    invited_user = relationship("User", foreign_keys=[used_by], backref="received_invitation")
    
    __table_args__ = (
        Index('idx_invitation_code_expires', 'invitation_code', 'expires_at'),
    )


# Removed Team and TeamMember models - using tenant-based team structure instead
# Each tenant represents one team, users are either admins (is_team_member=False) or team members (is_team_member=True)


class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    bucket_name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean(), default=True, nullable=False)
    settings = Column(JSONB, nullable=True, default={})
    max_users = Column(Integer, nullable=True)
    max_storage_mb = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    users = relationship("User", back_populates="tenant")
    documents = relationship("Document", back_populates="tenant")
    tags = relationship("Tag", back_populates="tenant")
    roles = relationship("Role", back_populates="tenant")
    team_invitations = relationship("TeamInvitation", back_populates="tenant", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_tenants_active', 'is_active'),
    )


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(200), nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)
    version = Column(Integer, default=1, nullable=False)
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    indexed = Column(Integer, default=0, nullable=False)
    indexing_error = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    tenant = relationship("Tenant", back_populates="documents")
    creator = relationship("User", foreign_keys=[created_by], back_populates="created_documents")
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    metrics = relationship("DocumentMetrics", back_populates="document", uselist=False, cascade="all, delete-orphan")
    views = relationship("DocumentView", back_populates="document", cascade="all, delete-orphan")
    shares = relationship("DocumentShare", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_documents_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_documents_creator_created', 'created_by', 'created_at'),
        Index('idx_documents_type_tenant', 'file_type', 'tenant_id'),
        Index('idx_documents_indexed', 'indexed'),
    )
    
    def increment_metric(self, metric_name: str, session, amount: int = 1):
        if not self.metrics:
            self.metrics = DocumentMetrics(document_id=self.id, tenant_id=self.tenant_id)
            session.add(self.metrics)
        
        current_value = getattr(self.metrics, metric_name, 0)
        setattr(self.metrics, metric_name, current_value + amount)
        
        if metric_name == "view_count":
            self.metrics.last_viewed_at = datetime.now(timezone.utc)
        
        self._update_relevance_score()
        
    def _update_relevance_score(self):
        if not self.metrics:
            return
            
        view_weight = 1.0
        download_weight = 3.0
        share_weight = 2.0
        query_weight = 1.5
        recency_weight = 2.0
        
        base_score = (
            self.metrics.view_count * view_weight +
            self.metrics.download_count * download_weight +
            self.metrics.share_count * share_weight +
            self.metrics.query_count * query_weight
        )
        
        recency_factor = 1.0
        if self.metrics.last_viewed_at:
            days_since_view = (datetime.now() - self.metrics.last_viewed_at).days
            if days_since_view < 30:
                recency_factor = 1 + ((30 - days_since_view) / 30) * recency_weight
        
        self.metrics.relevance_score = base_score * recency_factor


class DocumentView(Base):
    __tablename__ = "document_views"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    view_duration_seconds = Column(Integer, nullable=True)
    is_complete_view = Column(Boolean, default=False, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    page_views = Column(Integer, default=1, nullable=False)
    scroll_percentage = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    user = relationship("User", back_populates="document_views")
    document = relationship("Document", back_populates="views")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_document_views_doc_user', 'document_id', 'user_id'),
        Index('idx_document_views_tenant_date', 'tenant_id', 'viewed_at'),
        Index('idx_document_views_user_date', 'user_id', 'viewed_at'),
    )


class DocumentShare(Base):
    __tablename__ = "document_shares"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Share settings
    share_token = Column(String(255), nullable=False, unique=True, index=True)
    share_type = Column(String(50), nullable=False, default='view')  # view, download, edit
    permissions = Column(JSONB, nullable=True)  # Additional permissions
    
    # Access control
    password_hash = Column(String(255), nullable=True)  # Optional password protection
    max_access_count = Column(Integer, nullable=True)  # Limit number of accesses
    current_access_count = Column(Integer, nullable=False, default=0)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Recipient info (optional)
    recipient_email = Column(String(255), nullable=True)
    recipient_name = Column(String(255), nullable=True)
    share_message = Column(Text, nullable=True)
    
    # Tracking
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    first_accessed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="shares")
    tenant = relationship("Tenant")
    creator = relationship("User", foreign_keys=[created_by])
    revoker = relationship("User", foreign_keys=[revoked_by])
    access_logs = relationship("DocumentShareAccessLog", back_populates="share", cascade="all, delete-orphan")
    recipients = relationship("DocumentShareRecipient", back_populates="share", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_document_shares_document', 'document_id'),
        Index('idx_document_shares_tenant', 'tenant_id'),
        Index('idx_document_shares_expires', 'expires_at'),
        Index('idx_document_shares_created_by', 'created_by'),
    )
    
    def is_valid(self):
        """Check if the share link is still valid"""
        now = datetime.now(timezone.utc)
        
        # Check if active
        if not self.is_active:
            return False
        
        # Check if expired
        if self.expires_at and self.expires_at < now:
            return False
        
        # Check if revoked
        if self.revoked_at:
            return False
        
        # Check access count limit
        if self.max_access_count and self.current_access_count >= self.max_access_count:
            return False
        
        return True
    
    def increment_access_count(self):
        """Increment the access count"""
        self.current_access_count += 1
        if not self.first_accessed_at:
            self.first_accessed_at = datetime.now(timezone.utc)
        self.last_accessed_at = datetime.now(timezone.utc)


class DocumentShareAccessLog(Base):
    __tablename__ = "document_share_access_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    share_id = Column(UUID(as_uuid=True), ForeignKey("document_shares.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Access details
    accessed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    referrer = Column(Text, nullable=True)
    
    # Action performed
    action = Column(String(50), nullable=False, default='view')  # view, download, print
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    
    # Geographic info (optional)
    country_code = Column(String(2), nullable=True)
    city = Column(String(100), nullable=True)
    
    # Device info
    device_type = Column(String(50), nullable=True)  # desktop, mobile, tablet
    browser = Column(String(50), nullable=True)
    os = Column(String(50), nullable=True)
    
    # User info if authenticated
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    share = relationship("DocumentShare", back_populates="access_logs")
    document = relationship("Document")
    tenant = relationship("Tenant")
    user = relationship("User")
    
    __table_args__ = (
        Index('idx_share_access_logs_share', 'share_id'),
        Index('idx_share_access_logs_document', 'document_id'),
        Index('idx_share_access_logs_accessed', 'accessed_at'),
        Index('idx_share_access_logs_tenant', 'tenant_id'),
    )


class DocumentShareRecipient(Base):
    __tablename__ = "document_share_recipients"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    share_id = Column(UUID(as_uuid=True), ForeignKey("document_shares.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Recipient info
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    verification_code = Column(String(100), nullable=True)  # For email verification
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notification status
    notified_at = Column(DateTime(timezone=True), nullable=True)
    notification_error = Column(Text, nullable=True)
    
    # Access status
    first_accessed_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    access_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    share = relationship("DocumentShare", back_populates="recipients")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        UniqueConstraint('share_id', 'email', name='uq_share_recipient_email'),
        Index('idx_share_recipients_share', 'share_id'),
        Index('idx_share_recipients_email', 'email'),
        Index('idx_share_recipients_tenant', 'tenant_id'),
    )


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    color = Column(String(7), nullable=True)
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    tenant = relationship("Tenant", back_populates="tags")
    documents = relationship("Document", secondary=document_tags, back_populates="tags")
    
    __table_args__ = (
        UniqueConstraint('name', 'tenant_id', name='uq_tag_name_tenant'),
        Index('idx_tags_tenant_name', 'tenant_id', 'name'),
    )


class DocumentMetrics(Base):
    __tablename__ = "document_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    
    view_count = Column(Integer, default=0, nullable=False)
    download_count = Column(Integer, default=0, nullable=False)
    share_count = Column(Integer, default=0, nullable=False)
    query_count = Column(Integer, default=0, nullable=False)
    
    relevance_score = Column(Float, default=0.0, nullable=False)
    last_viewed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    document = relationship("Document", back_populates="metrics")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_document_metrics_tenant_relevance', 'tenant_id', 'relevance_score'),
        Index('idx_document_metrics_last_viewed', 'last_viewed_at'),
    )


# =====================================
# SISTEMA DE FIRMAS DIGITALES
# =====================================

class SignatureProvider(Base):
    __tablename__ = "signature_providers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    provider_name = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    encrypted_credentials = Column(LargeBinary, nullable=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    configuration = Column(JSONB, nullable=False, default={})
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    tenant = relationship("Tenant")
    signature_requests = relationship("SignatureRequest", back_populates="provider")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider_name', name='uq_tenant_provider'),
    )


class SignatureRequest(Base):
    __tablename__ = "signature_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("signature_providers.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    external_id = Column(String(255), nullable=True)
    document_name = Column(String(255), nullable=False)
    document_content = Column(LargeBinary, nullable=True)
    document_url = Column(String(500), nullable=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    signature_type = Column(String(20), default='sequential')
    status = Column(String(30), default='draft')
    callback_url = Column(String(500), nullable=True)
    success_url = Column(String(500), nullable=True)
    error_url = Column(String(500), nullable=True)
    request_metadata = Column(JSONB, nullable=False, default={})
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    tenant = relationship("Tenant")
    provider = relationship("SignatureProvider", back_populates="signature_requests")
    creator = relationship("User")
    signers = relationship("SignatureRequestSigner", back_populates="request")
    events = relationship("SignatureEvent", back_populates="request")


class SignatureRequestSigner(Base):
    __tablename__ = "signature_request_signers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("signature_requests.id"), nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    order = Column(Integer, nullable=False, default=1)
    authentication_method = Column(String(20), default='email')
    success_url = Column(String(500), nullable=True)
    error_url = Column(String(500), nullable=True)
    status = Column(String(20), default='pending')
    external_id = Column(String(255), nullable=True)
    signing_url = Column(String(500), nullable=True)
    
    signed_at = Column(DateTime, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    request = relationship("SignatureRequest", back_populates="signers")


class SignatureEvent(Base):
    __tablename__ = "signature_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("signature_requests.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    event_data = Column(JSONB, nullable=False, default={})
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    request = relationship("SignatureRequest", back_populates="events")