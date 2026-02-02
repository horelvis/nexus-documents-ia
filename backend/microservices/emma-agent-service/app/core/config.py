"""Configuration for Emma Agent Service"""
import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


DEBUG_DEFAULT = os.getenv("DEBUG", "true").lower() == "true"


class Settings(BaseSettings):
    """Emma Agent Service settings"""

    # Service configuration
    service_name: str = "emma-agent-service"
    service_port: int = 8009

    # ==========================================================================
    # Active Sector (Multi-Pipeline RAG)
    # ==========================================================================
    # Set before data ingestion. Valid: legal, medical, documental, or empty for generic mode.
    # Changing sector requires clearing Weaviate collections + AGE graph.
    active_sector: str = os.getenv("ACTIVE_SECTOR", "")

    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    debug: bool = DEBUG_DEFAULT

    # ==========================================================================
    # Weaviate Service Connection (HTTP client)
    # ==========================================================================
    # This service calls weaviate-service for RAG and vector search
    weaviate_service_url: str = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")
    weaviate_service_timeout: int = int(os.getenv("WEAVIATE_SERVICE_TIMEOUT", "120"))

    # ==========================================================================
    # Deployment Mode: Single-tenant vs Multi-tenant
    # ==========================================================================
    single_tenant_mode: bool = os.getenv("SINGLE_TENANT_MODE", "true").lower() == "true"
    default_tenant_id: str = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")
    default_tenant_name: str = os.getenv("DEFAULT_TENANT_NAME", "NouxCubeIA Organization")

    # ==========================================================================
    # LLM Configuration
    # ==========================================================================
    agents_enabled: bool = os.getenv("AGENTS_ENABLED", "true").lower() == "true"
    llm_provider: str = os.getenv("LLM_PROVIDER", "vllm").lower()

    # vLLM configuration (PRIMARY - Qwen2.5-7B-Instruct AWQ 4-bit)
    vllm_enabled: bool = os.getenv("VLLM_ENABLED", "true").lower() == "true"
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    vllm_model: str = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
    vllm_max_tokens: int = int(os.getenv("VLLM_MAX_TOKENS", "16384"))
    vllm_temperature: float = float(os.getenv("VLLM_TEMPERATURE", "0.6"))
    vllm_enable_thinking: bool = os.getenv("VLLM_ENABLE_THINKING", "true").lower() == "true"
    vllm_thinking_budget: int = int(os.getenv("VLLM_THINKING_BUDGET", "4096"))

    # Ollama configuration (LEGACY)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://genai-ollama:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2:latest"))

    # OpenAI configuration (FALLBACK)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Anthropic configuration
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # Google Gemini configuration
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # OpenRouter configuration
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")

    # ==========================================================================
    # Redis Configuration (for sessions and caching)
    # ==========================================================================
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_url: str = f"redis://{redis_host}:{redis_port}"

    # ==========================================================================
    # Agent Framework Configuration
    # ==========================================================================
    # Specialist agent generation settings (used by base.py specialist nodes)
    agent_temperature: float = float(os.getenv("AGENT_TEMPERATURE", "0.3"))
    agent_max_tokens: int = int(os.getenv("AGENT_MAX_TOKENS", "2048"))

    default_workflow: str = os.getenv("DEFAULT_WORKFLOW", "auto")
    agent_max_turns: int = int(os.getenv("AGENT_MAX_TURNS", "15"))
    agent_timeout_seconds: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "300"))
    agent_fallback_to_rag: bool = os.getenv("AGENT_FALLBACK_TO_RAG", "true").lower() == "true"

    # Concurrency Control
    llm_max_concurrent: int = int(os.getenv("LLM_MAX_CONCURRENT", "8"))
    analysis_max_per_tenant: int = int(os.getenv("ANALYSIS_MAX_PER_TENANT", "3"))
    llm_queue_timeout: int = int(os.getenv("LLM_QUEUE_TIMEOUT", "90"))
    tenant_isolation_enabled: bool = os.getenv("TENANT_ISOLATION_ENABLED", "true").lower() == "true"

    # Visualization settings
    enable_dynamic_display: bool = os.getenv("ENABLE_DYNAMIC_DISPLAY", "true").lower() == "true"
    max_display_items: int = int(os.getenv("MAX_DISPLAY_ITEMS", "50"))

    # Learning and feedback
    enable_feedback_learning: bool = os.getenv("ENABLE_FEEDBACK_LEARNING", "true").lower() == "true"
    feedback_storage_days: int = int(os.getenv("FEEDBACK_STORAGE_DAYS", "30"))

    # ==========================================================================
    # Langfuse Observability
    # ==========================================================================
    langfuse_enabled: bool = os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_flush_at: int = int(os.getenv("LANGFUSE_FLUSH_AT", "10"))
    langfuse_flush_interval: float = float(os.getenv("LANGFUSE_FLUSH_INTERVAL", "5"))
    langfuse_sample_rate: float = float(os.getenv("LANGFUSE_SAMPLE_RATE", "1.0"))
    langfuse_debug: bool = os.getenv("LANGFUSE_DEBUG", "false").lower() == "true"

    # Main API URL (for auth validation)
    api_url: str = os.getenv("API_URL", "http://api:8000")

    # Knowledge Tree Service (structural context)
    knowledge_tree_service_url: str = os.getenv("KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
    knowledge_tree_service_timeout: int = int(os.getenv("KNOWLEDGE_TREE_SERVICE_TIMEOUT", "30"))

    # Text Extraction Service (for uploaded files)
    text_extraction_service_url: str = os.getenv("TEXT_EXTRACTION_SERVICE_URL", "http://textextract-service:8000")
    text_extraction_service_timeout: int = int(os.getenv("TEXT_EXTRACTION_SERVICE_TIMEOUT", "60"))

    # Database (for session persistence)
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")

    # PostgreSQL for Apache AGE (graph queries via weaviate-service)
    postgres_host: str = os.getenv("POSTGRES_SERVER", os.getenv("POSTGRES_HOST", "db"))
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "nexus_db")
    postgres_user: str = os.getenv("POSTGRES_USER", "nexus_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "nexus_password")

    # ==========================================================================
    # RLM (Recursive Language Models) Configuration
    # ==========================================================================
    rlm_enabled: bool = os.getenv("RLM_ENABLED", "false").lower() == "true"
    rlm_token_threshold: int = int(os.getenv("RLM_TOKEN_THRESHOLD", "16000"))
    rlm_chunk_size: int = int(os.getenv("RLM_CHUNK_SIZE", "6000"))
    rlm_chunk_overlap: int = int(os.getenv("RLM_CHUNK_OVERLAP", "500"))
    rlm_max_depth: int = int(os.getenv("RLM_MAX_DEPTH", "3"))
    rlm_max_chunks: int = int(os.getenv("RLM_MAX_CHUNKS", "20"))

    # ==========================================================================
    # Background Worker (for Celery verification tasks)
    # ==========================================================================
    background_worker_url: str = os.getenv("BACKGROUND_WORKER_URL", "http://background-worker:8100")

    # ==========================================================================
    # Verified Generation Configuration
    # ==========================================================================
    verified_cache_ttl_seconds: int = int(os.getenv("VERIFIED_CACHE_TTL_SECONDS", "3600"))
    verified_claim_temperature: float = float(os.getenv("VERIFIED_CLAIM_TEMPERATURE", "0.3"))

    # ==========================================================================
    # Web Search (DuckDuckGo)
    # ==========================================================================
    web_search_enabled: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
    web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    web_search_region: str = os.getenv("WEB_SEARCH_REGION", "es-es")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    request_logging_enabled: bool = os.getenv(
        "REQUEST_LOGGING_ENABLED",
        "true" if DEBUG_DEFAULT else "false"
    ).lower() == "true"

    # Temporary upload handling (non-indexed files)
    upload_tmp_dir: str = os.getenv("EMMA_UPLOAD_TMP_DIR", "/tmp/emma_uploads")
    upload_ttl_seconds: int = int(os.getenv("EMMA_UPLOAD_TTL_SECONDS", "3600"))
    upload_max_chars_per_doc: int = int(os.getenv("EMMA_UPLOAD_MAX_CHARS_PER_DOC", "15000"))
    upload_max_total_chars: int = int(os.getenv("EMMA_UPLOAD_MAX_TOTAL_CHARS", "40000"))

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
