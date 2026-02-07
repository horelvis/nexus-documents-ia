"""
Emma ReAct Agent — Classify Node

Entry point of the ReAct graph. Performs fast intent classification and
routes to either:
- Fast-path: Direct response for greetings, identity, farewells (no tools needed)
- React loop: Full ReAct cycle for document queries, analysis, etc.

This is a refactored/simplified version of coordinator.py + plan.py fast-paths.
The classify node reuses the existing IntentRouter (semantic + LLM fallback).
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from ..state import ReActState
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)

# Cached conversational config
_conversational_config: Optional[Dict[str, Any]] = None


def _load_conversational_config() -> Optional[Dict[str, Any]]:
    """Load conversational response patterns from emma_prompts.yaml (cached)."""
    global _conversational_config
    if _conversational_config is not None:
        return _conversational_config

    candidates = [
        Path("/app/config/prompts/emma_prompts.yaml"),
        Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
    ]
    for p in candidates:
        if p.exists():
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                _conversational_config = data.get("conversational_responses", {})
                return _conversational_config
            except Exception as e:
                logger.warning(f"Failed to load conversational config: {e}")

    _conversational_config = {}
    return _conversational_config


def _get_conversational_response(query: str, intent: str = "") -> str:
    """Get a fast-path conversational response.

    Tries YAML patterns first, falls back to inline responses.
    """
    config = _load_conversational_config()
    query_lower = query.lower().strip()

    if config:
        for category, patterns in config.items():
            if isinstance(patterns, dict):
                for pattern, response in patterns.items():
                    if pattern.lower() in query_lower:
                        return response if isinstance(response, str) else str(response)

    # Inline fallbacks
    if intent == "identity":
        if any(w in query_lower for w in ("quién eres", "quien eres", "qué eres", "que eres",
                                           "who are you", "what are you")):
            return (
                "Soy Emma, la asistente de inteligencia artificial de NouxCubeIA. "
                "Te ayudo a gestionar y consultar tus documentos empresariales, "
                "analizar legislación y generar informes."
            )
        if any(w in query_lower for w in ("qué puedes", "que puedes", "qué sabes",
                                           "what can you")):
            return (
                "Puedo buscar en tus documentos, consultar legislación española (BOE), "
                "analizar contratos, generar borradores, contar expedientes, "
                "y mucho más. ¿En qué te puedo ayudar?"
            )

    if intent == "conversational":
        if any(w in query_lower for w in ("hola", "buenos días", "buenas tardes",
                                           "hello", "hi ")):
            return "¡Hola! ¿En qué puedo ayudarte hoy?"
        if any(w in query_lower for w in ("adiós", "adios", "hasta luego", "bye",
                                           "chao")):
            return "¡Hasta luego! Si necesitas algo más, aquí estaré."
        if any(w in query_lower for w in ("gracias", "thanks", "thank you")):
            return "¡De nada! ¿Puedo ayudarte en algo más?"

    return "¡Hola! ¿En qué puedo ayudarte?"


async def classify_node(state: ReActState) -> Dict[str, Any]:
    """Classify intent and route to fast-path or react_loop.

    Fast-path intents (conversational, identity) return immediately.
    All other intents proceed to the ReAct loop for dynamic tool use.

    Returns:
        State updates including fast_path_used, fast_path_answer,
        reasoning_steps, and metadata.
    """
    start = time.time()
    query = state.get("query", "")
    reasoning_steps = []

    # Empty query guard
    if not query or not query.strip():
        return {
            "fast_path_used": True,
            "fast_path_answer": "¿Puedes formular tu consulta?",
            "is_complete": True,
            "final_answer": "¿Puedes formular tu consulta?",
            "success": True,
            "reasoning_steps": [{"type": "routing", "content": "Empty query — fast path"}],
            "metadata": {"classify_intent": "empty", "classify_latency_ms": 0},
        }

    # Intent classification (reuses existing hybrid router)
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

    # Fast-path: conversational and identity intents
    if intent in ("conversational", "identity") and confidence >= 0.7:
        answer = _get_conversational_response(query, intent)

        reasoning_steps.append({
            "type": StepType.RESPONSE.value,
            "content": f"Fast-path: {intent}",
        })

        return {
            "fast_path_used": True,
            "fast_path_answer": answer,
            "is_complete": True,
            "final_answer": answer,
            "success": True,
            "messages": [AIMessage(content=answer)],
            "reasoning_steps": reasoning_steps,
            "metadata": {
                "classify_intent": intent,
                "classify_confidence": confidence,
                "classify_latency_ms": latency_ms,
            },
        }

    # Not fast-path → proceed to react_loop
    logger.info(f"Classify: intent={intent}, confidence={confidence:.2f} → react_loop")

    return {
        "fast_path_used": False,
        "reasoning_steps": reasoning_steps,
        "metadata": {
            "classify_intent": intent,
            "classify_confidence": confidence,
            "classify_latency_ms": latency_ms,
        },
    }
