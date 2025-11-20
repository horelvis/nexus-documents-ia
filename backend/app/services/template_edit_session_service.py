"""
Service layer for managing template edit sessions in the core API.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.edit_session_models import TemplateEditSession


class TemplateEditSessionService:
    """Encapsulates CRUD operations for template edit sessions."""

    SESSION_TIMEOUT_HOURS = 2

    @staticmethod
    def _default_expiration() -> datetime:
        return datetime.utcnow() + timedelta(hours=TemplateEditSessionService.SESSION_TIMEOUT_HOURS)

    @classmethod
    def create_session(
        cls,
        db: Session,
        *,
        template_id: UUID,
        template_name: str,
        template_file_name: Optional[str],
        template_file_mime: Optional[str],
        user_id: str,
        user_email: str,
        tenant_id: str,
        google_doc_id: str,
        google_doc_url: str,
        google_doc_edit_url: str,
        original_content_hash: Optional[str],
        content_size_bytes: int,
        expires_at: Optional[datetime] = None,
        status: str = "active",
    ) -> TemplateEditSession:
        session = TemplateEditSession(
            template_id=template_id,
            template_name=template_name,
            template_file_name=template_file_name,
            template_file_mime=template_file_mime,
            user_id=user_id,
            user_email=user_email,
            tenant_id=tenant_id,
            google_doc_id=google_doc_id,
            google_doc_url=google_doc_url,
            google_doc_edit_url=google_doc_edit_url,
            original_content_hash=original_content_hash,
            content_size_bytes=content_size_bytes,
            expires_at=expires_at or cls._default_expiration(),
            status=status,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get_session(
        db: Session, session_id: UUID, user_id: Optional[str] = None
    ) -> Optional[TemplateEditSession]:
        stmt = select(TemplateEditSession).where(TemplateEditSession.id == session_id)
        if user_id:
            stmt = stmt.where(TemplateEditSession.user_id == user_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_active_session(
        db: Session, template_id: UUID, user_id: str
    ) -> Optional[TemplateEditSession]:
        stmt = (
            select(TemplateEditSession)
            .where(
                TemplateEditSession.template_id == template_id,
                TemplateEditSession.user_id == user_id,
                TemplateEditSession.status == "active",
            )
            .order_by(TemplateEditSession.created_at.desc())
        )
        session = db.execute(stmt).scalar_one_or_none()
        if session and session.expires_at and session.expires_at < datetime.utcnow():
            session.status = "expired"
            db.commit()
            db.refresh(session)
            return None
        return session

    @staticmethod
    def list_sessions(
        db: Session,
        *,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        include_completed: bool = False,
        include_expired: bool = False,
    ) -> List[TemplateEditSession]:
        stmt = select(TemplateEditSession)
        if user_id:
            stmt = stmt.where(TemplateEditSession.user_id == user_id)
        if tenant_id:
            stmt = stmt.where(TemplateEditSession.tenant_id == tenant_id)
        if not include_completed:
            stmt = stmt.where(TemplateEditSession.status == "active")
        if not include_expired:
            stmt = stmt.where(TemplateEditSession.expires_at >= datetime.utcnow())
        stmt = stmt.order_by(TemplateEditSession.created_at.desc())
        return db.execute(stmt).scalars().all()

    @staticmethod
    def extend_session(
        db: Session, session: TemplateEditSession, hours: int
    ) -> TemplateEditSession:
        session.expires_at = max(
            session.expires_at + timedelta(hours=hours),
            datetime.utcnow() + timedelta(hours=hours),
        )
        session.last_activity = datetime.utcnow()
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def complete_session(
        db: Session,
        session: TemplateEditSession,
        *,
        changes_detected: bool,
        final_content_hash: Optional[str],
        content_size_bytes: Optional[int],
        cleanup_completed: bool,
        error_message: Optional[str] = None,
    ) -> TemplateEditSession:
        session.status = "completed" if cleanup_completed else "cleanup_pending"
        session.completed_at = datetime.utcnow()
        session.final_content_hash = final_content_hash
        session.changes_detected = changes_detected
        if content_size_bytes is not None:
            session.content_size_bytes = content_size_bytes
        session.cleanup_completed = cleanup_completed
        if error_message:
            session.error_message = error_message
        session.last_activity = datetime.utcnow()
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def cancel_session(
        db: Session, session: TemplateEditSession, *, reason: Optional[str] = None
    ) -> TemplateEditSession:
        session.status = "cancelled"
        session.completed_at = datetime.utcnow()
        session.cleanup_completed = True
        if reason:
            session.error_message = reason
        db.commit()
        db.refresh(session)
        return session


template_edit_session_service = TemplateEditSessionService()
