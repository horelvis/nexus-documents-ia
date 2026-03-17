"""
Emma ReAct Agent — Query Rewrite Node

Contextualizes follow-up queries using conversation history, following the
ConversationalRetrievalChain pattern from LangChain and Self-RAG principles.

When a user asks "cuales son?" after "cuantos contratos estan caducados?",
the rewrite node transforms it into a self-contained query like
"¿Cuáles son los contratos caducados?" so downstream retrieval works correctly.

This prevents hallucination caused by ambiguous follow-ups where the ReAct
loop has no context about what to search for, and responds directly with
fabricated data.

Design:
- Runs AFTER classify (which handles fast-path exits) and BEFORE memory_recall
- Only activates when conversation history exists (messages > 1)
- Uses a fast PLANNER LLM call (~100-200ms) for contextualization
- Transparent pass-through when no rewrite is needed
- Updates both `query` and the last HumanMessage in state

References:
- ConversationalRetrievalChain: https://python.langchain.com/docs/use_cases/question_answering/conversational_retrieval/
- Self-RAG: https://arxiv.org/abs/2310.11511
"""

import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from app.core.config import settings
from ..state import ReActState
from ..reasoning_tracker import StepType

logger = logging.getLogger(__name__)

# ── Rewrite system prompt (loaded from Langfuse) ─────────────────────


async def rewrite_node(state: ReActState) -> Dict[str, Any]:
    """Rewrite the user query to be self-contained using conversation history.

    Follows the ConversationalRetrievalChain pattern:
    1. Check if there's conversation history (prior messages)
    2. If yes, ask the LLM to contextualize the query
    3. Update state with the rewritten query

    If the query is already self-contained, the LLM returns it unchanged.
    On any failure, passes through transparently (non-blocking).

    Returns:
        State updates: query (if rewritten), messages (updated HumanMessage),
        reasoning_steps, metadata.
    """
    start = time.time()
    query = state.get("query", "")
    all_messages = list(state.get("messages", []))

    # Build conversation history from messages BEFORE the current HumanMessage
    history_messages: List[Dict[str, str]] = []
    for msg in all_messages[:-1]:
        role = "user" if msg.type == "human" else "assistant"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if content:
            history_messages.append({"role": role, "content": content})

    # No history → pass through (first query in session)
    if not history_messages:
        return {
            "reasoning_steps": [{
                "type": StepType.ROUTING.value,
                "content": "Rewrite: no history, pass-through",
            }],
        }

    # Use LLM to contextualize the query
    # Last 4 messages (2 turns) is enough context for reference resolution
    recent_history = history_messages[-4:]
    context_lines = []
    for msg in recent_history:
        label = "Usuario" if msg["role"] == "user" else "Asistente"
        # Truncate long responses to keep prompt small
        content = msg["content"][:400]
        context_lines.append(f"{label}: {content}")
    context_text = "\n".join(context_lines)

    # Load prompt from Langfuse
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    prompt = await client.get_prompt("emma_rewrite_system")
    rewrite_system = prompt.content

    llm_messages = [
        {"role": "system", "content": rewrite_system},
        {
            "role": "user",
            "content": (
                f"Conversación previa:\n{context_text}\n\n"
                f"Última pregunta del usuario: {query}\n\n"
                f"Consulta reformulada:"
            ),
        },
    ]

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        lc_messages = [
            SystemMessage(content=llm_messages[0]["content"]),
            HumanMessage(content=llm_messages[1]["content"]),
        ]
        model = get_planner_model().bind(temperature=0.1, max_tokens=200)
        response = await model.ainvoke(lc_messages)
        rewritten = (response.content or "").strip().strip('"').strip("'")

        latency_ms = (time.time() - start) * 1000

        # Only accept rewrite if it's meaningfully different from original
        if rewritten and rewritten.lower() != query.lower():
            logger.info(
                f"Query rewritten: '{query}' → '{rewritten}' ({latency_ms:.0f}ms)"
            )

            # Replace the last HumanMessage via ID matching (add_messages reducer)
            result: Dict[str, Any] = {
                "query": rewritten,
                "reasoning_steps": [{
                    "type": StepType.ROUTING.value,
                    "content": f"Rewrite: '{query}' → '{rewritten}'",
                }],
                "metadata": {
                    "original_query": query,
                    "rewritten_query": rewritten,
                    "rewrite_latency_ms": latency_ms,
                },
            }

            # Update the HumanMessage in-place via ID match
            if all_messages and all_messages[-1].type == "human":
                original_id = all_messages[-1].id
                result["messages"] = [
                    HumanMessage(content=rewritten, id=original_id)
                ]

            return result

        # Query unchanged — LLM determined it was already self-contained
        logger.debug(f"Query rewrite: no change needed ({latency_ms:.0f}ms)")
        return {
            "reasoning_steps": [{
                "type": StepType.ROUTING.value,
                "content": "Rewrite: query already self-contained",
            }],
            "metadata": {"rewrite_latency_ms": latency_ms},
        }

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.warning(f"Query rewrite failed (non-blocking, {latency_ms:.0f}ms): {e}")
        return {
            "reasoning_steps": [{
                "type": StepType.ROUTING.value,
                "content": f"Rewrite: skipped (error: {e})",
            }],
            "metadata": {"rewrite_latency_ms": latency_ms, "rewrite_error": str(e)},
        }
