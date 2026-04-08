"""Configuration for Knowledge Tree Service (FalkorDB graph backend)."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service configuration
    service_name: str = "knowledge-tree-service"
    service_port: int = int(os.getenv("SERVICE_PORT", "8011"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Knowledge graph toggle
    rag_knowledge_graph_enabled: bool = os.getenv(
        "RAG_KNOWLEDGE_GRAPH_ENABLED", "true"
    ).lower() == "true"
    active_sector: str = ""

    # Database URL (used by emma_persistence_service for session storage, NOT for graph)
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/nouxcube",
    )

    # FalkorDB (sole graph backend)
    falkordb_host: str = os.getenv("FALKORDB_HOST", "falkordb")
    falkordb_port: int = int(os.getenv("FALKORDB_PORT", "6379"))
    falkordb_graph_name: str = os.getenv("FALKORDB_GRAPH_NAME", "knowledge_graph")
    falkordb_password: str = os.getenv("FALKORDB_PASSWORD", "")

    # SGLang
    SGLANG_BASE_URL: str = os.getenv("SGLANG_BASE_URL", "http://sglang:8000/v1")
    SGLANG_MODEL: str = os.getenv("SGLANG_MODEL", "Qwen/Qwen3-8B")

    # Extraction parallelism
    extraction_parallel_chunks: int = int(os.getenv("EXTRACTION_PARALLEL_CHUNKS", "5"))

    # Langfuse
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-local")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-local")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://langfuse:3002")

    # Weaviate (for reindexation)
    WEAVIATE_SERVICE_URL: str = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")

    # Microservice auth
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
