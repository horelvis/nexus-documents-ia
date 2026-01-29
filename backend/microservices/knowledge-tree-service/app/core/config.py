"""Configuration for Knowledge Tree Service"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service configuration
    service_name: str = "knowledge-tree-service"
    service_port: int = int(os.getenv("SERVICE_PORT", "8011"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Apache AGE (PostgreSQL) configuration
    rag_knowledge_graph_enabled: bool = os.getenv(
        "RAG_KNOWLEDGE_GRAPH_ENABLED", "true"
    ).lower() == "true"
    age_graph_name: str = os.getenv("AGE_GRAPH_NAME", "knowledge_graph")

    # Database URL for AGE
    database_url: str = os.getenv(
        "AGE_DATABASE_URL",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db",
        ),
    )

    # Microservice auth
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
