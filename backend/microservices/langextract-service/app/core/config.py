"""
Configuration for LangExtract Service
"""
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Service configuration
    service_name: str = "langextract-service"
    service_version: str = "1.0.0"
    debug: bool = True
    
    # Ollama endpoint configuration
    ollama_host: str = Field(
        "http://ollama:11434",
        validation_alias=AliasChoices("OLLAMA_HOST", "OLLAMA_BASE_URL")
    )
    
    # Optional: Gemini configuration
    gemini_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY")
    )
    
    # Optional: OpenAI configuration
    openai_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY")
    )

    # Generic LLM configuration shared across providers (REQUIRED)
    llm_model: str = Field(
        validation_alias=AliasChoices("LLM_MODEL", "DEFAULT_LLM_MODEL")
    )  # Required - no default, will error if not set
    llm_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY")
    )
    llm_api_base: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_BASE", "LLM_BASE_URL")
    )
    
    # LangExtract configuration
    default_provider: str = Field(
        "ollama",
        validation_alias=AliasChoices("default_provider", "LLM_PROVIDER")
    )  # ollama, gemini, openai, anthropic
    extraction_passes: int = 2  # Number of extraction passes for better recall
    max_char_buffer: int = 10000  # Max characters per chunk
    parallel_workers: int = 4  # Parallel processing workers
    
    # API Security
    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    
    # Document type configurations
    confidence_threshold: float = 0.7  # Minimum confidence for extractions
    
    # OpenAI specific configurations
    openai_max_tokens: int = 4000  # Max tokens for OpenAI models
    openai_temperature: float = 0.3  # Temperature for OpenAI models


    class Config:
        env_file = ".env"
        case_sensitive = False


# Create settings instance
settings = Settings()
