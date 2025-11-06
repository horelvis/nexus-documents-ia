"""Configuration for Weaviate Service"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Weaviate Service settings"""
    
    # Service configuration
    service_name: str = "weaviate-service"
    service_port: int = 8007
    api_key: str = os.getenv("MICROSERVICES_API_KEY", "unified-microservices-key-12345")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # Weaviate configuration
    weaviate_url: str = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
    weaviate_api_key: str = os.getenv("WEAVIATE_API_KEY", "")  # For cloud instances
    weaviate_timeout: int = int(os.getenv("WEAVIATE_TIMEOUT", "30"))
    
    # Elysia configuration
    elysia_enabled: bool = os.getenv("ELYSIA_ENABLED", "true").lower() == "true"
    elysia_model_provider: str = os.getenv("ELYSIA_MODEL_PROVIDER", "ollama")
    elysia_model_name: str = os.getenv("ELYSIA_MODEL_NAME", "llama3.2:latest")
    
    # Model configuration (fallback to existing Ollama)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://genai-ollama:11434")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    
    # Embedding configuration
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
    
    # Performance settings
    batch_size: int = int(os.getenv("BATCH_SIZE", "100"))
    max_chunk_size: int = int(os.getenv("MAX_CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    
    # Redis configuration (for caching and coordination)
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_url: str = f"redis://{redis_host}:{redis_port}"
    
    # Database (for metadata coordination)
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")
    
    # Collection naming (tenant isolation)
    collection_prefix: str = "nexus_"
    default_collection: str = "documents"
    
    # Decision tree configuration
    decision_tree_max_depth: int = int(os.getenv("DECISION_TREE_MAX_DEPTH", "5"))
    decision_tree_timeout: int = int(os.getenv("DECISION_TREE_TIMEOUT", "60"))
    
    # Visualization settings
    enable_dynamic_display: bool = os.getenv("ENABLE_DYNAMIC_DISPLAY", "true").lower() == "true"
    max_display_items: int = int(os.getenv("MAX_DISPLAY_ITEMS", "50"))
    
    # Learning and feedback
    enable_feedback_learning: bool = os.getenv("ENABLE_FEEDBACK_LEARNING", "true").lower() == "true"
    feedback_storage_days: int = int(os.getenv("FEEDBACK_STORAGE_DAYS", "30"))
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()