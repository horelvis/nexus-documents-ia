"""
COORDINATOR Node - Emma's high-level orchestration

This node performs lightweight, high-level routing decisions before retrieval.
It represents Emma's coordinator role (intent triage + guardrails) and is
intentionally fast and deterministic.
"""

import logging
import os
import re
import time
from typing import Any, Dict, Optional

from ..state import RAGState
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)


COORDINATOR_LLM_ENABLED = os.getenv("COORDINATOR_LLM_ENABLED", "false").lower() == "true"


def _detect_intent(query: str) -> str:
    """Lightweight intent detection for coordinator routing."""
    q = query.lower().strip()

    # Basic conversational intent
    greetings = [
        "hola", "buenos días", "buenas tardes", "buenas noches",
        "hello", "hi", "hey", "good morning", "good afternoon",
        "qué tal", "cómo estás", "how are you",
    ]
    if any(q.startswith(g) or q == g for g in greetings):
        return "conversational"

    # Identity/meta
    meta_patterns = [
        "quién eres", "qué puedes hacer", "ayuda", "help",
        "who are you", "what can you do", "what are you",
    ]
    if any(p in q for p in meta_patterns):
        return "identity"

    # Name declaration / recall
    name_patterns = [
        r"(me llamo|mi nombre es|llámame|puedes llamarme)\s+\w+",
        r"(my name is|call me)\s+\w+",
        r"cómo me llamo|como me llamo|recuerdas mi nombre|what is my name",
    ]
    if any(re.search(p, q) for p in name_patterns):
        return "identity"

    return "document_query"


async def _detect_intent_with_llm(query: str) -> Optional[str]:
    """LLM-based intent detection for the coordinator."""
    try:
        from app.agents.llm_client import get_llm_client

        llm_client = await get_llm_client()
        system_prompt = (
            "Eres Emma, coordinadora de un sistema multi-agente. "
            "Clasifica la intención del usuario en una de estas etiquetas: "
            "CONVERSATIONAL, IDENTITY, DOCUMENT_QUERY. "
            "Responde SOLO con la etiqueta."
        )
        user_prompt = f"Consulta: {query}\nEtiqueta:"

        response = await llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=10,
        )

        if not response or not response.content:
            return None

        label = response.content.strip().upper()
        if "CONVERSATIONAL" in label:
            return "conversational"
        if "IDENTITY" in label:
            return "identity"
        if "DOCUMENT_QUERY" in label:
            return "document_query"
        return None
    except Exception as e:
        logger.warning(f"Coordinator LLM intent failed: {e}")
        return None


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

        intent = _detect_intent(query)
        if COORDINATOR_LLM_ENABLED:
            llm_intent = await _detect_intent_with_llm(query)
            if llm_intent:
                intent = llm_intent
                tracker.add_step(
                    StepType.ROUTING,
                    f"Coordinador LLM decidió intención: {intent}",
                    confidence=0.9,
                    metadata={"intent": intent, "method": "llm"},
                )
        tracker.add_step(
            StepType.ROUTING,
            f"Coordinador detectó intención: {intent}",
            confidence=0.8,
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
