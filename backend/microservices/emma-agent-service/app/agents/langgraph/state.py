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
    reasoning_steps: List[Dict[str, Any]]

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
    # Metadata
    # =========================================================================
    # Additional metadata for tracing/debugging
    metadata: Dict[str, Any]


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

        # Metadata
        metadata={
            "document_id": normalized_context.get("document_id"),
            "indexed_document_ids": normalized_context.get("indexed_document_ids", []),
            "attachment_summary": normalized_context.get("attachment_summary"),
            "uploaded_file_ids": normalized_context.get("uploaded_file_ids", []),
            "uploaded_texts": normalized_context.get("uploaded_texts", []),
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
