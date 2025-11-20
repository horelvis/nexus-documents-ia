"""Pydantic schemas for internal template edit session APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class TemplateEditSessionBase(BaseModel):
    template_id: UUID
    template_name: str
    template_file_name: Optional[str] = None
    template_file_mime: Optional[str] = None
    user_id: str
    user_email: str
    tenant_id: str
    google_doc_id: str
    google_doc_url: str
    google_doc_edit_url: str
    original_content_hash: Optional[str] = None
    final_content_hash: Optional[str] = None
    content_size_bytes: int = 0


class TemplateEditSessionCreateRequest(TemplateEditSessionBase):
    expires_at: Optional[datetime] = None
    status: str = "active"


class TemplateEditSessionResponse(TemplateEditSessionBase):
    id: UUID
    created_at: datetime
    expires_at: datetime
    last_activity: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str
    changes_detected: Optional[bool] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    cleanup_attempted: bool = False
    cleanup_completed: bool = False
    cleanup_error: Optional[str] = None

    class Config:
        from_attributes = True


class TemplateEditSessionCompleteRequest(BaseModel):
    user_id: str
    changes_detected: bool
    final_content_hash: Optional[str] = None
    content_size_bytes: Optional[int] = None
    cleanup_completed: bool = False
    error_message: Optional[str] = None


class TemplateEditSessionExtendRequest(BaseModel):
    user_id: str
    hours: int = Field(1, ge=1, le=24)


class TemplateEditSessionCancelRequest(BaseModel):
    user_id: str
    reason: Optional[str] = None


class TemplateEditSessionListResponse(BaseModel):
    sessions: List[TemplateEditSessionResponse]
    total_count: int
