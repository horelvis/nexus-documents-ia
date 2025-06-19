"""
Configuration for Langroid Service
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration"""
    
    # Service settings
    SERVICE_NAME: str = "langroid-service"
    SERVICE_PORT: int = 8002
    LOG_LEVEL: str = "INFO"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this")
    API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "unified-microservices-key-12345")
    
    # LLM Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama-service:11434")
    
    # Default models
    DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "llama3.1:8b")
    DEFAULT_EMBEDDING_MODEL: str = os.getenv("DEFAULT_EMBEDDING_MODEL", "nomic-embed-text")
    
    # Vector Store Configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION_PREFIX: str = "nexus_langroid"
    
    # Document Processing
    MAX_CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    MAX_DOCUMENT_SIZE_MB: int = 10
    
    # Agent Configuration
    MAX_CONVERSATION_LENGTH: int = 50
    DEFAULT_AGENT_TIMEOUT: int = 300  # seconds
    
    # Security settings
    ALLOWED_ORIGINS: list = ["*"]  # Configure for production
    REQUIRE_TENANT_AUTH: bool = True
    
    # Main API URL for fetching agent definitions
    MAIN_API_URL: str = os.getenv("MAIN_API_URL", "http://backend:8000")
    
    class Config:
        env_file = ".env"


settings = Settings()