"""
Emma ReAct Agent — Classify Node

Entry point of the ReAct graph. Performs fast intent classification and
routes to either:
- Fast-path: LLM-generated response for greetings, identity, farewells (no tools)
- React loop: Full ReAct cycle for document queries, analysis, etc.

This is a refactored/simplified version of coordinator.py + plan.py fast-paths.
The classify node reuses the existing IntentRouter (semantic + LLM fallback).
"""

import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from app.core.config import settings
from ..state import ReActState
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)

# System prompt for conversational fast-path (lightweight LLM call, no tools)
_CONVERSATIONAL_SYSTEM_PROMPT = """\
Eres Emma, la asistente de inteligencia artificial de NouxCubeIA.
Ayudas a gestionar documentos empresariales, consultar legislación española (BOE), \
analizar contratos, generar borradores y mucho más.

Instrucciones:
- Responde en español, de forma breve y natural (2-3 frases máximo).
- Si el usuario te saluda, preséntate brevemente y menciona 2-3 cosas que puedes hacer.
- Si preguntan quién eres o qué puedes hacer, responde con tus capacidades principales.
- Usa un tono profesional pero cercano.
- Si conoces el nombre del usuario, úsalo para personalizar la respuesta.
- Si tienes memoria del usuario (su nombre, departamento, intereses), \
úsala PROACTIVAMENTE en el saludo. Ejemplo: "¡Hola, Carlos! ¿Cómo va todo en Legal? ¿En qué te ayudo hoy?". \
NO repitas toda la memoria, solo úsala de forma natural y breve.
- NO uses emojis excesivos (máximo 1 si es natural).
- Responde SOLO en texto plano, sin markdown."""


async def _generate_conversational_response(
    query: str,
    user_name: str = "",
    conversation_history: Optional[List[Dict[str, str]]] = None,
    user_memory: str = "",
) -> str:
    """Generate a conversational response via LLM (no tools).

    Makes a single lightweight chat completion call to produce natural,
    personalized responses for greetings, identity, and farewell intents.
    Includes conversation history and user memory for contextual replies.
    Falls back to a simple greeting if the LLM call fails.
    """
    from app.agents.llm_router import get_llm_router
    from app.agents.llm_client import ModelRole

    system_msg = _CONVERSATIONAL_SYSTEM_PROMPT
    if user_name:
        system_msg += f"\n\nEl usuario se llama: {user_name}"
    if user_memory:
        system_msg += f"\n\n{user_memory}"

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]

    # Include prior conversation for context (last 6 messages max)
    if conversation_history:
        messages.extend(conversation_history[-6:])

    messages.append({"role": "user", "content": query})

    try:
        router = await get_llm_router()
        response = await router.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=150,
            role=ModelRole.PLANNER,
        )
        answer = (response.content or "").strip()
        if answer:
            return answer
    except Exception as e:
        logger.warning(f"Conversational LLM call failed, using fallback: {e}")

    # Minimal fallback if LLM fails
    first_name = user_name.split()[0] if user_name else ""
    greeting = f"¡Hola, {first_name}!" if first_name else "¡Hola!"
    return f"{greeting} Soy Emma, tu asistente documental. ¿En qué te ayudo?"


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
    """Classify intent and route to fast-path or react_loop.

    Fast-path intents (conversational, identity) return immediately.
    All other intents proceed to the ReAct loop for dynamic tool use.

    When PostgresSaver checkpointer is active, merge_lists fields
    (reasoning_steps, swarm_worker_results, swarm_pending_events)
    accumulate across invocations.  We emit a ``_checkpoint_offsets``
    marker in metadata so downstream consumers know how many items
    came from the checkpoint vs the current turn.

    Returns:
        State updates including fast_path_used, fast_path_answer,
        reasoning_steps, and metadata.
    """
    start = time.time()
    query = state.get("query", "")
    reasoning_steps = []

    # Record checkpoint baseline counts so downstream can distinguish
    # old (accumulated) items from new (current-turn) items.
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
            "reasoning_steps": [{"type": "routing", "content": "Empty query — fast path"}],
            "metadata": {"classify_intent": "empty", "classify_latency_ms": 0, "_checkpoint_offsets": _checkpoint_offsets},
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

    # Fast-path: conversational and identity intents — LLM-generated (no tools)
    if intent in ("conversational", "identity") and confidence >= 0.7:
        user_name = state.get("metadata", {}).get("user_name", "") or ""
        user_memory = state.get("user_memory") or ""

        # Build conversation history from state messages (excluding current query)
        conv_history: List[Dict[str, str]] = []
        for msg in state.get("messages", [])[:-1]:  # skip last (current HumanMessage)
            role = "user" if msg.type == "human" else "assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content:
                conv_history.append({"role": role, "content": content})

        answer = await _generate_conversational_response(
            query, user_name=user_name, conversation_history=conv_history,
            user_memory=user_memory,
        )

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
                "_checkpoint_offsets": _checkpoint_offsets,
            },
        }

    # Query clarification — detect ambiguous queries before wasting a search cycle
    if settings.react_query_clarification_enabled:
        try:
            from ..clarification import detect_ambiguity

            # Build minimal history from state messages
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
                    "content": f"Query clarification: ambiguous query detected",
                })
                return {
                    "fast_path_used": True,
                    "fast_path_answer": clarification_msg,
                    "is_complete": True,
                    "final_answer": clarification_msg,
                    "success": True,
                    "messages": [AIMessage(content=clarification_msg)],
                    "reasoning_steps": reasoning_steps,
                    "metadata": {
                        "classify_intent": intent,
                        "classify_confidence": confidence,
                        "classify_latency_ms": latency_ms,
                        "query_clarification": True,
                        "clarification_options": clarification_options,
                        "_checkpoint_offsets": _checkpoint_offsets,
                    },
                }
        except Exception as e:
            logger.debug(f"Query clarification check failed (non-blocking): {e}")

    # Assess complexity for swarm routing
    use_swarm = _assess_complexity(query, intent, confidence)
    route_target = "decompose (swarm)" if use_swarm else "react_loop"

    logger.info(f"Classify: intent={intent}, confidence={confidence:.2f} → {route_target}")

    return {
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
