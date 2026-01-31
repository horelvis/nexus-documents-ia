"""
Emma API Endpoints

Main API endpoints for Emma AI assistant.

Endpoints:
- POST /emma/query - Execute query (non-streaming)
- POST /emma/query/stream - Execute query with SSE streaming
- GET /emma/tools - List available tools
- GET /emma/health - Health check
- GET /emma/sessions - List conversation sessions
- POST /emma/sessions/{id}/continue - Continue a session
- PATCH /emma/sessions/{id} - Update session metadata
- DELETE /emma/sessions/{id} - Delete a session

Architecture:
- Uses Emma agent with SIL fast path and domain routing
- LangGraph integration available via LANGGRAPH_RAG_ENABLED flag
- Session persistence in PostgreSQL + Redis cache
"""

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.langfuse_config import (
    flush_langfuse,
    langfuse_context,
    score_emma_result,
    trace_context,
    trace_emma_query,
)
from app.core.security import verify_api_key
from app.agents.emma import (
    Emma,
    EmmaConfig,
    EmmaResult,
    ExecutionContext,
    get_emma,
    MAX_AGENTIC_ITERATIONS,
)
from app.agents.emma_tools import EMMA_TOOLS, get_emma_tools
from app.services.emma_persistence_service import get_emma_persistence_service
from app.schemas.emma import (
    EmmaSessionListResponse,
    EmmaSessionResponse,
    EmmaSessionUpdate,
    EmmaContinueSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Emma"])

FAST_MAX_ITERATIONS = 3


def _generate_contextual_suggestions(
    query: str,
    response: str,
    tools_used: List[str]
) -> List[str]:
    """
    Generate contextual suggestions based on query, response and tools used.

    These suggestions help guide the user to relevant follow-up questions.
    """
    query_lower = query.lower()
    response_lower = response.lower()

    # If tools found documents, suggest follow-ups
    if tools_used and any("search" in t.lower() or "analyze" in t.lower() for t in tools_used):
        if "no se encontraron" not in response_lower and "no encontré" not in response_lower:
            return [
                "¿Puedes resumir los puntos clave?",
                "¿Qué riesgos identificas?",
                "Muestra más detalles",
            ]

    # Contract-related
    if "contrato" in query_lower or "contract" in query_lower:
        return [
            "¿Cuáles son las cláusulas importantes?",
            "Identifica los riesgos",
            "¿Cuándo vence?",
        ]

    # Count/list queries
    if any(word in query_lower for word in ["cuántos", "cuantos", "lista", "listar"]):
        return [
            "Muestra los más recientes",
            "¿Cuáles requieren atención?",
            "Dame más detalles de uno",
        ]

    # Analysis queries
    if any(word in query_lower for word in ["analiza", "revisa", "verifica", "evalúa"]):
        return [
            "¿Qué acciones recomiendas?",
            "Explica los riesgos",
            "¿Cumple con la normativa?",
        ]

    # If no documents found
    if "no se encontraron" in response_lower or "no encontré" in response_lower:
        return [
            "Buscar con otros términos",
            "¿Qué documentos tengo?",
            "Ayúdame a reformular",
        ]

    # Greeting/intro - suggest getting started
    if any(word in query_lower for word in ["hola", "me llamo", "buenos días", "buenas"]):
        return [
            "¿Cuántos documentos tengo?",
            "Muestra mis contratos",
            "¿Qué puedes hacer?",
        ]

    # Default suggestions
    return [
        "¿Puedes explicar más?",
        "Muestra documentos relacionados",
        "¿Qué más puedo preguntar?",
    ]


# =============================================================================
# Request/Response Models
# =============================================================================

class EmmaQuery(BaseModel):
    """Query request for Emma."""
    query: str = Field(..., description="User's natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    user_role_ids: Optional[List[str]] = Field(None, description="User role IDs for ACL filtering")
    is_admin: bool = Field(False, description="Whether user is admin (bypasses ACL)")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID for history")
    session_id: Optional[str] = Field(None, description="Session ID (alias for thread_id)")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context (document_id, indexed_document_ids, attachments)")
    enable_sil: bool = Field(True, description="Enable SIL fast path for structural queries")
    enable_domain_routing: bool = Field(True, description="Enable domain-specific prompts")
    enable_streaming: bool = Field(False, description="Enable streaming (use /stream endpoint instead)")
    deep_reasoning: bool = Field(default=True, description="Enable deep reasoning mode (slower but more thorough)")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "¿Cuántos contratos laborales tengo?",
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "thread_id": "thread-789",
                "enable_sil": True,
            }
        }


class EmmaQueryResponse(BaseModel):
    """Response from Emma."""
    success: bool
    answer: str
    domain: str = "general"
    tools_called: List[str] = Field(default_factory=list)
    iterations: int = 0
    sil_answered: bool = False
    tokens_saved: int = 0
    latency_ms: float = 0.0
    thread_id: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "Tienes 5 contratos laborales.",
                "domain": "labor",
                "tools_called": [],
                "iterations": 0,
                "sil_answered": True,
                "tokens_saved": 2500,
                "latency_ms": 45.2,
                "thread_id": "thread-789",
            }
        }


class ToolInfo(BaseModel):
    """Information about a tool."""
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolsResponse(BaseModel):
    """Response listing available tools."""
    tools: List[ToolInfo]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "2.0"
    llm_connected: bool
    sil_enabled: bool
    features: Dict[str, Any]
    orchestration: Optional[str] = None


# =============================================================================
# Feature Flag
# =============================================================================

def is_emma_enabled() -> bool:
    """Check if Emma is enabled."""
    # Can be controlled via environment variable
    import os
    return os.getenv("EMMA_ENABLED", "true").lower() == "true"


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/query", response_model=EmmaQueryResponse)
async def emma_query(
    query: EmmaQuery,
    _: bool = Depends(verify_api_key),
):
    """
    Execute a query with Emma or LangGraph (if enabled).

    This endpoint routes to:
    - LangGraph multi-agent RAG (if LANGGRAPH_RAG_ENABLED=true)
    - Emma architecture (default):
      1. SIL fast path for structural queries (70-90% token savings)
      2. Domain-specific dynamic prompts
      3. Native async LLM client
      4. Consolidated tool set (6 tools)

    Use thread_id to maintain conversation context across requests.
    """
    if not is_emma_enabled():
        raise HTTPException(
            status_code=503,
            detail="Emma is not enabled. Set EMMA_ENABLED=true",
        )

    # Build context
    thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

    # Extend TTL and restore document context from previous session
    try:
        persistence = get_emma_persistence_service()
        await persistence.touch_session(thread_id, query.tenant_id)
        session = await persistence.get_session(thread_id)
        if session:
            saved_ctx = (session.get("metadata") or {}).get("document_context")
            if saved_ctx:
                ctx = query.context or {}
                for key in ("document_id", "uploaded_file_ids", "indexed_document_ids"):
                    if not ctx.get(key) and saved_ctx.get(key):
                        ctx[key] = saved_ctx[key]
                query.context = ctx
    except Exception as e:
        logger.warning(f"Failed to restore session context for {thread_id}: {e}")

    # Check if LangGraph is enabled for this tenant
    from app.agents.langgraph import is_langgraph_enabled_for_tenant, execute_langgraph_query

    if is_langgraph_enabled_for_tenant(query.tenant_id):
        logger.info(f"🔀 LangGraph enabled for tenant {query.tenant_id}, routing to LangGraph")
        try:
            langgraph_result = await execute_langgraph_query(
                query=query.query,
                tenant_id=query.tenant_id,
                user_id=query.user_id,
                user_role_ids=query.user_role_ids,
                is_admin=query.is_admin,
                thread_id=thread_id,
                context=query.context,
            )

            return EmmaQueryResponse(
                success=langgraph_result.success,
                answer=langgraph_result.answer,
                domain="general",  # LangGraph handles domains internally
                tools_called=langgraph_result.agents_used,
                iterations=len(langgraph_result.agents_used),
                sil_answered=langgraph_result.fast_path,
                tokens_saved=0,
                latency_ms=langgraph_result.latency_ms,
                thread_id=langgraph_result.thread_id,
                metadata={
                    "langgraph": True,
                    "domains": langgraph_result.domains,
                    **langgraph_result.metadata,
                },
            )
        except Exception as e:
            logger.error(f"LangGraph query failed, falling back to Emma: {e}")
            # Fall through to Emma

    # Create Langfuse trace for this query
    with trace_context(
        name="emma.query",
        session_id=thread_id,
        user_id=query.user_id,
        metadata={
            "tenant_id": query.tenant_id,
            "sil_enabled": query.enable_sil,
            "domain_routing_enabled": query.enable_domain_routing,
        },
        input={"query": query.query},
        tags=["emma", "api"],
    ) as trace:
        try:
            emma = await get_emma()

            context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=query.user_id,
                role_ids=query.user_role_ids or [],
                is_admin=query.is_admin,
                thread_id=thread_id,
            )

            # Configure Emma based on request
            emma.config.enable_domain_routing = query.enable_domain_routing
            emma.config.enable_thinking = query.deep_reasoning
            emma.config.max_iterations = (
                MAX_AGENTIC_ITERATIONS if query.deep_reasoning else FAST_MAX_ITERATIONS
            )
            emma.config.enable_thinking = query.deep_reasoning
            emma.config.max_iterations = (
                MAX_AGENTIC_ITERATIONS if query.deep_reasoning else FAST_MAX_ITERATIONS
            )

            # Execute query
            result = await emma.execute(query.query, context)

            # Update trace with output
            if trace:
                trace.update(
                    output={
                        "answer": result.answer[:500] + "..." if len(result.answer) > 500 else result.answer,
                        "domain": result.domain.value,
                        "sil_answered": result.sil_answered,
                    }
                )

            return EmmaQueryResponse(
                success=result.success,
                answer=result.answer,
                domain=result.domain.value,
                tools_called=result.tools_called,
                iterations=result.iterations,
                sil_answered=result.sil_answered,
                tokens_saved=result.tokens_saved,
                latency_ms=result.latency_ms,
                thread_id=result.thread_id,
                metadata=result.metadata,
            )

        except Exception as e:
            logger.error(f"Emma query error: {e}", exc_info=True)
            if trace:
                trace.update(level="ERROR", status_message=str(e))
            raise HTTPException(status_code=500, detail=str(e))


async def _generate_langgraph_sse(
    query: EmmaQuery,
    stream_func,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events from LangGraph streaming.

    Transforms LangGraph events to frontend-expected format with
    reasoning step visibility for structural queries.

    Event mappings:
    - started → start
    - retrieve_complete → progress (stage='retrieval')
    - plan_complete → slm_plan (with reasoning steps)
    - agent_started → delegation
    - agent_complete → step_complete
    - structural_step → slm_thinking (reasoning steps)
    - complete → complete
    - error → error
    """
    thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

    try:
        step_counter = 0
        first_token_sent = False
        conversation_history = None
        try:
            persistence = get_emma_persistence_service()
            # Extend TTL for active session
            await persistence.touch_session(thread_id, query.tenant_id)
            session = await persistence.get_session(thread_id)
            if session and session.get("messages"):
                conversation_history = session.get("messages")
            # Restore document context from previous session into current query
            if session:
                saved_ctx = (session.get("metadata") or {}).get("document_context")
                if saved_ctx:
                    ctx = query.context or {}
                    for key in ("document_id", "uploaded_file_ids", "indexed_document_ids"):
                        if not ctx.get(key) and saved_ctx.get(key):
                            ctx[key] = saved_ctx[key]
                    query.context = ctx
        except Exception as e:
            logger.warning(f"Failed to load conversation history for {thread_id}: {e}")

        async for event in stream_func(
            query=query.query,
            tenant_id=query.tenant_id,
            user_id=query.user_id,
            thread_id=thread_id,
            conversation_history=conversation_history,
            context=query.context,
        ):
            event_type = event.get("type", "")
            data = event.get("data", {})

            if event_type == "started":
                yield f"event: start\ndata: {json.dumps({'message': 'Iniciando análisis con LangGraph...', 'progress': 0, 'thread_id': data.get('thread_id')})}\n\n"

            elif event_type == "retrieve_complete":
                doc_count = data.get("doc_count", 0)
                step_counter += 1
                yield f"event: slm_thinking\ndata: {json.dumps({'step': step_counter, 'type': 'retrieval', 'content': f'Documentos recuperados: {doc_count}', 'slmIsThinking': True})}\n\n"
                yield f"event: progress\ndata: {json.dumps({'message': f'Recuperados {doc_count} documentos', 'stage': 'retrieval', 'progress': 20})}\n\n"

            elif event_type == "plan_complete":
                domains = data.get("domains", [])
                agents = data.get("agents", [])
                reasoning = data.get("reasoning", "")

                # Emit reasoning steps for traceability
                step_counter += 1
                yield f"event: slm_thinking\ndata: {json.dumps({'step': step_counter, 'type': 'domain_detection', 'content': f'Dominios detectados: {", ".join(domains)}', 'confidence': 1.0, 'slmIsThinking': True})}\n\n"

                step_counter += 1
                yield f"event: slm_thinking\ndata: {json.dumps({'step': step_counter, 'type': 'agent_selection', 'content': f'Agentes seleccionados: {", ".join(agents)}', 'slmIsThinking': True})}\n\n"

                # Emit plan ready
                yield f"event: slm_plan\ndata: {json.dumps({'stage': 'slm_plan_ready', 'slmIsThinking': False, 'slmPlan': {'route': 'MULTI_AGENT' if len(agents) > 1 else agents[0] if agents else 'general_agent', 'confidence': 0.9, 'agents': agents, 'domains': domains, 'reasoning': reasoning}})}\n\n"
                yield f"event: progress\ndata: {json.dumps({'message': f'Plan: {reasoning}', 'stage': 'planning', 'progress': 30})}\n\n"

            elif event_type == "agent_started":
                agent_name = data.get("agent", "unknown")
                agent_display = {
                    "general_agent": "Agente General",
                    "privacy_agent": "Agente de Privacidad",
                    "legal_agent": "Agente Legal",
                    "labor_agent": "Agente Laboral",
                    "fiscal_agent": "Agente Fiscal",
                    "contract_agent": "Agente de Contratos",
                }.get(agent_name, agent_name)

                step_counter += 1
                yield f"event: slm_thinking\ndata: {json.dumps({'step': step_counter, 'type': 'agent_execution', 'content': f'Ejecutando {agent_display}...', 'slmIsThinking': True})}\n\n"

            elif event_type == "structural_step":
                # Reasoning step from structural query tool
                step_counter += 1
                yield f"event: slm_thinking\ndata: {json.dumps({'step': step_counter, 'type': data.get('step_type', 'structural'), 'content': data.get('content', ''), 'slmIsThinking': True, 'slmThinkingStep': {'step': step_counter, 'type': data.get('step_type'), 'content': data.get('content'), 'entities': data.get('entities', []), 'confidence': data.get('confidence', 1.0)}})}\n\n"

            elif event_type == "agent_complete":
                agent_name = data.get("agent", "unknown")
                yield f"event: progress\ndata: {json.dumps({'message': f'{agent_name} finalizado', 'stage': 'agent_complete', 'progress': 70})}\n\n"

            elif event_type == "token":
                # Stream tokens for real-time text display
                token_text = data.get("text", data.get("token", ""))
                if token_text:
                    # Emit first_token on the very first token to switch frontend to streaming mode
                    if not first_token_sent:
                        first_token_sent = True
                        yield f"event: first_token\ndata: {json.dumps({'text': token_text})}\n\n"
                    yield f"event: token\ndata: {json.dumps({'text': token_text, 'token': token_text})}\n\n"

            elif event_type == "complete":
                # Final result
                suggestions = _generate_contextual_suggestions(
                    query.query,
                    data.get("answer", ""),
                    data.get("agents_used", [])
                )
                yield f"event: progress\ndata: {json.dumps({'message': 'Generando respuesta...', 'stage': 'synthesizing', 'progress': 90, 'slmIsThinking': False})}\n\n"
                yield f"event: complete\ndata: {json.dumps({'success': data.get('success', True), 'answer': data.get('answer', ''), 'tools_used': data.get('agents_used', []), 'execution_time_ms': data.get('latency_ms', 0), 'session_id': data.get('thread_id', thread_id), 'domains': data.get('domains', []), 'final_result': data, 'suggestions': suggestions})}\n\n"

            elif event_type == "error":
                yield f"event: error\ndata: {json.dumps({'error': data.get('error', 'Unknown error')})}\n\n"

            await asyncio.sleep(0)

    except Exception as e:
        logger.error(f"LangGraph streaming error: {e}")
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.post("/query/stream")
async def emma_query_stream(
    query: EmmaQuery,
    _: bool = Depends(verify_api_key),
):
    """
    Execute a query with Emma using Server-Sent Events (SSE) streaming.

    Events:
    - `thinking`: LLM reasoning process (if thinking mode enabled)
    - `content`: Response text chunks
    - `tool_call`: Tool invocation with name and arguments
    - `tool_result`: Result from tool execution
    - `slm_thinking`: Reasoning step during structural query processing
    - `slm_plan`: Execution plan ready
    - `done`: Final result with full metadata
    - `error`: Error message

    Example SSE stream:
    ```
    event: content
    data: {"content": "Analizando tu consulta..."}

    event: slm_thinking
    data: {"step": 1, "type": "query_analysis", "content": "Detectando consulta estructural..."}

    event: tool_call
    data: {"name": "search", "arguments": {"query": "contratos laborales"}}

    event: tool_result
    data: {"name": "search", "result": {"count": 5}}

    event: content
    data: {"content": "Encontré 5 contratos laborales."}

    event: done
    data: {"success": true, "answer": "...", "latency_ms": 1234.5}
    ```
    """
    if not is_emma_enabled():
        raise HTTPException(
            status_code=503,
            detail="Emma is not enabled. Set EMMA_ENABLED=true",
        )

    # Check if LangGraph is enabled for this tenant
    from app.agents.langgraph import is_langgraph_enabled_for_tenant, stream_langgraph_query

    if is_langgraph_enabled_for_tenant(query.tenant_id):
        logger.info(f"🔀 LangGraph streaming enabled for tenant {query.tenant_id}")
        return StreamingResponse(
            _generate_langgraph_sse(query, stream_langgraph_query),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def generate_sse() -> AsyncGenerator[str, None]:
        """
        Generate SSE events, transforming Emma internal events to frontend format.

        Emma internal → Frontend expected:
        - content → token (with text field)
        - thinking → progress (with stage='thinking')
        - tool_call → delegation (with tool field)
        - tool_result → step_complete
        - done → complete (with answer, success, tools_used)
        - error → error
        """
        thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

        # Extend TTL and restore document context from previous session
        try:
            persistence = get_emma_persistence_service()
            await persistence.touch_session(thread_id, query.tenant_id)
            session = await persistence.get_session(thread_id)
            if session:
                saved_ctx = (session.get("metadata") or {}).get("document_context")
                if saved_ctx:
                    ctx = query.context or {}
                    for key in ("document_id", "uploaded_file_ids", "indexed_document_ids"):
                        if not ctx.get(key) and saved_ctx.get(key):
                            ctx[key] = saved_ctx[key]
                    query.context = ctx
        except Exception as e:
            logger.warning(f"Failed to restore session context for {thread_id}: {e}")

        # Create Langfuse trace for this streaming query
        trace = trace_emma_query(
            query=query.query,
            tenant_id=query.tenant_id,
            user_id=query.user_id,
            thread_id=thread_id,
        )
        if trace:
            trace.update(metadata={"streaming": True})
            langfuse_context.push_observation(trace)

        try:
            logger.info(f"[Emma Stream] Starting for tenant={query.tenant_id}, query={query.query[:50]}...")

            # Send start event
            yield f"event: start\ndata: {json.dumps({'message': 'Iniciando análisis...', 'progress': 0})}\n\n"
            await asyncio.sleep(0)

            try:
                emma = await get_emma()
                logger.info("[Emma Stream] Emma instance created")
            except Exception as init_err:
                logger.error(f"[Emma Stream] Failed to create Emma instance: {init_err}")
                yield f"event: error\ndata: {json.dumps({'error': f'Error inicializando Emma: {str(init_err)}'})}\n\n"
                return

            yield f"event: progress\ndata: {json.dumps({'message': 'Emma inicializada...', 'stage': 'init', 'progress': 5})}\n\n"
            await asyncio.sleep(0)

            context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=query.user_id,
                role_ids=query.user_role_ids or [],
                is_admin=query.is_admin,
                thread_id=thread_id,
            )

            emma.config.enable_domain_routing = query.enable_domain_routing

            # Send progress event
            yield f"event: progress\ndata: {json.dumps({'message': 'Procesando consulta...', 'stage': 'context_preparation', 'progress': 10})}\n\n"
            await asyncio.sleep(0)

            logger.info(f"[Emma Stream] Starting execute_stream loop (SIL={query.enable_sil})")
            event_count = 0
            has_complete = False

            try:
                async for event in emma.execute_stream(query.query, context):
                    event_count += 1
                    event_type = event.get("type", "message")
                    logger.debug(f"[Emma Stream] Event {event_count}: {event_type}")

                    # Transform events to frontend expected format
                    if event_type == "content":
                        # content → token (text streaming)
                        frontend_data = {
                            "text": event.get("content", ""),
                            "token": event.get("content", ""),
                        }
                        yield f"event: token\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "thinking":
                        # thinking → progress with stage
                        frontend_data = {
                            "message": "Razonando...",
                            "stage": "thinking",
                            "text": event.get("content", ""),
                        }
                        yield f"event: progress\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    # SLM Router chain-of-thought events
                    elif event_type == "slm_thinking_start":
                        # SLM started reasoning
                        frontend_data = {
                            "message": event.get("content", "Analizando consulta..."),
                            "stage": "slm_reasoning",
                            "slmIsThinking": True,
                            "slmThinkingSteps": [],
                        }
                        yield f"event: progress\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "slm_thinking_step":
                        # SLM reasoning step (entity, intent, route)
                        frontend_data = {
                            "message": event.get("content", ""),
                            "stage": "slm_reasoning",
                            "slmIsThinking": True,
                            "slmThinkingStep": {
                                "step": event.get("step"),
                                "type": event.get("step_type"),
                                "content": event.get("content"),
                                "entities": event.get("entities", []),
                                "confidence": event.get("confidence", 1.0),
                            },
                        }
                        yield f"event: slm_thinking\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "slm_plan_ready":
                        # SLM plan generated
                        frontend_data = {
                            "message": f"Plan: {event.get('route', 'N/A')} ({event.get('confidence', 0)*100:.0f}% confianza)",
                            "stage": "slm_plan_ready",
                            "slmIsThinking": False,
                            "slmPlan": {
                                "route": event.get("route"),
                                "confidence": event.get("confidence", 0),
                                "entities_count": event.get("entities_count", 0),
                                "reasoning": event.get("reasoning"),
                            },
                        }
                        yield f"event: slm_plan\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "slm_execution_start":
                        # SLM starting execution
                        frontend_data = {
                            "message": event.get("message", "Ejecutando plan..."),
                            "stage": "slm_executing",
                            "slmIsExecuting": True,
                            "route": event.get("route"),
                        }
                        yield f"event: progress\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "done":
                        # done → complete
                        has_complete = True
                        result = event.get("result", {})
                        # Generate contextual suggestions based on query and result
                        suggestions = _generate_contextual_suggestions(
                            query.query,
                            result.get("answer", ""),
                            result.get("tools_called", [])
                        )
                        frontend_data = {
                            "success": result.get("success", True),
                            "answer": result.get("answer", ""),
                            "tools_used": result.get("tools_called", []),
                            "execution_time_ms": result.get("latency_ms", 0),
                            "session_id": result.get("thread_id", thread_id),
                            "process_info": result.get("process_info", {}),
                            "final_result": result,
                            "suggestions": suggestions,
                        }
                        yield f"event: complete\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "error":
                        # error stays as error
                        frontend_data = {"error": event.get("error", "Unknown error")}
                        yield f"event: error\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    else:
                        # Unknown event types → progress
                        event_data = {k: v for k, v in event.items() if k != "type"}
                        event_data["message"] = event_data.get("message", f"Procesando ({event_type})...")
                        yield f"event: progress\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    # Force immediate flush after each event
                    await asyncio.sleep(0)

                # After loop: Check if we got events
                logger.info(f"[Emma Stream] Loop finished with {event_count} events, has_complete={has_complete}")
                if event_count == 0:
                    logger.warning("[Emma Stream] No events received from execute_stream!")
                    if trace:
                        trace.update(level="WARNING", status_message="No events received")
                    yield f"event: error\ndata: {json.dumps({'error': 'No se recibieron eventos del procesamiento'})}\n\n"
                elif not has_complete:
                    logger.warning("[Emma Stream] Stream ended without 'done' event")

                # Finalize trace on success
                if trace and has_complete:
                    trace.update(
                        output={"event_count": event_count, "completed": has_complete}
                    )

            except Exception as stream_err:
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"[Emma Stream] Error in execute_stream: {stream_err}\n{error_details}")
                if trace:
                    trace.update(level="ERROR", status_message=str(stream_err))
                yield f"event: error\ndata: {json.dumps({'error': f'Error en procesamiento: {str(stream_err)}'})}\n\n"

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Emma stream error: {e}\n{error_details}")
            if trace:
                trace.update(level="ERROR", status_message=str(e))
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'details': error_details[:500]})}\n\n"
        finally:
            # Cleanup: pop trace from context and flush
            if trace:
                langfuse_context.pop_observation()
                flush_langfuse()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tools", response_model=ToolsResponse)
async def list_tools(_: bool = Depends(verify_api_key)):
    """
    List all available Emma tools.

    Emma uses a consolidated set of 5 tools:
    - search: Semantic/keyword/hybrid document search
    - read_document: Get full document content
    - analyze: Deep RAG-based document analysis
    - ask_user: Human-in-the-loop clarification
    - legal_search: Public legal knowledge search
    """
    tools = get_emma_tools()

    return ToolsResponse(
        tools=[
            ToolInfo(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in tools
        ],
        count=len(tools),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check Emma health status.

    Returns:
    - LLM connection status
    - SIL availability
    - Enabled features
    """
    try:
        emma = await get_emma()

        # Check LLM connection
        llm_connected, llm_msg = await emma._llm_client.validate_connection()

        # Check LangGraph status
        from app.agents.langgraph import is_langgraph_enabled
        langgraph_enabled = is_langgraph_enabled()

        return HealthResponse(
            status="healthy" if llm_connected else "degraded",
            version="2.0",
            llm_connected=llm_connected,
            sil_enabled=False,
            orchestration="LangGraph" if langgraph_enabled else "Emma",
            features={
                "sil_fast_path": False,
                "domain_routing": emma.config.enable_domain_routing,
                "streaming": emma.config.enable_streaming,
                "emma_enabled": is_emma_enabled(),
                "langgraph_enabled": langgraph_enabled,
            },
        )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="unhealthy",
            version="2.0",
            llm_connected=False,
            sil_enabled=False,
            features={"error": str(e)},
        )


@router.get("/compare")
async def compare_service_vs_direct(
    query: str = Query(..., description="Query to compare"),
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Compare Emma service vs direct Emma responses for the same query.

    Useful for testing. Returns both responses with timing information.
    """
    import time
    from app.services.emma_service import emma_service
    from app.schemas.emma import EmmaQuery as ServiceEmmaQuery

    results = {}

    # Execute via service
    try:
        service_start = time.time()
        service_query = ServiceEmmaQuery(
            query=query,
            tenant_id=tenant_id,
        )
        service_response = await emma_service.execute_query(service_query)
        service_latency = (time.time() - service_start) * 1000

        results["service"] = {
            "success": service_response.success,
            "answer": service_response.answer[:500] + "..." if len(service_response.answer) > 500 else service_response.answer,
            "latency_ms": service_latency,
        }
    except Exception as e:
        results["service"] = {"error": str(e)}

    # Execute direct
    try:
        emma = await get_emma()
        direct_start = time.time()
        context = ExecutionContext(tenant_id=tenant_id)
        direct_result = await emma.execute(query, context)
        direct_latency = (time.time() - direct_start) * 1000

        results["direct"] = {
            "success": direct_result.success,
            "answer": direct_result.answer[:500] + "..." if len(direct_result.answer) > 500 else direct_result.answer,
            "latency_ms": direct_latency,
            "sil_answered": direct_result.sil_answered,
            "tokens_saved": direct_result.tokens_saved,
            "domain": direct_result.domain.value,
        }
    except Exception as e:
        results["direct"] = {"error": str(e)}

    # Calculate comparison
    if "latency_ms" in results.get("service", {}) and "latency_ms" in results.get("direct", {}):
        service_lat = results["service"]["latency_ms"]
        direct_lat = results["direct"]["latency_ms"]
        results["comparison"] = {
            "latency_improvement_pct": round((service_lat - direct_lat) / service_lat * 100, 1) if service_lat > 0 else 0,
            "sil_fast_path": results["direct"].get("sil_answered", False),
            "tokens_saved": results["direct"].get("tokens_saved", 0),
        }

    return results


# =============================================================================
# Session Persistence Endpoints
# =============================================================================

@router.get("/sessions", response_model=EmmaSessionListResponse)
async def list_sessions(
    user_id: str = Query(..., description="User ID"),
    tenant_id: str = Query(..., description="Tenant ID"),
    include_archived: bool = Query(False, description="Include archived sessions"),
    limit: int = Query(50, ge=1, le=100, description="Max sessions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    _: bool = Depends(verify_api_key),
):
    """
    List Emma chat sessions for a user.

    Returns paginated list of sessions with previews of first/last messages.
    Sessions are ordered by:
    1. Pinned sessions first
    2. Then by last_message_at (most recent first)

    Use this to build a conversation history sidebar.
    """
    persistence = get_emma_persistence_service()

    result = await persistence.get_user_sessions(
        user_id=user_id,
        tenant_id=tenant_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )

    return EmmaSessionListResponse(**result)


@router.get("/sessions/{session_id}", response_model=EmmaSessionResponse)
async def get_session(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Get a full Emma session with all messages.

    Returns the complete conversation history including:
    - All messages (user and assistant)
    - Sources cited in responses
    - Tools used
    - Metadata

    Use this when the user opens an old conversation.
    """
    persistence = get_emma_persistence_service()

    session = await persistence.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify tenant access
    if session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    return EmmaSessionResponse(**session)


@router.post("/sessions/{session_id}/continue", response_model=EmmaContinueSessionResponse)
async def continue_session(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Continue an old Emma session.

    This endpoint:
    1. Loads the session from PostgreSQL
    2. Restores it to Redis (hot cache)
    3. Returns confirmation

    After calling this, use the regular /query or /query/stream endpoints
    with the same session_id to continue the conversation.
    The LLM will have access to the full conversation history.
    """
    persistence = get_emma_persistence_service()

    # Check if session exists
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify tenant access
    if session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Check if already in Redis
    in_redis = await persistence.session_exists_in_redis(session_id)

    if in_redis:
        return EmmaContinueSessionResponse(
            success=True,
            session_id=session_id,
            message_count=session["message_count"],
            loaded_to_redis=False,  # Already there
            message="Session already active in cache",
        )

    # Load to Redis
    loaded = await persistence.load_session_to_redis(session_id)

    if not loaded:
        raise HTTPException(
            status_code=500,
            detail="Failed to load session to cache. Please try again.",
        )

    return EmmaContinueSessionResponse(
        success=True,
        session_id=session_id,
        message_count=session["message_count"],
        loaded_to_redis=True,
        message=f"Session restored with {session['message_count']} messages",
    )


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    update: EmmaSessionUpdate,
    user_id: str = Query(..., description="User ID"),
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Update session properties.

    Allows updating:
    - title: Custom session title
    - is_archived: Archive/unarchive session
    - is_pinned: Pin/unpin session
    """
    persistence = get_emma_persistence_service()

    # Verify session exists
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify ownership
    if session["user_id"] != user_id or session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Update
    updated = await persistence.update_session(
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        title=update.title,
        is_archived=update.is_archived,
        is_pinned=update.is_pinned,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update session")

    return {"success": True, "message": "Session updated"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Query(..., description="User ID"),
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Permanently delete an Emma session.

    This action:
    - Removes the session from PostgreSQL
    - Clears it from Redis if present
    - Cannot be undone

    Consider archiving instead for recoverable deletion.
    """
    persistence = get_emma_persistence_service()

    # Verify session exists
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify ownership
    if session["user_id"] != user_id or session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Delete
    deleted = await persistence.delete_session(
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete session")

    return {"success": True, "message": "Session deleted"}
