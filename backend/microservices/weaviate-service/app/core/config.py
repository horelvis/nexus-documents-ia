"""Configuration for Weaviate Service with Microsoft Agent Framework"""
import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


DEBUG_DEFAULT = os.getenv("DEBUG", "true").lower() == "true"


class Settings(BaseSettings):
    """Weaviate Service settings"""

    # Service configuration
    service_name: str = "weaviate-service"
    service_port: int = 8007
    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    debug: bool = DEBUG_DEFAULT

    # Weaviate configuration
    weaviate_url: str = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
    weaviate_api_key: str = os.getenv("WEAVIATE_API_KEY", "")  # For cloud instances
    weaviate_timeout: int = int(os.getenv("WEAVIATE_TIMEOUT", "30"))

    # Agent Framework / LLM configuration
    agents_enabled: bool = os.getenv("AGENTS_ENABLED", "true").lower() == "true"
    # NOTE: Using tytn/vllm-openai:cu12.2 for CUDA 12.2 + RTX 4090 + driver 535.x compatibility
    llm_provider: str = os.getenv("LLM_PROVIDER", "vllm").lower()

    # vLLM configuration (PRIMARY - high-throughput GPU inference)
    vllm_enabled: bool = os.getenv("VLLM_ENABLED", "true").lower() == "true"
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    vllm_model: str = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    vllm_max_tokens: int = int(os.getenv("VLLM_MAX_TOKENS", "4096"))
    vllm_temperature: float = float(os.getenv("VLLM_TEMPERATURE", "0.7"))

    # Ollama configuration (LEGACY - use vLLM instead)
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

    # Embedding configuration
    # Providers: tei (HuggingFace TEI), sentence-transformers (local)
    # TEI models: BAAI/bge-m3 (1024 dims), intfloat/multilingual-e5-large (1024 dims)
    # ST models: paraphrase-multilingual-MiniLM-L12-v2 (384 dims)
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "tei")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    tei_url: str = os.getenv("TEI_URL", "http://text-embeddings-inference:8080")
    # Legacy: Sentence Transformers device (only if provider=sentence-transformers)
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")

    # Performance settings
    batch_size: int = int(os.getenv("BATCH_SIZE", "100"))
    max_chunk_size: int = int(os.getenv("MAX_CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))

    # Redis configuration (for caching and coordination)
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_url: str = f"redis://{redis_host}:{redis_port}"

    # RAG Pipeline - Semantic Cache settings
    rag_cache_enabled: bool = os.getenv("RAG_CACHE_ENABLED", "true").lower() == "true"
    rag_cache_similarity_threshold: float = float(os.getenv("RAG_CACHE_SIMILARITY_THRESHOLD", "0.92"))
    rag_cache_ttl_seconds: int = int(os.getenv("RAG_CACHE_TTL_SECONDS", "3600"))
    rag_cache_max_entries: int = int(os.getenv("RAG_CACHE_MAX_ENTRIES", "1000"))
    rag_cache_min_confidence: float = float(os.getenv("RAG_CACHE_MIN_CONFIDENCE", "0.65"))

    # RAG Pipeline - RRF Fusion settings
    rag_rrf_k: int = int(os.getenv("RAG_RRF_K", "60"))
    rag_dense_weight: float = float(os.getenv("RAG_DENSE_WEIGHT", "1.0"))
    rag_sparse_weight: float = float(os.getenv("RAG_SPARSE_WEIGHT", "1.0"))

    # RAG Pipeline - Claim Validation settings
    rag_validation_semantic: bool = os.getenv("RAG_VALIDATION_SEMANTIC", "false").lower() == "true"
    rag_validation_threshold: float = float(os.getenv("RAG_VALIDATION_THRESHOLD", "0.7"))

    # RAG Pipeline - Public Knowledge Integration
    rag_public_knowledge_enabled: bool = os.getenv("RAG_PUBLIC_KNOWLEDGE_ENABLED", "true").lower() == "true"
    rag_public_knowledge_weight: float = float(os.getenv("RAG_PUBLIC_KNOWLEDGE_WEIGHT", "0.7"))  # Weight for public vs tenant docs
    rag_public_knowledge_limit: int = int(os.getenv("RAG_PUBLIC_KNOWLEDGE_LIMIT", "10"))  # Max public docs to include
    rag_public_knowledge_categories: str = os.getenv("RAG_PUBLIC_KNOWLEDGE_CATEGORIES", "legislation,regulation,jurisprudence")  # Comma-separated

    # RAG Pipeline - Soft Selection (heuristic diversity-aware selection)
    rag_soft_selection_enabled: bool = os.getenv("RAG_SOFT_SELECTION_ENABLED", "true").lower() == "true"
    rag_soft_selection_temperature: float = float(os.getenv("RAG_SOFT_SELECTION_TEMPERATURE", "0.5"))  # Lower=sharper, Higher=uniform
    # MMR formula: λ*relevance - (1-λ)*redundancy (NOT: rel - λ*redundancy)
    rag_mmr_lambda: float = float(os.getenv("RAG_MMR_LAMBDA", "0.7"))  # 1.0=pure relevance, 0.0=pure diversity
    rag_num_clusters: int = int(os.getenv("RAG_NUM_CLUSTERS", "5"))  # For stratified selection
    # Safety caps to avoid noise
    rag_max_docs: int = int(os.getenv("RAG_MAX_DOCS", "12"))  # Hard cap on documents
    rag_min_weight: float = float(os.getenv("RAG_MIN_WEIGHT", "0.02"))  # Drop docs with weight < 2%
    rag_min_tokens_per_doc: int = int(os.getenv("RAG_MIN_TOKENS_PER_DOC", "200"))  # If can't fit minimum, drop
    # Context assembly budget: fraction of model max tokens reserved for context (rest for query/response)
    rag_context_budget_fraction: float = float(os.getenv("RAG_CONTEXT_BUDGET_FRACTION", "0.7"))
    # Smart truncation priority: sections > paragraphs > sentences
    rag_truncation_priority: str = os.getenv("RAG_TRUNCATION_PRIORITY", "sections")  # sections, paragraphs, sentences

    # Storage service URL
    storage_service_url: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8003")

    # Main API URL
    api_url: str = os.getenv("API_URL", "http://api:8000")

    # Database (for metadata coordination)
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")

    # Collection naming (tenant isolation)
    collection_prefix: str = "nexus_"
    default_collection: str = "documents"

    # Agent Framework configuration
    default_workflow: str = os.getenv("DEFAULT_WORKFLOW", "auto")
    agent_max_turns: int = int(os.getenv("AGENT_MAX_TURNS", "15"))
    agent_timeout_seconds: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "300"))
    agent_fallback_to_rag: bool = os.getenv("AGENT_FALLBACK_TO_RAG", "true").lower() == "true"

    # Concurrency Control (SaaS multi-tenant)
    # Max concurrent LLM calls across all tenants (RTX 4090 can handle 8+ concurrent)
    llm_max_concurrent: int = int(os.getenv("LLM_MAX_CONCURRENT", "8"))
    # Max concurrent analyses per tenant
    analysis_max_per_tenant: int = int(os.getenv("ANALYSIS_MAX_PER_TENANT", "3"))
    # Queue timeout for waiting LLM slot (seconds) - reduced for faster feedback
    llm_queue_timeout: int = int(os.getenv("LLM_QUEUE_TIMEOUT", "90"))
    # Enable tenant isolation in queuing
    tenant_isolation_enabled: bool = os.getenv("TENANT_ISOLATION_ENABLED", "true").lower() == "true"

    # Visualization settings
    enable_dynamic_display: bool = os.getenv("ENABLE_DYNAMIC_DISPLAY", "true").lower() == "true"
    max_display_items: int = int(os.getenv("MAX_DISPLAY_ITEMS", "50"))

    # Learning and feedback
    enable_feedback_learning: bool = os.getenv("ENABLE_FEEDBACK_LEARNING", "true").lower() == "true"
    feedback_storage_days: int = int(os.getenv("FEEDBACK_STORAGE_DAYS", "30"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    request_logging_enabled: bool = os.getenv(
        "REQUEST_LOGGING_ENABLED",
        "true" if DEBUG_DEFAULT else "false"
    ).lower() == "true"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
