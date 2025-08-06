"""Configuration for CAG Service"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """CAG Service settings"""
    
    # Service configuration
    service_name: str = "cag-service"
    service_port: int = 8008
    api_key: str = os.getenv("MICROSERVICES_API_KEY", "unified-microservices-key-12345")
    
    # Ollama configuration
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://ollama-service:11434")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.2")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-minilm:latest")
    
    # Qdrant configuration
    qdrant_host: str = os.getenv("QDRANT_HOST", "qdrant")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    
    # Redis configuration
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Database configuration
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")
    
    # CAG configuration
    cag_max_iterations: int = 3
    cag_context_window: int = 4096
    cag_temperature: float = 0.7
    cag_gap_detection_threshold: float = 0.7
    cag_quality_threshold: float = 0.8
    
    # LangGraph configuration
    langgraph_checkpointing: bool = True
    langgraph_memory_type: str = "memory"  # memory, redis, postgres
    langgraph_max_memory_size: int = 1000
    langgraph_enable_tracing: bool = True
    langgraph_parallel_execution: bool = True
    
    # Performance settings
    request_timeout: int = 300  # 5 minutes
    llm_timeout: int = 120  # 2 minutes
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()