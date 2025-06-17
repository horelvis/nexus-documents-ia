from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Service configuration
    service_name: str = "langgraph-service"
    service_port: int = 8007
    debug: bool = False
    
    # API Security
    service_api_key: Optional[str] = None
    
    # External services
    ollama_base_url: str = "http://ollama-service:11434"
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    redis_url: str = "redis://redis:6379"
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/nexus_db"
    
    # LangGraph configuration
    langgraph_backend: str = "sqlite"  # Options: sqlite, redis
    checkpoint_db_path: str = "/tmp/langgraph_checkpoints.db"
    
    # Model configuration
    llm_model: str = "llama3.2"
    embedding_model: str = "nomic-embed-text"
    
    # Graph execution settings
    max_iterations: int = 10
    recursion_limit: int = 25
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()