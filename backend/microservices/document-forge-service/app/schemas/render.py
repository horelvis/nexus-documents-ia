"""Schemas for template preparation and rendering."""

from typing import Optional

from pydantic import BaseModel, Field


class CustomField(BaseModel):
    field_name: str
    search_text: str = Field(..., description="Exact text to find and replace in DOCX")
    label: str = ""


class PrepareRequest(BaseModel):
    session_id: str
    fields_to_mark: list[str] = Field(
        default_factory=list,
        description="Field names from analysis to insert as markers",
    )
    custom_fields: list[CustomField] = Field(
        default_factory=list,
        description="Additional fields not detected by analysis",
    )


class PrepareResponse(BaseModel):
    session_id: str
    markers_inserted: int = 0
    markers_failed: int = 0
    failed_fields: list[str] = Field(default_factory=list)
    template_ready: bool = False


class RenderRequest(BaseModel):
    session_id: str
    field_values: dict[str, str] = Field(
        ..., description="Map of field_name → new value"
    )
    output_formats: list[str] = Field(
        default=["docx"], description="Output formats: docx, pdf, both"
    )
    document_title: Optional[str] = None


class OutputInfo(BaseModel):
    size_bytes: int
    download_url: str


class RenderResponse(BaseModel):
    session_id: str
    outputs: dict[str, OutputInfo] = Field(default_factory=dict)
    fields_filled: int = 0
    document_title: str = ""
