import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_port: int = int(os.getenv("BACKGROUND_WORKER_PORT", "8100"))
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    # DATABASE_URL is required - no hardcoded credentials fallback
    database_url: str = os.getenv("DATABASE_URL", "")
    # MICROSERVICES_API_KEY is required - no hardcoded fallback
    microservices_api_key: str = os.getenv("MICROSERVICES_API_KEY", "")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://genai-ollama:11434")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Weaviate Service (for verification tasks)
    weaviate_service_url: str = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")

    # vLLM configuration (for claim verification)
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    vllm_model: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-4B-Thinking-2507")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to: postgresql+asyncpg://user:password@host:port/dbname"
            )
        if not self.microservices_api_key:
            raise ValueError("MICROSERVICES_API_KEY environment variable is required.")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
