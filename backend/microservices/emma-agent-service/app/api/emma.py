"""
Emma API Endpoints

Main API endpoints for Emma AI assistant, powered by LangGraph ReAct agent.

Endpoints:
- POST /emma/query - Execute query (non-streaming)
- POST /emma/query/stream - Execute query with SSE streaming
- POST /emma/query/resume/stream - Resume interrupted query (HITL)
- GET /emma/health - Health check
- GET /emma/sessions - List conversation sessions
- POST /emma/sessions/{id}/continue - Continue a session
- PATCH /emma/sessions/{id} - Update session metadata
- DELETE /emma/sessions/{id} - Delete a session
- GET /emma/memory/facts - List user memory facts
- DELETE /emma/memory/facts - Clear all user facts (GDPR)
- DELETE /emma/memory/facts/{id} - Delete a single fact

Architecture:
- LangGraph is the single orchestration engine (ReAct agent with tools)
- Session persistence via LangGraph checkpointer (PostgreSQL)
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
from app.core.security import verify_api_key
from app.core.auth_headers import extract_user_roles, extract_user_id
from app.services.emma_persistence_service import get_emma_persistence_service
from app.schemas.emma import (
    EmmaSessionCreate,
    EmmaSessionListResponse,
    EmmaSessionResponse,
    EmmaSessionUpdate,
    EmmaContinueSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Emma"])

class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalar types (float32, int64, etc.)."""

    def default(self, obj):
        # Handle numpy floating types (float16, float32, float64)
        try:
            import numpy as np
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _dumps(obj) -> str:
    """json.dumps with numpy-safe encoding."""
    return json.dumps(obj, cls=_SafeEncoder)


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
    user_id: Optional[str] = Field(None, description="User identifier")
    user_roles: Optional[List[str]] = Field(None, description="User role IDs for ACL filtering")
    is_admin: bool = Field(False, description="Whether user is admin (bypasses ACL)")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID for history")
    session_id: Optional[str] = Field(None, description="Session ID (alias for thread_id)")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context (document_id, indexed_document_ids, attachments)")
    enable_streaming: bool = Field(False, description="Enable streaming (use /stream endpoint instead)")
    deep_reasoning: Optional[bool] = Field(default=None, description="Enable deep reasoning / thinking mode. None=use global default, True=force thinking, False=disable thinking")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "¿Cuántos contratos laborales tengo?",
                "user_id": "user-456",
                "thread_id": "thread-789",
            }
        }


class EmmaQueryResponse(BaseModel):
    """Response from Emma."""
    success: bool
    answer: str = ""
    tools_called: List[str] = Field(default_factory=list)
    iterations: int = 0
    latency_ms: float = 0.0
    thread_id: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sources cited in the response. May include graph_link for BOE legislation."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "Tienes 5 contratos laborales.",
                "tools_called": [],
                "iterations": 0,
                "latency_ms": 45.2,
                "thread_id": "thread-789",
                "sources": [
                    {
                        "title": "Real Decreto Legislativo 2/2015 - ET",
                        "boe_id": "BOE-A-2015-11430",
                        "graph_link": "/admin/knowledge-tree?focus=BOE-A-2015-11430"
                    }
                ],
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "2.0"
    llm_connected: bool
    features: Dict[str, Any]
    orchestration: Optional[str] = None


class CendojStatusResponse(BaseModel):
    """CENDOJ service status."""
    enabled: bool
    sector: str
    docker_image: str


class CendojStatusUpdate(BaseModel):
    """CENDOJ toggle request."""
    enabled: bool


# =============================================================================
# Redis helper (CENDOJ toggle)
# =============================================================================

import redis.asyncio as aioredis

CENDOJ_REDIS_KEY = "emma:cendoj:enabled"
_cendoj_redis = None


async def _get_cendoj_redis() -> aioredis.Redis:
    global _cendoj_redis
    if _cendoj_redis is None:
        _cendoj_redis = aioredis.Redis(
            host=settings.redis_host, port=settings.redis_port, decode_responses=True
        )
    return _cendoj_redis


async def _get_cendoj_enabled() -> bool:
    """Read CENDOJ enabled state: Redis → env var → sector default."""
    try:
        r = await _get_cendoj_redis()
        val = await r.get(CENDOJ_REDIS_KEY)
        if val is not None:
            return val.lower() == "true"
    except Exception as e:
        logger.warning(f"Redis read failed for CENDOJ toggle: {e}")
    return settings.cendoj_enabled


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
    user_roles: List[str] = Depends(extract_user_roles),
    header_user_id: Optional[str] = Depends(extract_user_id),
    _: bool = Depends(verify_api_key),
):
    """
    Execute a query with Emma (LangGraph ReAct agent).

    Uses LangGraph multi-agent RAG with ReAct loop and tool calling.
    Use thread_id to maintain conversation context across requests.
    """
    if not is_emma_enabled():
        raise HTTPException(
            status_code=503,
            detail="Emma is not enabled. Set EMMA_ENABLED=true",
        )

    # Resolve user_id: prefer header, then body, then context
    if not query.user_id:
        query.user_id = header_user_id
    if not query.user_id and query.context:
        query.user_id = query.context.get("user_id")

    # Merge roles from header if body did not provide them
    if not query.user_roles:
        query.user_roles = user_roles

    # Build context
    thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

    # Extend TTL and restore document context from previous session
    try:
        persistence = get_emma_persistence_service()
        await persistence.touch_session(thread_id)
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

    # LangGraph is the only orchestration engine
    from app.agents.langgraph import is_langgraph_enabled, execute_langgraph_query

    if not is_langgraph_enabled():
        raise HTTPException(
            status_code=500,
            detail="Legacy Emma engine has been removed. LangGraph is the only orchestration engine.",
        )

    logger.info(f"LangGraph query (user={query.user_id})")
    try:
        langgraph_result = await execute_langgraph_query(
            query=query.query,
            user_id=query.user_id,
            user_roles=query.user_roles,
            is_admin=query.is_admin,
            thread_id=thread_id,
            context=query.context,
        )

        # Fire-and-forget: extract user facts from conversation
        if query.user_id and settings.user_memory_enabled:
            try:
                from app.services.memory.fact_extractor import extract_and_save_facts
                asyncio.create_task(extract_and_save_facts(
                    user_id=query.user_id,
                    user_message=query.query,
                    assistant_response=langgraph_result.answer or "",
                ))
            except Exception as e:
                logger.debug(f"Fact extraction dispatch failed: {e}")

        return EmmaQueryResponse(
            success=langgraph_result.success,
            answer=langgraph_result.answer,
            tools_called=langgraph_result.agents_used,
            iterations=len(langgraph_result.agents_used),
            latency_ms=langgraph_result.latency_ms,
            thread_id=langgraph_result.thread_id,
            metadata={
                "langgraph": True,
                "domains": langgraph_result.domains,
                **langgraph_result.metadata,
            },
            sources=langgraph_result.sources,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LangGraph query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


import re as _re


def _humanize_tool_call(raw_content: str) -> tuple:
    """Parse tool_name(args...) → (action_type, human_text, detail)."""
    # Extract tool name and args from format: tool_name(key=value, ...)
    m = _re.match(r'(\w+)\((.*)\)', raw_content, _re.DOTALL)
    if not m:
        return ("thinking", raw_content[:100], raw_content)

    tool_name = m.group(1)
    args_str = m.group(2)

    # Parse key=value args
    def _extract_arg(name: str) -> str:
        am = _re.search(rf'{name}=([^,\)]+)', args_str)
        return am.group(1).strip().strip("'\"") if am else ""

    query = _extract_arg("query")
    scope = _extract_arg("scope")

    mapping = {
        "smart_search": ("searching", f'Buscando "{query}" en {scope or "documentos"}...'),
        "get_document_content": ("reading", "Leyendo documento..."),
        "structural_query": ("querying", f'Consultando: "{query}"' if query else "Ejecutando consulta estructural..."),
        "analyze_domain": ("analyzing", f'Analizando dominio {_extract_arg("domain") or ""}...'.rstrip(". ") + "..."),
        "web_search": ("browsing", f'Buscando en internet: "{query}"'),
        "search_jurisprudence": ("searching", f'Buscando jurisprudencia: "{query}"'),
        "list_sources": ("listing", "Consultando fuentes disponibles..."),
        "query_connector": ("connecting", f'Consultando {_extract_arg("connector") or "conector externo"}...'),
        "terminate": ("preparing", "Preparando respuesta..."),
    }

    action_type, human_text = mapping.get(tool_name, ("thinking", f"Ejecutando {tool_name}..."))
    return (action_type, human_text, raw_content)


def _humanize_observation(raw_content: str, source: str) -> tuple:
    """Parse observation text → (action_type, human_text, detail)."""
    full = f"[{source}] {raw_content}" if source else raw_content

    # Pattern: [smart_search] Se encontraron N resultados...
    m = _re.search(r'Se encontraron (\d+) resultado', raw_content)
    if m:
        return ("search_result", f"{m.group(1)} documentos encontrados", full)

    # Pattern: [get_document_content] **Documento: Title.pdf**
    m = _re.search(r'\*\*Documento:\s*(.+?)\*\*', raw_content)
    if m:
        return ("doc_read", f"Documento leído: {m.group(1)}", full)

    # Pattern: [smart_search] No se encontraron resultados
    if "No se encontraron" in raw_content or "0 resultado" in raw_content:
        return ("search_result", "Sin resultados relevantes", full)

    # Fallback: first meaningful line, max 80 chars
    first_line = raw_content.strip().split('\n')[0][:80]
    if source == "structural_query":
        return ("querying", first_line, full)
    if source == "web_search":
        return ("browsing", first_line, full)

    return ("search_result", first_line, full)


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
    - plan_complete → agent_reasoning + progress (stage='planning')
    - agent_started → delegation
    - agent_complete → step_complete
    - structural_step → agent_reasoning
    - complete → complete
    - error → error
    """
    thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

    try:
        step_counter = 0
        first_token_sent = False
        reasoning_steps: list[dict] = []  # Collect for persistence

        # Evidence sub-graph accumulators — Piece A of TrustGraph Provenance DAG.
        # Built from source_evidence payloads emitted by graph_rag (and future tools);
        # stored alongside the reasoning_trace in Redis and returned by
        # GET /emma/explainability/trace/{tid}/{idx}.
        evidence_nodes: dict[str, dict] = {}  # URI → node dict (deduped)
        evidence_edges: list[dict] = []
        seen_evidence_edges: set[tuple] = set()  # (s_uri, p_uri, o_uri)

        def _track_step(step_type: str, content: str, detail: str = ""):
            """Append reasoning step for later persistence."""
            import time
            reasoning_steps.append({
                "step": step_counter,
                "type": step_type,
                "content": content,
                "detail": detail,
                "timestamp_ms": int(time.time() * 1000),
            })

        def _absorb_source_evidence(src_list: list) -> None:
            """Merge a source_evidence list into evidence_nodes + evidence_edges."""
            for src in src_list:
                if not isinstance(src, dict):
                    continue

                s_uri = src.get("subject_uri") or ""
                p_uri = src.get("predicate_uri") or ""
                o_uri = src.get("object_uri") or ""
                doc_id = src.get("document_id") or ""
                s_label = src.get("subject_label") or (s_uri.rsplit("/", 1)[-1] if s_uri else "")
                o_label = src.get("object_label") or (o_uri.rsplit("/", 1)[-1] if o_uri else "")
                p_name = src.get("predicate_name") or (p_uri.rsplit("/", 1)[-1] if p_uri else "relates-to")

                if s_uri and s_uri not in evidence_nodes:
                    evidence_nodes[s_uri] = {
                        "id": s_uri,
                        "type": "entity",
                        "label": s_label,
                        "properties": {"uri": s_uri},
                    }
                if o_uri and o_uri not in evidence_nodes:
                    evidence_nodes[o_uri] = {
                        "id": o_uri,
                        "type": "entity",
                        "label": o_label,
                        "properties": {"uri": o_uri},
                    }
                if doc_id:
                    doc_uri = f"nouxcube://document/default/{doc_id}"
                    if doc_uri not in evidence_nodes:
                        evidence_nodes[doc_uri] = {
                            "id": doc_uri,
                            "type": "document",
                            "label": src.get("document_title") or doc_id[:12],
                            "properties": {"document_id": doc_id},
                        }

                if s_uri and o_uri and p_uri:
                    edge_key = (s_uri, p_uri, o_uri)
                    if edge_key not in seen_evidence_edges:
                        seen_evidence_edges.add(edge_key)
                        evidence_edges.append({
                            "id": f"{s_uri}|{p_uri}|{o_uri}",
                            "source": s_uri,
                            "target": o_uri,
                            "type": p_name,
                            "properties": {
                                "confidence": src.get("confidence"),
                                "document_id": doc_id or None,
                                "chunk_offset": src.get("chunk_offset"),
                            },
                        })
        # Session loaded for document context restoration and TTL extension.
        # Conversation history is NO LONGER loaded here — PostgresSaver
        # checkpointer restores previous messages automatically from its
        # checkpoint when graph.astream() is called with the same thread_id.
        try:
            persistence = get_emma_persistence_service()
            # Extend TTL for active session
            await persistence.touch_session(thread_id)
            session = await persistence.get_session(thread_id)
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
            logger.warning(f"Failed to load session context for {thread_id}: {e}")

        async for event in stream_func(
            query=query.query,
            user_id=query.user_id,
            user_roles=query.user_roles,
            thread_id=thread_id,
            context=query.context,
            enable_thinking=getattr(query, "deep_reasoning", None),
        ):
            event_type = event.get("type", "")
            data = event.get("data", {})

            if event_type == "started":
                yield f"event: start\ndata: {_dumps({'message': 'Iniciando análisis...', 'progress': 0, 'thread_id': data.get('thread_id')})}\n\n"

            elif event_type == "retrieve_complete":
                doc_count = data.get("doc_count", 0)
                step_counter += 1
                _track_step("search_result", f"{doc_count} documentos recuperados")
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'search_result', 'content': f'{doc_count} documentos recuperados', 'isThinking': True})}\n\n"
                yield f"event: progress\ndata: {_dumps({'message': f'Recuperados {doc_count} documentos', 'stage': 'retrieval', 'progress': 20})}\n\n"

            elif event_type == "plan_complete":
                domains = data.get("domains", [])
                agents = data.get("agents", [])
                reasoning = data.get("reasoning", "")

                # Emit reasoning steps for traceability
                step_counter += 1
                _track_step("analyzing", f'Dominios detectados: {", ".join(domains)}')
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'analyzing', 'content': f'Dominios detectados: {", ".join(domains)}', 'isThinking': True})}\n\n"

                step_counter += 1
                _track_step("preparing", f'Agentes seleccionados: {", ".join(agents)}')
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'preparing', 'content': f'Agentes seleccionados: {", ".join(agents)}', 'isThinking': True})}\n\n"

                yield f"event: progress\ndata: {_dumps({'message': f'Plan: {reasoning}', 'stage': 'planning', 'progress': 30})}\n\n"

            elif event_type == "agent_started":
                agent_name = data.get("agent", "unknown")
                agent_display = {
                    "general_agent": "Agente General",
                    "privacy_agent": "Agente de Privacidad",
                    "legal_agent": "Agente Legal",
                    "labor_agent": "Agente Laboral",
                    "fiscal_agent": "Agente Fiscal",
                    "contract_agent": "Agente de Contratos",
                    "compliance_agent": "Agente de Compliance",
                    "realestate_agent": "Agente Inmobiliario",
                    "education_agent": "Agente de Educación",
                    "docgen_agent": "Agente de Generación Documental",
                }.get(agent_name, agent_name)

                step_counter += 1
                _track_step("analyzing", f"Ejecutando {agent_display}...")
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'analyzing', 'content': f'Ejecutando {agent_display}...', 'isThinking': True})}\n\n"

            elif event_type == "structural_step":
                # Reasoning step from structural query tool
                step_counter += 1
                _track_step("querying", data.get("content", ""))
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'querying', 'content': data.get('content', ''), 'detail': data.get('content', ''), 'isThinking': True})}\n\n"

            elif event_type == "agent_complete":
                agent_name = data.get("agent", "unknown")
                yield f"event: progress\ndata: {_dumps({'message': f'{agent_name} finalizado', 'stage': 'agent_complete', 'progress': 70})}\n\n"

            # ReAct loop reasoning steps (Think-Act-Observe cycle)
            # Filter out internal steps that aren't meaningful to the user
            elif event_type == "thinking":
                content = data.get("content", "")
                # Skip short or meaningless content
                if content and len(content.strip()) > 20 and not content.strip().isdigit():
                    # Truncate to first sentence, max 100 chars
                    first_sentence = _re.split(r'[.\n]', content.strip())[0][:100]
                    step_counter += 1
                    _track_step("thinking", first_sentence, content)
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'thinking', 'content': first_sentence, 'detail': content, 'isThinking': True})}\n\n"

            elif event_type == "tool_call":
                content = data.get("content", "")
                if content:
                    action_type, human_text, detail = _humanize_tool_call(content)
                    step_counter += 1
                    _track_step(action_type, human_text, detail)
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': action_type, 'content': human_text, 'detail': detail, 'isThinking': True})}\n\n"

            elif event_type == "tool_result":
                content = data.get("content", "")
                if content:
                    source = data.get("source", "")
                    action_type, human_text, detail = _humanize_observation(content, source)
                    step_counter += 1
                    _track_step(action_type, human_text, detail)
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': action_type, 'content': human_text, 'detail': detail, 'isThinking': True})}\n\n"

            elif event_type == "reasoning_step":
                step_type = data.get("step_type", "thinking")
                content = data.get("content", "")
                # Intercept source_evidence payloads (JSON-encoded lists emitted
                # by react_loop when graph_rag resolves provenance) and fold them
                # into the evidence_graph accumulator instead of the timeline.
                if step_type == "source_evidence":
                    try:
                        src_list = json.loads(content) if isinstance(content, str) else content
                        if isinstance(src_list, list):
                            _absorb_source_evidence(src_list)
                    except (ValueError, TypeError) as ev_err:
                        logger.warning(f"source_evidence absorb failed: {ev_err}")
                # Skip internal routing markers (fast-path, terminate, etc.)
                elif step_type == "response":
                    pass  # Internal marker — not useful for the user
                elif content and len(content.strip()) > 3 and not content.strip().isdigit():
                    # Map legacy step_type to semantic type
                    semantic_type = {
                        "query_analysis": "searching", "routing": "preparing",
                        "tool_call": "searching", "tool_execution": "searching",
                        "observation": "search_result", "reflection": "thinking",
                        "search": "searching", "data_extraction": "reading",
                        "validation": "analyzing", "retrieval": "search_result",
                        "domain_detection": "analyzing", "agent_selection": "preparing",
                        "agent_execution": "analyzing", "structural": "querying",
                        "entity_detection": "searching", "intent_detection": "analyzing",
                        "route_decision": "preparing", "connection": "connecting",
                        "connector": "connecting", "transformation": "analyzing",
                    }.get(step_type, step_type)
                    step_counter += 1
                    _track_step(semantic_type, content)
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': semantic_type, 'content': content, 'isThinking': True})}\n\n"

            # Swarm events (parallel sub-agent execution)
            elif event_type == "swarm_started":
                num_workers = data.get("num_workers", 0)
                step_counter += 1
                _track_step("swarm_decompose", f"Descomponiendo en {num_workers} tareas paralelas...")
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'swarm_decompose', 'content': f'Descomponiendo en {num_workers} tareas paralelas...', 'isThinking': True})}\n\n"
                yield f"event: swarm_started\ndata: {_dumps(data)}\n\n"

            elif event_type == "worker_started":
                worker_id = data.get("worker_id", 0)
                sub_task = data.get("sub_task", "")[:80]
                step_counter += 1
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'swarm_worker', 'content': f'Agente {worker_id}: {sub_task}', 'isThinking': True})}\n\n"

            elif event_type == "worker_complete":
                worker_id = data.get("worker_id", 0)
                latency = data.get("latency_ms", 0)
                step_counter += 1
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'swarm_worker_done', 'content': f'Agente {worker_id} completado ({latency:.0f}ms)', 'isThinking': True})}\n\n"

            elif event_type == "swarm_synthesizing":
                successful_count = data.get("successful_workers", 0)
                step_counter += 1
                yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'swarm_synthesize', 'content': f'Sintetizando resultados de {successful_count} agentes...', 'isThinking': True})}\n\n"
                yield f"event: progress\ndata: {_dumps({'message': 'Sintetizando resultados...', 'stage': 'synthesizing', 'progress': 80})}\n\n"

            elif event_type.startswith("report."):
                # Knowledge report progressive events
                stage_labels = {
                    "report.assembling": "Recopilando datos del grafo...",
                    "report.generating": "Generando informe...",
                    "report.kpi": None,
                    "report.complete": None,
                }
                if event_type == "report.complete":
                    step_counter += 1
                    _track_step("report_complete", "Informe generado")
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_complete', 'content': 'Informe generado', 'isThinking': True})}\n\n"
                    yield f"event: report_complete\ndata: {_dumps(data)}\n\n"
                elif event_type == "report.kpi":
                    kpi_name = data.get("description") or data.get("name", "")
                    kpi_value = data.get("value", "")
                    step_counter += 1
                    _track_step("report_kpi", f"{kpi_name}: {kpi_value}")
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_kpi', 'content': f'KPI: {kpi_name} = {kpi_value}', 'isThinking': True})}\n\n"
                    yield f"event: report_kpi\ndata: {_dumps(data)}\n\n"
                else:
                    label = stage_labels.get(event_type)
                    if label:
                        step_counter += 1
                        _track_step("report_progress", label)
                        yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_progress', 'content': label, 'isThinking': True})}\n\n"

            elif event_type == "token":
                # Stream tokens for real-time text display
                token_text = data.get("text", data.get("token", ""))
                if token_text:
                    # Emit first_token on the very first token to switch frontend to streaming mode
                    if not first_token_sent:
                        first_token_sent = True
                        yield f"event: first_token\ndata: {_dumps({'text': token_text})}\n\n"
                    yield f"event: token\ndata: {_dumps({'text': token_text, 'token': token_text})}\n\n"
                    # Yield to event loop between tokens for HTTP chunk flushing
                    await asyncio.sleep(0)
                    continue  # Skip the general sleep below (already yielded)

            elif event_type in ("clarification", "confirmation", "hitl_review"):
                # HITL interrupt — graph paused for user input.
                # Dispatch the actual interrupt type so frontend renders the right UI.
                actual_type = event_type
                if isinstance(data, dict):
                    actual_type = data.get("type", event_type)
                yield f"event: {actual_type}\ndata: {_dumps({**data, 'thread_id': data.get('thread_id', thread_id)})}\n\n"
                # SSE closes after interrupt — frontend will resume via /query/resume/stream
                return

            elif event_type == "complete":
                metadata = data.get("metadata", {})

                # Persist reasoning trace to Redis (fire-and-forget)
                if reasoning_steps:
                    try:
                        import redis.asyncio as aioredis
                        r = aioredis.from_url(settings.redis_url, decode_responses=True)
                        trace_key = f"reasoning_trace:{thread_id}:{step_counter}"
                        trace_data = {
                            "thread_id": thread_id,
                            "message_index": step_counter,
                            "timeline": reasoning_steps,
                            "tools_used": data.get("agents_used", []),
                            "total_execution_ms": data.get("latency_ms", 0),
                            "sources_cited": len(data.get("sources", [])),
                            "evidence_graph": {
                                "nodes": list(evidence_nodes.values()),
                                "edges": evidence_edges,
                            },
                        }
                        await r.set(trace_key, json.dumps(trace_data), ex=86400)  # 24h TTL
                        # Also store latest message index for this thread
                        await r.set(f"reasoning_trace:{thread_id}:latest", str(step_counter), ex=86400)
                        await r.close()
                    except Exception as e:
                        logger.warning(f"Failed to persist reasoning trace: {e}")

                # Normal completion — final result
                suggestions = _generate_contextual_suggestions(
                    query.query,
                    data.get("answer", ""),
                    data.get("agents_used", [])
                )
                yield f"event: progress\ndata: {_dumps({'message': 'Generando respuesta...', 'stage': 'synthesizing', 'progress': 90, 'isThinking': False})}\n\n"
                yield f"event: complete\ndata: {_dumps({'success': data.get('success', True), 'answer': data.get('answer', ''), 'tools_used': data.get('agents_used', []), 'execution_time_ms': data.get('latency_ms', 0), 'session_id': data.get('thread_id', thread_id), 'domains': data.get('domains', []), 'final_result': data, 'suggestions': suggestions})}\n\n"

                # Guardrail SSE events
                guardrail_meta = data.get("guardrail_metadata") or {}
                if guardrail_meta.get("guardrail_blocked"):
                    yield f"event: guardrail_blocked\ndata: {_dumps({'sector': data.get('metadata', {}).get('sector') if isinstance(data.get('metadata'), dict) else None, 'warnings': guardrail_meta.get('guardrail_warnings', [])})}\n\n"
                elif guardrail_meta.get("guardrail_redacted"):
                    yield f"event: guardrail_redacted\ndata: {_dumps({'warnings': guardrail_meta.get('guardrail_warnings', [])})}\n\n"
                elif guardrail_meta.get("guardrail_warnings"):
                    yield f"event: guardrail_warning\ndata: {_dumps({'warnings': guardrail_meta.get('guardrail_warnings', [])})}\n\n"

                # Fire-and-forget: extract user facts from conversation
                if query.user_id and settings.user_memory_enabled:
                    try:
                        from app.services.memory.fact_extractor import extract_and_save_facts
                        asyncio.create_task(extract_and_save_facts(
                            user_id=query.user_id,
                            user_message=query.query,
                            assistant_response=data.get("answer", ""),
                        ))
                    except Exception as e:
                        logger.debug(f"Fact extraction dispatch failed: {e}")

                # Fire-and-forget: save conversation turn for session continuity
                try:
                    persistence = get_emma_persistence_service()
                    doc_ctx = {}
                    if query.context:
                        for key in ("document_id", "uploaded_file_ids", "indexed_document_ids"):
                            if query.context.get(key):
                                doc_ctx[key] = query.context[key]
                    asyncio.create_task(persistence.save_message(
                        session_id=thread_id,
                        user_id=query.user_id or "",
                        user_message=query.query,
                        assistant_response=data.get("answer", ""),
                        sources=data.get("sources"),
                        tools_used=data.get("agents_used"),
                        document_context=doc_ctx or None,
                    ))
                except Exception as e:
                    logger.warning(f"Failed to save conversation: {e}")

            elif event_type == "error":
                yield f"event: error\ndata: {_dumps({'error': data.get('error', 'Unknown error')})}\n\n"

            await asyncio.sleep(0)

    except Exception as e:
        logger.error(f"LangGraph streaming error: {e}")
        yield f"event: error\ndata: {_dumps({'error': 'Lo siento, hubo un problema temporal. Por favor, inténtalo de nuevo.'})}\n\n"


@router.post("/query/stream")
async def emma_query_stream(
    query: EmmaQuery,
    user_roles: List[str] = Depends(extract_user_roles),
    header_user_id: Optional[str] = Depends(extract_user_id),
    _: bool = Depends(verify_api_key),
):
    """
    Execute a query with Emma using Server-Sent Events (SSE) streaming.

    Events:
    - `thinking`: LLM reasoning process (if thinking mode enabled)
    - `content`: Response text chunks
    - `tool_call`: Tool invocation with name and arguments
    - `tool_result`: Result from tool execution
    - `agent_reasoning`: Reasoning step emitted by the agent during tool use
    - `progress`: Stage progress update (retrieval, planning, etc.)
    - `done`: Final result with full metadata
    - `error`: Error message

    Example SSE stream:
    ```
    event: content
    data: {"content": "Analizando tu consulta..."}

    event: agent_reasoning
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

    # Resolve user_id: prefer header, then body, then context
    if not query.user_id:
        query.user_id = header_user_id
    if not query.user_id and query.context:
        query.user_id = query.context.get("user_id")

    # Merge roles from header if body did not provide them
    if not query.user_roles:
        query.user_roles = user_roles

    # Check if LangGraph is enabled → uses ReAct agent graph (default behavior)
    from app.agents.langgraph import (
        is_langgraph_enabled, stream_react_query,
    )

    if not is_langgraph_enabled():
        raise HTTPException(
            status_code=500,
            detail="Legacy Emma engine has been removed. LangGraph is the only orchestration engine.",
        )

    logger.info(f"LangGraph ReAct streaming (user={query.user_id})")
    return StreamingResponse(
        _generate_langgraph_sse(query, stream_react_query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ResumeRequest(BaseModel):
    """Request to resume a paused graph (HITL interrupt).

    resume_value accepts:
    - str: legacy confirm/cancel strings (backwards compat)
    - dict: HITLDecision object (approve/edit/reject with optional args)
    """
    thread_id: str = Field(..., description="Thread ID of the paused graph")
    resume_value: Any = Field(..., description="User's decision — string (legacy) or dict (HITLDecision)")
    user_id: Optional[str] = Field(None, description="User identifier")


@router.post("/query/resume/stream")
async def emma_query_resume_stream(
    body: ResumeRequest,
    user_roles: List[str] = Depends(extract_user_roles),
    header_user_id: Optional[str] = Depends(extract_user_id),
    _: bool = Depends(verify_api_key),
):
    """Resume a paused ReAct graph after a HITL interrupt (e.g., clarification).

    Uses LangGraph Command(resume=value) to continue graph execution from
    where interrupt() paused it. The graph resumes with the user's selection
    and continues the normal ReAct pipeline.

    SSE events are identical to /query/stream (token, complete, etc.).
    """
    from app.agents.langgraph import is_langgraph_enabled
    from app.agents.langgraph.api import resume_react_query

    if not is_emma_enabled():
        raise HTTPException(status_code=503, detail="Emma is not enabled")

    if not is_langgraph_enabled():
        raise HTTPException(status_code=400, detail="LangGraph not enabled")

    resolved_user_id = body.user_id or header_user_id

    async def generate_resume_sse() -> AsyncGenerator[str, None]:
        async for event in resume_react_query(
            thread_id=body.thread_id,
            resume_value=body.resume_value,
            user_id=resolved_user_id,
            user_roles=user_roles,
        ):
            event_type = event.get("type", "")
            data = event.get("data", {})

            if event_type == "started":
                yield f"event: start\ndata: {_dumps({'message': 'Procesando selección...', 'progress': 0, 'thread_id': data.get('thread_id')})}\n\n"
            elif event_type == "thinking":
                yield f"event: agent_reasoning\ndata: {_dumps({'type': 'thinking', 'content': data.get('content', ''), 'isThinking': True})}\n\n"
            elif event_type == "tool_call":
                yield f"event: agent_reasoning\ndata: {_dumps({'type': 'searching', 'content': data.get('content', ''), 'isThinking': True})}\n\n"
            elif event_type == "tool_result":
                yield f"event: agent_reasoning\ndata: {_dumps({'type': 'search_result', 'content': data.get('content', ''), 'isThinking': True})}\n\n"
            elif event_type == "reasoning_step":
                yield f"event: agent_reasoning\ndata: {_dumps({'type': data.get('step_type', 'analyzing'), 'content': data.get('content', ''), 'isThinking': True})}\n\n"
            elif event_type == "token":
                yield f"event: token\ndata: {_dumps({'text': data.get('text', ''), 'token': data.get('token', '')})}\n\n"
            elif event_type == "complete":
                yield f"event: complete\ndata: {_dumps({'success': data.get('success', True), 'answer': data.get('answer', ''), 'sources': data.get('sources', []), 'execution_time_ms': data.get('latency_ms', 0), 'session_id': data.get('thread_id')})}\n\n"
            elif event_type in ("clarification", "confirmation", "hitl_review"):
                # Dispatch the actual interrupt type from the data payload
                actual_type = event_type
                if isinstance(data, dict):
                    actual_type = data.get("type", event_type)
                yield f"event: {actual_type}\ndata: {_dumps({**data, 'thread_id': data.get('thread_id', thread_id)})}\n\n"
                return
            elif event_type == "error":
                yield f"event: error\ndata: {_dumps({'error': 'Lo siento, hubo un problema temporal. Por favor, inténtalo de nuevo.'})}\n\n"

            await asyncio.sleep(0)

    return StreamingResponse(
        generate_resume_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check Emma health status (LangGraph orchestration).

    Returns:
    - LLM connection status
    - Enabled features
    """
    try:
        from app.agents.llm_models import get_chat_model

        # Check LLM connection by verifying model is available
        llm_connected = False
        try:
            model = get_chat_model()
            llm_connected = model is not None
        except Exception:
            pass

        return HealthResponse(
            status="healthy" if llm_connected else "degraded",
            version="2.0",
            llm_connected=llm_connected,
            orchestration="LangGraph",
            features={
                "emma_enabled": is_emma_enabled(),
                "langgraph_enabled": True,
                "user_memory_enabled": settings.user_memory_enabled,
                "swarm_enabled": settings.swarm_enabled,
            },
        )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="unhealthy",
            version="2.0",
            llm_connected=False,
            features={"error": str(e)},
        )


# =============================================================================
# CENDOJ Toggle Endpoints
# =============================================================================

@router.get("/cendoj/status", response_model=CendojStatusResponse)
async def cendoj_status(_: bool = Depends(verify_api_key)):
    """Get CENDOJ jurisprudence search status."""
    enabled = await _get_cendoj_enabled()
    return CendojStatusResponse(
        enabled=enabled,
        sector=settings.active_sector or "none",
        docker_image="nouxcube-cendoj-agent",
    )


@router.patch("/cendoj/status", response_model=CendojStatusResponse)
async def update_cendoj_status(
    body: CendojStatusUpdate,
    _: bool = Depends(verify_api_key),
):
    """Toggle CENDOJ jurisprudence search on/off (persisted in Redis)."""
    try:
        r = await _get_cendoj_redis()
        await r.set(CENDOJ_REDIS_KEY, str(body.enabled).lower())
        logger.info(f"CENDOJ toggled to {body.enabled}")
    except Exception as e:
        logger.error(f"Failed to write CENDOJ toggle to Redis: {e}")
        raise HTTPException(status_code=500, detail="Failed to update CENDOJ status")

    return CendojStatusResponse(
        enabled=body.enabled,
        sector=settings.active_sector or "none",
        docker_image="nouxcube-cendoj-agent",
    )


# =============================================================================
# Session Persistence Endpoints
# =============================================================================

@router.post("/sessions")
async def create_session(
    body: EmmaSessionCreate,
    user_id: str = Query(..., description="User ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Create a new empty Emma session.

    Used by the frontend to create a session before the first query,
    so the sidebar can show it immediately. The session_id returned
    should be used as thread_id in subsequent /query calls.
    """
    persistence = get_emma_persistence_service()

    result = await persistence.create_session(
        user_id=user_id,
        session_id=body.session_id,
        title=body.title,
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return result


@router.get("/sessions", response_model=EmmaSessionListResponse)
async def list_sessions(
    user_id: str = Query(..., description="User ID"),
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
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )

    return EmmaSessionListResponse(**result)


@router.get("/sessions/{session_id}", response_model=EmmaSessionResponse)
async def get_session(
    session_id: str,
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

    return EmmaSessionResponse(**session)


@router.post("/sessions/{session_id}/continue")
async def continue_session(
    session_id: str,
    _: bool = Depends(verify_api_key),
):
    """
    Continue an old Emma session.

    Returns SSE stream with session restoration events, matching the
    same event format used by /query/stream so the SDK can handle
    both endpoints uniformly.

    Events emitted:
    - start: Session restoration initiated
    - complete: Session restored successfully (includes session data)
    - error: Restoration failed
    """
    persistence = get_emma_persistence_service()

    async def _generate_sse():
        try:
            # Check if session exists
            session = await persistence.get_session(session_id)
            if not session:
                yield f"event: error\ndata: {json.dumps({'error': f'Session {session_id} not found', 'success': False})}\n\n"
                return

            yield f"event: start\ndata: {json.dumps({'message': 'Restoring session...', 'session_id': session_id})}\n\n"

            # Check if already in Redis
            in_redis = await persistence.session_exists_in_redis(session_id)

            if not in_redis:
                loaded = await persistence.load_session_to_redis(session_id)
                if not loaded:
                    yield f"event: error\ndata: {json.dumps({'error': 'Failed to load session to cache', 'success': False})}\n\n"
                    return

            yield f"event: complete\ndata: {json.dumps({'success': True, 'session_id': session_id, 'message_count': session['message_count'], 'loaded_to_redis': not in_redis, 'message': 'Session restored' if not in_redis else 'Session already active'})}\n\n"

        except Exception as e:
            logger.error(f"Session continue SSE error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'success': False})}\n\n"

    return StreamingResponse(
        _generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.api_route("/sessions/{session_id}/history", methods=["GET", "POST"])
async def get_session_history(
    session_id: str,
    limit: int = Query(10, ge=1, le=50, description="Max state snapshots to return"),
    _: bool = Depends(verify_api_key),
):
    """
    Get LangGraph checkpoint history for a session.

    Returns state snapshots in the format expected by the LangGraph SDK's
    useStream hook (fetchStateHistory: true). Each snapshot contains the
    graph state at a checkpoint boundary.

    Returns [] if the session has no checkpoints yet or if the checkpointer
    is disabled.
    """
    from app.core.checkpointer import get_checkpointer
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

    # Sessions created implicitly by the checkpointer may not have an
    # emma_sessions row yet — the checkpointer itself is keyed by
    # thread_id only.
    persistence = get_emma_persistence_service()
    await persistence.get_session(session_id)

    checkpointer = await get_checkpointer()
    if checkpointer is None:
        return []

    config = {"configurable": {"thread_id": session_id}}
    snapshots = []

    try:
        async for state in checkpointer.alist(config, limit=limit):
            # CheckpointTuple has: config, checkpoint, metadata, parent_config
            # checkpoint is a dict with channel_values containing the graph state
            ckpt = state.checkpoint or {}
            channel = ckpt.get("channel_values", {})

            # Convert LangChain messages to SDK-compatible format
            messages = []
            for msg in channel.get("messages", []):
                if isinstance(msg, HumanMessage):
                    messages.append({"type": "human", "content": msg.content, "id": getattr(msg, "id", None)})
                elif isinstance(msg, AIMessage):
                    entry = {"type": "ai", "content": msg.content or "", "id": getattr(msg, "id", None)}
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        entry["tool_calls"] = msg.tool_calls
                    messages.append(entry)
                elif isinstance(msg, ToolMessage):
                    messages.append({
                        "type": "tool",
                        "content": msg.content or "",
                        "tool_call_id": getattr(msg, "tool_call_id", None),
                        "id": getattr(msg, "id", None),
                    })

            # Build checkpoint info from config
            cp = state.config.get("configurable", {})
            parent_cp = state.parent_config.get("configurable", {}) if state.parent_config else None

            snapshots.append({
                "values": {"messages": messages},
                "next": [],
                "config": {
                    "configurable": {
                        "thread_id": cp.get("thread_id", session_id),
                        "checkpoint_ns": cp.get("checkpoint_ns", ""),
                        "checkpoint_id": cp.get("checkpoint_id", ""),
                    }
                },
                "metadata": state.metadata or {},
                "created_at": ckpt.get("ts"),
                "parent_config": {
                    "configurable": {
                        "thread_id": parent_cp.get("thread_id", session_id),
                        "checkpoint_ns": parent_cp.get("checkpoint_ns", ""),
                        "checkpoint_id": parent_cp.get("checkpoint_id", ""),
                    }
                } if parent_cp else None,
                "checkpoint": {
                    "thread_id": cp.get("thread_id", session_id),
                    "checkpoint_ns": cp.get("checkpoint_ns", ""),
                    "checkpoint_id": cp.get("checkpoint_id", ""),
                },
            })
    except Exception as e:
        logger.error(f"Failed to get session history for {session_id}: {e}")
        return []

    return snapshots


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    update: EmmaSessionUpdate,
    user_id: str = Query(..., description="User ID"),
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
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Update
    updated = await persistence.update_session(
        session_id=session_id,
        user_id=user_id,
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
    if session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Delete
    deleted = await persistence.delete_session(
        session_id=session_id,
        user_id=user_id,
    )

    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete session")

    return {"success": True, "message": "Session deleted"}


# =============================================================================
# User Memory (Cross-Session Facts) Endpoints
# =============================================================================

class UserFactResponse(BaseModel):
    """A single user memory fact."""
    id: Optional[str] = None
    category: str
    fact_key: str
    fact_value: str
    confidence: float = 1.0
    source: str = "declared"


class UserFactsListResponse(BaseModel):
    """Response listing user memory facts."""
    facts: List[UserFactResponse]
    count: int


@router.get("/memory/facts", response_model=UserFactsListResponse)
async def list_user_facts(
    user_id: str = Query(..., description="User ID"),
    _: bool = Depends(verify_api_key),
):
    """
    List all active memory facts for a user.

    Returns facts Emma has learned about the user across conversations,
    such as name, department, preferences, and interests.
    """
    from app.services.memory.user_facts import get_user_facts_service

    service = get_user_facts_service()
    facts = await service.get_user_facts(user_id)

    return UserFactsListResponse(
        facts=[UserFactResponse(**f) for f in facts],
        count=len(facts),
    )


@router.delete("/memory/facts")
async def clear_user_facts(
    user_id: str = Query(..., description="User ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Delete ALL memory facts for a user (GDPR right-to-erasure).

    This permanently removes all facts Emma has learned about the user.
    After this call, Emma will not remember anything from previous conversations.
    """
    from app.services.memory.user_facts import get_user_facts_service

    service = get_user_facts_service()
    count = await service.clear_user_facts(user_id)

    return {"success": True, "deleted_count": count, "message": f"Cleared {count} facts"}


@router.delete("/memory/facts/{fact_id:path}")
async def delete_user_fact(
    fact_id: str,
    user_id: str = Query(..., description="User ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Delete a single memory fact by ID.

    Soft-deletes the fact (marks as inactive). The fact will no longer
    be included in Emma's context for future conversations.
    """
    from app.services.memory.user_facts import get_user_facts_service

    service = get_user_facts_service()
    deleted = await service.delete_fact(user_id, fact_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found or already deleted")

    return {"success": True, "message": "Fact deleted"}


# ============================================================================
# Document Memory Generation (MemoRAG)
# ============================================================================

class GenerateMemoryRequest(BaseModel):
    document_id: str
    document_text: str = Field(..., description="Full or partial document text")
    filename: str = Field("", description="Document filename")
    semantic_type: str = Field("", description="Document type")


@router.post("/memory/generate")
async def generate_document_memory(
    request: GenerateMemoryRequest,
    _: bool = Depends(verify_api_key),
):
    """
    Generate and store a document memory using the planner LLM.

    Called by weaviate-service after document indexing. The planner model
    generates a compact summary + key entities + key topics, then stores
    the result in the knowledge graph via knowledge-tree-service.

    This is a fire-and-forget call — indexing should not block on this.
    """
    from app.services.memory.memory_generator import generate_and_store_memory

    result = await generate_and_store_memory(
        document_id=request.document_id,
        document_text=request.document_text,
        filename=request.filename,
        semantic_type=request.semantic_type,
    )
    return result


# ============================================================================
# MemoRAG Memorize (DEPRECATED — no-op, kept for backward compatibility)
# ============================================================================

class MemorizeRequest(BaseModel):
    document_id: str
    document_text: str = Field("", description="Full or partial document text")
    filename: str = Field("", description="Document filename")
    semantic_type: str = Field("", description="Document type")


@router.post("/memorag/memorize")
async def memorag_memorize(
    request: MemorizeRequest,
    _: bool = Depends(verify_api_key),
):
    """No-op: documents are already indexed in Weaviate by the indexing pipeline.

    Kept for backward compatibility — callers (weaviate-service) may still
    hit this endpoint during rolling deployments.
    """
    return {"success": True, "skipped": True, "document_id": request.document_id}


# ============================================================================
# Proactive Welcome Message
# ============================================================================

@router.get("/welcome")
async def get_welcome_message(
    user_id: str = Query(..., description="User ID"),
    user_name: str = Query("", description="User display name"),
    _: bool = Depends(verify_api_key),
):
    """
    Generate a personalized, proactive welcome message for the user.

    Gathers user context (memory facts, recent sessions) and uses the LLM
    to produce a short, contextual greeting that references the user's
    recent activity or interests.

    Returns:
        {message: str, personalized: bool}
    """
    import redis.asyncio as aioredis

    # Check Redis cache first (1h TTL per user)
    cache_key = f"emma:welcome:{user_id}"
    redis_client = None
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        cached = await redis_client.get(cache_key)
        if cached:
            await redis_client.aclose()
            return {"message": cached, "personalized": True}
    except Exception:
        redis_client = None

    # Gather context
    context_parts = []

    # 1. User memory facts
    try:
        from app.services.memory.user_facts import get_user_facts_service
        facts_service = get_user_facts_service()
        facts = await facts_service.get_user_facts(user_id)
        if facts:
            fact_lines = [f"- {f['fact_key']}: {f['fact_value']}" for f in facts if f.get('fact_value')]
            if fact_lines:
                context_parts.append("Datos del usuario:\n" + "\n".join(fact_lines))
    except Exception as e:
        logger.debug(f"Welcome: facts load skipped: {e}")

    # 2. Recent sessions (last 3)
    try:
        persistence = get_emma_persistence_service()
        sessions_result = await persistence.get_user_sessions(
            user_id=user_id,
            include_archived=False, limit=3, offset=0,
        )
        sessions = sessions_result.get("sessions", [])
        if sessions:
            session_lines = []
            for s in sessions:
                title = s.get("title", "")
                first_msg = s.get("first_message_preview", "")
                last_msg = s.get("last_message_preview", "")
                # Build a meaningful description of what the session was about
                parts = []
                if title and title.lower() not in ("nueva conversación", "hola", "hola emma"):
                    parts.append(f"Tema: {title}")
                if first_msg:
                    parts.append(f"Pregunta: {first_msg}")
                if last_msg and last_msg != first_msg:
                    parts.append(f"Última respuesta: {last_msg}")
                if parts:
                    session_lines.append("- " + " | ".join(parts))
            if session_lines:
                context_parts.append("Conversaciones recientes:\n" + "\n".join(session_lines))
    except Exception as e:
        logger.debug(f"Welcome: sessions load skipped: {e}")

    # If no context at all, return simple greeting
    first_name = user_name.split()[0] if user_name else ""
    if not context_parts:
        fallback = f"¡Hola{' ' + first_name if first_name else ''}! ¿En qué puedo ayudarte hoy?"
        return {"message": fallback, "personalized": False}

    # 3. Generate via LLM
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        system_prompt = (
            "Eres Emma, asistente de inteligencia empresarial. "
            "Genera un saludo de bienvenida BREVE (1-2 frases, máximo 30 palabras). "
            "Usa el nombre de pila del usuario (NO el apellido). "
            "Sé proactiva: menciona algo de su actividad reciente o sugiere continuar con algo. "
            "Tono cálido y profesional. No uses emojis excesivos (máximo 1). "
            "Responde SOLO con el saludo, sin explicaciones."
        )

        user_prompt = f"Nombre del usuario: {user_name or 'desconocido'}\n\n"
        user_prompt += "\n\n".join(context_parts)
        logger.info(f"Welcome context for {user_name}: {context_parts}")

        model = get_planner_model().bind(temperature=0.7, max_tokens=80)
        response = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        welcome_msg = response.content.strip().strip('"')

        # Cache for 1 hour
        if redis_client and welcome_msg:
            try:
                await redis_client.setex(cache_key, 3600, welcome_msg)
                await redis_client.aclose()
            except Exception:
                pass

        return {"message": welcome_msg, "personalized": True}

    except Exception as e:
        logger.warning(f"Welcome LLM generation failed: {e}")
        fallback = f"¡Hola{' ' + first_name if first_name else ''}! ¿En qué puedo ayudarte hoy?"
        return {"message": fallback, "personalized": False}
