"""
Podcast Service Schemas

Pydantic models for podcast generation requests and responses.
"""
from datetime import datetime
from typing import List, Optional, Literal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class AudioTone(str, Enum):
    """Tone options for podcast generation."""
    CONVERSATIONAL = "conversational"
    FORMAL = "formal"
    EDUCATIONAL = "educational"


class AudioLength(str, Enum):
    """Length options for podcast generation."""
    SHORT = "short"        # 3-5 minutes
    STANDARD = "standard"  # 5-10 minutes
    LONG = "long"          # 10-15 minutes


class AudioStatus(str, Enum):
    """Status of audio generation process."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING_SCRIPT = "generating_script"
    GENERATING_AUDIO = "generating_audio"
    STITCHING = "stitching"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class VoiceConfig(BaseModel):
    """Configuration for a podcast voice."""
    id: str = Field(..., description="Voice ID from TTS service")
    name: str = Field(..., description="Display name for the voice")


class AudioConfig(BaseModel):
    """Configuration for audio generation."""
    tone: AudioTone = Field(default=AudioTone.CONVERSATIONAL)
    length: AudioLength = Field(default=AudioLength.STANDARD)
    language: str = Field(default="es-ES")
    focus_topics: Optional[List[str]] = Field(default=None)
    voice_a: Optional[VoiceConfig] = Field(default=None, description="Voice for host A")
    voice_b: Optional[VoiceConfig] = Field(default=None, description="Voice for host B")


class SourceInfo(BaseModel):
    """Information about a source document."""
    id: UUID
    title: str
    source_type: str = "document"
    word_count: int = 0
    content: Optional[str] = None  # Full document content from Weaviate
    summary: Optional[str] = None  # Legacy: pre-computed summary
    key_points: Optional[List[str]] = None  # Legacy: pre-computed key points


class SourceAnalysis(BaseModel):
    """Analysis results from source documents."""
    main_themes: List[str] = Field(default_factory=list)
    key_insights: List[str] = Field(default_factory=list)
    interesting_facts: List[str] = Field(default_factory=list)
    potential_questions: List[str] = Field(default_factory=list)
    connections: List[str] = Field(default_factory=list)
    total_word_count: int = 0


class ScriptOutline(BaseModel):
    """Outline for the podcast script."""
    introduction: str
    main_topics: List[str]
    conclusion: str
    estimated_duration_seconds: int


class ScriptSegment(BaseModel):
    """A segment of the podcast script."""
    speaker: Literal["A", "B"]
    text: str
    segment_id: int
    estimated_duration_ms: Optional[int] = None


class TranscriptSegment(BaseModel):
    """A segment of the transcript with timestamps."""
    speaker: Literal["A", "B"]
    text: str
    start_ms: int
    end_ms: int


class PodcastScript(BaseModel):
    """Complete podcast script."""
    title: str
    outline: ScriptOutline
    segments: List[ScriptSegment]
    total_segments: int
    estimated_duration_ms: int


class GeneratePodcastRequest(BaseModel):
    """Request to generate a podcast."""
    audio_id: UUID = Field(..., description="ID of the NotebookAudio record")
    notebook_id: UUID = Field(..., description="ID of the notebook")
    tenant_id: UUID = Field(..., description="Tenant ID")
    sources: List[SourceInfo] = Field(..., description="Sources to use for generation")
    config: AudioConfig = Field(default_factory=AudioConfig)


class GeneratePodcastResponse(BaseModel):
    """Response from podcast generation initiation."""
    audio_id: UUID
    status: AudioStatus
    message: str


class PodcastStatusResponse(BaseModel):
    """Status response for podcast generation."""
    audio_id: UUID
    status: AudioStatus
    status_message: Optional[str] = None
    progress_percent: int = 0
    error_message: Optional[str] = None
    audio_url: Optional[str] = None
    duration_ms: Optional[int] = None


class PodcastProgressUpdate(BaseModel):
    """Progress update for podcast generation (for SSE/WebSocket)."""
    audio_id: UUID
    status: AudioStatus
    status_message: str
    progress_percent: int
    current_step: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
