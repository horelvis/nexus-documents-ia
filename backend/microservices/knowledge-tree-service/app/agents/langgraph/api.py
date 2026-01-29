"""
LangGraph RAG API Integration

API layer for executing LangGraph-based RAG queries.
Can be integrated into existing Emma endpoints via feature flag.

Usage:
    from app.agents.langgraph.api import execute_langgraph_query, is_langgraph_enabled

    if is_langgraph_enabled():
        result = await execute_langgraph_query(query, tenant_id, user_id)
    else:
        result = await emma.execute(query, context)

Feature Flag: LANGGRAPH_RAG_ENABLED (default: false)

Migration Strategy:
1. Set LANGGRAPH_RAG_ENABLED=true to route to LangGraph
2. Monitor performance and errors
3. Gradually roll out by tenant
4. Eventually make LangGraph the default
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import BaseModel, Field

from .graph import execute_rag_query, get_rag_graph
from .state import RAGState, ExecutionConfig, create_initial_state

logger = logging.getLogger(__name__)


# =============================================================================
# Feature Flags
# =============================================================================

def is_langgraph_enabled() -> bool:
    """
    Check if LangGraph RAG is enabled.

    Controlled via environment variable LANGGRAPH_RAG_ENABLED.
    Defaults to false for backward compatibility.
    """
    return os.getenv("LANGGRAPH_RAG_ENABLED", "false").lower() == "true"


def get_langgraph_tenants() -> List[str]:
    """
    Get list of tenant IDs with LangGraph enabled.

    For gradual rollout, specific tenants can be whitelisted.
    Set LANGGRAPH_TENANTS="tenant-1,tenant-2" to enable for specific tenants.
    Set LANGGRAPH_TENANTS="*" to enable for all tenants (same as LANGGRAPH_RAG_ENABLED=true).
    """
    tenants = os.getenv("LANGGRAPH_TENANTS", "")
    if not tenants or tenants == "*":
        return []  # Empty means check global flag
    return [t.strip() for t in tenants.split(",") if t.strip()]


def is_langgraph_enabled_for_tenant(tenant_id: str) -> bool:
    """
    Check if LangGraph is enabled for a specific tenant.

    Allows gradual rollout by tenant.
    """
    # Check global flag first
    if is_langgraph_enabled():
        return True

    # Check tenant-specific whitelist
    whitelisted = get_langgraph_tenants()
    if whitelisted and tenant_id in whitelisted:
        return True

    return False


# =============================================================================
# Request/Response Models
# =============================================================================

class LangGraphQueryRequest(BaseModel):
    """Request for LangGraph RAG query."""
    query: str = Field(..., description="User's natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: Optional[str] = Field(None, description="User identifier for ACL")
    user_role_ids: Optional[List[str]] = Field(None, description="User role IDs for ACL")
    is_admin: bool = Field(False, description="Admin bypass for ACL")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "¿Qué documentos sobre RGPD tengo?",
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "thread_id": "thread-789",
            }
        }


class LangGraphQueryResponse(BaseModel):
    """Response from LangGraph RAG query."""
    success: bool
    answer: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    thread_id: str
    agents_used: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    slm_fast_path: bool = False
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "Encontré 3 documentos relacionados con RGPD...",
                "sources": [{"title": "Política RGPD", "id": "doc-123"}],
                "thread_id": "thread-789",
                "agents_used": ["privacy_agent"],
                "domains": ["privacy"],
                "slm_fast_path": False,
                "latency_ms": 1250.5,
            }
        }


# =============================================================================
# API Functions
# =============================================================================

async def execute_langgraph_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    config: Optional[ExecutionConfig] = None,
) -> LangGraphQueryResponse:
    """
    Execute a RAG query using LangGraph.

    This is the main API function for executing queries.
    Can be called directly or integrated into Emma v2 endpoints.

    Args:
        query: User's natural language query
        tenant_id: Tenant ID for ACL isolation
        user_id: Optional user ID for fine-grained ACL
        user_role_ids: Optional role IDs for permission checks
        is_admin: Admin bypass flag
        thread_id: Optional conversation thread ID
        config: Optional execution configuration

    Returns:
        LangGraphQueryResponse with answer, sources, and metadata

    Example:
        >>> response = await execute_langgraph_query(
        ...     query="¿Qué contratos tienen cláusula RGPD?",
        ...     tenant_id="tenant-123",
        ...     user_id="user-456",
        ... )
        >>> print(response.answer)
    """
    start_time = time.time()

    # Generate thread ID if not provided
    if not thread_id:
        thread_id = str(uuid.uuid4())

    logger.info(
        f"🚀 LangGraph query: tenant={tenant_id}, "
        f"thread={thread_id[:8]}..., query='{query[:50]}...'"
    )

    try:
        # Execute via graph
        result = await execute_rag_query(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            thread_id=thread_id,
            config=config,
        )

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"✅ LangGraph query completed: success={result.get('success')}, "
            f"agents={result.get('agents_used', [])}, latency={latency_ms:.1f}ms"
        )

        return LangGraphQueryResponse(
            success=result.get("success", False),
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            thread_id=result.get("thread_id", thread_id),
            agents_used=result.get("agents_used", []),
            domains=result.get("domains", []),
            slm_fast_path=result.get("slm_fast_path", False),
            latency_ms=latency_ms,
            metadata=result.get("metadata", {}),
        )

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ LangGraph query failed: {e}")

        return LangGraphQueryResponse(
            success=False,
            answer=f"Error processing query: {str(e)}",
            sources=[],
            thread_id=thread_id,
            agents_used=[],
            domains=[],
            slm_fast_path=False,
            latency_ms=latency_ms,
            metadata={"error": str(e)},
        )


async def stream_langgraph_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream a RAG query execution using LangGraph.

    Yields events as the graph executes, allowing real-time
    progress updates to the frontend.

    Event Types:
        - started: Query execution started
        - retrieve_complete: Document retrieval finished
        - plan_complete: Execution plan created
        - structural_step: Reasoning step during structural query (traceability)
        - agent_started: Agent started execution
        - agent_complete: Agent finished execution
        - synthesize_started: Synthesis started
        - complete: Final answer ready
        - error: Error occurred

    Args:
        query: User's query
        tenant_id: Tenant ID
        user_id: Optional user ID
        user_role_ids: Optional role IDs
        is_admin: Admin flag
        thread_id: Optional thread ID

    Yields:
        Event dictionaries with type and data

    Example:
        >>> async for event in stream_langgraph_query(query, tenant_id):
        ...     if event["type"] == "complete":
        ...         print(event["data"]["answer"])
    """
    start_time = time.time()
    thread_id = thread_id or str(uuid.uuid4())

    # Validate tenant_id to prevent Weaviate schema errors
    if not tenant_id or not tenant_id.strip():
        logger.error("❌ tenant_id is required for streaming query")
        yield {
            "type": "error",
            "data": {
                "error": "tenant_id is required",
                "thread_id": thread_id,
            }
        }
        return

    yield {
        "type": "started",
        "data": {
            "thread_id": thread_id,
            "query": query,
        }
    }

    # Track emitted events to avoid duplicates
    # LangGraph's stream_mode="values" emits cumulative state after each node
    emitted_events = {
        "retrieve_complete": False,
        "plan_complete": False,
        "agents_started": set(),  # Track which agents we've sent started events for
        "agents_completed": set(),  # Track which agents we've sent completed events for
        "reasoning_steps_emitted": set(),  # Track emitted step hashes
    }

    try:
        # Create initial state
        initial_state = create_initial_state(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            thread_id=thread_id,
        )

        # Get graph
        graph = get_rag_graph()

        # Stream execution
        config = {"configurable": {"thread_id": thread_id}}

        # Use astream_events for detailed progress
        async for event in graph.astream(initial_state, config, stream_mode="values"):
            # Emit retrieve_complete only once
            if not emitted_events["retrieve_complete"] and "retrieved_docs" in event and event.get("retrieved_docs"):
                emitted_events["retrieve_complete"] = True
                yield {
                    "type": "retrieve_complete",
                    "data": {
                        "doc_count": len(event["retrieved_docs"]),
                    }
                }

            # Emit plan_complete only once
            if not emitted_events["plan_complete"] and "execution_plan" in event and event.get("execution_plan"):
                emitted_events["plan_complete"] = True

                # Emit all reasoning steps from the plan node (deduplicated)
                reasoning_steps = event.get("reasoning_steps", [])
                for step in reasoning_steps:
                    step_hash = hash((step.get("type", ""), step.get("content", "")))
                    if step_hash not in emitted_events["reasoning_steps_emitted"]:
                        emitted_events["reasoning_steps_emitted"].add(step_hash)
                        yield {
                            "type": "structural_step",
                            "data": {
                                "step_type": step.get("type", "reasoning"),
                                "content": step.get("content", ""),
                                "confidence": step.get("confidence", 1.0),
                                "entities": step.get("entities", []),
                            }
                        }

                metadata = event.get("metadata", {})
                yield {
                    "type": "plan_complete",
                    "data": {
                        "domains": event.get("detected_domains", []),
                        "agents": event.get("execution_plan", []),
                        "reasoning": event.get("plan_reasoning", ""),
                        "is_structural": metadata.get("is_structural_query", False),
                    }
                }

            # Emit agent_started only once per agent
            if "current_agent" in event and event.get("current_agent"):
                agent = event["current_agent"]
                if agent not in emitted_events["agents_started"]:
                    emitted_events["agents_started"].add(agent)
                    yield {
                        "type": "agent_started",
                        "data": {
                            "agent": agent,
                        }
                    }

            # Emit agent_complete only once per agent
            if "agent_results" in event:
                for agent, result in event.get("agent_results", {}).items():
                    if agent not in emitted_events["agents_completed"]:
                        emitted_events["agents_completed"].add(agent)

                        # Emit structural reasoning steps if available (deduplicated)
                        if isinstance(result, dict) and result.get("reasoning_steps"):
                            for step in result["reasoning_steps"]:
                                step_hash = hash((step.get("type", ""), step.get("content", "")))
                                if step_hash not in emitted_events["reasoning_steps_emitted"]:
                                    emitted_events["reasoning_steps_emitted"].add(step_hash)
                                    yield {
                                        "type": "structural_step",
                                        "data": {
                                            "step_type": step.get("type", "reasoning"),
                                            "content": step.get("content", ""),
                                            "entities": step.get("entities", []),
                                            "confidence": step.get("confidence", 1.0),
                                        }
                                    }

                        yield {
                            "type": "agent_complete",
                            "data": {
                                "agent": agent,
                                "tools_used": result.get("tools_used", []) if isinstance(result, dict) else [],
                            }
                        }

            # Emit complete only once (when final_answer appears)
            if "final_answer" in event and event.get("final_answer"):
                latency_ms = (time.time() - start_time) * 1000
                final_answer = event["final_answer"]

                # Stream the answer as tokens before sending complete
                # This provides real-time text streaming to the frontend
                words = final_answer.split(' ')
                for i, word in enumerate(words):
                    # Add space before word (except first)
                    token = f" {word}" if i > 0 else word
                    yield {
                        "type": "token",
                        "data": {
                            "text": token,
                            "token": token,
                        }
                    }
                    # Small delay for visual effect (non-blocking)
                    await asyncio.sleep(0.02)

                # Now emit complete (answer already streamed via tokens)
                yield {
                    "type": "complete",
                    "data": {
                        "success": event.get("success", True),
                        "answer": final_answer,
                        "sources": event.get("sources", []),
                        "thread_id": thread_id,
                        "agents_used": list(event.get("agent_results", {}).keys()),
                        "domains": event.get("detected_domains", []),
                        "latency_ms": latency_ms,
                    }
                }
                # Break after complete to avoid any further duplicate processing
                break

    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield {
            "type": "error",
            "data": {
                "error": str(e),
                "thread_id": thread_id,
            }
        }


# =============================================================================
# Integration Helper
# =============================================================================

async def maybe_use_langgraph(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    **kwargs,
) -> Optional[LangGraphQueryResponse]:
    """
    Try to use LangGraph if enabled, otherwise return None.

    This helper allows gradual migration from Emma to LangGraph.
    If LangGraph is not enabled for this tenant, returns None
    so the caller can fall back to Emma.

    Usage in Emma endpoints:
        langgraph_result = await maybe_use_langgraph(query, tenant_id, user_id)
        if langgraph_result:
            return langgraph_result
        # Fall back to Emma
        return await emma.execute(query, context)

    Args:
        query: User's query
        tenant_id: Tenant ID
        user_id: Optional user ID
        thread_id: Optional thread ID
        **kwargs: Additional arguments passed to execute_langgraph_query

    Returns:
        LangGraphQueryResponse if LangGraph is enabled, None otherwise
    """
    if not is_langgraph_enabled_for_tenant(tenant_id):
        return None

    logger.info(f"🔀 Using LangGraph for tenant {tenant_id}")

    return await execute_langgraph_query(
        query=query,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=thread_id,
        **kwargs,
    )
