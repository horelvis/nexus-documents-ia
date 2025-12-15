"""
TTS Service Pydantic Schemas

Defines request/response models for TTS endpoints.
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class SynthesizeRequest(BaseModel):
    """Request model for text-to-speech synthesis."""

    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize")
    voice_id: Optional[str] = Field(default="Carter", description="Voice identifier")
    language: Optional[str] = Field(default="en-US", description="Language code (en-US, es-ES)")
    speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0, description="Playback speed multiplier")


class SynthesizeResponse(BaseModel):
    """Response model for batch synthesis."""

    audio_base64: str = Field(..., description="Base64 encoded audio data")
    format: Literal["wav", "mp3"] = Field(default="wav", description="Audio format")
    duration_ms: int = Field(..., description="Audio duration in milliseconds")
    sample_rate: int = Field(default=24000, description="Audio sample rate in Hz")
    text_length: int = Field(..., description="Number of characters synthesized")


class StreamMessage(BaseModel):
    """WebSocket message for streaming TTS."""

    text: str = Field(..., description="Text chunk to synthesize")
    voice_id: Optional[str] = Field(default="Carter", description="Voice identifier")
    language: Optional[str] = Field(default="en-US", description="Language code")
    is_final: bool = Field(default=False, description="Indicates last chunk of text")


class StreamChunk(BaseModel):
    """WebSocket response chunk for streaming audio."""

    audio_chunk: str = Field(..., description="Base64 encoded audio chunk")
    chunk_index: int = Field(..., description="Sequential chunk number")
    is_final: bool = Field(default=False, description="Indicates last audio chunk")
    error: Optional[str] = Field(default=None, description="Error message if any")


class VoiceInfo(BaseModel):
    """Information about an available voice."""

    voice_id: str = Field(..., description="Unique voice identifier")
    name: str = Field(..., description="Display name")
    language: str = Field(..., description="Primary language")
    gender: Optional[str] = Field(default=None, description="Voice gender")
    description: Optional[str] = Field(default=None, description="Voice description")
    provider: str = Field(..., description="TTS provider (vibevoice, google)")


class VoicesResponse(BaseModel):
    """Response model for listing available voices."""

    voices: List[VoiceInfo] = Field(..., description="List of available voices")
    default_voice_id: str = Field(default="Carter", description="Default voice ID")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    service: str = Field(default="tts-service", description="Service name")
    version: str = Field(..., description="Service version")
    provider: str = Field(..., description="Active TTS provider")
    model_loaded: bool = Field(..., description="Whether TTS model is loaded")
    gpu_available: bool = Field(..., description="Whether GPU is available")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error information")
    code: Optional[str] = Field(default=None, description="Error code")
