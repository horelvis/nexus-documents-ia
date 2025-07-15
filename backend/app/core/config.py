import os
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    SERVER_NAME: str = "NexusDocs360 API"
    SERVER_HOST: AnyHttpUrl = "http://localhost:8000"
    STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLIC_KEY: Optional[str] = os.getenv("STRIPE_PUBLIC_KEY")
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PORTAL_CONFIGURATION_ID: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = os.getenv("STRIPE_PRO_PRICE_ID")
    STRIPE_ENTERPRISE_PRICE_ID: Optional[str] = os.getenv("STRIPE_ENTERPRISE_PRICE_ID")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
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
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # "redis" for Docker, "localhost" for local
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    
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
    
    
    # LangGraph Microservice (State-based Workflows)
    LANGGRAPH_SERVICE_URL: str = "http://langgraph-service:8007"

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama-service:11434"
    OLLAMA_MODEL: str = "llama3.2"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Gotenberg Service (direct container)
    GOTENBERG_BASE_URL: str = "http://gotenberg:3000"
    
    # Procesamiento de Documentos
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB por defecto
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx", "txt", "md", "csv", "xlsx", "png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp", "json"]
    CHUNK_SIZE: int = 2000
    CHUNK_OVERLAP: int = 200
    
    # Tenants
    MULTI_TENANT: bool = True
    DEFAULT_TENANT: str = "default"

    # Unified API Key for all microservices
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "unified-microservices-key-12345")
    
    # Legacy API Key (for backward compatibility)
    API_KEY: str = "your-secret-api-key-here" # Default value, should be overridden by env var
    
    # Clerk Configuration
    CLERK_SECRET_KEY: Optional[str] = os.getenv("CLERK_SECRET_KEY")
    CLERK_PUBLISHABLE_KEY: Optional[str] = os.getenv("CLERK_PUBLISHABLE_KEY")
    CLERK_JWT_VERIFICATION_KEY: Optional[str] = os.getenv("CLERK_JWT_VERIFICATION_KEY")
    
    # Microservices URLs
    STORAGE_SERVICE_URL: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8001")
    
    # Email Configuration
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "noreply@nexusdocument.com")
    MAIL_FROM_NAME: str = os.getenv("MAIL_FROM_NAME", "Nexus Document Management")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_STARTTLS: bool = os.getenv("MAIL_STARTTLS", "True").lower() == "true"
    MAIL_SSL_TLS: bool = os.getenv("MAIL_SSL_TLS", "False").lower() == "true"
    MAIL_USE_CREDENTIALS: bool = os.getenv("MAIL_USE_CREDENTIALS", "True").lower() == "true"
    MAIL_VALIDATE_CERTS: bool = os.getenv("MAIL_VALIDATE_CERTS", "True").lower() == "true"
    
    # Signature Service Configuration
    SIGNATURE_ENCRYPTION_KEY: Optional[str] = os.getenv("SIGNATURE_ENCRYPTION_KEY")
    SIGNATURE_WEBHOOK_SECRET: Optional[str] = os.getenv("SIGNATURE_WEBHOOK_SECRET")
    
    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "extra": "ignore"  # Ignorar campos extra del .env
    }
    
    # Propiedades de compatibilidad para API keys antiguos
    @property
    def LANGGRAPH_API_KEY(self) -> str:
        return self.MICROSERVICES_API_KEY
    
    @property
    def STORAGE_API_KEY(self) -> str:
        return self.MICROSERVICES_API_KEY


settings = Settings()