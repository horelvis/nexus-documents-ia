import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Table, Float, LargeBinary, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from sqlalchemy.sql import func
from app.db.base_class import Base
from app.db.edit_session_models import TemplateEditSession  # noqa: F401

# Import agent models
from app.db.agent_models import (
    AgentType, AgentExecutionMode, AgentDefinition, 
    AgentConfiguration, AgentExecution, AgentExecutionLog
)

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
    subscription_plan = Column(String(50), nullable=True, default="trial")
    subscription_status = Column(String(50), nullable=True, default="trialing")
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    
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

    @property
    def is_admin(self) -> bool:
        """
        Convenience flag used across the API to determine if the user
        should be treated as a tenant administrator. By definition:
        - Superusers are always admins
        - Tenant owners (is_team_member == False) are admins
        - Users with a role named 'admin' are admins
        """
        if self.is_superuser:
            return True
        if not self.is_team_member:
            return True
        try:
            return any((role.name or "").lower() == "admin" for role in (self.roles or []))
        except Exception:  # pragma: no cover - relationship issues should not block checks
            return False

    @property
    def is_tenant_admin(self) -> bool:
        """Alias used by some parts of the API."""
        return self.is_admin


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
    slug = Column(String(100), nullable=True, unique=True, index=True)  # URL-friendly identifier for Site portal
    description = Column(Text, nullable=True)
    bucket_name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean(), default=True, nullable=False)
    settings = Column(JSONB, nullable=True, default={})
    max_users = Column(Integer, nullable=True)
    max_storage_mb = Column(Integer, nullable=True)

    # Auto-classification settings (RAG + LLM)
    auto_classification_enabled = Column(Boolean, default=False, nullable=False)
    auto_classification_k = Column(Integer, default=7, nullable=False)
    auto_classification_min_confidence = Column(Float, default=0.6, nullable=False)

    # Site Guest Portal settings
    site_enabled = Column(Boolean, default=False, nullable=False)  # Enable external guest access
    site_logo_url = Column(String(500), nullable=True)  # Custom logo for portal
    site_welcome_message = Column(Text, nullable=True)  # Custom welcome message

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    users = relationship("User", back_populates="tenant")
    documents = relationship("Document", back_populates="tenant")
    tags = relationship("Tag", back_populates="tenant")
    roles = relationship("Role", back_populates="tenant")
    team_invitations = relationship("TeamInvitation", back_populates="tenant", cascade="all, delete-orphan")
    site_guests = relationship("SiteGuest", back_populates="tenant", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_tenants_active', 'is_active'),
        Index('idx_tenants_slug', 'slug'),
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
    
    # Categorization fields
    category = Column(String(50), nullable=True)
    tags_array = Column(JSONB, nullable=True)  # Array of tags stored as JSONB
    document_metadata = Column(JSONB, nullable=True, default={})
    # content field removed - stored in Elasticsearch, Vector DB, and GCP only
    extracted_entities = Column(JSONB, nullable=True)
    
    indexed = Column(Integer, default=0, nullable=False)
    indexing_error = Column(Text, nullable=True)

    # Folder organization (physical folders in GCS)
    folder_path = Column(String(2000), nullable=True, default='/Sin Clasificar')
    auto_classified = Column(Boolean, default=False, nullable=False)
    classification_confidence = Column(Float, nullable=True)
    classification_reasoning = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    tenant = relationship("Tenant", back_populates="documents")
    creator = relationship("User", foreign_keys=[created_by], back_populates="created_documents")
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    metrics = relationship("DocumentMetrics", back_populates="document", uselist=False, cascade="all, delete-orphan")
    views = relationship("DocumentView", back_populates="document", cascade="all, delete-orphan")
    shares = relationship("DocumentShare", back_populates="document", cascade="all, delete-orphan")
    analyses = relationship("DocumentAnalysis", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_documents_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_documents_creator_created', 'created_by', 'created_at'),
        Index('idx_documents_type_tenant', 'file_type', 'tenant_id'),
        Index('idx_documents_indexed', 'indexed'),
        Index('idx_documents_category', 'category'),
        Index('idx_documents_category_tenant', 'category', 'tenant_id'),
        Index('idx_documents_folder_path', 'tenant_id', 'folder_path'),
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


class FolderMarker(Base):
    """
    Markers for empty folders created by users.

    In the Google Drive style navigation, folders only "exist" when they have documents.
    This table allows users to create empty folders that persist until they add documents.
    When a folder has documents, the marker is not needed (folder is derived from document paths).
    """
    __tablename__ = "folder_markers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    folder_path = Column(String(2000), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    creator = relationship("User")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'folder_path', name='uq_folder_marker_tenant_path'),
        Index('idx_folder_markers_tenant_path', 'tenant_id', 'folder_path'),
    )


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


class GoogleDriveToken(Base):
    """OAuth tokens per user for Google Drive/Docs integration."""
    __tablename__ = "google_drive_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    google_user_id = Column(String, nullable=False)
    google_email = Column(String, nullable=False)
    scopes = Column(JSONB, default=list)
    access_token_encrypted = Column(LargeBinary, nullable=False)
    refresh_token_encrypted = Column(LargeBinary, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User")
    tenant = relationship("Tenant")


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
    role = Column(String(20), nullable=False, default='signer')  # signer, viewer, approver
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


class SignatureProviderAudit(Base):
    """Auditoría de cambios en proveedores de firma digital"""
    __tablename__ = "signature_provider_audits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("signature_providers.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True)  # 'created', 'updated', 'deleted', 'activated', 'deactivated', 'set_default'
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changes = Column(JSONB, nullable=False, default={})  # Cambios realizados (excepto credenciales)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    provider = relationship("SignatureProvider")
    tenant = relationship("Tenant")
    user = relationship("User")
    
    __table_args__ = (
        Index('idx_provider_audits_provider_action', 'provider_id', 'action'),
        Index('idx_provider_audits_tenant_created', 'tenant_id', 'created_at'),
    )


# =====================================
# SIGNATURE CONTACTS
# =====================================

class SignatureContact(Base):
    """Saved contacts for signature requests"""
    __tablename__ = "signature_contacts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Contact information
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(String(100), nullable=True)  # Common role/title for this contact
    company = Column(String(200), nullable=True)
    
    # Usage tracking
    is_favorite = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Additional metadata
    notes = Column(Text, nullable=True)
    contact_metadata = Column(JSONB, nullable=True, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'email', name='uq_signature_contact_tenant_email'),
        Index('idx_signature_contacts_tenant_favorite', 'tenant_id', 'is_favorite'),
        Index('idx_signature_contacts_tenant_usage', 'tenant_id', 'usage_count'),
        Index('idx_signature_contacts_email', 'email'),
        Index('idx_signature_contacts_name', 'name'),
    )


# =====================================
# SIGNATURE AI MODELS
# =====================================

class SignatureFieldPlacement(Base):
    """Records actual signature field placements for learning"""
    __tablename__ = "signature_field_placements"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    field_type = Column(String(50), nullable=False)  # signature, date, text, etc.
    signer_identifier = Column(String(100))  # Role or identifier for the signer
    
    # Position data
    x_position = Column(Float, nullable=False)
    y_position = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    page_number = Column(Integer, nullable=False)
    
    # Additional properties
    is_required = Column(Boolean, default=True)
    label = Column(String(200))
    field_metadata = Column(JSONB, default={})
    
    # Tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", backref="signature_placements")
    tenant = relationship("Tenant")
    user = relationship("User")


class DocumentTypeClassification(Base):
    """Document type classifications for AI"""
    __tablename__ = "document_type_classifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    name = Column(String(100), nullable=False)  # contract, agreement, form, etc.
    display_name = Column(String(200))
    description = Column(Text)
    
    # Classification rules
    keywords = Column(JSONB, default=[])  # Keywords that identify this type
    patterns = Column(JSONB, default=[])  # Regex patterns
    
    # Default signature configuration
    default_signer_count = Column(Integer, default=1)
    default_field_config = Column(JSONB, default={})
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_document_type_tenant_name'),
    )


class SignaturePlacementPattern(Base):
    """Learned patterns for signature placement"""
    __tablename__ = "signature_placement_patterns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    document_type = Column(String(100), nullable=False)
    
    # Pattern configuration
    field_configurations = Column(JSONB, nullable=False)  # Array of field positions
    confidence = Column(Float, default=0.5)  # Pattern confidence score
    usage_count = Column(Integer, default=0)  # How many times this pattern was used
    
    # Metadata
    source = Column(String(50))  # manual, learned, imported
    pattern_metadata = Column(JSONB, default={})
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant")


# =====================================
# SISTEMA DE ANÁLISIS DE DOCUMENTOS (EMMA AI)
# =====================================

class DocumentAnalysis(Base):
    """
    Persisted document analysis results from Emma AI.

    Stores completed analyses with their results, annotations,
    and PDF paths for later retrieval. Enables background processing
    queue and historical analysis access.
    """
    __tablename__ = "document_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Analysis state
    status = Column(String(30), nullable=False, default="pending", index=True)  # pending, processing, completed, failed
    progress = Column(Integer, nullable=False, default=0)  # 0-100
    current_step = Column(String(200), nullable=True)  # Current step description
    error_message = Column(Text, nullable=True)

    # Analysis configuration
    analysis_type = Column(String(50), nullable=False, default="legal")  # legal, contract, compliance, general
    detected_document_type = Column(String(100), nullable=True)  # Detected type from content
    detected_document_type_display = Column(String(200), nullable=True)  # Human-readable type
    detection_confidence = Column(Float, nullable=True)  # 0.0 - 1.0

    # Plan information
    plan_id = Column(String(100), nullable=True)  # Internal plan identifier
    plan_title = Column(String(500), nullable=True)
    total_steps = Column(Integer, nullable=True, default=0)
    steps_completed = Column(Integer, nullable=True, default=0)

    # Results - stored as JSONB for flexibility
    summary = Column(Text, nullable=True)  # Executive summary
    risks = Column(JSONB, nullable=True, default=[])  # List of identified risks
    recommendations = Column(JSONB, nullable=True, default=[])  # List of recommendations
    findings = Column(JSONB, nullable=True, default=[])  # Detailed findings per agent
    annotations = Column(JSONB, nullable=True, default=[])  # PDF annotations with positions
    execution_log = Column(JSONB, nullable=True, default=[])  # Step-by-step execution log

    # Output files
    annotated_pdf_path = Column(String(1000), nullable=True)  # GCS path to annotated PDF
    annotated_pdf_url = Column(String(2000), nullable=True)  # Signed URL (temporary)

    # Metrics
    confidence_score = Column(Float, nullable=True)  # Overall confidence 0.0 - 1.0
    execution_time_ms = Column(Integer, nullable=True)  # Total execution time

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", back_populates="analyses")
    tenant = relationship("Tenant")
    creator = relationship("User")

    __table_args__ = (
        Index('idx_document_analyses_tenant_status', 'tenant_id', 'status'),
        Index('idx_document_analyses_document', 'document_id'),
        Index('idx_document_analyses_created', 'created_at'),
        Index('idx_document_analyses_tenant_created', 'tenant_id', 'created_at'),
    )

    def mark_started(self):
        """Mark analysis as started"""
        self.status = "processing"
        self.started_at = datetime.now(timezone.utc)
        self.progress = 0

    def mark_completed(self, execution_time_ms: int = None):
        """Mark analysis as completed"""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        self.progress = 100
        if execution_time_ms:
            self.execution_time_ms = execution_time_ms
        elif self.started_at:
            delta = self.completed_at - self.started_at
            self.execution_time_ms = int(delta.total_seconds() * 1000)

    def mark_failed(self, error_message: str):
        """Mark analysis as failed"""
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = datetime.now(timezone.utc)

    def update_progress(self, progress: int, current_step: str = None):
        """Update analysis progress"""
        self.progress = min(max(progress, 0), 100)
        if current_step:
            self.current_step = current_step


# =====================================
# INFORMATION CHANNELS (RAG Data Sources)
# =====================================

class InformationChannel(Base):
    """
    External data source channels for RAG pipeline.

    Supports Gmail, Google Drive, and external databases as data sources.
    Each channel can be personal (only visible to creator) or tenant-wide
    (visible to all tenant users in RAG queries).
    """
    __tablename__ = "information_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Channel identification
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    channel_type = Column(String(50), nullable=False, index=True)  # gmail, google_drive, external_db

    # Visibility control - determines who can see documents in RAG queries
    visibility = Column(String(20), nullable=False, default="personal")  # personal, tenant

    # Type-specific configuration (non-sensitive)
    # Gmail: {"labels": ["INBOX"], "max_age_days": 90, "include_attachments": true}
    # Google Drive: {"folder_id": "xxx", "folder_name": "...", "include_subfolders": true}
    # External DB: {"db_type": "postgresql", "host": "xxx", "port": 5432, "database": "xxx", "query": "SELECT..."}
    configuration = Column(JSONB, nullable=False, default={})

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(50), nullable=True)  # success, partial, failed
    last_sync_error = Column(Text, nullable=True)
    documents_indexed = Column(Integer, default=0, nullable=False)

    # Sync schedule (0 = manual only)
    sync_interval_minutes = Column(Integer, default=60, nullable=False)
    next_sync_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")
    credential = relationship("ChannelCredential", back_populates="channel", uselist=False, cascade="all, delete-orphan")
    documents = relationship("ChannelDocument", back_populates="channel", cascade="all, delete-orphan")
    sync_logs = relationship("ChannelSyncLog", back_populates="channel", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_channels_tenant_type', 'tenant_id', 'channel_type'),
        Index('idx_channels_creator_visibility', 'created_by', 'visibility'),
        Index('idx_channels_next_sync', 'next_sync_at', 'is_active'),
        Index('idx_channels_tenant_active', 'tenant_id', 'is_active'),
    )


class ChannelCredential(Base):
    """
    Encrypted credentials for channel authentication.

    Uses Fernet symmetric encryption (same pattern as GoogleDriveToken).
    Supports OAuth tokens (Gmail, Drive) and database credentials.
    """
    __tablename__ = "channel_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("information_channels.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Encrypted credentials blob (Fernet encryption with CHANNEL_ENCRYPTION_KEY)
    credentials_encrypted = Column(LargeBinary, nullable=False)

    # OAuth-specific fields (for Gmail/Drive)
    oauth_provider = Column(String(50), nullable=True)  # google
    oauth_user_id = Column(String(255), nullable=True)
    oauth_email = Column(String(255), nullable=True)
    oauth_scopes = Column(JSONB, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    channel = relationship("InformationChannel", back_populates="credential")


class ChannelDocument(Base):
    """
    Tracks documents indexed from information channels.

    Maps external IDs (Gmail message ID, Drive file ID, DB row hash) to
    Weaviate document IDs. Stores content hash for incremental sync
    (only re-index if content changed).
    """
    __tablename__ = "channel_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("information_channels.id", ondelete="CASCADE"), nullable=False, index=True)

    # External source reference
    external_id = Column(String(500), nullable=False)  # Gmail message ID, Drive file ID, DB row hash
    external_url = Column(String(2000), nullable=True)  # Link to original (if available)

    # Content hash for change detection (SHA-256)
    content_hash = Column(String(64), nullable=False)

    # Indexed document reference
    weaviate_id = Column(String(100), nullable=True)  # Weaviate object UUID

    # Metadata snapshot
    title = Column(String(500), nullable=True)
    source_metadata = Column(JSONB, nullable=True)  # Type-specific metadata

    # Processing status
    status = Column(String(30), nullable=False, default="pending", index=True)  # pending, indexed, failed, deleted
    error_message = Column(Text, nullable=True)

    # Source timestamps
    source_created_at = Column(DateTime(timezone=True), nullable=True)
    source_modified_at = Column(DateTime(timezone=True), nullable=True)

    # Indexing timestamps
    first_indexed_at = Column(DateTime(timezone=True), nullable=True)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    channel = relationship("InformationChannel", back_populates="documents")

    __table_args__ = (
        UniqueConstraint('channel_id', 'external_id', name='uq_channel_document_external'),
        Index('idx_channel_docs_status', 'channel_id', 'status'),
        Index('idx_channel_docs_hash', 'content_hash'),
        Index('idx_channel_docs_weaviate', 'weaviate_id'),
    )


class ChannelSyncLog(Base):
    """
    Audit log for channel synchronization operations.

    Tracks each sync execution with timing, results, and errors.
    Used for monitoring, debugging, and displaying sync history in UI.
    """
    __tablename__ = "channel_sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("information_channels.id", ondelete="CASCADE"), nullable=False, index=True)

    # Sync execution
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, index=True)  # running, success, partial, failed
    trigger_type = Column(String(20), nullable=False)  # manual, scheduled, webhook

    # Results
    items_found = Column(Integer, default=0, nullable=False)
    items_new = Column(Integer, default=0, nullable=False)
    items_updated = Column(Integer, default=0, nullable=False)
    items_deleted = Column(Integer, default=0, nullable=False)
    items_failed = Column(Integer, default=0, nullable=False)

    # Error details
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    channel = relationship("InformationChannel", back_populates="sync_logs")

    __table_args__ = (
        Index('idx_sync_logs_channel_started', 'channel_id', 'started_at'),
        Index('idx_sync_logs_status', 'status'),
    )


class LGPDDeletionAudit(Base):
    """LGPD User Deletion Audit Trail for compliance"""
    __tablename__ = "lgpd_deletion_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Don't FK since user will be deleted
    user_email = Column(String(255), nullable=False)  # Keep for audit
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    reason = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, in_progress, completed, failed

    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Deletion results
    deletion_summary = Column(JSONB, nullable=True)
    total_records_deleted = Column(Integer, nullable=True, default=0)
    anonymized_records = Column(Integer, nullable=True, default=0)

    # LGPD compliance fields
    lgpd_article = Column(String(50), nullable=False, default="Article 18")
    deletion_method = Column(String(100), nullable=False, default="complete_data_destruction")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    requested_by_user = relationship("User")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index('idx_lgpd_deletions_tenant_status', 'tenant_id', 'status'),
        Index('idx_lgpd_deletions_user_date', 'user_id', 'created_at'),
    )


# =====================================
# DOCUMENT ACCESS CONTROL (ACL)
# =====================================

class DocumentACL(Base):
    """
    Document-level Access Control List entry.

    Each ACL entry grants permissions to a specific grantee (user, role, or everyone)
    for a specific document. Permissions are granular: view, edit, delete, share.

    Access hierarchy:
    1. Document owner always has full access
    2. Tenant admin always has full access
    3. Explicit user ACL
    4. Role-based ACL (any matching role grants access)
    5. 'everyone' ACL (all tenant users)
    6. Default: deny
    """
    __tablename__ = "document_acls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    # Grantee: user, role, or everyone
    grantee_type = Column(String(20), nullable=False)  # 'user', 'role', 'everyone'
    grantee_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # NULL when grantee_type='everyone'

    # Granular permissions
    can_view = Column(Boolean, default=True, nullable=False)
    can_edit = Column(Boolean, default=False, nullable=False)
    can_delete = Column(Boolean, default=False, nullable=False)
    can_share = Column(Boolean, default=False, nullable=False)

    # Metadata
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    source = Column(String(50), default='manual', nullable=False)  # manual, share_link, inherited, migration

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", backref="acls")
    tenant = relationship("Tenant")
    granter = relationship("User", foreign_keys=[granted_by])
    # Note: grantee relationship depends on grantee_type - use service layer to resolve

    __table_args__ = (
        UniqueConstraint('document_id', 'grantee_type', 'grantee_id', name='uq_document_acl_grantee'),
        Index('idx_document_acls_tenant_grantee', 'tenant_id', 'grantee_type'),
        Index('idx_document_acls_document_view', 'document_id', 'can_view'),
    )

    def is_expired(self) -> bool:
        """Check if this ACL entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_permissions_dict(self) -> dict:
        """Return permissions as a dictionary."""
        return {
            "can_view": self.can_view,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_share": self.can_share,
        }


class DocumentACLAudit(Base):
    """
    Audit trail for document ACL changes.

    Records all ACL operations (granted, revoked, modified, expired) with
    before/after state for compliance and debugging. No foreign keys to
    allow audit retention even after document/user deletion.
    """
    __tablename__ = "document_acl_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # No FK - document may be deleted
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # No FK - for audit retention
    acl_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to the ACL entry (may be deleted)

    # Action details
    action = Column(String(20), nullable=False, index=True)  # granted, revoked, modified, expired
    grantee_type = Column(String(20), nullable=False)
    grantee_id = Column(UUID(as_uuid=True), nullable=True)

    # Permission state
    permissions_before = Column(JSONB, nullable=True)
    permissions_after = Column(JSONB, nullable=True)

    # Actor
    performed_by = Column(UUID(as_uuid=True), nullable=True)  # NULL for system actions like expiration
    source = Column(String(50), nullable=True)  # Where the action originated

    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_acl_audits_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_acl_audits_document_action', 'document_id', 'action'),
    )


# =====================================
# SITE GUEST ACCESS SYSTEM (SharePoint-like External Sharing)
# =====================================

class SiteGuest(Base):
    """
    External users invited to access tenant content via OTP authentication.

    Guests don't have full accounts - they authenticate via email OTP and can only
    see documents/folders explicitly shared with them. Permissions are configurable
    per guest (view, download, upload).
    """
    __tablename__ = "site_guests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Invitation tracking
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invited_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Access tracking
    last_access_at = Column(DateTime(timezone=True), nullable=True)
    access_count = Column(Integer, default=0, nullable=False)

    # Default permissions (can be overridden per document/folder)
    can_view = Column(Boolean, default=True, nullable=False)
    can_download = Column(Boolean, default=False, nullable=False)
    can_upload = Column(Boolean, default=False, nullable=False)

    # Expiration (optional)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="site_guests")
    inviter = relationship("User", foreign_keys=[invited_by_user_id])
    otp_codes = relationship("SiteGuestOTP", back_populates="guest", cascade="all, delete-orphan")
    sessions = relationship("SiteGuestSession", back_populates="guest", cascade="all, delete-orphan")
    permissions = relationship("SiteGuestPermission", back_populates="guest", cascade="all, delete-orphan")
    access_logs = relationship("SiteGuestAccessLog", back_populates="guest", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'email', name='uq_site_guest_tenant_email'),
        Index('idx_site_guests_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_site_guests_email', 'email'),
    )

    def is_expired(self) -> bool:
        """Check if guest access has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if guest can access the portal."""
        return self.is_active and not self.is_expired()


class SiteGuestOTP(Base):
    """
    One-Time Password codes for guest authentication.

    OTP codes are 6-digit numbers, hashed with SHA256, valid for 10 minutes.
    Only one active OTP per guest at a time (previous ones are invalidated).
    """
    __tablename__ = "site_guest_otp"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guest_id = Column(UUID(as_uuid=True), ForeignKey("site_guests.id", ondelete="CASCADE"), nullable=False, index=True)

    # OTP code (SHA256 hash of the 6-digit code)
    otp_hash = Column(String(64), nullable=False)

    # Validity
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Tracking
    ip_address = Column(String(45), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)  # Failed verification attempts

    # Relationships
    guest = relationship("SiteGuest", back_populates="otp_codes")

    __table_args__ = (
        Index('idx_site_guest_otp_guest_expires', 'guest_id', 'expires_at'),
    )

    def is_valid(self) -> bool:
        """Check if OTP is still valid (not expired, not used)."""
        now = datetime.now(timezone.utc)
        return (
            self.used_at is None and
            self.expires_at > now and
            self.attempts < 5  # Max 5 failed attempts
        )


class SiteGuestSession(Base):
    """
    Active sessions for authenticated guests.

    After successful OTP verification, a session token is issued. Sessions
    expire after 8 hours or on explicit logout. Token is stored as SHA256 hash.
    """
    __tablename__ = "site_guest_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guest_id = Column(UUID(as_uuid=True), ForeignKey("site_guests.id", ondelete="CASCADE"), nullable=False, index=True)

    # Session token (SHA256 hash of the actual token)
    session_token_hash = Column(String(64), nullable=False, unique=True, index=True)

    # Validity
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Client info
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    # Relationships
    guest = relationship("SiteGuest", back_populates="sessions")
    access_logs = relationship("SiteGuestAccessLog", back_populates="session")

    __table_args__ = (
        Index('idx_site_guest_sessions_active', 'is_active', 'expires_at'),
        Index('idx_site_guest_sessions_guest', 'guest_id', 'is_active'),
    )

    def is_valid(self) -> bool:
        """Check if session is still valid."""
        now = datetime.now(timezone.utc)
        return (
            self.is_active and
            self.revoked_at is None and
            self.expires_at > now
        )


class SiteGuestPermission(Base):
    """
    Specific permissions granted to a guest for a document or folder.

    Each entry grants specific permission types (view, download, upload) to
    a guest for a specific document OR folder (not both). Folder permissions
    apply to all documents within that folder.
    """
    __tablename__ = "site_guest_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guest_id = Column(UUID(as_uuid=True), ForeignKey("site_guests.id", ondelete="CASCADE"), nullable=False, index=True)

    # Target: document OR folder (mutually exclusive)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    folder_path = Column(String(2000), nullable=True)  # Folder path instead of folder_id

    # Permission type
    permission_type = Column(String(20), nullable=False)  # view, download, upload

    # Granting info
    granted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Optional expiration
    expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    guest = relationship("SiteGuest", back_populates="permissions")
    document = relationship("Document")
    granter = relationship("User", foreign_keys=[granted_by_user_id])

    __table_args__ = (
        # Either document_id OR folder_path must be set, not both
        CheckConstraint(
            '(document_id IS NOT NULL AND folder_path IS NULL) OR '
            '(document_id IS NULL AND folder_path IS NOT NULL)',
            name='ck_site_guest_permission_target'
        ),
        UniqueConstraint('guest_id', 'document_id', 'permission_type', name='uq_site_guest_doc_permission'),
        UniqueConstraint('guest_id', 'folder_path', 'permission_type', name='uq_site_guest_folder_permission'),
        Index('idx_site_guest_permissions_guest', 'guest_id'),
        Index('idx_site_guest_permissions_document', 'document_id'),
    )

    def is_expired(self) -> bool:
        """Check if permission has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class SiteGuestAccessLog(Base):
    """
    Audit trail for all guest actions.

    Logs every significant action: login, document view, download, upload.
    Used for security monitoring and compliance reporting.
    """
    __tablename__ = "site_guest_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guest_id = Column(UUID(as_uuid=True), ForeignKey("site_guests.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("site_guest_sessions.id", ondelete="SET NULL"), nullable=True)

    # Action details
    action = Column(String(50), nullable=False, index=True)  # login, logout, otp_request, view, download, upload
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)

    # Target (optional, for document actions)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    folder_path = Column(String(2000), nullable=True)

    # Client info
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    # Additional context
    details = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    guest = relationship("SiteGuest", back_populates="access_logs")
    session = relationship("SiteGuestSession", back_populates="access_logs")
    document = relationship("Document")

    __table_args__ = (
        Index('idx_site_guest_access_logs_guest_created', 'guest_id', 'created_at'),
        Index('idx_site_guest_access_logs_action', 'action', 'created_at'),
        Index('idx_site_guest_access_logs_document', 'document_id'),
    )
