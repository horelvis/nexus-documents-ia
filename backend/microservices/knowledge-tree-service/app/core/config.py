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
        "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db",
    )

    # FalkorDB (sole graph backend)
    falkordb_host: str = os.getenv("FALKORDB_HOST", "falkordb")
    falkordb_port: int = int(os.getenv("FALKORDB_PORT", "6379"))
    falkordb_graph_name: str = os.getenv("FALKORDB_GRAPH_NAME", "knowledge_graph")
    falkordb_password: str = os.getenv("FALKORDB_PASSWORD", "")

    # Microservice auth
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
