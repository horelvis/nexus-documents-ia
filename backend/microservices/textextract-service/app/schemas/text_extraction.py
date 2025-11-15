"""
Pydantic schemas for text extraction endpoints.
"""
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ExtractionStrategy(str, Enum):
    """Available extraction strategies."""

    auto = "auto"
    fast = "fast"
    hi_res = "hi_res"


class ExtractionResponse(BaseModel):
    """Response payload for text extraction."""

    success: bool = True
    text: str
    characters: int = Field(..., description="Number of characters in the extracted text")
    language: Optional[str] = Field(None, description="Detected language code (ISO 639-1)")
    metadata: Dict[str, Optional[str]] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: str
    service: str
    version: str
    strategies: Dict[str, str]
