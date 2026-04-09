"""
NexusLM Notebook Schemas

Pydantic schemas for the NexusLM feature - an on-premise NotebookLM alternative
using Qwen3-4B-Thinking for LLM and VibeVoice for TTS.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, computed_field


# =====================================
# ENUMS
# =====================================

class AudioTone(str, Enum):
    """Tone options for podcast generation"""
    CONVERSATIONAL = "conversational"  # Casual, friendly tone
    FORMAL = "formal"                  # Professional, formal tone
    EDUCATIONAL = "educational"        # Teaching, explanatory tone


class AudioLength(str, Enum):
    """Length options for podcast generation"""
    SHORT = "short"        # 3-5 minutes
    STANDARD = "standard"  # 5-10 minutes
    LONG = "long"          # 10-15 minutes


class AudioStatus(str, Enum):
    """Status of audio generation process"""
    PENDING = "pending"
    GENERATING_SCRIPT = "generating_script"
    GENERATING_AUDIO = "generating_audio"
    STITCHING = "stitching"
    COMPLETED = "completed"
    FAILED = "failed"


class PresentationStatus(str, Enum):
    """Status of presentation generation process"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING_OUTLINE = "generating_outline"
    GENERATING_SLIDES = "generating_slides"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class PresentationTemplate(str, Enum):
    """Available presentation templates"""
    CORPORATE = "corporate"      # Professional, neutral colors
    EDUCATIONAL = "educational"  # Academic, clarity focused
    MINIMAL = "minimal"          # Clean, whitespace
    CREATIVE = "creative"        # Colorful, dynamic
    NOUXCUBE = "nouxcube"        # NouxCube branding


# =====================================
# NOTEBOOK SCHEMAS
# =====================================

class NotebookSettings(BaseModel):
    """Settings for a notebook"""
    language: str = Field(default="es-ES", description="Default language for audio generation")
    default_voice_a: Optional[str] = Field(default=None, description="Default voice for host A")
    default_voice_b: Optional[str] = Field(default=None, description="Default voice for host B")


class NotebookBase(BaseModel):
    """Base notebook schema"""
    title: str = Field(..., min_length=1, max_length=255, description="Notebook title")
    description: Optional[str] = Field(default=None, max_length=2000, description="Notebook description")
    emoji: Optional[str] = Field(default="📓", max_length=10, description="Emoji icon for the notebook")


class NotebookCreate(NotebookBase):
    """Schema for creating a new notebook"""
    settings: Optional[NotebookSettings] = Field(default_factory=NotebookSettings)


class NotebookUpdate(BaseModel):
    """Schema for updating a notebook"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    emoji: Optional[str] = Field(default=None, max_length=10)
    settings: Optional[NotebookSettings] = None
    is_archived: Optional[bool] = None


class NotebookResponse(NotebookBase):
    """Response schema for a notebook"""
    id: UUID
    user_id: UUID
    settings: Dict[str, Any] = Field(default_factory=dict)
    source_count: int = 0
    total_words: int = 0
    chat_count: int = 0
    audio_count: int = 0
    presentation_count: int = 0
    is_archived: bool = False
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotebookListResponse(BaseModel):
    """Response schema for listing notebooks"""
    notebooks: List[NotebookResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# =====================================
# NOTEBOOK SOURCE SCHEMAS
# =====================================

class KeyPoint(BaseModel):
    """A key point extracted from a source"""
    point: str
    importance: float = Field(ge=0.0, le=1.0, default=0.5)


class NotebookSourceBase(BaseModel):
    """Base source schema"""
    title: str = Field(..., max_length=512)
    source_type: str = Field(..., max_length=50)


class NotebookSourceAdd(BaseModel):
    """Schema for adding a source to a notebook"""
    document_id: Optional[UUID] = Field(default=None, description="Internal document ID")
    indexed_document_id: Optional[UUID] = Field(default=None, description="External indexed document ID")

    def model_post_init(self, __context):
        """Validate that exactly one document reference is provided"""
        if self.document_id is None and self.indexed_document_id is None:
            raise ValueError("Either document_id or indexed_document_id must be provided")
        if self.document_id is not None and self.indexed_document_id is not None:
            raise ValueError("Only one of document_id or indexed_document_id can be provided")


class NotebookSourceResponse(NotebookSourceBase):
    """Response schema for a notebook source"""
    id: UUID
    notebook_id: UUID
    document_id: Optional[UUID] = None
    indexed_document_id: Optional[UUID] = None
    word_count: int = 0
    is_processed: bool = False
    processing_error: Optional[str] = None
    key_points: Optional[List[KeyPoint]] = None
    summary: Optional[str] = None
    added_at: datetime
    processed_at: Optional[datetime] = None

    @computed_field
    @property
    def status(self) -> str:
        """Computed status based on processing state"""
        if self.processing_error:
            return "error"
        if self.is_processed:
            return "ready"
        return "processing"

    class Config:
        from_attributes = True


# =====================================
# NOTEBOOK AUDIO SCHEMAS
# =====================================

class VoiceConfig(BaseModel):
    """Configuration for a podcast voice"""
    id: str = Field(..., description="Voice ID from TTS service")
    name: str = Field(..., description="Display name for the voice")


class AudioConfig(BaseModel):
    """Configuration for audio generation"""
    tone: AudioTone = Field(default=AudioTone.CONVERSATIONAL, description="Tone of the podcast")
    length: AudioLength = Field(default=AudioLength.STANDARD, description="Length of the podcast")
    language: str = Field(default="es-ES", description="Language for the podcast")
    focus_topics: Optional[List[str]] = Field(default=None, description="Topics to focus on")
    voice_a: Optional[VoiceConfig] = Field(default=None, description="Voice for host A (Emma)")
    voice_b: Optional[VoiceConfig] = Field(default=None, description="Voice for host B (Alex)")


class AudioGenerateRequest(BaseModel):
    """Request schema for generating podcast audio"""
    config: AudioConfig = Field(default_factory=AudioConfig)


class ScriptSegment(BaseModel):
    """A segment of the podcast script"""
    speaker: Literal["A", "B"]
    text: str
    segment_id: int


class TranscriptSegment(BaseModel):
    """A segment of the transcript with timestamps"""
    speaker: Literal["A", "B"]
    text: str
    start_ms: int
    end_ms: int


class NotebookAudioResponse(BaseModel):
    """Response schema for notebook audio"""
    id: UUID
    notebook_id: UUID
    config: Dict[str, Any] = Field(default_factory=dict)
    status: AudioStatus
    status_message: Optional[str] = None
    progress_percent: int = 0
    script: Optional[List[ScriptSegment]] = None
    audio_url: Optional[str] = None
    audio_format: str = "mp3"
    duration_ms: Optional[int] = None
    file_size_bytes: Optional[int] = None
    transcript: Optional[List[TranscriptSegment]] = None
    error_message: Optional[str] = None
    generation_started_at: Optional[datetime] = None
    generation_completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @computed_field
    @property
    def duration_formatted(self) -> Optional[str]:
        """Human-readable duration"""
        if self.duration_ms is None:
            return None
        total_seconds = self.duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    class Config:
        from_attributes = True


class AudioStatusResponse(BaseModel):
    """Response schema for audio generation status"""
    id: UUID
    status: AudioStatus
    status_message: Optional[str] = None
    progress_percent: int = 0
    error_message: Optional[str] = None


# =====================================
# NOTEBOOK PRESENTATION SCHEMAS
# =====================================

class SlideOutline(BaseModel):
    """A single slide in the presentation outline"""
    slide_number: int
    title: str
    bullet_points: List[str] = Field(default_factory=list)
    speaker_notes: Optional[str] = None


class PresentationConfig(BaseModel):
    """Configuration for presentation generation"""
    template: PresentationTemplate = Field(default=PresentationTemplate.CORPORATE, description="Presentation template style")
    language: str = Field(default="es-ES", description="Language for the presentation")
    max_slides: int = Field(default=10, ge=3, le=30, description="Maximum number of slides")
    focus_topics: Optional[List[str]] = Field(default=None, description="Topics to focus on")
    include_speaker_notes: bool = Field(default=True, description="Include speaker notes in slides")


class PresentationGenerateRequest(BaseModel):
    """Request schema for generating a presentation"""
    config: PresentationConfig = Field(default_factory=PresentationConfig)


class NotebookPresentationResponse(BaseModel):
    """Response schema for notebook presentation"""
    id: UUID
    notebook_id: UUID
    config: Dict[str, Any] = Field(default_factory=dict)
    status: PresentationStatus
    status_message: Optional[str] = None
    progress_percent: int = 0
    outline: Optional[List[SlideOutline]] = None
    pptx_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    slide_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    generation_started_at: Optional[datetime] = None
    generation_completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PresentationStatusResponse(BaseModel):
    """Response schema for presentation generation status"""
    id: UUID
    status: PresentationStatus
    status_message: Optional[str] = None
    progress_percent: int = 0
    error_message: Optional[str] = None


# =====================================
# NOTEBOOK CHAT SCHEMAS
# =====================================

class Citation(BaseModel):
    """A citation from a source"""
    source_id: UUID
    source_title: str
    text: str
    page: Optional[int] = None


class ChatMessage(BaseModel):
    """A single chat message"""
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime
    citations: Optional[List[Citation]] = None


class NotebookChatCreate(BaseModel):
    """Schema for creating a new chat"""
    title: Optional[str] = Field(default=None, max_length=255)


class NotebookChatMessage(BaseModel):
    """Schema for sending a chat message"""
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")


class NotebookChatResponse(BaseModel):
    """Response schema for a notebook chat"""
    id: UUID
    notebook_id: UUID
    user_id: UUID
    title: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    message_count: int = 0
    is_archived: bool = False
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatCompletionResponse(BaseModel):
    """Response schema for a chat completion"""
    message: ChatMessage
    sources_used: int = 0


# =====================================
# AGGREGATED RESPONSES
# =====================================

class NotebookDetailResponse(NotebookResponse):
    """Detailed notebook response with sources and recent activity"""
    sources: List[NotebookSourceResponse] = Field(default_factory=list)
    recent_audios: List[NotebookAudioResponse] = Field(default_factory=list)
    recent_presentations: List[NotebookPresentationResponse] = Field(default_factory=list)
    recent_chats: List[NotebookChatResponse] = Field(default_factory=list)


class NotebookStatsResponse(BaseModel):
    """Statistics for a user's notebooks"""
    total_notebooks: int = 0
    total_sources: int = 0
    total_words: int = 0
    total_audios: int = 0
    total_presentations: int = 0
    total_chats: int = 0
    recent_activity: List[NotebookResponse] = Field(default_factory=list)
