"""Document Forge Service configuration."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "document-forge-service"
    service_port: int = 8013
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Security
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "")

    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    # LLM (direct SGLang — OpenAI-compatible)
    sglang_base_url: str = os.getenv("SGLANG_BASE_URL", os.getenv("VLLM_BASE_URL", "http://sglang:8000/v1"))
    sglang_model_name: str = os.getenv("SGLANG_MODEL_NAME", os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen3.5-9B"))
    llm_temperature: float = float(os.getenv("FORGE_LLM_TEMPERATURE", "0.3"))
    llm_max_tokens: int = int(os.getenv("FORGE_LLM_MAX_TOKENS", "4096"))

    # Dependent services
    gotenberg_service_url: str = os.getenv(
        "GOTENBERG_SERVICE_URL", "http://gotenberg:3000"
    )
    weaviate_service_url: str = os.getenv(
        "WEAVIATE_SERVICE_URL", "http://weaviate-service:8000"
    )
    main_api_url: str = os.getenv("MAIN_API_URL", "http://main-api:8000")

    # Session
    forge_session_ttl: int = int(os.getenv("FORGE_SESSION_TTL", "1800"))  # 30 min

    # Document limits
    max_source_chars: int = int(os.getenv("FORGE_MAX_SOURCE_CHARS", "20000"))
    max_document_size_mb: int = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "50"))
    max_fields: int = int(os.getenv("FORGE_MAX_FIELDS", "30"))

    class Config:
        env_file = ".env"
        case_sensitive = False


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
