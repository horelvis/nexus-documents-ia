"""Schemas for forge session management."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    CREATED = "created"
    ANALYZED = "analyzed"
    PREPARED = "prepared"
    RENDERED = "rendered"
    PERSISTED = "persisted"


class ForgeSession(BaseModel):
    session_id: str
    user_id: str
    status: SessionStatus = SessionStatus.CREATED
    source_title: str = ""
    document_type: str = ""
    fields: list[dict[str, Any]] = Field(default_factory=list)
    field_values: dict[str, str] = Field(default_factory=dict)
    document_title: str = ""
    confidence: float = 0.0
    source_format: str = "docx"  # "pdf" or "docx"
    created_at: str = ""
    updated_at: str = ""


class PersistRequest(BaseModel):
    session_id: str
    user_id: str
    persist_formats: list[str] = Field(default=["docx"])
    index_in_weaviate: bool = True
    folder_path: str = ""


class PersistResponse(BaseModel):
    document_id: Optional[str] = None
    gcs_paths: dict[str, str] = Field(default_factory=dict)
    weaviate_indexed: bool = False
    indexed_document_id: Optional[str] = None
