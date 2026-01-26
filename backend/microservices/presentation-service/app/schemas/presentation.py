"""
Presentation generation schemas.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PresentationStatus(str, Enum):
    """Status of presentation generation process."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING_OUTLINE = "generating_outline"
    GENERATING_SLIDES = "generating_slides"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class SlideType(str, Enum):
    """Types of slides in a presentation."""
    TITLE = "title"
    CONTENT = "content"
    SECTION = "section"
    CLOSING = "closing"
    TWO_COLUMN = "two_column"
    IMAGE = "image"


class PresentationTemplate(str, Enum):
    """Available presentation templates."""
    # Built-in programmatic templates
    CORPORATE = "corporate"
    EDUCATIONAL = "educational"
    MINIMAL = "minimal"
    CREATIVE = "creative"
    NOUXCUBE = "nouxcube"
    # External .pptx templates (from Microsoft Create, SlidesCarnival, etc.)
    PROFESSIONAL_BLUE = "professional-blue"
    MODERN_GRADIENT = "modern-gradient"
    TECH_DARK = "tech-dark"
    NATURE_GREEN = "nature-green"
    BUSINESS_CLEAN = "business-clean"
    STARTUP_PITCH = "startup-pitch"
    ACADEMIC_FORMAL = "academic-formal"
    MARKETING_BOLD = "marketing-bold"
    FINANCE_ELEGANT = "finance-elegant"


class SourceInfo(BaseModel):
    """Information about a source document."""
    id: str
    title: str
    content: str
    word_count: int = 0
    source_type: str = "document"
    document_id: Optional[str] = None
    indexed_document_id: Optional[str] = None


class PresentationConfig(BaseModel):
    """Configuration for presentation generation."""
    template: str = Field(default="corporate")
    language: str = Field(default="es-ES")
    max_slides: int = Field(default=10, ge=3, le=30)
    focus_topics: Optional[List[str]] = None
    include_speaker_notes: bool = True


class SlideOutline(BaseModel):
    """Outline for a single slide."""
    slide_number: int
    title: str
    slide_type: SlideType = SlideType.CONTENT  # Type of slide layout to use
    bullet_points: List[str] = Field(default_factory=list)
    speaker_notes: Optional[str] = None
    image_prompt: Optional[str] = None  # For future image generation support


class GeneratePresentationRequest(BaseModel):
    """Request to generate a presentation."""
    presentation_id: str
    notebook_id: str
    tenant_id: str
    sources: List[SourceInfo]
    config: PresentationConfig = Field(default_factory=PresentationConfig)


class GeneratePresentationResponse(BaseModel):
    """Response after queuing presentation generation."""
    presentation_id: str
    status: PresentationStatus
    message: str


class PresentationStatusResponse(BaseModel):
    """Status of a presentation generation."""
    presentation_id: str
    status: PresentationStatus
    status_message: Optional[str] = None
    progress_percent: int = 0
    outline: Optional[List[SlideOutline]] = None
    pptx_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    slide_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
