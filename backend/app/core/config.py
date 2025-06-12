import os
import secrets
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    SERVER_NAME: str = "Document Management API"
    SERVER_HOST: AnyHttpUrl = "http://localhost:8000"
    STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLIC_KEY: Optional[str] = os.getenv("STRIPE_PUBLIC_KEY")
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PORTAL_CONFIGURATION_ID: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = os.getenv("STRIPE_PRO_PRICE_ID")
    STRIPE_ENTERPRISE_PRICE_ID: Optional[str] = os.getenv("STRIPE_ENTERPRISE_PRICE_ID")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    ALGORITHM: str = "HS256"
    
    # Development/Debug mode
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # CORS - Valores por defecto para desarrollo
    # CORS Origins - Configuración para desarrollo con IPs dinámicas
    ALLOW_ALL_CORS: bool = os.getenv("ALLOW_ALL_CORS", "false").lower() == "true"
    
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000", 
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://192.168.1.47:3000",
        "http://192.168.1.47:8000",
        "http://192.168.1.45:3000",
        "http://192.168.1.45:8000",
        "http://192.168.1.54:3000",
        "http://192.168.1.54:8000"
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
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
    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> Any:
        if isinstance(v, str):
            return v
        values = info.data if hasattr(info, 'data') else {}
        user = values.get("POSTGRES_USER")
        password = values.get("POSTGRES_PASSWORD")
        host = values.get("POSTGRES_SERVER")
        db = values.get("POSTGRES_DB")
        
        # Construir URL manualmente para Pydantic v2
        url = f"postgresql://{user}:{password}@{host}/{db}"
        return url
    
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
    
    # LangChain Microservice
    LANGCHAIN_SERVICE_URL: str = "http://langchain-service:8001"
    
    # Langroid Microservice (Advanced AI Agents)
    LANGROID_SERVICE_URL: str = "http://langroid-service:8002"

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama-service:11434"
    OLLAMA_MODEL: str = "llama3.2"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Gotenberg Service (direct container)
    GOTENBERG_BASE_URL: str = "http://gotenberg:3000"
    
    # Procesamiento de Documentos
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB por defecto
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx", "txt", "md", "csv", "xlsx"]
    CHUNK_SIZE: int = 2000
    CHUNK_OVERLAP: int = 200
    
    # Tenants
    MULTI_TENANT: bool = True
    DEFAULT_TENANT: str = "default"

    # Temporary API Key for basic auth during development
    API_KEY: str = "your-secret-api-key-here" # Default value, should be overridden by env var
    
    # Clerk Configuration
    CLERK_SECRET_KEY: Optional[str] = os.getenv("CLERK_SECRET_KEY")
    CLERK_PUBLISHABLE_KEY: Optional[str] = os.getenv("CLERK_PUBLISHABLE_KEY")
    CLERK_JWT_VERIFICATION_KEY: Optional[str] = os.getenv("CLERK_JWT_VERIFICATION_KEY")
    
    # Microservices - Usando la misma API_KEY para todos
    STORAGE_SERVICE_URL: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8001")
    STORAGE_API_KEY: str = os.getenv("STORAGE_API_KEY", "dev-storage-api-key-12345")
    
    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "extra": "ignore"  # Ignorar campos extra del .env
    }


settings = Settings()