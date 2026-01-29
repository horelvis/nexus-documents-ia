import logging
import os
import secrets
from typing import Any, ClassVar, Dict, List, Optional, Union
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, field_validator
from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # Token expiration: default 8 days (11520 minutes)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 8)))
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
    STAGING_FRONTEND_URL: str = "https://pre.nouxcubeia.app"
    STAGING_API_URL: str = "https://api.pre.nouxcubeia.app"
    ALGORITHM: str = "HS256"
    
    # Development/Debug mode
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    SQL_ECHO: bool = os.getenv("SQL_ECHO", "false").lower() == "true"
    DB_POOL_DEBUG: bool = os.getenv("DB_POOL_DEBUG", "false").lower() == "true"

    # ==========================================================================
    # DEPLOYMENT MODE: Single Tenant vs Multi-Tenant
    # ==========================================================================
    # For on-premise deployments: SINGLE_TENANT_MODE=true (recommended)
    #   - One tenant for the entire organization
    #   - All users auto-assigned to the single tenant
    #   - Simpler configuration and management
    #   - Access control via roles and document ACLs
    #
    # For SaaS deployments: SINGLE_TENANT_MODE=false
    #   - Multiple organizations, each with their own tenant
    #   - Complete data isolation between tenants
    #   - Tenant creation on user registration
    SINGLE_TENANT_MODE: bool = os.getenv("SINGLE_TENANT_MODE", "true").lower() == "true"

    # Default tenant configuration (used when SINGLE_TENANT_MODE=true)
    # This tenant is created automatically on first startup
    DEFAULT_TENANT_ID: str = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")
    DEFAULT_TENANT_NAME: str = os.getenv("DEFAULT_TENANT_NAME", "NouxCubeIA Organization")
    DEFAULT_TENANT_SLUG: str = os.getenv("DEFAULT_TENANT_SLUG", "nouxcube")

    # Database bootstrap behavior
    # In production, prefer running migrations in the deployment pipeline.
    DB_AUTO_MIGRATE: bool = os.getenv("DB_AUTO_MIGRATE", "true" if DEBUG else "false").lower() == "true"
    
    # CORS Configuration
    # Set ALLOW_ALL_CORS=true for development with dynamic IPs
    # For production, configure BACKEND_CORS_ORIGINS via environment variable
    ALLOW_ALL_CORS: bool = os.getenv("ALLOW_ALL_CORS", "false").lower() == "true"

    # Default CORS origins - safe localhost only
    # Add additional origins via BACKEND_CORS_ORIGINS env var (comma-separated)
    # Example: BACKEND_CORS_ORIGINS=http://192.168.1.50:3000,https://app.example.com
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
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
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    ASYNC_DATABASE_URL: Optional[str] = os.getenv("ASYNC_DATABASE_URL")
    POSTGRES_SERVER: Optional[str] = os.getenv("POSTGRES_SERVER")
    POSTGRES_PORT: Optional[int] = int(os.getenv("POSTGRES_PORT", "5432")) if os.getenv("POSTGRES_PORT") else None
    POSTGRES_USER: Optional[str] = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: Optional[str] = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB: Optional[str] = os.getenv("POSTGRES_DB")
    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> Any:
        if isinstance(v, str):
            return v
        values = info.data if hasattr(info, 'data') else {}
        database_url = values.get("DATABASE_URL") or os.getenv("DATABASE_URL")
        if database_url:
            return database_url
        user = values.get("POSTGRES_USER")
        password = values.get("POSTGRES_PASSWORD")
        host = values.get("POSTGRES_SERVER")
        db = values.get("POSTGRES_DB")

        # Construir URL manualmente para Pydantic v2
        if not (user and password and host and db):
            return None
        url = f"postgresql://{user}:{password}@{host}/{db}"
        return url

    @model_validator(mode="after")
    def _validate_and_populate_database_fields(self) -> "Settings":
        database_url = self.SQLALCHEMY_DATABASE_URI or self.DATABASE_URL
        if not database_url:
            raise ValueError(
                "Database configuration missing: set DATABASE_URL or "
                "POSTGRES_SERVER/POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB"
            )

        if not self.SQLALCHEMY_DATABASE_URI:
            self.SQLALCHEMY_DATABASE_URI = database_url

        # Populate POSTGRES_* fields from URL if needed (used by security validator/logging).
        try:
            parsed = urlparse(database_url)
            self.POSTGRES_SERVER = self.POSTGRES_SERVER or parsed.hostname
            self.POSTGRES_PORT = self.POSTGRES_PORT or parsed.port
            self.POSTGRES_USER = self.POSTGRES_USER or parsed.username
            self.POSTGRES_PASSWORD = self.POSTGRES_PASSWORD or parsed.password
            self.POSTGRES_DB = self.POSTGRES_DB or (parsed.path.lstrip("/") if parsed.path else None)
        except Exception:
            # Keep whatever we already have; downstream validators will handle missing fields if needed.
            pass

        return self
    
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
    GCS_REGION: str = os.getenv("GCS_REGION", "europe-west1")
    # Signed URL expiration in seconds (default: 5 minutes)
    SIGNED_URL_EXPIRATION: int = int(os.getenv("SIGNED_URL_EXPIRATION", "300"))
    # Cloud Run detection
    IS_CLOUD_RUN: bool = os.getenv("K_SERVICE", None) is not None
    
    # REMOVED: LangChain/LangGraph services - migrated to Weaviate/Elysia
    # LANGCHAIN_SERVICE_URL: str = "http://langchain-service:8001"  # DEPRECATED
    # LANGGRAPH_SERVICE_URL: str = "http://langgraph-service:8007"  # DEPRECATED
    
    # NEW: Weaviate Service with Elysia integration (DEFAULT VECTOR ENGINE)
    WEAVIATE_SERVICE_URL: str = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
    USE_WEAVIATE_ELYSIA: bool = os.getenv("USE_WEAVIATE_ELYSIA", "true").lower() == "true"  # Default to true

    # Emma Agent Service (AI orchestration)
    EMMA_SERVICE_URL: str = os.getenv("EMMA_SERVICE_URL", "http://emma-agent-service:8009")

    # Text extraction microservice
    TEXT_EXTRACTION_SERVICE_URL: str = os.getenv("TEXT_EXTRACTION_SERVICE_URL", "http://textextract-service:8000")
    TEXT_EXTRACTION_DEFAULT_STRATEGY: str = os.getenv("TEXT_EXTRACTION_DEFAULT_STRATEGY", "auto")

    # Elasticsearch for hybrid search (SPECIALIZED SEARCH ENGINE)
    # NOTE: Elasticsearch service was removed from architecture - Weaviate handles all search
    ENABLE_ELASTICSEARCH: bool = os.getenv("ENABLE_ELASTICSEARCH", "false").lower() == "true"
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    ELASTICSEARCH_SERVICE_URL: str = os.getenv("ELASTICSEARCH_SERVICE_URL", "http://elasticsearch-service:8005")
    
    # CAG Microservice (Contextual Augmented Generation)
    CAG_SERVICE_URL: str = os.getenv("CAG_SERVICE_URL", "http://weaviate-service:8000")
    
    # LangExtract Service (Entity Extraction)
    LANGEXTRACT_SERVICE_URL: str = os.getenv("LANGEXTRACT_SERVICE_URL", "http://langextract-service:8009")
    BACKGROUND_TASKS_URL: str = os.getenv("BACKGROUND_TASKS_URL", "http://background-worker:8100")
    MCP_ALFRESCO_URL: str = os.getenv("MCP_ALFRESCO_URL", "http://mcp-alfresco:8000")

    # Identity Document Processing (GDPR-compliant)
    IDENTITY_DOC_ENABLED: bool = os.getenv("IDENTITY_DOC_ENABLED", "true").lower() == "true"
    IDENTITY_DOC_RETENTION_DAYS: int = int(os.getenv("IDENTITY_DOC_RETENTION_DAYS", "90"))
    IDENTITY_DOC_REQUIRE_CONSENT: bool = os.getenv("IDENTITY_DOC_REQUIRE_CONSENT", "true").lower() == "true"

    TEMPLATE_EDITOR_SERVICE_URL: str = os.getenv(
        "TEMPLATE_EDITOR_SERVICE_URL", "http://template-editor-service:8011"
    )

    # LLM / AI providers
    # NOTE: Ollama was removed; vLLM is the default local provider.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "vllm").lower()
    VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1").rstrip("/")
    VLLM_MODEL: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

    # Google Gemini (for Emma Voice Mode)
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    GEMINI_VOICE_MODEL: str = os.getenv("GEMINI_VOICE_MODEL", "gemini-2.5-flash-native-audio-preview-09-2025")
    GEMINI_VOICE_ENABLED: bool = os.getenv("GEMINI_VOICE_ENABLED", "true").lower() == "true"
    
    # Gotenberg Service (direct container)
    GOTENBERG_BASE_URL: str = "http://gotenberg:3000"
    
    # Document Processing - Max upload size in bytes (default: 50MB)
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))
    # Store as string to avoid JSON parsing issues
    _ALLOWED_EXTENSIONS: str = "pdf,docx,txt,md,csv,xlsx,png,jpg,jpeg,gif,bmp,tiff,webp,json,odt"
    # Text chunking configuration for RAG
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "2000"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    
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
    CAMUNDA_SERVICE_URL: str = os.getenv("CAMUNDA_SERVICE_URL", "http://camunda-service:8000")
    TTS_SERVICE_URL: str = os.getenv("TTS_SERVICE_URL", "http://tts-service:8000")
    
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
    # Credentials Encryption Key (Fernet - 32 bytes base64 URL-safe)
    # Used for: OAuth tokens, database credentials, API keys
    # Generate with: python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
    CREDENTIALS_ENCRYPTION_KEY: Optional[str] = os.getenv(
        "CREDENTIALS_ENCRYPTION_KEY",
        os.getenv("GOOGLE_DRIVE_ENCRYPTION_KEY")  # Legacy fallback
    )

    # Legacy alias (deprecated - use CREDENTIALS_ENCRYPTION_KEY)
    @property
    def GOOGLE_DRIVE_ENCRYPTION_KEY(self) -> Optional[str]:
        return self.CREDENTIALS_ENCRYPTION_KEY

    # Information Channels Configuration
    # IMPORTANT: Do NOT include gmail.metadata alongside gmail.readonly - it causes scope conflicts
    # gmail.readonly already includes metadata access
    GMAIL_OAUTH_SCOPES: str = os.getenv(
        "GMAIL_OAUTH_SCOPES",
        "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.readonly"
    )
    CHANNEL_OAUTH_REDIRECT_URI: str = os.getenv(
        "CHANNEL_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/v1/channels/oauth/callback"
    )
    CHANNEL_OAUTH_SUCCESS_REDIRECT_URL: str = os.getenv(
        "CHANNEL_OAUTH_SUCCESS_REDIRECT_URL",
        "http://localhost:3000/channels/setup/success"
    )
    CHANNEL_OAUTH_ERROR_REDIRECT_URL: str = os.getenv(
        "CHANNEL_OAUTH_ERROR_REDIRECT_URL",
        "http://localhost:3000/channels/setup/error"
    )

    @property
    def gmail_oauth_scopes_list(self) -> list[str]:
        return [scope.strip() for scope in self.GMAIL_OAUTH_SCOPES.split() if scope.strip()]

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
