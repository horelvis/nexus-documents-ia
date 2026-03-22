"""
Emma ReAct Agent — Classify Node

Entry point of the ReAct graph. All queries go through the ReAct loop —
the LLM decides whether to use tools or respond conversationally based
on conversation context. No fast-path bifurcation.

The classify node performs intent classification for metadata/logging
and complexity assessment for swarm routing.
"""

import logging
import time
from typing import Any, Dict, List

from app.core.config import settings
from ..state import ReActState
from ..reasoning_tracker import StepType

logger = logging.getLogger(__name__)


def _assess_complexity(query: str, intent: str, confidence: float) -> bool:
    """Decide whether to use swarm path based on query complexity.

    Heuristic scoring — fast (no LLM call) and good enough:
    - Comparison words (+2): "compara", "diferencia", "versus"
    - Multi-source words (+2): "legislación y", "jurisprudencia y"
    - Analysis words (+1): "analiza", "evalúa", "riesgos"
    - Long query (+1): >120 chars
    - Complex intent (+1): analysis, comparison, generation

    Returns True if signals >= swarm_complexity_threshold (default: 3).
    """
    if not settings.swarm_enabled:
        return False

    q = query.lower()
    threshold = settings.swarm_complexity_threshold

    comparison_words = ("compara", "diferencia", "versus", "vs ", "frente a", "respecto a")
    multi_source_words = (
        "legislación y", "jurisprudencia y", "documentos y",
        "contratos y leyes", "normativa y", "ley y",
        "legislación,", "jurisprudencia,",
    )
    analysis_words = (
        "analiza", "evalúa", "riesgos", "implicaciones",
        "consecuencias", "impacto", "cumplimiento",
    )

    signals = 0
    if any(w in q for w in comparison_words):
        signals += 2
    if any(w in q for w in multi_source_words):
        signals += 2
    if any(w in q for w in analysis_words):
        signals += 1
    if len(query) > 120:
        signals += 1
    if intent in ("analysis", "comparison", "generation"):
        signals += 1

    return signals >= threshold


async def classify_node(state: ReActState) -> Dict[str, Any]:
    """Classify intent and route ALL queries to the ReAct loop.

    No fast-path — the LLM handles greetings, confirmations, and
    document queries uniformly via the react_loop with full conversation
    context. This prevents losing the thread on continuation replies
    ("Sí", "Ok") and simplifies the architecture.

    Returns:
        State updates: reasoning_steps, metadata, use_swarm flag.
    """
    start = time.time()
    query = state.get("query", "")
    reasoning_steps: List[Dict[str, Any]] = []

    # Record checkpoint baseline counts
    _checkpoint_offsets = {
        "reasoning_steps": len(state.get("reasoning_steps", [])),
        "swarm_worker_results": len(state.get("swarm_worker_results", [])),
    }

    # Empty query guard
    if not query or not query.strip():
        return {
            "fast_path_used": True,
            "fast_path_answer": "¿Puedes formular tu consulta?",
            "is_complete": True,
            "final_answer": "¿Puedes formular tu consulta?",
            "success": True,
            "reasoning_steps": [{"type": "routing", "content": "Empty query — guard"}],
            "metadata": {"classify_intent": "empty", "classify_latency_ms": 0, "_checkpoint_offsets": _checkpoint_offsets},
        }

    # Intent classification (for metadata/logging, NOT for routing)
    intent = "document_query"
    confidence = 0.5

    try:
        from .intent_router import classify_intent
        intent, confidence = await classify_intent(query)
    except Exception as e:
        logger.warning(f"Intent classification failed, defaulting to document_query: {e}")

    reasoning_steps.append({
        "type": StepType.ROUTING.value,
        "content": f"Intent: {intent} (confidence: {confidence:.2f})",
    })

    latency_ms = (time.time() - start) * 1000

    # Query clarification — detect ambiguous queries via interrupt() HITL pattern.
    if settings.react_query_clarification_enabled:
        try:
            from langgraph.types import interrupt
            from ..clarification import detect_ambiguity

            conv_history: List[Dict[str, str]] = []
            for msg in state.get("messages", [])[:-1]:
                role = "user" if msg.type == "human" else "assistant"
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content:
                    conv_history.append({"role": role, "content": content})

            is_ambiguous, clarification_msg, clarification_options = detect_ambiguity(
                query=query, intent=intent, history=conv_history,
            )

            if is_ambiguous:
                reasoning_steps.append({
                    "type": StepType.ROUTING.value,
                    "content": "Query clarification: ambiguous query detected",
                })

                refined_query = interrupt({
                    "type": "clarification",
                    "question": clarification_msg,
                    "options": clarification_options,
                })

                logger.info(f"Classify: clarification resolved → '{refined_query[:80]}'")
                query = refined_query
                try:
                    from .intent_router import classify_intent as _classify
                    intent, confidence = await _classify(query)
                except Exception:
                    pass
                reasoning_steps.append({
                    "type": StepType.ROUTING.value,
                    "content": f"Re-classified after clarification: intent={intent}",
                })
        except Exception as e:
            if "GraphInterrupt" not in type(e).__name__:
                logger.debug(f"Query clarification check failed (non-blocking): {e}")
            else:
                raise

    # Assess complexity for swarm routing
    use_swarm = _assess_complexity(query, intent, confidence)
    route_target = "decompose (swarm)" if use_swarm else "react_loop"

    logger.info(f"Classify: intent={intent}, confidence={confidence:.2f} → {route_target}")

    result: Dict[str, Any] = {
        "fast_path_used": False,
        "use_swarm": use_swarm,
        "reasoning_steps": reasoning_steps,
        "metadata": {
            "classify_intent": intent,
            "classify_confidence": confidence,
            "classify_latency_ms": latency_ms,
            "use_swarm": use_swarm,
            "_checkpoint_offsets": _checkpoint_offsets,
        },
    }

    # If query was refined by clarification, propagate to state
    if query != state.get("query", ""):
        result["query"] = query

    return result
