"""
Emma ReAct Agent — Synthesize Node (ReAct version)

Simplified synthesize for the ReAct graph. Unlike the RAG synthesize
which merges agent_results from multiple specialist nodes, this node
simply reads the final_answer and sources that the react_loop already
produced (either via the terminate tool or direct LLM response).

If no final_answer is available (edge case), it extracts the last
assistant message from the conversation as the answer.
"""

import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, ToolMessage

from ..state import ReActState

logger = logging.getLogger(__name__)


async def synthesize_react_node(state: ReActState) -> Dict[str, Any]:
    """Synthesize the final response from the ReAct loop.

    In most cases, react_loop already set final_answer via the terminate
    tool. This node:
    1. Validates the answer exists
    2. Deduplicates sources
    3. Sets success=True
    4. Adds the answer as an AIMessage for conversation persistence

    Returns:
        State updates: final_answer, sources, success, messages, metadata
    """
    start = time.time()
    final_answer = state.get("final_answer")
    sources = state.get("sources", [])

    # If no final_answer, extract from last assistant message
    if not final_answer:
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_answer = msg.content
                break

    # Last resort: generate a minimal response
    if not final_answer:
        final_answer = (
            "No pude encontrar información suficiente para responder tu consulta. "
            "Intenta reformular la pregunta o proporciona más contexto."
        )
        logger.warning("Synthesize: no final_answer found, using fallback")

    # Deduplicate sources by document_id or boe_id or title
    seen = set()
    unique_sources = []
    for src in sources:
        key = src.get("document_id") or src.get("boe_id") or src.get("url") or src.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique_sources.append(src)
        elif not key:
            unique_sources.append(src)

    latency_ms = (time.time() - start) * 1000

    # Only add AIMessage if react_loop didn't already set one with the same content
    messages = state.get("messages", [])
    last_is_answer = (
        messages and isinstance(messages[-1], AIMessage)
        and messages[-1].content == final_answer
    )

    result = {
        "final_answer": final_answer,
        "sources": unique_sources,
        "success": True,
        "reasoning_steps": [{
            "type": "response",
            "content": f"Synthesize: {len(unique_sources)} sources, answer length={len(final_answer)}",
        }],
        "metadata": {
            "synthesize_latency_ms": latency_ms,
            "source_count": len(unique_sources),
        },
    }

    if not last_is_answer:
        result["messages"] = [AIMessage(content=final_answer)]

    return result
