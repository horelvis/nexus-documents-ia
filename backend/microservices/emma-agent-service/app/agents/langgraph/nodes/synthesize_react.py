"""
Emma ReAct Agent — Synthesize Node (ReAct version)

Simplified synthesize for the ReAct graph. Unlike the RAG synthesize
which merges agent_results from multiple specialist nodes, this node
simply reads the final_answer and sources that the react_loop already
produced (either via the terminate tool or direct LLM response).

If no final_answer is available (edge case), it extracts the last
assistant message from the conversation as the answer.

Token streaming: emits tokens via get_stream_writer() so the adapter
can translate them to event: messages for progressive rendering.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, ToolMessage

from ..state import ReActState
from .guardrail_helper import apply_guardrails

logger = logging.getLogger(__name__)


async def synthesize_react_node(state: ReActState) -> Dict[str, Any]:
    """Synthesize the final response from the ReAct loop.

    In most cases, react_loop already set final_answer via the terminate
    tool. This node:
    1. Validates the answer exists
    2. Deduplicates sources
    3. Streams tokens via get_stream_writer() for progressive rendering
    4. Applies guardrails
    5. Sets success=True

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

    # Guardrail validation
    final_answer, guardrail_metadata = await apply_guardrails(final_answer, state)

    # Stream tokens via get_stream_writer() for progressive rendering.
    # The adapter translates these custom events to event: messages SSE
    # events that the SDK accumulates via BaseMessageChunk.concat().
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
        words = final_answer.split(' ')
        batch_size = 3
        for i in range(0, len(words), batch_size):
            batch = words[i:i + batch_size]
            token = (" " if i > 0 else "") + " ".join(batch)
            writer({"type": "token", "data": {"text": token}})
            await asyncio.sleep(0.03)
    except Exception:
        pass  # No stream writer (e.g., graph.invoke() without stream_mode)

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
        "guardrail_metadata": guardrail_metadata,
        "metadata": {
            "synthesize_latency_ms": latency_ms,
            "source_count": len(unique_sources),
        },
    }

    if not last_is_answer:
        result["messages"] = [AIMessage(content=final_answer)]

    return result
