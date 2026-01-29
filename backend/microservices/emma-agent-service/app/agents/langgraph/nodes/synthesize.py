"""
SYNTHESIZE Node - Emma's Result Synthesis

This node combines results from all specialist agents into
a coherent final answer with proper citations.

Responsibilities:
1. Aggregate results from agent_results
2. Handle partial failures (some agents succeeded, some failed)
3. Generate coherent synthesis with LLM
4. Extract and format source citations
5. Handle retry logic if all agents failed

Design Decisions:
1. Use LLM for synthesis to ensure coherent narrative
2. Maintain source citations from individual agents
3. Graceful degradation on partial failures
4. Support retry with general_agent as fallback
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from ..state import RAGState, AgentResult

logger = logging.getLogger(__name__)

# Synthesis System Prompt
SYNTHESIS_PROMPT = """Eres Emma, asistente de IA para gestión documental.

Tu tarea es sintetizar las respuestas de múltiples agentes especializados en una respuesta coherente y completa.

Directrices de síntesis:
1. **Coherencia**: Combina la información de forma lógica y fluida
2. **Completitud**: Incluye todos los puntos relevantes de cada agente
3. **Citas**: Mantén las referencias legales y citas de documentos
4. **Conflictos**: Si hay información contradictoria, señálalo
5. **Claridad**: Usa un lenguaje claro y accesible

Formato de respuesta:
- Respuesta principal (sin encabezados para respuestas cortas)
- Para respuestas largas, usa encabezados apropiados
- Lista de fuentes al final si hay citas específicas

Responde SIEMPRE en español."""


async def synthesize_node(state: RAGState) -> Dict[str, Any]:
    """
    Synthesize results from all specialist agents.

    This node:
    1. Collects results from agent_results
    2. Handles errors and partial failures
    3. Uses LLM to create coherent synthesis
    4. Formats final answer with citations

    Args:
        state: Current RAG state with agent_results

    Returns:
        State updates: final_answer, sources, success
    """
    start_time = time.time()
    query = state.get("query", "")
    agent_results = state.get("agent_results", {})
    agent_errors = state.get("agent_errors", {})
    retrieved_docs = state.get("retrieved_docs", [])
    retry_count = state.get("retry_count", 0)

    logger.info(
        f"📝 SYNTHESIZE: {len(agent_results)} results, "
        f"{len(agent_errors)} errors"
    )

    # Check if SLM already provided answer
    if state.get("fast_path_used") and state.get("fast_path_answer"):
        logger.info("⚡ Using fast-path answer")
        return {
            "final_answer": state.get("fast_path_answer"),
            "sources": [],
            "success": True,
            "total_latency_ms": (time.time() - start_time) * 1000,
        }

    # Try MEN service for sector-specialized generation
    men_answer = await _try_men_synthesis(query, agent_results, retrieved_docs, state)
    if men_answer:
        sources = _extract_sources(agent_results, retrieved_docs)
        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ SYNTHESIZE (MEN): Completed in {latency_ms:.1f}ms")
        return {
            "final_answer": men_answer,
            "sources": sources,
            "success": True,
            "total_latency_ms": latency_ms,
            "messages": [AIMessage(content=men_answer)],
            "metadata": {
                **state.get("metadata", {}),
                "synthesis_method": "men_service",
                "synthesis_latency_ms": latency_ms,
            },
        }

    # Handle complete failure - always generate a fallback response
    # (Graph doesn't support retry loops, so we just generate best response we can)
    if not agent_results and agent_errors:
        logger.warning("❌ All agents failed, generating fallback response")
        fallback = _generate_fallback_response(query, retrieved_docs, agent_errors)
        return {
            "final_answer": fallback,
            "sources": [],
            "success": False,
            "metadata": {
                **state.get("metadata", {}),
                "fallback_used": True,
                "errors": agent_errors,
            },
        }

    # Handle no results at all
    if not agent_results:
        logger.warning("❌ No agent results, generating fallback")
        fallback = _generate_fallback_response(query, retrieved_docs, {})
        return {
            "final_answer": fallback,
            "sources": [],
            "success": False,
        }

    # Synthesize results
    try:
        if len(agent_results) == 1:
            # Single agent - use directly with minor formatting
            final_answer = _format_single_result(agent_results, retrieved_docs)
        else:
            # Multiple agents - use LLM synthesis
            final_answer = await _llm_synthesis(
                query, agent_results, retrieved_docs
            )

        # Extract sources
        sources = _extract_sources(agent_results, retrieved_docs)

        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ SYNTHESIZE: Completed in {latency_ms:.1f}ms")

        return {
            "final_answer": final_answer,
            "sources": sources,
            "success": True,
            "total_latency_ms": state.get("metadata", {}).get("retrieval_latency_ms", 0) + latency_ms,
            "messages": [AIMessage(content=final_answer)],
            "metadata": {
                **state.get("metadata", {}),
                "synthesis_latency_ms": latency_ms,
                "agents_used": list(agent_results.keys()),
            },
        }

    except Exception as e:
        logger.error(f"❌ SYNTHESIZE failed: {e}")
        latency_ms = (time.time() - start_time) * 1000

        # Fallback to raw concatenation
        fallback = _concatenate_results(agent_results)

        return {
            "final_answer": fallback,
            "sources": _extract_sources(agent_results, retrieved_docs),
            "success": True,  # Partial success
            "metadata": {
                **state.get("metadata", {}),
                "synthesis_error": str(e),
                "synthesis_latency_ms": latency_ms,
            },
        }


def _format_single_result(
    agent_results: Dict[str, AgentResult],
    retrieved_docs: List[Dict],
) -> str:
    """Format single agent result with sources."""
    agent_name, result = next(iter(agent_results.items()))

    output = result.get("output", "") if isinstance(result, dict) else result.output

    # Add sources if available
    sources = result.get("sources", []) if isinstance(result, dict) else result.sources
    if sources:
        output += "\n\n**Fuentes**:\n"
        for source in sources[:5]:
            output += f"- {source}\n"

    return output


def _concatenate_results(agent_results: Dict[str, AgentResult]) -> str:
    """Simple concatenation of results (fallback)."""
    parts = []

    for agent_name, result in agent_results.items():
        output = result.get("output", "") if isinstance(result, dict) else result.output
        if output:
            # Clean agent name for display
            display_name = agent_name.replace("_agent", "").title()
            parts.append(f"**{display_name}**:\n{output}")

    return "\n\n".join(parts)


async def _llm_synthesis(
    query: str,
    agent_results: Dict[str, AgentResult],
    retrieved_docs: List[Dict],
) -> str:
    """
    Use LLM to synthesize multiple agent results.

    Creates a coherent narrative from potentially
    overlapping or complementary agent outputs.
    """
    try:
        from app.agents.llm_client import get_llm_client

        llm_client = await get_llm_client()

        # Build synthesis prompt
        results_text = []
        for agent_name, result in agent_results.items():
            output = result.get("output", "") if isinstance(result, dict) else result.output
            tools = result.get("tools_used", []) if isinstance(result, dict) else result.tools_used

            display_name = agent_name.replace("_agent", "").title()
            results_text.append(
                f"### Agente {display_name}\n"
                f"Herramientas usadas: {', '.join(tools) if tools else 'ninguna'}\n\n"
                f"{output}"
            )

        # Build document context summary
        doc_summary = ""
        if retrieved_docs:
            doc_titles = [d.get("title", "Sin título") for d in retrieved_docs[:5]]
            doc_summary = f"Documentos consultados: {', '.join(doc_titles)}"

        user_message = f"""**Pregunta del usuario**: {query}

**Resultados de los agentes especializados**:

{chr(10).join(results_text)}

**Contexto documental**: {doc_summary if doc_summary else 'Sin documentos específicos'}

Por favor, sintetiza esta información en una respuesta coherente y completa."""

        messages = [
            {"role": "system", "content": SYNTHESIS_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = await llm_client.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        if response and response.content:
            return response.content

        # Fallback to concatenation
        return _concatenate_results(agent_results)

    except Exception as e:
        logger.warning(f"LLM synthesis failed: {e}")
        return _concatenate_results(agent_results)


def _extract_sources(
    agent_results: Dict[str, AgentResult],
    retrieved_docs: List[Dict],
) -> List[Dict[str, Any]]:
    """Extract and deduplicate sources from all agents."""
    sources = []
    seen_ids = set()

    # From agent results
    for result in agent_results.values():
        agent_sources = result.get("sources", []) if isinstance(result, dict) else result.sources
        for source in agent_sources:
            if isinstance(source, str) and source not in seen_ids:
                sources.append({"title": source, "type": "agent_citation"})
                seen_ids.add(source)
            elif isinstance(source, dict):
                source_id = source.get("id", source.get("title", ""))
                if source_id and source_id not in seen_ids:
                    sources.append(source)
                    seen_ids.add(source_id)

    # From retrieved docs (if not already cited)
    for doc in retrieved_docs[:5]:
        doc_id = doc.get("id", "")
        if doc_id and doc_id not in seen_ids:
            sources.append({
                "id": doc_id,
                "title": doc.get("title", "Documento"),
                "type": "retrieved",
                "score": doc.get("score", 0.0),
            })
            seen_ids.add(doc_id)

    return sources


def _generate_fallback_response(
    query: str,
    retrieved_docs: List[Dict],
    errors: Dict[str, str],
) -> str:
    """Generate fallback response when all agents fail."""
    response = f"""Lo siento, no pude procesar completamente tu consulta: "{query}"

"""

    if retrieved_docs:
        response += "Sin embargo, encontré estos documentos relacionados:\n\n"
        for i, doc in enumerate(retrieved_docs[:3], 1):
            title = doc.get("title", "Sin título")
            score = doc.get("score", 0.0)
            preview = doc.get("content", "")[:150]
            response += f"{i}. **{title}** (relevancia: {score:.2f})\n   {preview}...\n\n"

        response += "¿Te gustaría que explore alguno de estos documentos en detalle?"
    else:
        response += """No encontré documentos relacionados con tu consulta.

Sugerencias:
- Intenta reformular tu pregunta con términos más específicos
- Verifica que los documentos relevantes estén en tu repositorio
- Consulta con términos alternativos o sinónimos"""

    return response


async def _try_men_synthesis(
    query: str,
    agent_results: Dict[str, AgentResult],
    retrieved_docs: List[Dict],
    state: Dict[str, Any],
) -> Optional[str]:
    """
    Try to use MEN (Mixture of Experts Network) service for synthesis.

    Only used when ACTIVE_SECTOR and MEN_ENABLED are both configured.
    The MEN service skips domain classification because the sector
    already defines the domain.

    Returns:
        Synthesized answer string, or None if MEN is unavailable/disabled.
    """
    sector_config = state.get("sector_config")
    if not sector_config:
        return None

    try:
        from app.core.config import settings

        if not settings.men_enabled:
            return None

        import httpx

        # Build context from agent results
        context_parts = []
        for agent_name, result in agent_results.items():
            output = result.get("output", "") if isinstance(result, dict) else result.output
            if output:
                context_parts.append(output)

        # Add retrieved doc context
        for doc in retrieved_docs[:5]:
            content = doc.get("content", "")
            if content:
                context_parts.append(content[:500])

        context = "\n\n".join(context_parts)

        men_domain = sector_config.get("men_domain", "general")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.men_service_url}/men/query",
                json={
                    "query": query,
                    "context": context,
                    "domain": men_domain,
                    "tenant_id": state.get("tenant_id", ""),
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )

            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                if answer:
                    logger.info(f"🧠 MEN synthesis successful (domain={men_domain})")
                    return answer

    except Exception as e:
        logger.warning(f"MEN synthesis failed, falling back to standard: {e}")

    return None
