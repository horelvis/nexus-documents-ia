"""Schemas for document analysis (field detection)."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    DATE = "date"
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    NAME = "name"
    ADDRESS = "address"
    EMAIL = "email"
    PHONE = "phone"
    CHECKBOX = "checkbox"


class UserIntent(str, Enum):
    RENEWAL = "renewal"
    MODIFICATION = "modification"
    NEW_COPY = "new_copy"


class DetectedField(BaseModel):
    model_config = {"extra": "allow"}  # Allow widget_name, widget_names, etc.

    field_name: str = Field(..., description="Machine key, e.g. 'fecha_vencimiento'")
    label: str = Field(..., description="Human-readable label")
    current_value: str = Field(..., description="Current value found in the document")
    field_type: FieldType = Field(default=FieldType.TEXT)
    required: bool = True
    context_hint: str = Field(
        default="", description="Surrounding text showing where the field appears"
    )
    suggested_value: Optional[str] = Field(
        default=None, description="LLM suggestion based on intent"
    )
    widget_name: Optional[str] = Field(
        default=None, description="AcroForm widget name (PDF forms only)"
    )
    widget_names: Optional[list[str]] = Field(
        default=None, description="Composite digit widget names (PDF forms only)"
    )


class AnalyzeRequest(BaseModel):
    tenant_id: str
    user_id: str
    document_id: Optional[str] = Field(
        default=None, description="Fetch original DOCX from storage"
    )
    user_intent: UserIntent = UserIntent.MODIFICATION
    max_fields: int = Field(default=30, ge=1, le=50)


class AnalyzeResponse(BaseModel):
    session_id: str
    source_title: str
    document_type: str = ""
    fields: list[DetectedField]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
