"""Configuration for Temporalio Service"""
import os
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Temporalio Service settings"""
    
    # Service configuration
    service_name: str = "temporalio-service"
    service_port: int = 8010
    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    allowed_origins: List[str] = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    
    # Temporalio configuration
    temporalio_host: str = os.getenv("TEMPORALIO_HOST", "temporalio-server")
    temporalio_port: int = int(os.getenv("TEMPORALIO_PORT", "7233"))
    temporalio_namespace: str = os.getenv("TEMPORALIO_NAMESPACE", "nexus-workflows")
    temporalio_task_queue: str = os.getenv("TEMPORALIO_TASK_QUEUE", "nexus-workflow-tasks")
    temporalio_tls_enabled: bool = os.getenv("TEMPORALIO_TLS_ENABLED", "false").lower() == "true"
    
    # Worker configuration
    worker_max_concurrent_activities: int = int(os.getenv("WORKER_MAX_CONCURRENT_ACTIVITIES", "10"))
    worker_max_concurrent_workflows: int = int(os.getenv("WORKER_MAX_CONCURRENT_WORKFLOWS", "10"))
    
    # Database configuration
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")
    
    # External service URLs
    api_core_url: str = os.getenv("API_CORE_URL", "http://api:8000")
    weaviate_service_url: str = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://genai-ollama:11434")
    storage_service_url: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8003")
    
    # Redis configuration
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    
    # Emma AI configuration
    emma_ai_enabled: bool = os.getenv("EMMA_AI_ENABLED", "true").lower() == "true"
    emma_ai_model: str = os.getenv("EMMA_AI_MODEL", "gpt-oss:20b")
    emma_ai_embedding_model: str = os.getenv("EMMA_AI_EMBEDDING_MODEL", "nomic-embed-text")
    
    @property
    def temporalio_address(self) -> str:
        """Get Temporalio server address"""
        return f"{self.temporalio_host}:{self.temporalio_port}"
    
    @property
    def redis_url(self) -> str:
        """Get Redis connection URL"""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
