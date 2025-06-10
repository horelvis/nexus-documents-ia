"""
Configuration for LangChain microservice
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Security configuration
    API_KEY: str = "your-secret-api-key-here"
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()