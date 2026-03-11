"""
Emma Swarm Agent — Synthesize Swarm Node

Combines results from all parallel swarm workers into a single coherent answer.

Strategies:
- Single successful worker: Use answer directly (no extra LLM call)
- Multiple successful workers: LLM synthesis to merge and integrate
- No successful workers: Return error message

The synthesis prompt instructs the LLM to:
1. Integrate information from all workers naturally
2. Cite sources from each worker
3. Flag contradictions
4. Structure with sections if appropriate
"""

import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from app.core.config import settings
from app.core.langfuse_config import observe
from ..state import ReActState
from ..reasoning_tracker import StepType

logger = logging.getLogger(__name__)

# Fallback synthesis prompt
_SYNTHESIZE_SYSTEM_FALLBACK = """\
Varios agentes han investigado diferentes aspectos de la consulta del usuario.
Combina sus hallazgos en UNA respuesta coherente y completa.

Consulta original: {query}

Resultados de los agentes:
{worker_results_formatted}

Reglas:
- Integra la información de todos los agentes de forma natural
- Cita las fuentes de cada agente
- Si hay contradicciones, señálalas
- Estructura la respuesta con secciones si es apropiado
- No repitas información
- Sé directo y conciso
- Responde en el mismo idioma que la consulta original\
"""


def _format_worker_results(results: List[Dict[str, Any]]) -> str:
    """Format worker results for the synthesis prompt."""
    parts = []
    for r in results:
        focus = r.get("focus", "general")
        answer = r.get("answer", "")
        sources = r.get("sources", [])
        sources_str = ""
        if sources:
            source_names = [
                s.get("title") or s.get("boe_id") or s.get("document_id", "")
                for s in sources[:5]
            ]
            sources_str = f"\n  Fuentes: {', '.join(s for s in source_names if s)}"

        parts.append(
            f"--- Agente [{focus}] ---\n"
            f"Tarea: {r.get('sub_task', '')}\n"
            f"Resultado: {answer}"
            f"{sources_str}"
        )
    return "\n\n".join(parts)


def _deduplicate_sources(all_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate sources by document_id, boe_id, or url."""
    seen = set()
    unique = []
    for src in all_sources:
        key = (
            src.get("document_id")
            or src.get("boe_id")
            or src.get("url")
            or src.get("title", "")
        )
        if key and key not in seen:
            seen.add(key)
            unique.append(src)
        elif not key:
            unique.append(src)
    return unique


@observe(as_type="span", name="synthesize_swarm_node")
async def synthesize_swarm_node(state: ReActState) -> Dict[str, Any]:
    """Combine all worker results into a single coherent answer.

    This node collects swarm_worker_results (merged by reducer),
    synthesizes them via LLM (if multiple), and returns the final answer.

    Returns:
        State updates: final_answer, sources, success, is_complete,
        messages, reasoning_steps, metadata.
        Swarm events emitted via get_stream_writer() (not state).
    """
    start = time.time()
    all_results = state.get("swarm_worker_results", [])
    query = state.get("query", "")
    reasoning_steps = []

    # When checkpointer is active, swarm_worker_results accumulates across
    # turns via merge_lists.  Use the checkpoint offset (set by classify_node)
    # to only process results from the current invocation.
    offset = (state.get("metadata") or {}).get("_checkpoint_offsets", {}).get(
        "swarm_worker_results", 0
    )
    results = all_results[offset:]

    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    if failed:
        logger.warning(
            f"Synthesize swarm: {len(failed)} workers failed: "
            f"{[f.get('error', 'unknown') for f in failed]}"
        )

    # No successful workers — return error
    if not successful:
        reasoning_steps.append({
            "type": StepType.ERROR.value,
            "content": "All swarm workers failed — no results to synthesize",
        })
        return {
            "is_complete": True,
            "final_answer": (
                "No se pudieron obtener resultados. Los agentes encontraron errores "
                "al procesar tu consulta. Intenta reformular la pregunta."
            ),
            "sources": [],
            "success": False,
            "reasoning_steps": reasoning_steps,
            "messages": [AIMessage(content="No se pudieron obtener resultados.")],
            "metadata": {
                "swarm_workers_total": len(results),
                "swarm_workers_failed": len(failed),
            },
        }

    # Collect all sources across workers
    all_sources = []
    for r in successful:
        all_sources.extend(r.get("sources", []))
    unique_sources = _deduplicate_sources(all_sources)

    # Single worker — use answer directly (no synthesis LLM call needed)
    if len(successful) == 1:
        answer = successful[0].get("answer", "")
        latency_ms = (time.time() - start) * 1000

        reasoning_steps.append({
            "type": StepType.RESPONSE.value,
            "content": (
                f"Single worker result — using directly "
                f"({len(unique_sources)} sources, {latency_ms:.0f}ms)"
            ),
        })

        return {
            "is_complete": True,
            "final_answer": answer,
            "sources": unique_sources,
            "success": True,
            "messages": [AIMessage(content=answer)],
            "reasoning_steps": reasoning_steps,
            "metadata": {
                "swarm_workers_total": len(results),
                "swarm_workers_successful": 1,
                "swarm_single_worker": True,
                "synthesize_latency_ms": latency_ms,
            },
        }

    # Multiple workers — LLM synthesis with real token streaming
    reasoning_steps.append({
        "type": StepType.THINKING.value,
        "content": (
            f"Synthesizing {len(successful)} worker results "
            f"({len(unique_sources)} total sources)"
        ),
    })

    # Emit swarm_synthesizing event via stream writer (real-time to frontend)
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
        writer({
            "type": "swarm_synthesizing",
            "data": {
                "successful_workers": len(successful),
                "total_workers": len(results),
            },
        })
    except Exception:
        writer = None  # Fallback: no streaming (e.g., invoke() without stream_mode)

    # Build synthesis prompt
    results_formatted = _format_worker_results(successful)

    prompt_content = None
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        client = get_langfuse_prompt_client()
        prompt = await client.get_prompt(
            "emma_swarm_synthesize",
            variables={
                "query": query,
                "worker_results_formatted": results_formatted,
            },
        )
        if prompt:
            prompt_content = prompt.content
    except Exception as e:
        logger.debug(f"Langfuse prompt fetch failed for synthesis: {e}")

    if not prompt_content:
        prompt_content = _SYNTHESIZE_SYSTEM_FALLBACK.format(
            query=query,
            worker_results_formatted=results_formatted,
        )

    # LLM synthesis — stream tokens in real-time via stream writer
    llm_messages = [
        {"role": "system", "content": prompt_content},
        {"role": "user", "content": f"Sintetiza los resultados para la consulta: {query}"},
    ]

    synthesized_answer = ""
    streamed_tokens = False

    try:
        from app.agents.llm_router import get_llm_router
        from app.agents.llm_client import ModelRole
        router = await get_llm_router()
        llm_kwargs = {
            "messages": llm_messages,
            "max_tokens": settings.react_max_completion_tokens,
            "role": ModelRole.CHAT,
        }
        per_request_thinking = state.get("enable_thinking")
        if per_request_thinking is not None:
            llm_kwargs["enable_thinking"] = per_request_thinking

        # Stream tokens in real-time if writer is available
        if writer:
            chunks = []
            async for event in router.chat_stream(**llm_kwargs):
                if event.event_type == "content" and event.content:
                    chunks.append(event.content)
                    writer({"type": "token", "data": {"text": event.content}})
                elif event.event_type == "thinking" and event.thinking:
                    pass  # Skip thinking tokens from output
                elif event.event_type == "error" and event.error:
                    logger.warning(f"Synthesize swarm stream error: {event.error}")

            synthesized_answer = "".join(chunks)
            streamed_tokens = True
        else:
            # Fallback: non-streaming call (e.g., graph.invoke() without stream_mode)
            response = await router.chat(**llm_kwargs)
            synthesized_answer = response.content or ""

        # Clean thinking tags from synthesis
        import re
        synthesized_answer = re.sub(
            r"</?think(?:ing)?>.*?(?:</?think(?:ing)?>|$)", "",
            synthesized_answer, flags=re.DOTALL,
        ).strip()

    except Exception as e:
        logger.error(f"Synthesize swarm: LLM call failed: {e}")
        # Fallback: concatenate worker answers
        synthesized_answer = "\n\n".join(
            f"**{r.get('focus', 'Resultado')}**: {r.get('answer', '')}"
            for r in successful
        )

    latency_ms = (time.time() - start) * 1000

    reasoning_steps.append({
        "type": StepType.RESPONSE.value,
        "content": (
            f"Synthesis complete: {len(successful)} workers, "
            f"{len(unique_sources)} sources, {latency_ms:.0f}ms"
        ),
    })

    logger.info(
        f"Synthesize swarm: {len(successful)}/{len(results)} workers, "
        f"{len(unique_sources)} sources, {latency_ms:.0f}ms, "
        f"streamed={streamed_tokens}"
    )

    return {
        "is_complete": True,
        "final_answer": synthesized_answer,
        "sources": unique_sources,
        "success": True,
        "messages": [AIMessage(content=synthesized_answer)],
        "reasoning_steps": reasoning_steps,
        "metadata": {
            "swarm_workers_total": len(results),
            "swarm_workers_successful": len(successful),
            "swarm_workers_failed": len(failed),
            "synthesize_latency_ms": latency_ms,
            "source_count": len(unique_sources),
            "streamed_tokens": streamed_tokens,
        },
    }
