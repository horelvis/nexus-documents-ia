"""
Configuration settings for Ollama Microservice
"""
import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # Service configuration
    SERVICE_NAME: str = "ollama-microservice"
    API_V1_STR: str = "/api/v1"
    
    # Ollama configuration
    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434
    OLLAMA_BASE_URL: str = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
    
    # Default models to load (optimized for high-end hardware)
    DEFAULT_MODELS: List[str] = ["llama3.1:8b", "codellama:13b", "mistral:7b", "nomic-embed-text"]
    
    # API configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Security
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

# Create settings instance
settings = Settings()