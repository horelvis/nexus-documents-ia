import os
import secrets
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, BaseSettings, PostgresDsn, validator


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    SERVER_NAME: str = "Document Management API"
    SERVER_HOST: AnyHttpUrl = "http://localhost:8000"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # PostgreSQL
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None

    @validator("SQLALCHEMY_DATABASE_URI", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql",
            user=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_SERVER"),
            path=f"/{values.get('POSTGRES_DB') or ''}",
        )
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    
    # Vector DB (Qdrant)
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"
    
    # Google Cloud Storage
    GCS_BUCKET_NAME: str
    GCS_CREDENTIALS: Optional[str] = None
    GCS_PROJECT_ID: Optional[str] = None
    GCS_REGION: str = "europe-west1"  # Región por defecto
    # Tiempo de validez para URLs firmadas (segundos)
    SIGNED_URL_EXPIRATION: int = 300
    
    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma3:27b-it-qat"  # Modelo por defecto
    
    # Procesamiento de Documentos
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB por defecto
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx", "txt", "md", "csv", "xlsx"]
    CHUNK_SIZE: int = 2000
    CHUNK_OVERLAP: int = 200
    
    # Tenants
    MULTI_TENANT: bool = True
    DEFAULT_TENANT: str = "default"
    
    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()