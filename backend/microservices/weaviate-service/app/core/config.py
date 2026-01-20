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
    # NOTE: Using vllm-qwen3vl image (vLLM + transformers 4.57+) for Qwen3 support
    llm_provider: str = os.getenv("LLM_PROVIDER", "vllm").lower()

    # vLLM configuration (PRIMARY - high-throughput GPU inference)
    # Model: Qwen3-4B-Thinking-2507 - Extended reasoning with automatic thinking mode
    # Features: Automatic <think>...</think> blocks, 256K native context (32K recommended)
    # VRAM: ~10GB (coexists with Qwen3-VL-Embedding-2B at ~5GB = ~15GB total)
    # Docs: https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507
    vllm_enabled: bool = os.getenv("VLLM_ENABLED", "true").lower() == "true"
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    vllm_model: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-4B-Thinking-2507")
    vllm_max_tokens: int = int(os.getenv("VLLM_MAX_TOKENS", "4096"))
    vllm_temperature: float = float(os.getenv("VLLM_TEMPERATURE", "0.6"))  # Recommended for thinking mode
    # Thinking mode settings
    vllm_enable_thinking: bool = os.getenv("VLLM_ENABLE_THINKING", "true").lower() == "true"
    vllm_thinking_budget: int = int(os.getenv("VLLM_THINKING_BUDGET", "4096"))  # Increased for complex reasoning

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

    # ==========================================================================
    # Embedding configuration (Qwen3-VL-Embedding-2B - Multimodal)
    # ==========================================================================
    # Primary Provider: qwen3-vl (Qwen3-VL-Embedding-2B via vLLM)
    # Features: Unified vector space for text + images/diagrams/tables
    # Alternative providers: tei (deprecated), sentence-transformers (local)
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "qwen3-vl")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-VL-Embedding-2B")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    embedding_url: str = os.getenv("EMBEDDING_URL", "http://qwen3-vl-embedding:8000/v1")
    # Legacy: TEI URL (deprecated - use qwen3-vl instead)
    tei_url: str = os.getenv("TEI_URL", "http://text-embeddings-inference:8080")
    # Legacy: Sentence Transformers device (only if provider=sentence-transformers)
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")

    # Multimodal Embedding - NOW ENABLED BY DEFAULT
    # Uses same Qwen3-VL-Embedding-2B model for both text and images
    # Provides unified vector space for cross-modal search (text → images, images → text)
    multimodal_embedding_enabled: bool = os.getenv("MULTIMODAL_EMBEDDING_ENABLED", "true").lower() == "true"
    multimodal_embedding_url: str = os.getenv("MULTIMODAL_EMBEDDING_URL", "http://qwen3-vl-embedding:8000/v1")
    multimodal_embedding_model: str = os.getenv("MULTIMODAL_EMBEDDING_MODEL", "Qwen/Qwen3-VL-Embedding-2B")
    multimodal_embedding_dimensions: int = int(os.getenv("MULTIMODAL_EMBEDDING_DIMENSIONS", "1024"))
    # Visual content extraction settings
    multimodal_extract_tables: bool = os.getenv("MULTIMODAL_EXTRACT_TABLES", "true").lower() == "true"
    multimodal_extract_diagrams: bool = os.getenv("MULTIMODAL_EXTRACT_DIAGRAMS", "true").lower() == "true"
    multimodal_extract_images: bool = os.getenv("MULTIMODAL_EXTRACT_IMAGES", "true").lower() == "true"
    multimodal_page_thumbnails: bool = os.getenv("MULTIMODAL_PAGE_THUMBNAILS", "false").lower() == "true"
    # Image rendering settings for PDF visual extraction
    multimodal_render_dpi: int = int(os.getenv("MULTIMODAL_RENDER_DPI", "150"))  # 150-300 DPI for quality
    multimodal_max_image_size: int = int(os.getenv("MULTIMODAL_MAX_IMAGE_SIZE", "1024"))  # Max dimension in pixels
    multimodal_image_format: str = os.getenv("MULTIMODAL_IMAGE_FORMAT", "png")  # png or jpeg

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
    rag_max_docs: int = int(os.getenv("RAG_MAX_DOCS", "20"))  # Hard cap on documents (increased for RLM)
    rag_min_weight: float = float(os.getenv("RAG_MIN_WEIGHT", "0.02"))  # Drop docs with weight < 2%
    rag_min_tokens_per_doc: int = int(os.getenv("RAG_MIN_TOKENS_PER_DOC", "200"))  # If can't fit minimum, drop
    # Context assembly budget: fraction of model max tokens reserved for context (rest for query/response)
    rag_context_budget_fraction: float = float(os.getenv("RAG_CONTEXT_BUDGET_FRACTION", "0.85"))  # Increased for RLM
    # Smart truncation priority: sections > paragraphs > sentences
    rag_truncation_priority: str = os.getenv("RAG_TRUNCATION_PRIORITY", "sections")  # sections, paragraphs, sentences

    # ==========================================================================
    # RAG Pipeline - Long Context Extension (RLM + Chunk Expansion)
    # ==========================================================================
    # RLM (Recursive Language Models) - arXiv:2512.24601
    # Enables processing documents >50K tokens through recursive decomposition
    rlm_enabled: bool = os.getenv("RLM_ENABLED", "true").lower() == "true"
    rlm_threshold_tokens: int = int(os.getenv("RLM_THRESHOLD_TOKENS", "50000"))  # Activate RLM if context > 50K
    rlm_max_recursion_depth: int = int(os.getenv("RLM_MAX_RECURSION_DEPTH", "5"))  # Max recursion depth
    rlm_chunk_size_tokens: int = int(os.getenv("RLM_CHUNK_SIZE_TOKENS", "8000"))  # Size per sub-call
    # RLM Environment Storage: RAM (default, optimal) vs Redis (fallback for distributed workers)
    # Per paper arXiv:2512.24601 Section 3.2: RAM provides ~1000x lower latency than Redis
    rlm_use_redis: bool = os.getenv("RLM_USE_REDIS", "false").lower() == "true"

    # Chunk Expansion - Include adjacent chunks for context preservation
    rag_chunk_expansion_enabled: bool = os.getenv("RAG_CHUNK_EXPANSION_ENABLED", "true").lower() == "true"
    rag_chunk_expansion_size: int = int(os.getenv("RAG_CHUNK_EXPANSION_SIZE", "1"))  # Chunks before/after

    # Hierarchical Retrieval - Document summaries + detailed chunks
    rag_hierarchical_enabled: bool = os.getenv("RAG_HIERARCHICAL_ENABLED", "true").lower() == "true"
    rag_hierarchical_summary_weight: float = float(os.getenv("RAG_HIERARCHICAL_SUMMARY_WEIGHT", "0.3"))  # Weight for summary in RRF

    # ==========================================================================
    # RAG Pipeline - Hierarchical Structure Parsing
    # ==========================================================================
    # Document Structure Parsing - Builds hierarchical tree from document text
    # Enables structure-aware chunking and bottom-up summary generation
    rag_structure_parsing_enabled: bool = os.getenv("RAG_STRUCTURE_PARSING_ENABLED", "true").lower() == "true"
    rag_max_tree_depth: int = int(os.getenv("RAG_MAX_TREE_DEPTH", "6"))  # Max depth of document tree

    # Bottom-Up Summaries - Generate summaries from leaves to root
    # More accurate than top-down as it preserves full document context
    rag_bottomup_summaries_enabled: bool = os.getenv("RAG_BOTTOMUP_SUMMARIES_ENABLED", "true").lower() == "true"
    rag_summary_min_node_chars: int = int(os.getenv("RAG_SUMMARY_MIN_NODE_CHARS", "200"))  # Min chars for node summary
    rag_summary_max_children_combine: int = int(os.getenv("RAG_SUMMARY_MAX_CHILDREN_COMBINE", "10"))  # Max children summaries to combine

    # ==========================================================================
    # RAG Pipeline - Knowledge Graph (Apache AGE)
    # ==========================================================================
    # Knowledge Graph - Apache AGE (PostgreSQL extension) for persistent graph storage
    # Supports Cypher query language for complex graph traversals
    # Fallback: NetworkX in-memory + Redis (set RAG_GRAPH_USE_AGE=false)
    rag_knowledge_graph_enabled: bool = os.getenv("RAG_KNOWLEDGE_GRAPH_ENABLED", "true").lower() == "true"
    rag_graph_use_age: bool = os.getenv("RAG_GRAPH_USE_AGE", "true").lower() == "true"  # Use Apache AGE backend
    rag_graph_max_neighbors: int = int(os.getenv("RAG_GRAPH_MAX_NEIGHBORS", "10"))  # Max neighbors in traversal
    rag_graph_traversal_depth: int = int(os.getenv("RAG_GRAPH_TRAVERSAL_DEPTH", "2"))  # Cypher path depth
    rag_graph_redis_prefix: str = os.getenv("RAG_GRAPH_REDIS_PREFIX", "kg:")  # Redis key prefix (fallback)
    rag_graph_cache_ttl: int = int(os.getenv("RAG_GRAPH_CACHE_TTL", "3600"))  # Graph cache TTL (seconds)
    rag_graph_min_relationship_strength: float = float(os.getenv("RAG_GRAPH_MIN_RELATIONSHIP_STRENGTH", "0.3"))  # Min strength to store

    # ==========================================================================
    # RAG Pipeline - Dependency Graph (Hierarchical Structure)
    # ==========================================================================
    # Dependency Graph - Document structure (sections, chunks) and their relationships
    # Used for chunk context expansion in hierarchical RAG
    rag_dependency_graph_enabled: bool = os.getenv("RAG_DEPENDENCY_GRAPH_ENABLED", "true").lower() == "true"
    rag_chunk_expansion_adjacent: int = int(os.getenv("RAG_CHUNK_EXPANSION_ADJACENT", "2"))  # Adjacent chunks to include
    rag_include_section_hierarchy: bool = os.getenv("RAG_INCLUDE_SECTION_HIERARCHY", "true").lower() == "true"
    rag_include_chunk_references: bool = os.getenv("RAG_INCLUDE_CHUNK_REFERENCES", "true").lower() == "true"

    # Storage service URL (LEGACY - Use MCP storage server instead)
    storage_service_url: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8003")

    # ==========================================================================
    # MCP (Model Context Protocol) Configuration
    # ==========================================================================
    # MCP enables connecting to external data sources (storage, databases, APIs)
    # through standardized MCP servers. This replaces direct service calls with
    # a unified, extensible protocol.
    #
    # Configuration can be provided via:
    # 1. Environment variables (simple setup)
    # 2. YAML config file (complex multi-server setup)

    # Global MCP settings
    mcp_enabled: bool = os.getenv("MCP_ENABLED", "true").lower() == "true"
    mcp_servers_config: str = os.getenv("MCP_SERVERS_CONFIG", "")  # Path to YAML config
    mcp_connection_timeout: int = int(os.getenv("MCP_CONNECTION_TIMEOUT", "30"))
    mcp_max_connections: int = int(os.getenv("MCP_MAX_CONNECTIONS", "10"))

    # MCP Storage Server (replaces storage-service)
    mcp_storage_enabled: bool = os.getenv("MCP_STORAGE_ENABLED", "true").lower() == "true"
    mcp_storage_url: str = os.getenv("MCP_STORAGE_URL", "http://mcp-storage:8000")

    # MCP REST API Server (external APIs)
    mcp_rest_api_enabled: bool = os.getenv("MCP_REST_API_ENABLED", "false").lower() == "true"
    mcp_rest_api_url: str = os.getenv("MCP_REST_API_URL", "")

    # MCP Database Server (external databases)
    mcp_database_enabled: bool = os.getenv("MCP_DATABASE_ENABLED", "false").lower() == "true"
    mcp_database_url: str = os.getenv("MCP_DATABASE_URL", "")

    # MCP Filesystem Server (NFS/SMB/FTP)
    mcp_filesystem_enabled: bool = os.getenv("MCP_FILESYSTEM_ENABLED", "false").lower() == "true"
    mcp_filesystem_command: str = os.getenv("MCP_FILESYSTEM_COMMAND", "")

    # Main API URL
    api_url: str = os.getenv("API_URL", "http://api:8000")

    # Database (for metadata coordination)
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")

    # Collection naming (tenant isolation)
    collection_prefix: str = "Nexus_"
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
