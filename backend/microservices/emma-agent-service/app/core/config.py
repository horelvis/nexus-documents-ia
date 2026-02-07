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
    vllm_model: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-14B-AWQ")
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

    # OpenRouter configuration (unified gateway to 200+ models)
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-235b-a22b-2507")
    openrouter_site_url: str = os.getenv("OPENROUTER_SITE_URL", "https://nouxcube.com")
    openrouter_site_name: str = os.getenv("OPENROUTER_SITE_NAME", "NouxCubeIA")

    # LLM Fallback Configuration (automatic failover between providers)
    llm_fallback_enabled: bool = os.getenv("LLM_FALLBACK_ENABLED", "false").lower() == "true"
    llm_fallback_chain: str = os.getenv("LLM_FALLBACK_CHAIN", "vllm,openrouter,openai")

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

    # ReAct Agent Loop
    react_max_observe_length: int = int(os.getenv("REACT_MAX_OBSERVE_LENGTH", "8000"))
    react_stuck_detection_window: int = int(os.getenv("REACT_STUCK_DETECTION_WINDOW", "5"))
    react_max_completion_tokens: int = int(os.getenv("REACT_MAX_COMPLETION_TOKENS", "4096"))
    react_tool_timeout_seconds: float = float(os.getenv("REACT_TOOL_TIMEOUT_SECONDS", "60"))
    react_max_history_messages: int = int(os.getenv("REACT_MAX_HISTORY_MESSAGES", "40"))
    react_tool_description_max_chars: int = int(os.getenv("REACT_TOOL_DESCRIPTION_MAX_CHARS", "200"))
    react_global_timeout_seconds: float = float(os.getenv("REACT_GLOBAL_TIMEOUT_SECONDS", "120"))

    # LLM Fallback
    llm_retry_delay_seconds: float = float(os.getenv("LLM_RETRY_DELAY_SECONDS", "0.5"))

    # Agent Fallback Timeouts (factor_agent, writer_agent raw vLLM calls)
    agent_raw_vllm_timeout_seconds: float = float(os.getenv("AGENT_RAW_VLLM_TIMEOUT_SECONDS", "60"))

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

    # ==========================================================================
    # Prompt Management (Langfuse Prompts + Custom)
    # ==========================================================================
    # Feature flag to use Langfuse for prompt storage instead of YAML
    use_langfuse_prompts: bool = os.getenv("USE_LANGFUSE_PROMPTS", "false").lower() == "true"
    # Local cache TTL for Langfuse prompts (seconds)
    langfuse_prompt_cache_ttl: int = int(os.getenv("LANGFUSE_PROMPT_CACHE_TTL", "300"))
    # Enable few-shot example retrieval
    few_shot_enabled: bool = os.getenv("FEW_SHOT_ENABLED", "true").lower() == "true"
    # Max few-shot examples to include in prompts
    few_shot_max_examples: int = int(os.getenv("FEW_SHOT_MAX_EXAMPLES", "3"))
    # Min similarity score for few-shot retrieval (0.0-1.0)
    few_shot_min_similarity: float = float(os.getenv("FEW_SHOT_MIN_SIMILARITY", "0.6"))
    # Enable guardrail validation
    guardrails_enabled: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    # Enable rule engine for dynamic prompt injection
    rule_engine_enabled: bool = os.getenv("RULE_ENGINE_ENABLED", "true").lower() == "true"

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
    verified_duplicate_threshold: float = float(os.getenv("VERIFIED_DUPLICATE_THRESHOLD", "0.65"))
    verified_evidence_excerpt_limit: int = int(os.getenv("VERIFIED_EVIDENCE_EXCERPT_LIMIT", "2000"))

    # ==========================================================================
    # Web Search (Tavily primary, DuckDuckGo fallback)
    # ==========================================================================
    web_search_enabled: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
    web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    web_search_region: str = os.getenv("WEB_SEARCH_REGION", "es-es")
    web_search_snippet_max_chars: int = int(os.getenv("WEB_SEARCH_SNIPPET_MAX_CHARS", "500"))
    # Tavily API (get free key at https://tavily.com - 1000 searches/month free)
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # ==========================================================================
    # Predictive Analysis Thresholds
    # ==========================================================================
    predictive_duplicate_threshold: float = float(os.getenv("PREDICTIVE_DUPLICATE_THRESHOLD", "0.65"))
    predictive_similarity_threshold: float = float(os.getenv("PREDICTIVE_SIMILARITY_THRESHOLD", "0.60"))
    predictive_evidence_excerpt_limit: int = int(os.getenv("PREDICTIVE_EVIDENCE_EXCERPT_LIMIT", "500"))
    predictive_fallback_weight: float = float(os.getenv("PREDICTIVE_FALLBACK_WEIGHT", "0.5"))
    predictive_fallback_confidence: float = float(os.getenv("PREDICTIVE_FALLBACK_CONFIDENCE", "0.5"))

    # ==========================================================================
    # CENDOJ Jurisprudence Search (Legal Sector)
    # ==========================================================================
    cendoj_enabled: bool = os.getenv(
        "CENDOJ_ENABLED",
        "true" if os.getenv("ACTIVE_SECTOR", "") == "legal" else "false"
    ).lower() == "true"
    cendoj_timeout: int = int(os.getenv("CENDOJ_TIMEOUT", "300"))
    cendoj_max_content: int = int(os.getenv("CENDOJ_MAX_CONTENT", "2"))

    # ==========================================================================
    # Emma Service
    # ==========================================================================
    emma_document_content_max_chars: int = int(os.getenv("EMMA_DOCUMENT_CONTENT_MAX_CHARS", "20000"))

    # ==========================================================================
    # Emma Reactive Configuration
    # ==========================================================================
    event_bus_enabled: bool = os.getenv("EVENT_BUS_ENABLED", "true").lower() == "true"
    credentials_encryption_key: str = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")

    # Heartbeat Delivery
    heartbeat_insight_ttl_seconds: int = int(os.getenv("HEARTBEAT_INSIGHT_TTL_SECONDS", "604800"))
    heartbeat_max_insights_stored: int = int(os.getenv("HEARTBEAT_MAX_INSIGHTS_STORED", "100"))

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

    # ==========================================================================
    # Default Location for Social Channels
    # ==========================================================================
    default_location_city: str = os.getenv("DEFAULT_LOCATION_CITY", "Molina de Segura")
    default_location_region: str = os.getenv("DEFAULT_LOCATION_REGION", "Región de Murcia")
    default_location_country: str = os.getenv("DEFAULT_LOCATION_COUNTRY", "España")
    default_location_timezone: str = os.getenv("DEFAULT_LOCATION_TIMEZONE", "Europe/Madrid")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
