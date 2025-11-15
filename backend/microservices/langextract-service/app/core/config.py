"""
Configuration for LangExtract Service
"""
import os
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Service configuration
    service_name: str = "langextract-service"
    service_version: str = "1.0.0"
    debug: bool = True
    
    # Ollama configuration (default provider)
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    
    # Optional: Gemini configuration
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = "gemini-1.5-flash"
    
    # Optional: OpenAI configuration
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"
    
    # LangExtract configuration
    default_provider: str = "ollama"  # ollama, gemini, openai
    extraction_passes: int = 2  # Number of extraction passes for better recall
    max_char_buffer: int = 10000  # Max characters per chunk
    parallel_workers: int = 4  # Parallel processing workers
    
    # API Security
    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    
    # Document type configurations
    confidence_threshold: float = 0.7  # Minimum confidence for extractions


    class Config:
        env_file = ".env"
        case_sensitive = False


# Create settings instance
settings = Settings()
