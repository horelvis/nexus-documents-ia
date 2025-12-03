import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_port: int = int(os.getenv("BACKGROUND_WORKER_PORT", "8100"))
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nexus_user:nexus_password@db:5432/nexus_db",
    )
    microservices_api_key: str = os.getenv("MICROSERVICES_API_KEY", "dev_microservice_key_12345")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://genai-ollama:11434")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
