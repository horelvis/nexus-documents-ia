"""
LangGraph RAG State Definitions

Shared state for the multi-agent RAG graph using TypedDict.
This enables explicit state management with full type safety.

Key Design Decisions:
1. Use Annotated[List[BaseMessage], add_messages] for conversation history
   - LangGraph's add_messages reducer handles message deduplication
   - Maintains proper conversation threading

2. ACL context is explicit in state
   - tenant_id, user_id, role_ids, is_admin
   - Passed to all nodes for consistent access control

3. Execution plan drives agent routing
   - detected_domains: What domains were found in the query
   - execution_plan: Which agents to invoke (in order)
   - agent_results: Results from each completed agent

References:
- https://langchain-ai.github.io/langgraph/concepts/low_level/#state
- https://langchain-ai.github.io/langgraph/how-tos/state-reducers/
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

# LangGraph's built-in message reducer
# Handles message deduplication and proper ordering
try:
    from langgraph.graph.message import add_messages
except ImportError:
    # Fallback for older versions
    def add_messages(left: list, right: list) -> list:
        """Simple message concatenation fallback."""
        return left + right


# ─── Custom reducers for parallel node execution ─────────────────────────────
def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two dictionaries, with right taking precedence.
    Used for metadata field when parallel nodes both update it.

    Unlike a shallow merge, nested dicts at any depth are merged
    rather than overwritten. This ensures parallel nodes can both
    contribute to nested metadata sections without data loss.
    """
    if left is None:
        return right or {}
    if right is None:
        return left or {}
    result = {**left}
    for key, value in right.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def merge_lists(left: List[Any], right: List[Any]) -> List[Any]:
    """
    Concatenate two lists.
    Used for reasoning_steps when parallel nodes both add steps.
    """
    return (left or []) + (right or [])


class DocumentResult(TypedDict, total=False):
    """Document returned from retrieval."""
    id: str
    title: str
    content: str
    score: float
    metadata: Dict[str, Any]
    collection: str
    chunk_index: Optional[int]


class AgentResult(TypedDict, total=False):
    """Result from a specialist agent."""
    agent: str
    output: str
    tools_used: List[str]
    sources: List[str]
    error: Optional[str]
    latency_ms: float


class RAGState(TypedDict, total=False):
    """
    Shared state for the RAG graph.

    All nodes read from and write to this state.
    The Annotated types with reducers handle merging.

    State Flow:
        1. RETRIEVE: Populates retrieved_docs, doc_scores
        2. PLAN: Populates detected_domains, execution_plan, plan_reasoning
        3. AGENTS: Populates agent_results (each agent adds its result)
        4. SYNTHESIZE: Populates final_answer, sources
    """
    # =========================================================================
    # Conversation State
    # =========================================================================
    # Message history with automatic deduplication
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # The current user query
    query: str

    # Unique thread ID for conversation persistence
    thread_id: str

    # =========================================================================
    # ACL Context (from ExecutionContext)
    # =========================================================================
    # All operations are tenant-scoped
    tenant_id: str

    # Optional user for fine-grained ACL
    user_id: Optional[str]

    # User's role IDs for permission checks
    user_role_ids: Optional[List[str]]

    # Admin bypass flag
    is_admin: bool

    # =========================================================================
    # Retrieval Results
    # =========================================================================
    # Documents retrieved from vector search
    retrieved_docs: List[DocumentResult]

    # Relevance scores for retrieved docs
    doc_scores: List[float]

    # Whether retrieval was skipped (e.g., for conversational queries)
    retrieval_skipped: bool

    # =========================================================================
    # Planning State
    # =========================================================================
    # Domains detected in the query (e.g., ["labor", "fiscal"])
    detected_domains: List[str]

    # Agents to invoke (e.g., ["labor_agent", "fiscal_agent"])
    execution_plan: List[str]

    # LLM's reasoning for the plan
    plan_reasoning: str

    # Whether a fast-path was used (conversational/identity query shortcut)
    fast_path_used: bool

    # Fast-path answer (if fast-path was used)
    fast_path_answer: Optional[str]

    # =========================================================================
    # Reasoning Steps (for UI traceability)
    # =========================================================================
    # Dynamic reasoning steps from plan/agents for Emma chat visibility
    # Each step: {"type": str, "content": str, "confidence": float, "entities": [], ...}
    # Uses merge_lists reducer for parallel node execution (context_tree || graph_expand)
    reasoning_steps: Annotated[List[Dict[str, Any]], merge_lists]

    # =========================================================================
    # Execution State
    # =========================================================================
    # Currently executing agent
    current_agent: str

    # Index of current agent in execution_plan
    current_agent_index: int

    # Results from each completed agent
    agent_results: Dict[str, AgentResult]

    # Errors from failed agents
    agent_errors: Dict[str, str]

    # Retry counter for error recovery
    retry_count: int

    # Maximum retries allowed
    max_retries: int

    # =========================================================================
    # Output State
    # =========================================================================
    # Final synthesized answer
    final_answer: Optional[str]

    # Sources cited in the answer
    sources: List[Dict[str, Any]]

    # Whether execution completed successfully
    success: bool

    # Total latency in milliseconds
    total_latency_ms: float

    # Tokens saved vs naive approach
    tokens_saved: int

    # =========================================================================
    # Knowledge Source Routing
    # =========================================================================
    # Source of knowledge: tenant_documents, public_knowledge, hybrid
    knowledge_source: Optional[str]

    # Confidence in knowledge source classification
    knowledge_source_confidence: float

    # =========================================================================
    # Sector Configuration (Multi-Pipeline RAG)
    # =========================================================================
    # Active sector name (e.g., "legal", "medical", "documental") or None
    sector: Optional[str]

    # Sector config dict (serialized SectorConfig) for use by nodes
    sector_config: Optional[Dict[str, Any]]

    # =========================================================================
    # Graph Expansion (populated by graph_expand, used by retrieve)
    # =========================================================================
    # BOE IDs from graph expansion (QA matches + Cypher results)
    # Used by retrieve to filter PublicKnowledge searches
    expanded_boe_ids: List[str]

    # =========================================================================
    # RLM (Recursive Language Models) State
    # =========================================================================
    # Whether RLM was activated for this query
    rlm_activated: bool

    # Total estimated tokens in retrieved content
    rlm_total_tokens: int

    # Sub-results from recursive chunk processing
    rlm_sub_results: List[Dict[str, Any]]

    # Current recursion depth
    rlm_depth: int

    # RLM intermediate chunks (text chunks for map phase)
    rlm_chunks: List[str]

    # Cache key computed by rlm_plan for use by rlm_reduce
    rlm_cache_key: str

    # Count of relevant chunks after map filtering
    rlm_relevant_count: int

    # =========================================================================
    # Metadata
    # =========================================================================
    # Additional metadata for tracing/debugging
    # Uses merge_dicts reducer for parallel node execution (context_tree || graph_expand)
    metadata: Annotated[Dict[str, Any], merge_dicts]


def create_initial_state(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    conversation_history: Optional[List[BaseMessage]] = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> RAGState:
    """
    Create initial state for a RAG graph execution.

    Args:
        query: User's query
        tenant_id: Tenant ID for ACL
        user_id: Optional user ID for fine-grained ACL
        user_role_ids: Optional list of user role IDs
        is_admin: Whether user is admin (bypasses ACL)
        thread_id: Optional conversation thread ID
        conversation_history: Optional prior conversation messages
        request_context: Optional request context (document_id, attachments, etc.)

    Returns:
        Initialized RAGState ready for graph execution
    """
    # Generate thread ID if not provided
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    # Build initial messages
    messages: List[BaseMessage] = []

    # Add conversation history if provided
    if conversation_history:
        messages.extend(conversation_history)

    # Add current query
    messages.append(HumanMessage(content=query))

    normalized_context = request_context or {}

    # Load active sector config (singleton, cached)
    sector_name = None
    sector_config_dict = None
    try:
        from .sectors import get_active_sector_config
        sc = get_active_sector_config()
        if sc is not None:
            sector_name = sc.sector.value
            sector_config_dict = {
                "name": sc.name,
                "sector": sc.sector.value,
                "agents": sc.agents,
                "default_agent": sc.default_agent,
                "hybrid_alpha": sc.hybrid_alpha,
                "top_k": sc.top_k,
                "rerank_enabled": sc.rerank_enabled,
                "chunk_strategy": sc.chunk_strategy,
                "chunk_size": sc.chunk_size,
                "chunk_overlap": sc.chunk_overlap,
                "entity_patterns": sc.entity_patterns,
                "graph_name": sc.graph_name,
                "graph_schema": sc.graph_schema,
                "system_prompt_key": sc.system_prompt_key,
                "men_domain": sc.men_domain,
            }
    except Exception:
        pass

    return RAGState(
        # Conversation
        messages=messages,
        query=query,
        thread_id=thread_id,

        # ACL Context
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids or [],
        is_admin=is_admin,

        # Retrieval (populated by retrieve node)
        retrieved_docs=[],
        doc_scores=[],
        retrieval_skipped=False,

        # Planning (populated by plan node)
        detected_domains=[],
        execution_plan=[],
        plan_reasoning="",
        fast_path_used=False,
        fast_path_answer=None,
        reasoning_steps=[],

        # Execution
        current_agent="",
        current_agent_index=0,
        agent_results={},
        agent_errors={},
        retry_count=0,
        max_retries=2,

        # Output
        final_answer=None,
        sources=[],
        success=False,
        total_latency_ms=0.0,
        tokens_saved=0,

        # Knowledge Source
        knowledge_source=None,
        knowledge_source_confidence=0.0,

        # Sector
        sector=sector_name,
        sector_config=sector_config_dict,

        # Graph Expansion (populated by graph_expand node)
        expanded_boe_ids=[],

        # RLM
        rlm_activated=False,
        rlm_total_tokens=0,
        rlm_sub_results=[],
        rlm_depth=0,
        rlm_chunks=[],
        rlm_cache_key="",
        rlm_relevant_count=0,

        # Metadata
        metadata={
            "document_id": normalized_context.get("document_id"),
            "indexed_document_ids": normalized_context.get("indexed_document_ids", []),
            "attachment_summary": normalized_context.get("attachment_summary"),
            "uploaded_file_ids": normalized_context.get("uploaded_file_ids", []),
            "uploaded_texts": normalized_context.get("uploaded_texts", []),
            # Social channel mode: enables web search for external queries
            "social_channel_mode": normalized_context.get("social_channel_mode", False),
            # Location context for social channels
            "location": normalized_context.get("location"),
        },
    )


@dataclass
class ExecutionConfig:
    """Configuration for graph execution."""
    # Maximum agents to run in parallel
    max_parallel_agents: int = 3

    # Timeout per agent in seconds
    agent_timeout_seconds: float = 30.0

    # Maximum total execution time
    total_timeout_seconds: float = 120.0

    # Whether to enable SLM fast path
    enable_fast_path: bool = True

    # Whether to enable domain routing
    enable_domain_routing: bool = True

    # Maximum retrieval results
    max_retrieval_results: int = 10

    # Minimum relevance score for retrieval
    min_relevance_score: float = 0.5

    # Whether to include sources in response
    include_sources: bool = True

    # Whether to enable streaming
    enable_streaming: bool = True


# =============================================================================
# ReAct Agent State (new graph — coexists with RAGState via feature flag)
# =============================================================================

class ReActState(TypedDict, total=False):
    """
    Simplified state for the ReAct agent graph.

    Unlike RAGState which has ~40 fields for the static pipeline,
    ReActState lets information flow through messages (tool results)
    rather than explicit state fields. This mirrors the OpenManus
    pattern where the agent's memory IS the conversation history.

    State Flow:
        1. CLASSIFY: Sets fast_path or continues to react_loop
        2. REACT_LOOP: Iterates Think→Act→Observe via messages
        3. SYNTHESIZE: Reads final_answer + sources

    The agent accumulates knowledge through tool call/result messages
    rather than through explicit state fields like retrieved_docs,
    execution_plan, or agent_results.
    """

    # =========================================================================
    # Conversation
    # =========================================================================
    messages: Annotated[Sequence[BaseMessage], add_messages]
    query: str
    thread_id: str

    # =========================================================================
    # ACL Context (same as RAGState)
    # =========================================================================
    tenant_id: str
    user_id: Optional[str]
    user_role_ids: Optional[List[str]]
    is_admin: bool

    # =========================================================================
    # Sector Configuration (same as RAGState)
    # =========================================================================
    sector: Optional[str]
    sector_config: Optional[Dict[str, Any]]

    # =========================================================================
    # ReAct Loop Control
    # =========================================================================
    # Current iteration in the react loop
    current_step: int

    # Maximum iterations before forced exit (safety)
    max_steps: int

    # History of tool calls for observability and stuck detection
    tool_calls_history: List[Dict[str, Any]]

    # Whether the agent has decided to stop (terminate tool called)
    is_complete: bool

    # =========================================================================
    # Fast-path
    # =========================================================================
    fast_path_used: bool
    fast_path_answer: Optional[str]

    # =========================================================================
    # Output
    # =========================================================================
    final_answer: Optional[str]
    sources: List[Dict[str, Any]]
    success: bool

    # =========================================================================
    # Observability
    # =========================================================================
    # Structured reasoning steps (THINKING, TOOL_CALL, OBSERVATION, etc.)
    reasoning_steps: Annotated[List[Dict[str, Any]], merge_lists]

    # Metadata for tracing/debugging (merge-safe for parallel nodes)
    metadata: Annotated[Dict[str, Any], merge_dicts]

    # =========================================================================
    # Features (derived from request context)
    # =========================================================================
    features: Dict[str, bool]

    # =========================================================================
    # User Memory (cross-session persistent facts)
    # =========================================================================
    # Formatted facts injected into system prompt (loaded at state init)
    user_memory: Optional[str]

    # =========================================================================
    # Memory Clues (MemoRAG — planner scans document memories before retrieval)
    # =========================================================================
    # Retrieval hints generated by memory_recall node from document memories.
    # Injected into react_loop system prompt to focus the first search.
    # Format: "Pistas de memoria:\n- doc_id: X — resumen\n- keywords: ..."
    memory_clues: Optional[str]

    # =========================================================================
    # Per-Request LLM Overrides
    # =========================================================================
    # When True, CHAT-role LLM calls include <think> reasoning (UI toggle)
    enable_thinking: Optional[bool]

    # =========================================================================
    # Swarm Control (parallel sub-agent execution)
    # =========================================================================
    # Whether classify decided to use swarm path (multi-faceted query)
    use_swarm: bool

    # Sub-tasks generated by decompose_node (list of task dicts)
    swarm_sub_tasks: List[Dict[str, Any]]

    # Current worker's assigned task (set per-worker via Send)
    swarm_current_task: Optional[Dict[str, Any]]

    # Current worker's ID (set per-worker via Send)
    swarm_worker_id: Optional[int]

    # Accumulated results from all workers (merge_lists reducer)
    swarm_worker_results: Annotated[List[Dict[str, Any]], merge_lists]

    # SSE events from swarm nodes (merge_lists reducer for streaming)
    swarm_pending_events: Annotated[List[Dict[str, Any]], merge_lists]


async def create_initial_react_state(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    conversation_history: Optional[List[BaseMessage]] = None,
    request_context: Optional[Dict[str, Any]] = None,
    max_steps: int = 10,
    enable_thinking: Optional[bool] = None,
) -> ReActState:
    """Create initial state for the ReAct graph.

    When PostgresSaver checkpointer is active, only the new HumanMessage is
    included in ``messages``.  The checkpointer automatically restores previous
    messages from its checkpoint, and ``add_messages`` appends the new one.
    ``conversation_history`` is accepted for backwards-compatibility (non-
    checkpointed callers like RAGState, verified-generation, predictive) but
    ignored when the checkpointer is enabled.

    Control fields (``current_step``, ``is_complete``, etc.) use LastValue
    (TypedDict default) so they are **overwritten** each invocation — no stale
    state leaks across turns.

    Args:
        query: User's query
        tenant_id: Tenant ID for ACL
        user_id: Optional user ID
        user_role_ids: Optional role IDs
        is_admin: Admin bypass flag
        thread_id: Conversation thread ID
        conversation_history: Prior conversation messages (ignored when checkpointer active)
        request_context: Request context (document_id, social_channel_mode, etc.)
        max_steps: Maximum ReAct iterations (default: 10)
        enable_thinking: Per-request thinking override from UI deep_reasoning toggle

    Returns:
        Initialized ReActState
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    # When PostgresSaver is active the checkpointer restores previous messages
    # from its checkpoint — we only need the NEW HumanMessage here.
    # conversation_history is only used when no checkpointer is available
    # (fallback mode, or non-ReAct callers like RAGState).
    from app.core.config import settings as _cfg
    use_checkpointer = _cfg.langgraph_checkpointer_enabled

    messages: List[BaseMessage] = []
    if not use_checkpointer and conversation_history:
        messages.extend(conversation_history)
    messages.append(HumanMessage(content=query))

    normalized_context = request_context or {}

    # Load active sector
    sector_name = None
    sector_config_dict = None
    try:
        from .sectors import get_active_sector_config
        sc = get_active_sector_config()
        if sc is not None:
            sector_name = sc.sector.value
            sector_config_dict = {
                "name": sc.name,
                "sector": sc.sector.value,
                "agents": sc.agents,
                "default_agent": sc.default_agent,
                "hybrid_alpha": sc.hybrid_alpha,
                "top_k": sc.top_k,
                "rerank_enabled": sc.rerank_enabled,
                "chunk_strategy": sc.chunk_strategy,
                "system_prompt_key": sc.system_prompt_key,
            }
    except Exception:
        pass

    # Derive features from context and environment
    from app.core.config import settings as _settings
    features = {
        "web_search_enabled": normalized_context.get("social_channel_mode", False)
            or bool(normalized_context.get("web_search_enabled")),
        "connectors_enabled": bool(normalized_context.get("connectors_enabled")),
        "social_channel_mode": normalized_context.get("social_channel_mode", False),
        "document_generation_enabled": _settings.document_generation_enabled,
        "email_enabled": _settings.email_tool_enabled,
    }

    # Load persistent user memory (cross-session facts)
    user_memory = ""
    if user_id:
        try:
            from app.services.memory.user_facts import get_user_facts_service
            facts_service = get_user_facts_service()
            user_memory = await facts_service.format_facts_for_prompt(tenant_id, user_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"User memory load skipped: {e}")

    return ReActState(
        # Conversation
        messages=messages,
        query=query,
        thread_id=thread_id,

        # ACL
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids or [],
        is_admin=is_admin,

        # Sector
        sector=sector_name,
        sector_config=sector_config_dict,

        # ReAct control
        current_step=0,
        max_steps=max_steps,
        tool_calls_history=[],
        is_complete=False,

        # Fast-path
        fast_path_used=False,
        fast_path_answer=None,

        # Output
        final_answer=None,
        sources=[],
        success=False,

        # Observability
        reasoning_steps=[],
        metadata={
            "document_id": normalized_context.get("document_id"),
            "indexed_document_ids": normalized_context.get("indexed_document_ids", []),
            "social_channel_mode": normalized_context.get("social_channel_mode", False),
            "location": normalized_context.get("location"),
            "user_name": normalized_context.get("user_name"),
        },

        # Features
        features=features,

        # User Memory
        user_memory=user_memory or None,

        # Memory Clues (populated by memory_recall node)
        memory_clues=None,

        # Per-request LLM overrides
        enable_thinking=enable_thinking,

        # Swarm
        use_swarm=False,
        swarm_sub_tasks=[],
        swarm_current_task=None,
        swarm_worker_id=None,
        swarm_worker_results=[],
        swarm_pending_events=[],
    )
