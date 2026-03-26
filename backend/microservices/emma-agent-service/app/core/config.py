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
    llm_provider: str = os.getenv("LLM_PROVIDER", "sglang").lower()

    @property
    def llm_provider_normalized(self) -> str:
        """Normalize 'vllm' → 'sglang' for backwards compat."""
        return "sglang" if self.llm_provider == "vllm" else self.llm_provider

    # SGLang configuration — Single-Model Dual-Phase (Qwen3.5-9B)
    # One model, two behavioral phases controlled by temperature + thinking:
    # PLANNER phase: temp=0.3, no thinking → fast routing, tool calling, classification
    # CHAT phase: temp=0.6, thinking on → reasoning, synthesis, final responses
    # Runtime: SGLang v0.5.9 | Set SGLANG_DUAL_MODEL=true for separate planner model
    sglang_enabled: bool = os.getenv("SGLANG_ENABLED", os.getenv("VLLM_ENABLED", "true")).lower() == "true"
    sglang_dual_model: bool = os.getenv("SGLANG_DUAL_MODEL", os.getenv("VLLM_DUAL_MODEL", "false")).lower() == "true"

    # Chat model (Qwen3.5-9B) — quality generation
    sglang_base_url: str = os.getenv("SGLANG_BASE_URL", os.getenv("VLLM_BASE_URL", "http://sglang:8000/v1"))
    sglang_model: str = os.getenv("SGLANG_MODEL", os.getenv("VLLM_MODEL", "Qwen/Qwen3.5-9B"))
    sglang_max_tokens: int = int(os.getenv("SGLANG_MAX_TOKENS", os.getenv("VLLM_MAX_TOKENS", "16384")))
    sglang_temperature: float = float(os.getenv("SGLANG_TEMPERATURE", os.getenv("VLLM_TEMPERATURE", "0.6")))
    sglang_enable_thinking: bool = os.getenv("SGLANG_ENABLE_THINKING", os.getenv("VLLM_ENABLE_THINKING", "false")).lower() == "true"
    sglang_thinking_budget: int = int(os.getenv("SGLANG_THINKING_BUDGET", os.getenv("VLLM_THINKING_BUDGET", "4096")))

    # Planner parameters — always used for ModelRole.PLANNER regardless of dual_model
    # dual_model=true: separate SGLang instance at sglang_planner_url
    # dual_model=false: same model, these temp/max_tokens override chat defaults
    sglang_planner_url: str = os.getenv("SGLANG_PLANNER_URL", os.getenv("VLLM_PLANNER_URL", os.getenv("SGLANG_BASE_URL", os.getenv("VLLM_BASE_URL", "http://sglang:8000/v1"))))
    sglang_planner_model: str = os.getenv("SGLANG_PLANNER_MODEL", os.getenv("VLLM_PLANNER_MODEL", os.getenv("SGLANG_MODEL", os.getenv("VLLM_MODEL", "Qwen/Qwen3.5-9B"))))
    sglang_planner_max_tokens: int = int(os.getenv("SGLANG_PLANNER_MAX_TOKENS", os.getenv("VLLM_PLANNER_MAX_TOKENS", "4096")))
    sglang_planner_temperature: float = float(os.getenv("SGLANG_PLANNER_TEMPERATURE", os.getenv("VLLM_PLANNER_TEMPERATURE", "0.3")))

    # LLM Layer (ChatOpenAI) — aliases for backwards compatibility with SGLANG_*/VLLM_* vars
    llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("SGLANG_BASE_URL", os.getenv("VLLM_BASE_URL", "http://sglang:8000/v1")))
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("SGLANG_MODEL", os.getenv("VLLM_MODEL", "Qwen/Qwen3.5-9B")))
    llm_api_key: str = os.getenv("LLM_API_KEY", "not-needed")
    planner_temperature: float = float(os.getenv("PLANNER_TEMPERATURE", "0.3"))
    planner_max_tokens: int = int(os.getenv("PLANNER_MAX_TOKENS", "4096"))
    chat_temperature: float = float(os.getenv("CHAT_TEMPERATURE", "0.6"))
    chat_max_tokens: int = int(os.getenv("CHAT_MAX_TOKENS", "16384"))

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
    llm_fallback_chain: str = os.getenv("LLM_FALLBACK_CHAIN", "sglang,openrouter,openai")

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
    react_max_observe_length: int = int(os.getenv("REACT_MAX_OBSERVE_LENGTH", "5000"))
    react_stuck_detection_window: int = int(os.getenv("REACT_STUCK_DETECTION_WINDOW", "5"))
    react_max_completion_tokens: int = int(os.getenv("REACT_MAX_COMPLETION_TOKENS", "2048"))
    react_tool_timeout_seconds: float = float(os.getenv("REACT_TOOL_TIMEOUT_SECONDS", "60"))
    react_max_history_messages: int = int(os.getenv("REACT_MAX_HISTORY_MESSAGES", "40"))
    react_tool_description_max_chars: int = int(os.getenv("REACT_TOOL_DESCRIPTION_MAX_CHARS", "200"))
    react_global_timeout_seconds: float = float(os.getenv("REACT_GLOBAL_TIMEOUT_SECONDS", "120"))

    # Swarm Agent (parallel sub-agent execution)
    swarm_enabled: bool = os.getenv("SWARM_ENABLED", "false").lower() == "true"
    swarm_max_workers: int = int(os.getenv("SWARM_MAX_WORKERS", "5"))
    swarm_worker_max_steps: int = int(os.getenv("SWARM_WORKER_MAX_STEPS", "2"))
    swarm_worker_timeout_seconds: float = float(os.getenv("SWARM_WORKER_TIMEOUT_SECONDS", "45"))
    swarm_complexity_threshold: int = int(os.getenv("SWARM_COMPLEXITY_THRESHOLD", "3"))

    # SmartSearch — unified multi-store search with graph-enhanced re-ranking
    smart_search_rerank_enabled: bool = os.getenv("SMART_SEARCH_RERANK_ENABLED", "true").lower() == "true"
    smart_search_graph_enabled: bool = os.getenv("SMART_SEARCH_GRAPH_ENABLED", "true").lower() == "true"

    # SmartSearch — Retrieval Intelligence (inline feedback)
    smart_search_feedback_enabled: bool = os.getenv("SMART_SEARCH_FEEDBACK_ENABLED", "true").lower() == "true"

    # GraphRAG — Multi-hop subgraph extraction (Phase 5, replaces flat graph expansion)
    graphrag_enabled: bool = os.getenv("GRAPHRAG_ENABLED", "true").lower() == "true"
    graphrag_max_hops: int = int(os.getenv("GRAPHRAG_MAX_HOPS", "2"))
    graphrag_max_nodes: int = int(os.getenv("GRAPHRAG_MAX_NODES", "30"))
    graphrag_include_legal: bool = os.getenv("GRAPHRAG_INCLUDE_LEGAL", "true").lower() == "true"
    graphrag_token_budget: int = int(os.getenv("GRAPHRAG_TOKEN_BUDGET", "1500"))

    # Graph Context — inject structural context into react_loop system prompt
    graph_context_enabled: bool = os.getenv("GRAPH_CONTEXT_ENABLED", "true").lower() == "true"
    graph_context_summary_enabled: bool = os.getenv("GRAPH_CONTEXT_SUMMARY_ENABLED", "true").lower() == "true"
    graph_context_subgraph_enabled: bool = os.getenv("GRAPH_CONTEXT_SUBGRAPH_ENABLED", "true").lower() == "true"
    graph_context_token_budget: int = int(os.getenv("GRAPH_CONTEXT_TOKEN_BUDGET", "1200"))

    # SmartSearch — Cross-Encoder Reranking (neural, FlashRank CPU)
    smart_search_cross_encoder_enabled: bool = os.getenv("SMART_SEARCH_CROSS_ENCODER_ENABLED", "true").lower() == "true"
    smart_search_cross_encoder_model: str = os.getenv("SMART_SEARCH_CROSS_ENCODER_MODEL", "ms-marco-MultiBERT-L-12")
    smart_search_cross_encoder_weight: float = float(os.getenv("SMART_SEARCH_CROSS_ENCODER_WEIGHT", "0.6"))

    # CRAG Quality Gates — prevent hallucination and premature termination
    react_quality_gate_enabled: bool = os.getenv("REACT_QUALITY_GATE_ENABLED", "true").lower() == "true"

    # Retrieval Guard — post-retrieval quality assessment (anti-hallucination)
    # LOW requires top_score below threshold AND entity mismatch (both must fail)
    retrieval_guard_low_top_score: float = float(os.getenv("RETRIEVAL_GUARD_LOW_TOP_SCORE", "0.25"))

    # Context Compression — compress old tool observations to fit token budget
    react_context_compress_enabled: bool = os.getenv("REACT_CONTEXT_COMPRESS_ENABLED", "true").lower() == "true"
    react_context_compress_threshold: int = int(os.getenv("REACT_CONTEXT_COMPRESS_THRESHOLD", "6000"))
    react_context_compress_preserve_recent: int = int(os.getenv("REACT_CONTEXT_COMPRESS_PRESERVE_RECENT", "2"))

    # Query Clarification — detect ambiguous queries before search
    react_query_clarification_enabled: bool = os.getenv("REACT_QUERY_CLARIFICATION_ENABLED", "true").lower() == "true"

    # Memory Recall — planner scans document memories before retrieval (MemoRAG)
    memory_recall_enabled: bool = os.getenv("MEMORY_RECALL_ENABLED", "true").lower() == "true"
    memory_recall_max_memories: int = int(os.getenv("MEMORY_RECALL_MAX_MEMORIES", "20"))
    memory_recall_max_clue_tokens: int = int(os.getenv("MEMORY_RECALL_MAX_CLUE_TOKENS", "300"))
    memory_recall_fallback_enabled: bool = os.getenv("MEMORY_RECALL_FALLBACK_ENABLED", "true").lower() == "true"

    # MemoRAG — global memory model (delegates to Weaviate)
    memorag_enabled: bool = os.getenv("MEMORAG_ENABLED", "true").lower() == "true"
    memorag_table_name: str = os.getenv("MEMORAG_TABLE_NAME", "memorag_memory")
    memorag_embedding_dim: int = int(os.getenv("MEMORAG_EMBEDDING_DIM", "1024"))
    memorag_memory_version: int = int(os.getenv("MEMORAG_MEMORY_VERSION", "1"))
    memorag_chunk_size: int = int(os.getenv("MEMORAG_CHUNK_SIZE", "1800"))
    memorag_chunk_overlap: int = int(os.getenv("MEMORAG_CHUNK_OVERLAP", "200"))
    memorag_max_chunks: int = int(os.getenv("MEMORAG_MAX_CHUNKS", "50"))
    memorag_min_text_chars: int = int(os.getenv("MEMORAG_MIN_TEXT_CHARS", "200"))
    memorag_recall_top_k: int = int(os.getenv("MEMORAG_RECALL_TOP_K", "20"))
    memorag_embed_text_max_chars: int = int(os.getenv("MEMORAG_EMBED_TEXT_MAX_CHARS", "3000"))
    memorag_embedding_task_document: str = os.getenv("MEMORAG_EMBEDDING_TASK_DOCUMENT", "retrieval.document")
    memorag_embedding_task_query: str = os.getenv("MEMORAG_EMBEDDING_TASK_QUERY", "retrieval.query")
    memorag_keyword_fallback_enabled: bool = os.getenv("MEMORAG_KEYWORD_FALLBACK_ENABLED", "true").lower() == "true"

    # LLM Fallback
    llm_retry_delay_seconds: float = float(os.getenv("LLM_RETRY_DELAY_SECONDS", "0.5"))

    # Agent Fallback Timeouts (factor_agent, writer_agent raw SGLang calls)
    agent_raw_sglang_timeout_seconds: float = float(os.getenv("AGENT_RAW_SGLANG_TIMEOUT_SECONDS", os.getenv("AGENT_RAW_VLLM_TIMEOUT_SECONDS", "60")))

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
    # Prompt Management (Langfuse — Single Source of Truth)
    # ==========================================================================
    # Langfuse is the ONLY prompt source. All prompts must exist in Langfuse.
    # Missing prompts cause PromptNotFoundError (fail-fast).
    # Label pins to promoted versions — prevents draft prompts from going live.
    langfuse_prompt_label: str = os.getenv("LANGFUSE_PROMPT_LABEL", "production")
    # Local cache TTL for Langfuse prompts (seconds)
    langfuse_prompt_cache_ttl: int = int(os.getenv("LANGFUSE_PROMPT_CACHE_TTL", "300"))
    # Enable guardrail validation
    guardrails_enabled: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    # Enable rule engine for dynamic prompt injection
    rule_engine_enabled: bool = os.getenv("RULE_ENGINE_ENABLED", "true").lower() == "true"

    # Main API URL (for auth validation)
    api_url: str = os.getenv("API_URL", "http://api:8000")

    # Knowledge Tree Service (structural context)
    knowledge_tree_service_url: str = os.getenv("KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
    knowledge_tree_service_timeout: int = int(os.getenv("KNOWLEDGE_TREE_SERVICE_TIMEOUT", "30"))

    # Intelligence Docs Service (text extraction for uploaded files)
    text_extraction_service_url: str = os.getenv("TEXT_EXTRACTION_SERVICE_URL", "http://intelligence-docs-service:8000")
    text_extraction_service_timeout: int = int(os.getenv("TEXT_EXTRACTION_SERVICE_TIMEOUT", "60"))

    # Database (for session persistence)
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/nexus_db")

    # LangGraph Checkpointer (PostgresSaver)
    # Enables: conversation continuity, time travel, HITL interrupts
    langgraph_checkpointer_enabled: bool = os.getenv("LANGGRAPH_CHECKPOINTER_ENABLED", "true").lower() == "true"

    # PostgreSQL (graph queries routed via knowledge-tree-service to FalkorDB)
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
    verified_claim_temperature: float = float(os.getenv("VERIFIED_CLAIM_TEMPERATURE", "0.0"))
    verified_duplicate_threshold: float = float(os.getenv("VERIFIED_DUPLICATE_THRESHOLD", "0.65"))
    verified_evidence_excerpt_limit: int = int(os.getenv("VERIFIED_EVIDENCE_EXCERPT_LIMIT", "2000"))
    verified_section_size: int = int(os.getenv("VERIFIED_SECTION_SIZE", "16000"))
    verified_section_overlap: int = int(os.getenv("VERIFIED_SECTION_OVERLAP", "500"))

    # HITL — Human-in-the-Loop review before document assembly
    verified_hitl_enabled: bool = os.getenv("VERIFIED_HITL_ENABLED", "false").lower() == "true"
    verified_hitl_confidence_threshold: float = float(os.getenv("VERIFIED_HITL_CONFIDENCE_THRESHOLD", "0.75"))
    verified_hitl_timeout_seconds: int = int(os.getenv("VERIFIED_HITL_TIMEOUT_SECONDS", "300"))

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

    # ==========================================================================
    # User Memory (cross-session persistent facts)
    # ==========================================================================
    user_memory_enabled: bool = os.getenv("USER_MEMORY_ENABLED", "true").lower() == "true"
    user_memory_llm_extraction: bool = os.getenv("USER_MEMORY_LLM_EXTRACTION", "false").lower() == "true"
    user_memory_max_facts: int = int(os.getenv("USER_MEMORY_MAX_FACTS", "50"))
    user_memory_cache_ttl: int = int(os.getenv("USER_MEMORY_CACHE_TTL", "3600"))

    # ==========================================================================
    # Explanation Generation (humanized reasoning trace)
    # ==========================================================================
    explain_enabled: bool = os.getenv("EXPLAIN_ENABLED", "true").lower() == "true"

    # ==========================================================================
    # Document Generation & Email Tools (ReAct)
    # ==========================================================================
    document_generation_enabled: bool = os.getenv("DOCUMENT_GENERATION_ENABLED", "true").lower() == "true"
    document_forge_enabled: bool = os.getenv("DOCUMENT_FORGE_ENABLED", "true").lower() == "true"
    document_forge_service_url: str = os.getenv("DOCUMENT_FORGE_SERVICE_URL", "http://document-forge-service:8013")
    email_tool_enabled: bool = os.getenv("EMAIL_TOOL_ENABLED", "true").lower() == "true"
    email_max_per_conversation: int = int(os.getenv("EMAIL_MAX_PER_CONVERSATION", "5"))
    generated_doc_ttl_seconds: int = int(os.getenv("GENERATED_DOC_TTL_SECONDS", "3600"))

    # SMTP Configuration (shared with main backend)
    mail_server: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    mail_port: int = int(os.getenv("MAIL_PORT", "465"))
    mail_username: str = os.getenv("MAIL_USERNAME", "")
    mail_password: str = os.getenv("MAIL_PASSWORD", "")
    mail_from: str = os.getenv("MAIL_FROM", "")
    mail_from_name: str = os.getenv("MAIL_FROM_NAME", "NouxCubeIA")
    mail_ssl_tls: bool = os.getenv("MAIL_SSL_TLS", "true").lower() == "true"
    mail_starttls: bool = os.getenv("MAIL_STARTTLS", "false").lower() == "true"

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    request_logging_enabled: bool = os.getenv(
        "REQUEST_LOGGING_ENABLED",
        "true" if DEBUG_DEFAULT else "false"
    ).lower() == "true"

    # Temporary upload handling (non-indexed files)
    upload_tmp_dir: str = os.getenv("EMMA_UPLOAD_TMP_DIR", "/tmp/emma_uploads")
    upload_ttl_seconds: int = int(os.getenv("EMMA_UPLOAD_TTL_SECONDS", "3600"))
    # Hard limit per uploaded file — rejects (not truncates) files exceeding this.
    # 2M chars covers extreme Tika inflation (~10x for PDFs with embedded metadata).
    # The stop-and-go pipeline handles sectioning downstream.
    upload_max_chars_per_doc: int = int(os.getenv("EMMA_UPLOAD_MAX_CHARS_PER_DOC", "2000000"))

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
