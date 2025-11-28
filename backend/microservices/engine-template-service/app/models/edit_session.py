"""
Edit Session Model - Temporary editing sessions with Google Docs
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timedelta
import uuid

Base = declarative_base()


class EditSession(Base):
    """
    Temporary editing session for Google Docs integration
    Following Alfresco ECM pattern: create temp doc, edit, sync back, delete
    """
    __tablename__ = "edit_sessions"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Multi-tenant
    tenant_id = Column(String, nullable=False, index=True)
    
    # Reference to template being edited
    template_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_name = Column(String, nullable=False)
    template_file_name = Column(String, nullable=True)
    template_file_mime = Column(String, nullable=True)
    
    # User who initiated the editing session
    user_id = Column(String, nullable=False, index=True)
    user_email = Column(String, nullable=False)
    
    # Google Docs temporary document
    google_doc_id = Column(String, nullable=False, unique=True, index=True)
    google_doc_url = Column(Text, nullable=False)
    google_doc_edit_url = Column(Text, nullable=False)
    
    # Session timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    # Session status
    status = Column(
        String, 
        default="active", 
        nullable=False
    )  # "active", "completed", "expired", "error", "cleanup_pending"
    
    # Content tracking
    original_content_hash = Column(String)  # To detect if changes were made
    final_content_hash = Column(String)
    changes_detected = Column(Boolean, default=False)
    content_size_bytes = Column(Integer, default=0)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Cleanup tracking
    cleanup_attempted = Column(Boolean, default=False)
    cleanup_completed = Column(Boolean, default=False)
    cleanup_error = Column(Text)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.expires_at:
            from app.core.config import settings
            self.expires_at = datetime.utcnow() + timedelta(
                hours=settings.edit_session_timeout_hours
            )
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_active(self) -> bool:
        """Check if session is still active"""
        return self.status == "active" and not self.is_expired
    
    @property
    def time_remaining(self) -> timedelta:
        """Time remaining before expiration"""
        if self.is_expired:
            return timedelta(0)
        return self.expires_at - datetime.utcnow()
    
    def extend_session(self, hours: int = 1):
        """Extend session expiration time"""
        self.expires_at = max(
            self.expires_at + timedelta(hours=hours),
            datetime.utcnow() + timedelta(hours=hours)
        )
        self.last_activity = datetime.utcnow()
    
    def mark_completed(self, content_hash: str = None, changes_detected: bool = False):
        """Mark session as completed"""
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        self.final_content_hash = content_hash
        self.changes_detected = changes_detected
    
    def mark_expired(self):
        """Mark session as expired"""
        self.status = "expired"
        self.completed_at = datetime.utcnow()
    
    def mark_error(self, error_message: str):
        """Mark session with error"""
        self.status = "error"
        self.error_message = error_message
        self.completed_at = datetime.utcnow()
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
    
    def __repr__(self):
        return f"<EditSession(id={self.id}, template_id={self.template_id}, status={self.status})>"
