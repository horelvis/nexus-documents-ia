"""
Internal API for managing template edit sessions consumed by microservices.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.async_dependencies import require_microservice_api_key
from app.schemas.template_edit_session import (
    TemplateEditSessionCreateRequest,
    TemplateEditSessionResponse,
    TemplateEditSessionCompleteRequest,
    TemplateEditSessionExtendRequest,
    TemplateEditSessionCancelRequest,
    TemplateEditSessionListResponse,
)
from app.services.template_edit_session_service import template_edit_session_service

router = APIRouter(
    tags=["internal-template-edit-sessions"],
    dependencies=[Depends(require_microservice_api_key)],
)


@router.get(
    "/active",
    response_model=TemplateEditSessionResponse,
    responses={404: {"description": "No active session found"}},
)
def get_active_session(
    template_id: UUID,
    user_id: str,
    db: Session = Depends(get_db),
):
    session = template_edit_session_service.get_active_session(
        db, template_id=template_id, user_id=user_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")
    return session


@router.get(
    "/{session_id}",
    response_model=TemplateEditSessionResponse,
    responses={404: {"description": "Session not found"}},
)
def get_session(
    session_id: UUID,
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    session = template_edit_session_service.get_session(
        db, session_id=session_id, user_id=user_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/", response_model=TemplateEditSessionListResponse)
def list_sessions(
    user_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    include_completed: bool = Query(default=False),
    include_expired: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    sessions = template_edit_session_service.list_sessions(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        include_completed=include_completed,
        include_expired=include_expired,
    )
    return TemplateEditSessionListResponse(
        sessions=sessions,
        total_count=len(sessions),
    )


@router.post(
    "/",
    response_model=TemplateEditSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: TemplateEditSessionCreateRequest,
    db: Session = Depends(get_db),
):
    session = template_edit_session_service.create_session(
        db,
        template_id=payload.template_id,
        template_name=payload.template_name,
        template_file_name=payload.template_file_name,
        template_file_mime=payload.template_file_mime,
        user_id=payload.user_id,
        user_email=payload.user_email,
        tenant_id=payload.tenant_id,
        google_doc_id=payload.google_doc_id,
        google_doc_url=payload.google_doc_url,
        google_doc_edit_url=payload.google_doc_edit_url,
        original_content_hash=payload.original_content_hash,
        content_size_bytes=payload.content_size_bytes,
        expires_at=payload.expires_at,
        status=payload.status,
    )
    return session


@router.post(
    "/{session_id}/extend",
    response_model=TemplateEditSessionResponse,
)
def extend_session(
    session_id: UUID,
    request: TemplateEditSessionExtendRequest,
    db: Session = Depends(get_db),
):
    session = template_edit_session_service.get_session(
        db, session_id=session_id, user_id=request.user_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return template_edit_session_service.extend_session(
        db, session=session, hours=request.hours
    )


@router.post(
    "/{session_id}/complete",
    response_model=TemplateEditSessionResponse,
)
def complete_session(
    session_id: UUID,
    request: TemplateEditSessionCompleteRequest,
    db: Session = Depends(get_db),
):
    session = template_edit_session_service.get_session(
        db, session_id=session_id, user_id=request.user_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return template_edit_session_service.complete_session(
        db,
        session=session,
        changes_detected=request.changes_detected,
        final_content_hash=request.final_content_hash,
        content_size_bytes=request.content_size_bytes,
        cleanup_completed=request.cleanup_completed,
        error_message=request.error_message,
    )


@router.delete(
    "/{session_id}",
    response_model=TemplateEditSessionResponse,
)
def cancel_session(
    session_id: UUID,
    request: TemplateEditSessionCancelRequest,
    db: Session = Depends(get_db),
):
    session = template_edit_session_service.get_session(
        db, session_id=session_id, user_id=request.user_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return template_edit_session_service.cancel_session(
        db, session=session, reason=request.reason
    )
