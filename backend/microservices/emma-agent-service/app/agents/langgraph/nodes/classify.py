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
from .guardrail_helper import apply_guardrails

logger = logging.getLogger(__name__)

# Hardcoded fallbacks — used only when Langfuse AND YAML are both unavailable.
_CONVERSATIONAL_SYSTEM_FALLBACK = """\
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

_GENERAL_KNOWLEDGE_SYSTEM_FALLBACK = """\
Eres Emma, la asistente de inteligencia artificial de NouxCubeIA.
Además de ayudarte con documentos y legislación, también puedo echarte una mano \
con preguntas generales.

Instrucciones:
- Responde de forma clara y cercana, como si le explicaras a un compañero de trabajo.
- Evita jerga técnica innecesaria. Si usas un término especializado, explícalo brevemente.
- Estructura tu respuesta para que sea fácil de leer (usa negritas para lo importante, \
listas cuando haya varios puntos, y bloques de código solo cuando sea código real).
- Si el usuario pide código, incluye comentarios que expliquen qué hace cada parte \
en lenguaje sencillo.
- Responde en el mismo idioma que el usuario.
- Mantén un tono profesional pero amable, como el resto de mis respuestas.
- Si la pregunta realmente necesita buscar en los documentos del usuario, \
sugiérelo de forma natural ("Para eso necesitaría revisar tus documentos, \
¿quieres que lo busque?")."""


async def _load_fast_path_prompt(prompt_name: str, yaml_path: tuple, fallback: str) -> str:
    """Load a fast-path prompt: Langfuse → YAML → hardcoded fallback.

    Follows the same 3-tier pattern as _load_react_system_prompt in react_loop.py.
    """
    from pathlib import Path

    # Tier 1: Langfuse (TTL-cached, ~0ms on hit)
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        client = get_langfuse_prompt_client()
        cached = await client.get_prompt(prompt_name)
        if cached and cached.content:
            logger.debug(f"Fast-path prompt '{prompt_name}' loaded from Langfuse (v{cached.version})")
            return cached.content
    except Exception as e:
        logger.debug(f"Langfuse prompt '{prompt_name}' fetch skipped: {e}")

    # Tier 2: YAML fallback
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
                # Navigate nested YAML path (e.g., ("fast_path", "conversational_system"))
                node = data
                for key in yaml_path:
                    node = node.get(key, {}) if isinstance(node, dict) else {}
                if isinstance(node, str) and node.strip():
                    logger.debug(f"Fast-path prompt '{prompt_name}' loaded from YAML")
                    return node.strip()
            except Exception as e:
                logger.warning(f"Failed to load fast-path prompt from YAML: {e}")

    # Tier 3: Hardcoded fallback
    logger.debug(f"Fast-path prompt '{prompt_name}' using hardcoded fallback")
    return fallback


async def _generate_conversational_response(
    query: str,
    user_name: str = "",
    conversation_history: Optional[List[Dict[str, str]]] = None,
    user_memory: str = "",
    intent: str = "conversational",
) -> str:
    """Generate a fast-path response via LLM (no tools).

    Makes a single chat completion call to produce natural responses for
    greetings, identity, and general knowledge intents.
    Includes conversation history and user memory for contextual replies.
    Falls back to a simple greeting if the LLM call fails.

    Prompts loaded from: Langfuse → YAML → hardcoded fallback.
    For general_knowledge: uses CHAT model with higher token limit and markdown.
    For conversational/identity: uses PLANNER model with low token limit.
    """
    from langchain_core.messages import SystemMessage as SM, HumanMessage as HM, AIMessage as AIM

    is_general_knowledge = intent == "general_knowledge"

    if is_general_knowledge:
        from app.agents.llm_models import get_chat_model
        system_msg = await _load_fast_path_prompt(
            "emma_fast_general_knowledge_system",
            ("fast_path", "general_knowledge_system"),
            _GENERAL_KNOWLEDGE_SYSTEM_FALLBACK,
        )
        model = get_chat_model().bind(temperature=0.5, max_tokens=2048)
    else:
        from app.agents.llm_models import get_planner_model
        system_msg = await _load_fast_path_prompt(
            "emma_fast_conversational_system",
            ("fast_path", "conversational_system"),
            _CONVERSATIONAL_SYSTEM_FALLBACK,
        )
        model = get_planner_model().bind(temperature=0.7, max_tokens=150)

    if user_name:
        system_msg += f"\n\nEl usuario se llama: {user_name}"
    if user_memory:
        system_msg += f"\n\n{user_memory}"

    lc_messages = [SM(content=system_msg)]

    # Include prior conversation for context (last 6 messages max)
    if conversation_history:
        for m in conversation_history[-6:]:
            role = m.get("role", "user")
            if role == "assistant":
                lc_messages.append(AIM(content=m.get("content", "")))
            else:
                lc_messages.append(HM(content=m.get("content", "")))

    lc_messages.append(HM(content=query))

    try:
        response = await model.ainvoke(lc_messages)
        answer = (response.content or "").strip()
        if answer:
            return answer
    except Exception as e:
        logger.warning(f"Fast-path LLM call failed (intent={intent}), using fallback: {e}")

    # Minimal fallback if LLM fails
    if is_general_knowledge:
        return "Lo siento, no pude procesar tu consulta en este momento. ¿Podrías reformularla?"
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

    # Fast-path: conversational, identity, and general_knowledge intents — LLM-generated (no tools)
    if intent in ("conversational", "identity", "general_knowledge") and confidence >= 0.7:
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
            user_memory=user_memory, intent=intent,
        )

        # Guardrail validation (fast-path)
        answer, guardrail_metadata = await apply_guardrails(answer, state)

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
            "guardrail_metadata": guardrail_metadata,
            "metadata": {
                "classify_intent": intent,
                "classify_confidence": confidence,
                "classify_latency_ms": latency_ms,
                "_checkpoint_offsets": _checkpoint_offsets,
            },
        }

    # Query clarification — detect ambiguous queries via interrupt() HITL pattern.
    # When ambiguous, interrupt() pauses the graph and surfaces options to the user.
    # On resume (Command(resume=selected_value)), the node re-executes from the
    # beginning; interrupt() returns the user's selection which replaces the query.
    # All code before interrupt() is idempotent (intent classification is read-only).
    if settings.react_query_clarification_enabled:
        try:
            from langgraph.types import interrupt
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
                    "content": "Query clarification: ambiguous query detected",
                })

                # interrupt() pauses the graph on first run.
                # On resume, returns the user's selected option value.
                refined_query = interrupt({
                    "type": "clarification",
                    "question": clarification_msg,
                    "options": clarification_options,
                })

                # After resume: refined_query = user's selected option
                logger.info(f"Classify: clarification resolved → '{refined_query[:80]}'")
                query = refined_query
                # Re-classify with the refined query
                intent, confidence = await _classify_intent(query, tenant_id)
                reasoning_steps.append({
                    "type": StepType.ROUTING.value,
                    "content": f"Re-classified after clarification: intent={intent}",
                })
        except Exception as e:
            # Don't let clarification failure block the pipeline
            if "GraphInterrupt" not in type(e).__name__:
                logger.debug(f"Query clarification check failed (non-blocking): {e}")
            else:
                raise  # Re-raise GraphInterrupt — must propagate to runner

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
