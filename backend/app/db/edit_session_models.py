"""
Template Edit Session models for workflow template Google Docs editing.
"""
from datetime import datetime, timedelta
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class TemplateEditSession(Base):
    """
    Temporary editing session for Google Docs integration.
    """

    __tablename__ = "edit_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_name = Column(String, nullable=False)
    template_file_name = Column(String, nullable=True)
    template_file_mime = Column(String, nullable=True)
    user_id = Column(String, nullable=False, index=True)
    user_email = Column(String, nullable=False)
    google_doc_id = Column(String, nullable=False, unique=True, index=True)
    google_doc_url = Column(Text, nullable=False)
    google_doc_edit_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String, default="active", nullable=False)
    original_content_hash = Column(String)
    final_content_hash = Column(String)
    changes_detected = Column(Boolean, default=False)
    content_size_bytes = Column(Integer, default=0)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    cleanup_attempted = Column(Boolean, default=False)
    cleanup_completed = Column(Boolean, default=False)
    cleanup_error = Column(Text)

    __table_args__ = (
        UniqueConstraint("google_doc_id", name="uq_edit_sessions_google_doc_id"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=2)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
