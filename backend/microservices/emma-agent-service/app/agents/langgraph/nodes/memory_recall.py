"""
Emma ReAct Agent — Memory Recall Node (MemoRAG Phase 4e)

Runs between classify and react_loop/decompose. The planner LLM scans
recalled document memories to generate focused retrieval clues (keywords,
document IDs, entity names) that prime the agent's first search.

Flow:
    1. Extract topic hints from the user query (lightweight regex)
    2. Call knowledge-tree recall_memories() with topic/domain hints
    3. If memories found: planner LLM generates structured clues
    4. Inject clues into state → react_loop reads them in system prompt

If no memories exist, the service is down, or the feature is disabled,
the node passes through transparently (no state changes).
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from ..state import ReActState
from ..reasoning_tracker import StepType

logger = logging.getLogger(__name__)

# Lightweight topic extraction patterns (no LLM needed)
_TOPIC_PATTERNS = [
    # Document types
    (r"\b(factura|contrato|nomina|nómina|expediente|informe|acta|presupuesto|albarán|pedido|recibo|escritura|demanda|sentencia|recurso|convenio|estatuto|reglamento|certificado|circular|propuesta|memoria)\b", None),
    # Legal references
    (r"\b(ley|real decreto|orden|resolución|directiva|reglamento)\b", None),
    # Domain hints
    (r"\b(laboral|fiscal|mercantil|civil|penal|administrativo|compliance|rgpd|protección de datos)\b", None),
    # Person names (capitalized words after de/para/sobre)
    (r"\b(?:de|para|sobre|empleado|trabajador|cliente)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)", None),
]


def _extract_query_topics(query: str) -> List[str]:
    """Extract lightweight topic hints from the query via regex.

    Returns a deduplicated list of topics/entities found in the query.
    These are used to filter document memories before LLM scanning.
    """
    topics = set()
    q_lower = query.lower()

    for pattern, _ in _TOPIC_PATTERNS:
        for match in re.finditer(pattern, q_lower if "A-Z" not in pattern else query, re.IGNORECASE):
            # Use first captured group if exists, else full match
            value = match.group(1) if match.lastindex else match.group(0)
            value = value.strip().lower()
            if len(value) > 2:
                topics.add(value)

    return list(topics)[:10]  # Cap at 10 topics


def _format_memories_for_planner(memories: List[Dict[str, Any]], max_items: int = 20) -> str:
    """Format document summaries into a compact text block for the planner LLM."""
    lines = []
    for mem in memories[:max_items]:
        doc_id = mem.get("document_id", "?")
        summary = mem.get("summary", "")[:200]
        entities = mem.get("key_entities", [])
        topics = mem.get("key_topics", [])

        parts = [f"[{doc_id}] {summary}"]
        if entities:
            parts.append(f"  Entidades: {', '.join(entities[:5])}")
        if topics:
            parts.append(f"  Temas: {', '.join(topics[:5])}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines)


def _format_memorag_for_planner(memories: List[Dict[str, Any]], max_items: int = 20) -> str:
    """Format MemoRAG recall chunks into a compact text block for the planner LLM."""
    lines = []
    for mem in memories[:max_items]:
        doc_id = mem.get("document_id", "?")
        content = mem.get("content", "")[:220]
        metadata = mem.get("metadata", {}) or {}
        domain = metadata.get("domain")
        semantic_type = metadata.get("semantic_type")

        parts = [f"[{doc_id}] {content}"]
        if domain or semantic_type:
            parts.append(f"  Meta: {domain or 'n/a'} | {semantic_type or 'n/a'}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines)


async def _load_clue_system_prompt() -> str:
    """Load memory recall system prompt from Langfuse."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    cached = await client.get_prompt("emma_memory_recall_system")
    return cached.content


async def _generate_clues(query: str, memories_text: str) -> Optional[str]:
    """Call the planner LLM to generate retrieval clues from memories.

    Returns the clue text, or None if generation fails or no relevant clues.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.agents.llm_models import get_planner_model

    system_prompt = await _load_clue_system_prompt()
    user_msg = f"Consulta del usuario: {query}\n\nDocumentos disponibles:\n{memories_text}"

    try:
        lc_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ]
        model = get_planner_model().bind(
            temperature=0.0,
            max_tokens=settings.memory_recall_max_clue_tokens,
        )
        response = await model.ainvoke(lc_messages)
        clues = (response.content or "").strip()

        # Filter out empty or "no clues" responses
        if not clues or "SIN_PISTAS" in clues.upper():
            return None

        return clues

    except Exception as e:
        logger.warning(f"Memory clue generation failed: {e}")
        return None


async def memory_recall_node(state: ReActState) -> Dict[str, Any]:
    """Scan document memories and generate retrieval clues for the ReAct agent.

    This node is lightweight (~50-200ms):
    - Regex topic extraction: ~1ms
    - HTTP recall_memories: ~20-50ms
    - Planner LLM clue generation: ~100-300ms (only if memories found)

    Returns:
        State updates: memory_clues (Optional[str]), reasoning_steps, metadata.
        Returns empty dict if disabled or no memories found (transparent passthrough).
    """
    if not settings.memory_recall_enabled:
        return {}

    start = time.time()
    query = state.get("query", "")
    tenant_id = state.get("tenant_id", "")

    if not query or not tenant_id:
        return {}

    # Step 1: Determine domain from sector config
    domain = None
    sector_config = state.get("sector_config")
    if sector_config:
        domain = sector_config.get("men_domain")

    memories = []
    memorag_used = False

    # Step 2: MemoRAG recall (global memory model)
    if settings.memorag_enabled:
        try:
            from app.services.memorag import get_memorag_service
            service = get_memorag_service()
            results = await service.recall(
                tenant_id=tenant_id,
                query=query,
                limit=settings.memorag_recall_top_k,
                domain=domain,
            )
            if results:
                memories = [
                    {
                        "document_id": r.document_id,
                        "content": r.content,
                        "metadata": r.metadata,
                        "similarity": r.similarity,
                    }
                    for r in results
                ]
                memorag_used = True
        except Exception as e:
            logger.debug(f"MemoRAG recall skipped: {e}")

    # Step 3: Fallback to Memory Bank (summaries)
    if not memories and settings.memory_recall_fallback_enabled:
        topics = _extract_query_topics(query)
        try:
            from app.clients.knowledge_tree_client import get_knowledge_tree_client
            client = get_knowledge_tree_client()
            memories = await client.recall_memories(
                tenant_id=tenant_id,
                query_topics=topics if topics else None,
                domain=domain,
                limit=settings.memory_recall_max_memories,
            )
        except Exception as e:
            logger.debug(f"Memory bank recall skipped: {e}")
            return {}

    if not memories:
        latency_ms = (time.time() - start) * 1000
        logger.debug(f"Memory recall: no memories found ({latency_ms:.0f}ms)")
        return {
            "metadata": {"memory_recall_latency_ms": latency_ms, "memory_recall_count": 0},
        }

    # Step 4: Format memories and generate clues via planner LLM
    if memorag_used:
        memories_text = _format_memorag_for_planner(memories, max_items=settings.memorag_recall_top_k)
    else:
        memories_text = _format_memories_for_planner(memories, max_items=settings.memory_recall_max_memories)
    clues = await _generate_clues(query, memories_text)

    latency_ms = (time.time() - start) * 1000

    if not clues:
        logger.debug(f"Memory recall: {len(memories)} memories scanned, no relevant clues ({latency_ms:.0f}ms)")
        return {
            "metadata": {
                "memory_recall_latency_ms": latency_ms,
                "memory_recall_count": len(memories),
                "memory_recall_clues": False,
            },
        }

    logger.info(f"Memory recall: {len(memories)} memories → clues generated ({latency_ms:.0f}ms)")

    return {
        "memory_clues": clues,
        "reasoning_steps": [{
            "type": StepType.THINKING.value,
            "content": f"Memory recall: {len(memories)} documentos escaneados → pistas de búsqueda generadas",
        }],
        "metadata": {
            "memory_recall_latency_ms": latency_ms,
            "memory_recall_count": len(memories),
            "memory_recall_clues": True,
        },
    }
