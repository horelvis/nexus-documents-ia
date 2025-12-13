"""
TTS Service Configuration

Settings for the TTS microservice including provider configuration,
model paths, and service parameters.
"""

import os
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """TTS Service configuration settings."""

    # Service identity
    service_name: str = "tts-service"
    service_version: str = "1.0.0"
    service_port: int = Field(default=8000, alias="TTS_SERVICE_PORT")

    # Security
    microservices_api_key: str = Field(default="", alias="MICROSERVICES_API_KEY")

    # TTS Provider Configuration
    tts_provider: Literal["vibevoice", "google"] = Field(
        default="vibevoice",
        alias="TTS_PROVIDER",
        description="TTS provider to use"
    )

    # VibeVoice Configuration
    vibevoice_model_path: str = Field(
        default="microsoft/VibeVoice-Realtime-0.5B",
        alias="VIBEVOICE_MODEL_PATH"
    )
    vibevoice_device: str = Field(
        default="cuda",
        alias="VIBEVOICE_DEVICE",
        description="Device for inference (cuda, cpu, mps)"
    )
    vibevoice_default_voice: str = Field(
        default="Carter",
        alias="VIBEVOICE_DEFAULT_VOICE"
    )
    vibevoice_voice_prompts_dir: str = Field(
        default="/app/voice_prompts",
        alias="VIBEVOICE_VOICE_PROMPTS_DIR",
        description="Directory containing pre-computed voice prompt .pt files"
    )

    # Google Cloud TTS Configuration (fallback)
    google_tts_enabled: bool = Field(
        default=False,
        alias="GOOGLE_TTS_ENABLED"
    )
    google_application_credentials: str = Field(
        default="/app/credentials/gcs-credentials.json",
        alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    google_tts_default_voice: str = Field(
        default="es-ES-Neural2-A",
        alias="GOOGLE_TTS_DEFAULT_VOICE"
    )

    # HuggingFace Configuration
    hf_token: str = Field(default="", alias="HF_TOKEN")
    hf_cache_dir: str = Field(
        default="/root/.cache/huggingface",
        alias="HF_HOME"
    )

    # Audio Configuration
    audio_sample_rate: int = Field(default=24000, alias="AUDIO_SAMPLE_RATE")
    audio_format: Literal["wav", "mp3"] = Field(default="wav", alias="AUDIO_FORMAT")
    max_text_length: int = Field(default=5000, alias="MAX_TEXT_LENGTH")

    # Streaming Configuration
    stream_chunk_size_ms: int = Field(
        default=100,
        alias="STREAM_CHUNK_SIZE_MS",
        description="Size of audio chunks for streaming in milliseconds"
    )
    websocket_ping_interval: int = Field(default=30, alias="WEBSOCKET_PING_INTERVAL")
    websocket_ping_timeout: int = Field(default=10, alias="WEBSOCKET_PING_TIMEOUT")

    # Redis Configuration (for caching)
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=5, alias="REDIS_DB")
    cache_ttl_seconds: int = Field(
        default=3600,
        alias="CACHE_TTL_SECONDS",
        description="TTL for cached audio in seconds"
    )
    cache_enabled: bool = Field(default=True, alias="CACHE_ENABLED")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = False
        populate_by_name = True


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance for dependency injection."""
    return settings
