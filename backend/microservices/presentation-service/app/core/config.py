"""
Presentation Service Configuration

Environment-based settings for the presentation generation service.
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Presentation service settings from environment variables."""

    # Service info
    service_name: str = "presentation-service"
    service_version: str = "1.0.0"
    debug: bool = False

    # API Security
    api_key: str = ""

    # SGLang Configuration (for outline generation)
    sglang_base_url: str = os.getenv("PRESENTATION_SGLANG_BASE_URL", os.getenv("PRESENTATION_VLLM_BASE_URL", "http://sglang:8000/v1"))
    sglang_model: str = os.getenv("PRESENTATION_SGLANG_MODEL", os.getenv("PRESENTATION_VLLM_MODEL", "Qwen/Qwen3.5-9B"))
    sglang_max_tokens: int = 4096
    sglang_temperature: float = 0.7

    # Presentation settings
    default_language: str = "es-ES"
    default_template: str = "corporate"
    max_slides: int = 15
    default_max_slides: int = 10

    # Templates directory
    templates_dir: str = "/app/templates"

    # Storage (MinIO via storage-service)
    storage_service_url: str = "http://storage-service:8010"

    # Local storage for direct file writes
    local_storage_path: str = "/app/storage"

    # Main API (for database operations)
    main_api_url: str = "http://api:8000"

    # Public API URL (for generating download URLs)
    public_api_url: str = "http://nouxcube.local.es:8000"

    class Config:
        env_prefix = "PRESENTATION_"
        env_file = ".env"
        extra = "ignore"


settings = Settings()
