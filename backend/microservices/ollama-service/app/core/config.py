"""
Configuration settings for Ollama Microservice
"""
from typing import List
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Service configuration
    SERVICE_NAME: str = "ollama-microservice"
    API_V1_STR: str = "/api/v1"

    # Ollama configuration
    OLLAMA_HOST: str = "genai-ollama"
    OLLAMA_PORT: int = 11434
    OLLAMA_BASE_URL: str | None = None

    # Default models to load (optimized for high-end hardware)
    DEFAULT_MODELS: List[str] = ["llama3.1:8b", "codellama:13b", "mistral:7b", "nomic-embed-text"]

    # Primary models
    DEFAULT_MODEL: str = "llama3.2"  # Default chat model
    EMBEDDING_MODEL: str = "nomic-embed-text"  # Model for embeddings

    # API configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Security
    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    ALLOWED_HOSTS: List[str] = ["*"]

    # Logging
    LOG_LEVEL: str = "INFO"

    # Model settings
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 2048
    DEFAULT_TOP_P: float = 0.9

    # Timeouts
    REQUEST_TIMEOUT: int = 300  # 5 minutes
    MODEL_LOAD_TIMEOUT: int = 600  # 10 minutes

    class Config:
        env_file = ".env"
        case_sensitive = True

    @model_validator(mode="after")
    def ensure_base_url(self) -> "Settings":
        """Populate OLLAMA_BASE_URL when only host/port are provided."""
        if not self.OLLAMA_BASE_URL:
            self.OLLAMA_BASE_URL = f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
        return self


# Create settings instance
settings = Settings()
