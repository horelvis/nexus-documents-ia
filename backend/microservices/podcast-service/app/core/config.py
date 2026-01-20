"""
Podcast Service Configuration

Environment-based settings for the podcast generation service.
"""
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Podcast service settings from environment variables."""

    # Service info
    service_name: str = "podcast-service"
    service_version: str = "1.0.0"
    debug: bool = False

    # API Security
    api_key: str = ""

    # vLLM Configuration (for script generation)
    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_model: str = "Qwen/Qwen3-4B-Thinking-2507"
    vllm_max_tokens: int = 8192
    vllm_temperature: float = 0.7

    # TTS Configuration (VibeVoice)
    tts_service_url: str = "http://tts-service:8000"
    default_voice_a: str = "Spk0"  # Female Spanish voice
    default_voice_b: str = "Spk1"  # Male Spanish voice
    default_language: str = "es-ES"

    # Audio settings
    audio_sample_rate: int = 24000
    audio_format: str = "mp3"
    audio_bitrate: str = "192k"

    # Generation settings
    max_script_length: int = 10000  # Max characters in script
    segment_pause_ms: int = 500  # Pause between speaker turns
    crossfade_ms: int = 100  # Crossfade duration

    # Storage (GCS)
    gcs_bucket_prefix: str = "nexuslm-audio"
    storage_service_url: str = "http://storage-service:8000"

    # Redis for task queue
    redis_url: str = "redis://redis:6379/0"

    # Weaviate service (for RAG context)
    weaviate_service_url: str = "http://weaviate-service:8000"

    # Main API (for database operations)
    main_api_url: str = "http://api:8000"

    class Config:
        env_prefix = "PODCAST_"
        env_file = ".env"
        extra = "ignore"


settings = Settings()
