"""
COORDINATOR Node - Emma's high-level orchestration

This node performs lightweight, high-level routing decisions before retrieval.
It represents Emma's coordinator role (intent triage + guardrails) and is
intentionally fast and deterministic.

Intent classification uses a hybrid approach:
1. Semantic Router (embeddings, ~1-3ms) as first tier
2. LLM classifier (~200ms) only when semantic router has no match
3. Default to document_query if both fail
"""

import logging
import time
from typing import Any, Dict

from ..state import RAGState
from ..reasoning_tracker import ReasoningTracker, StepType
from .intent_router import classify_intent

logger = logging.getLogger(__name__)


async def coordinator_node(state: RAGState) -> Dict[str, Any]:
    """
    Coordinator node for high-level routing and guardrails.
    """
    start_time = time.time()
    query = (state.get("query") or "").strip()

    # Initialize a local tracker and merge steps back to state
    with ReasoningTracker.create() as tracker:
        tracker.set_source("coordinator")

        tracker.add_step(
            StepType.QUERY_ANALYSIS,
            f"Coordinador analizando consulta: '{query[:50]}...'"
        )

        if not query:
            response = "¿Puedes formular tu consulta?"
            tracker.add_step(
                StepType.RESPONSE,
                "Consulta vacía: respuesta directa del coordinador",
                confidence=0.9
            )

            latency_ms = (time.time() - start_time) * 1000
            return {
                "final_answer": response,
                "success": True,
                "fast_path_used": True,
                "fast_path_answer": response,
                "reasoning_steps": tracker.get_steps(),
                "metadata": {
                    **state.get("metadata", {}),
                    "coordinator_intent": "empty_query",
                    "coordinator_route": "end",
                    "coordinator_latency_ms": latency_ms,
                },
            }

        intent, confidence = await classify_intent(query)
        tracker.add_step(
            StepType.ROUTING,
            f"Coordinador detectó intención: {intent}",
            confidence=confidence,
            metadata={"intent": intent},
        )

        # Decide route: skip retrieval for conversational/identity
        route = "retrieve"
        if intent in {"conversational", "identity"}:
            route = "plan"

        latency_ms = (time.time() - start_time) * 1000

        return {
            "reasoning_steps": tracker.get_steps(),
            "metadata": {
                **state.get("metadata", {}),
                "coordinator_intent": intent,
                "coordinator_route": route,
                "coordinator_latency_ms": latency_ms,
            },
        }
