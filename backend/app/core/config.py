import logging
import os
import secrets
from typing import Any, ClassVar, Dict, List, Optional, Union
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


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
    STRIPE_BASIC_PRICE_ID: Optional[str] = os.getenv("STRIPE_BASIC_PRICE_ID")
    STRIPE_PRO_PRICE_ID: Optional[str] = os.getenv("STRIPE_PRO_PRICE_ID")
    STRIPE_PRO_YEARLY_PRICE_ID: Optional[str] = os.getenv("STRIPE_PRO_YEARLY_PRICE_ID")
    STRIPE_ENTERPRISE_PRICE_ID: Optional[str] = os.getenv("STRIPE_ENTERPRISE_PRICE_ID")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # Production/Staging URLs
    STAGING_FRONTEND_URL: str = "https://pre.nexusdocs360.app"
    STAGING_API_URL: str = "https://api.pre.nexusdocs360.app"
    ALGORITHM: str = "HS256"
    
    # Development/Debug mode
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # CORS - Valores por defecto para desarrollo
    # CORS Origins - Configuración para desarrollo con IPs dinámicas
    ALLOW_ALL_CORS: bool = os.getenv("ALLOW_ALL_CORS", "false").lower() == "true"
    
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://192.168.1.47:3000",
        "http://192.168.1.47:3001",
        "http://192.168.1.47:3002",
        "http://192.168.1.47:8000",
        "http://192.168.1.45:3000",
        "http://192.168.1.45:3001",
        "http://192.168.1.45:3002",
        "http://192.168.1.45:8000",
        "http://192.168.1.54:3000",
        "http://192.168.1.54:3001",
        "http://192.168.1.54:3002",
        "http://192.168.1.54:8000",
        "http://192.168.1.35:3000",
        "http://192.168.1.35:3001",
        "http://192.168.1.35:3002",
        "http://192.168.1.35:8000",
        "http://192.168.1.58:3000",
        "http://192.168.1.58:3001",
        "http://192.168.1.58:3002",
        "http://192.168.1.58:8000",
        "http://nexus-docs360.es",
        "http://nexus-docs360.es:3000",
        "http://nexus-docs360.es:3001",
        "https://nexus-docs360.es",
        "https://nexus-docs360.es:3000",
        "https://nexus-docs360.es:3001",
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
    _REDIS_URL_ENV: ClassVar[Optional[str]] = os.getenv("REDIS_URL")
    if _REDIS_URL_ENV:
        _parsed_redis_url = urlparse(_REDIS_URL_ENV)
        REDIS_HOST: str = _parsed_redis_url.hostname or os.getenv("REDIS_HOST", "redis")
        REDIS_PORT: int = _parsed_redis_url.port or int(os.getenv("REDIS_PORT", "6379"))
        REDIS_PASSWORD: Optional[str] = _parsed_redis_url.password or os.getenv("REDIS_PASSWORD")
    else:
        REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # "redis" for Docker, "localhost" for local
        REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
        REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    
    @property
    def REDIS_URL(self) -> str:
        """Generate Redis URL from host and port unless provided via env."""
        return self._REDIS_URL_ENV or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"
    
    # NEW: Elasticsearch for hybrid search and analytics
    ELASTICSEARCH_HOST: str = os.getenv("ELASTICSEARCH_HOST", "localhost")
    ELASTICSEARCH_PORT: int = int(os.getenv("ELASTICSEARCH_PORT", "9200"))
    ELASTICSEARCH_URL: str = f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"
    
    # Google Cloud Storage
    GCS_BUCKET_NAME: str
    GCS_CREDENTIALS: Optional[str] = None
    GCS_PROJECT_ID: Optional[str] = None
    GCS_REGION: str = "europe-west1"  # Región por defecto
    # Tiempo de validez para URLs firmadas (segundos)
    SIGNED_URL_EXPIRATION: int = 300
    # Cloud Run detection
    IS_CLOUD_RUN: bool = os.getenv("K_SERVICE", None) is not None
    
    # REMOVED: LangChain/LangGraph services - migrated to Weaviate/Elysia
    # LANGCHAIN_SERVICE_URL: str = "http://langchain-service:8001"  # DEPRECATED
    # LANGGRAPH_SERVICE_URL: str = "http://langgraph-service:8007"  # DEPRECATED
    
    # NEW: Weaviate Service with Elysia integration (DEFAULT VECTOR ENGINE)
    WEAVIATE_SERVICE_URL: str = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")
    USE_WEAVIATE_ELYSIA: bool = os.getenv("USE_WEAVIATE_ELYSIA", "true").lower() == "true"  # Default to true

    # Text extraction microservice
    TEXT_EXTRACTION_SERVICE_URL: str = os.getenv("TEXT_EXTRACTION_SERVICE_URL", "http://textextract-service:8000")
    TEXT_EXTRACTION_DEFAULT_STRATEGY: str = os.getenv("TEXT_EXTRACTION_DEFAULT_STRATEGY", "auto")

    # Elasticsearch for hybrid search (SPECIALIZED SEARCH ENGINE)
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    ELASTICSEARCH_SERVICE_URL: str = os.getenv("ELASTICSEARCH_SERVICE_URL", "http://elasticsearch-service:8005")
    
    # CAG Microservice (Contextual Augmented Generation)
    CAG_SERVICE_URL: str = os.getenv("CAG_SERVICE_URL", "http://weaviate-service:8000")
    
    # LangExtract Service (Entity Extraction)
    LANGEXTRACT_SERVICE_URL: str = os.getenv("LANGEXTRACT_SERVICE_URL", "http://langextract-service:8009")
    BACKGROUND_TASKS_URL: str = os.getenv("BACKGROUND_TASKS_URL", "http://background-worker:8100")
    
    # Temporalio Service
    TEMPORALIO_SERVICE_URL: str = os.getenv("TEMPORALIO_SERVICE_URL", "http://temporalio-service:8000")
    TEMPLATE_EDITOR_SERVICE_URL: str = os.getenv(
        "TEMPLATE_EDITOR_SERVICE_URL", "http://template-editor-service:8011"
    )

    # LLM / AI providers
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://genai-ollama:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Gotenberg Service (direct container)
    GOTENBERG_BASE_URL: str = "http://gotenberg:3000"
    
    # Procesamiento de Documentos
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB por defecto
    # Store as string to avoid JSON parsing issues
    _ALLOWED_EXTENSIONS: str = "pdf,docx,txt,md,csv,xlsx,png,jpg,jpeg,gif,bmp,tiff,webp,json,odt"
    CHUNK_SIZE: int = 2000
    CHUNK_OVERLAP: int = 200
    
    @property
    def ALLOWED_EXTENSIONS(self) -> List[str]:
        """Parse comma-separated extensions into list"""
        if hasattr(self, '_allowed_extensions_parsed'):
            return self._allowed_extensions_parsed
        
        extensions_str = os.getenv("ALLOWED_EXTENSIONS", self._ALLOWED_EXTENSIONS)
        self._allowed_extensions_parsed = [ext.strip() for ext in extensions_str.split(",") if ext.strip()]
        return self._allowed_extensions_parsed
    
    # Tenants
    MULTI_TENANT: bool = True
    DEFAULT_TENANT: str = "default"

    # Unified API Key for all microservices (required)
    MICROSERVICES_API_KEY: str
    
    # Clerk Configuration
    CLERK_API_URL: str = os.getenv("CLERK_API_URL", "https://api.clerk.com/v1")
    CLERK_SECRET_KEY: Optional[str] = os.getenv("CLERK_SECRET_KEY")
    CLERK_PUBLISHABLE_KEY: Optional[str] = os.getenv("CLERK_PUBLISHABLE_KEY")
    CLERK_JWT_VERIFICATION_KEY: Optional[str] = os.getenv("CLERK_JWT_VERIFICATION_KEY")
    
    # Microservices URLs
    STORAGE_SERVICE_URL: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8003")
    
    # Email Configuration
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "noreply@nexusdocument.com")
    MAIL_FROM_NAME: str = os.getenv("MAIL_FROM_NAME", "Nexus Document Management")
    
    # Google OAuth for Drive/Docs
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REDIRECT_URI: str = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/v1/google-drive/oauth/callback"
    )
    GOOGLE_OAUTH_SCOPES: str = os.getenv(
        "GOOGLE_OAUTH_SCOPES",
        "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/documents"
    )
    GOOGLE_OAUTH_SUCCESS_REDIRECT_URL: str = os.getenv(
        "GOOGLE_OAUTH_SUCCESS_REDIRECT_URL",
        "http://localhost:3000/integrations/google-drive/success"
    )
    GOOGLE_OAUTH_ERROR_REDIRECT_URL: str = os.getenv(
        "GOOGLE_OAUTH_ERROR_REDIRECT_URL",
        "http://localhost:3000/integrations/google-drive/error"
    )
    GOOGLE_DRIVE_ENCRYPTION_KEY: Optional[str] = os.getenv("GOOGLE_DRIVE_ENCRYPTION_KEY")
    
    @property
    def google_oauth_scopes_list(self) -> list[str]:
        return [scope.strip() for scope in self.GOOGLE_OAUTH_SCOPES.split() if scope.strip()]
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
    def LANGGRAPH_SERVICE_URL(self) -> str:
        """
        Compatibility property for legacy LangGraph clients.
        All LangGraph traffic is now handled by the integrated CAG engine.
        """
        return self.CAG_SERVICE_URL
    
    @property
    def STORAGE_API_KEY(self) -> str:
        return self.MICROSERVICES_API_KEY
    
    @property
    def microservices_api_key(self) -> str:
        """Compatibility property for microservices_api_key (lowercase)"""
        return self.MICROSERVICES_API_KEY


settings = Settings()
