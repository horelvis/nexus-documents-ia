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
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from ..state import RAGState, AgentResult
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)

# ─── Sector generation prompt loader (cached) ────────────────────────────────
_SECTOR_PROMPTS_CACHE: Optional[Dict] = None


def _load_sector_prompts() -> Dict:
    """Load sector prompts from emma_prompts.yaml (cached)."""
    global _SECTOR_PROMPTS_CACHE
    if _SECTOR_PROMPTS_CACHE is not None:
        return _SECTOR_PROMPTS_CACHE

    candidates = [
        Path("/app/config/prompts/emma_prompts.yaml"),
        Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
    ]
    for p in candidates:
        if p.exists():
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                _SECTOR_PROMPTS_CACHE = data.get("sectors", {})
                return _SECTOR_PROMPTS_CACHE
            except Exception as e:
                logger.warning(f"Failed to load sector prompts: {e}")

    _SECTOR_PROMPTS_CACHE = {}
    return _SECTOR_PROMPTS_CACHE


def _get_sector_generation_prompt(state: RAGState) -> str:
    """Get the sector generation_prompt from state's sector_config."""
    sector_config = state.get("sector_config")
    if not sector_config:
        return ""

    prompt_key = sector_config.get("system_prompt_key", "")
    if not prompt_key:
        return ""

    sector_key = prompt_key.replace("sectors.", "")
    prompts = _load_sector_prompts()
    return prompts.get(sector_key, {}).get("generation_prompt", "")

# Synthesis System Prompt — fallback when YAML system_prompts.synthesis is absent
_SYNTHESIS_PROMPT_FALLBACK = """Eres Emma, asistente de IA especializada en gestión documental y derecho español.

Tu tarea es sintetizar las respuestas de múltiples agentes especializados en una respuesta coherente y completa.

Directrices de síntesis:
1. **Conocimiento propio + documentos**: Utiliza los documentos recuperados como APOYO y VERIFICACIÓN, no como fuente exclusiva. Si tu conocimiento jurídico es más completo o preciso que los fragmentos recuperados, prioriza tu conocimiento e indica las fuentes legislativas correspondientes. Los documentos recuperados pueden ser parciales o tangencialmente relacionados.
2. **Coherencia**: Combina la información de forma lógica y fluida
3. **Completitud**: Incluye todos los puntos relevantes de cada agente
4. **Citas legales**: Cita siempre la legislación aplicable (ley, artículo, real decreto) aunque no aparezca literalmente en los documentos recuperados
5. **Conflictos**: Si hay información contradictoria entre documentos y tu conocimiento, prioriza la legislación vigente y señala la discrepancia
6. **Claridad**: Usa un lenguaje claro y accesible

Formato de respuesta:
- Respuesta principal (sin encabezados para respuestas cortas)
- Para respuestas largas, usa encabezados apropiados
- Lista de fuentes al final si hay citas específicas

Responde SIEMPRE en español."""


def _get_synthesis_prompt(state: Optional[RAGState] = None) -> str:
    """Load synthesis prompt from YAML via PromptEngine, with fallback."""
    if state:
        from ..prompt_engine import get_prompt_engine
        engine = get_prompt_engine()
        prompt = engine.render_system_prompt("synthesis", state)
        if prompt:
            return prompt
    return _SYNTHESIS_PROMPT_FALLBACK


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
    tracker = ReasoningTracker()
    tracker.set_source("synthesize")

    tracker.add_step(
        StepType.TRANSFORMATION,
        "Generando respuesta final...",
        confidence=1.0,
    )

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
        # Document generation: passthrough docgen_agent output without re-synthesis.
        # Re-processing a generated legal document through the synthesis LLM would
        # summarize/compress it, losing clauses, formatting, and legal references.
        if "docgen_agent" in agent_results:
            docgen_result = agent_results["docgen_agent"]
            docgen_output = (
                docgen_result.get("output", "")
                if isinstance(docgen_result, dict)
                else docgen_result.output
            )
            if docgen_output and len(docgen_output.strip()) > 100:
                logger.info("📄 SYNTHESIZE: Passthrough docgen_agent output (no re-synthesis)")
                final_answer = docgen_output
            else:
                # Docgen produced empty/short output — fall through to normal synthesis
                final_answer = None
        else:
            final_answer = None

        if final_answer is None:
            if len(agent_results) == 1:
                # Single agent - use directly with minor formatting
                final_answer = _format_single_result(agent_results, retrieved_docs)
            else:
                # Multiple agents - concatenate with headers (no LLM re-synthesis)
                final_answer = _concatenate_with_headers(agent_results, retrieved_docs)

        # Extract sources
        sources = _extract_sources(agent_results, retrieved_docs)

        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ SYNTHESIZE: Completed in {latency_ms:.1f}ms")

        tracker.add_step(
            StepType.RESPONSE,
            f"Respuesta generada en {latency_ms:.0f}ms",
            confidence=1.0,
        )

        return {
            "final_answer": final_answer,
            "sources": sources,
            "success": True,
            "total_latency_ms": state.get("metadata", {}).get("retrieval_latency_ms", 0) + latency_ms,
            "messages": [AIMessage(content=final_answer)],
            "reasoning_steps": tracker.get_steps(),
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

    # Add sources if available (deduplicated by title)
    sources = result.get("sources", []) if isinstance(result, dict) else result.sources
    if sources:
        seen = set()
        unique_sources = []
        for source in sources:
            title = source if isinstance(source, str) else source.get("title", str(source))
            if title not in seen:
                seen.add(title)
                unique_sources.append(title)
        if unique_sources:
            output += "\n\n**Fuentes**:\n"
            for source in unique_sources[:5]:
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


def _concatenate_with_headers(
    agent_results: Dict[str, AgentResult],
    retrieved_docs: List[Dict],
) -> str:
    """Concatenate multi-agent results with headers and sources (no LLM call).

    This replaces LLM-based synthesis for multi-agent results, avoiding
    the latency and potential summarisation/compression of specialist outputs.
    """
    parts = []

    for agent_name, result in agent_results.items():
        output = result.get("output", "") if isinstance(result, dict) else result.output
        if not output:
            continue
        display_name = agent_name.replace("_agent", "").replace("_", " ").title()
        parts.append(f"## {display_name}\n\n{output}")

    combined = "\n\n---\n\n".join(parts)

    # Append deduplicated sources
    seen_titles: set[str] = set()
    source_lines: list[str] = []
    for result in agent_results.values():
        sources = result.get("sources", []) if isinstance(result, dict) else result.sources
        for src in sources:
            title = src if isinstance(src, str) else src.get("title", str(src))
            if title not in seen_titles:
                seen_titles.add(title)
                source_lines.append(f"- {title}")
    if source_lines:
        combined += "\n\n**Fuentes**:\n" + "\n".join(source_lines[:8])

    return combined


async def _llm_synthesis(
    query: str,
    agent_results: Dict[str, AgentResult],
    retrieved_docs: List[Dict],
    state: Optional[RAGState] = None,
) -> str:
    """
    Use LLM to synthesize multiple agent results.

    Creates a coherent narrative from potentially
    overlapping or complementary agent outputs.
    """
    try:
        from app.agents.llm_client import get_llm_client
        from app.core.config import Settings

        settings = Settings()
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

        # Inject sector-specific generation prompt if available
        synthesis_prompt = _get_synthesis_prompt(state)
        if state:
            gen_prompt = _get_sector_generation_prompt(state)
            if gen_prompt:
                synthesis_prompt += f"\n\nDirectrices específicas del sector:\n{gen_prompt.strip()}"
                logger.info("🏷️ SYNTHESIZE: Injected sector generation prompt")

        messages = [
            {"role": "system", "content": synthesis_prompt},
            {"role": "user", "content": user_message},
        ]

        response = await llm_client.chat(
            messages=messages,
            temperature=settings.agent_temperature,
            max_tokens=settings.agent_max_tokens,
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

    # From retrieved docs (deduplicated by title to avoid showing
    # multiple chunks of the same document as separate sources)
    seen_titles = set()
    for doc in retrieved_docs:
        title = doc.get("title", "Documento")
        doc_id = doc.get("id", "")
        if title in seen_titles:
            continue
        if doc_id in seen_ids:
            continue
        sources.append({
            "id": doc_id,
            "title": title,
            "type": "retrieved",
            "score": doc.get("score", 0.0),
        })
        seen_ids.add(doc_id)
        seen_titles.add(title)

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


