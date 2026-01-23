"""
Pydantic schemas for text extraction endpoints.
"""
from typing import Dict, List, Optional

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


class OCRResponse(BaseModel):
    """Response payload for OCR extraction."""

    success: bool = Field(..., description="Whether OCR extraction was successful")
    text: str = Field(..., description="Extracted text content")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Average confidence score (0.0 - 1.0)"
    )
    engine: str = Field(..., description="OCR engine used (easyocr, tesseract, hybrid)")
    languages: List[str] = Field(
        default_factory=list,
        description="Languages used for OCR"
    )
    page_count: int = Field(default=0, description="Number of pages processed")
    processing_time_ms: float = Field(
        default=0.0,
        description="Processing time in milliseconds"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Any warnings during extraction"
    )
