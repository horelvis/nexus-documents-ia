"""
Pydantic schemas for text extraction endpoints.
"""
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ExtractionResponse(BaseModel):
    """Response payload for text extraction."""

    success: bool = True
    text: str
    characters: int = Field(..., description="Number of characters in the extracted text")
    language: Optional[str] = Field(None, description="Detected language code (ISO 639-1)")
    content_type: Optional[str] = Field(None, description="MIME type of the document")
    metadata: Dict[str, Optional[str]] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: str
    service: str
    version: str
    backend: str = Field(default="apache-tika", description="Text extraction backend")
