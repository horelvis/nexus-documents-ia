"""
Configuration for LangChain microservice
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Security configuration - Match environment variable name
    MICROSERVICES_API_KEY: str = "unified-microservices-key-12345"
    
    # LangChain/Ollama configuration
    OLLAMA_BASE_URL: str = "http://ollama-service:11434"
    OLLAMA_MODEL: str = "llama3.2"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Vector database configuration
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    
    # Text processing configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Default tenant
    DEFAULT_TENANT: str = "default"
    
    # Property for backward compatibility
    @property
    def API_KEY(self) -> str:
        return self.MICROSERVICES_API_KEY
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()