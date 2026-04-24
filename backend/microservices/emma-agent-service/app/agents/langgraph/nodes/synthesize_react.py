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
import re
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, ToolMessage

from ..state import ReActState
from .guardrail_helper import apply_guardrails

logger = logging.getLogger(__name__)

_EXT_RE = re.compile(r"\.(pdf|docx?|xlsx?|txt|md|odt|rtf)$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"[\s_\-./]+")


def _filter_cited_sources(
    sources: List[Dict[str, Any]],
    answer: str,
) -> List[Dict[str, Any]]:
    """Return only the sources whose identity appears in the answer text.

    Mirrors the heuristic used by the frontend's `filterReferencedSources`
    (frontend/src/components/emma-chat/hooks/useMessageConverter.ts) so that
    backend and UI agree on what counts as "cited". Matches by:
      1. boe_id substring
      2. document_id / id substring (rare but happens when the LLM prints UUIDs)
      3. title substring (short titles) or 50%+ keyword overlap (long titles)

    Single-retrieve fallback: when exactly one source was retrieved and none
    of the heuristics matched, assume the LLM cited it implicitly and keep it.
    This covers terse answers like "El total es 94,45€" that reference a
    single doc without naming it.
    """
    if not answer or not sources:
        return sources

    text_lower = answer.lower()
    cited: List[Dict[str, Any]] = []

    for src in sources:
        boe_id = (src.get("boe_id") or "").lower()
        if boe_id and boe_id in text_lower:
            cited.append(src)
            continue

        doc_id = (src.get("document_id") or src.get("id") or "").lower()
        if doc_id and doc_id in text_lower:
            cited.append(src)
            continue

        name = (src.get("title") or src.get("name") or "").lower()
        if not name:
            continue

        if 3 <= len(name) <= 40 and name in text_lower:
            cited.append(src)
            continue

        stripped = _EXT_RE.sub("", name)
        words = [w for w in _SPLIT_RE.split(stripped) if len(w) >= 3]
        if not words:
            continue
        threshold = max(2, (len(words) + 1) // 2)
        matched = sum(1 for w in words if w in text_lower)
        if matched >= threshold:
            cited.append(src)

    if not cited and len(sources) == 1:
        return sources

    return cited


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

    # Filter retrieved sources down to those actually cited in the final answer.
    # The react_loop accumulates every tool's retrieval into state.sources, but
    # the user-facing "sources" panel must show only what the answer references.
    cited_sources = _filter_cited_sources(unique_sources, final_answer)
    if len(cited_sources) < len(unique_sources):
        logger.info(
            f"Synthesize: filtered sources {len(unique_sources)} retrieved → "
            f"{len(cited_sources)} cited"
        )

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

    # Update the existing AI message (from react_loop) with the guardrail-modified content.
    # Using the same ID ensures LangGraph's add_messages reducer UPDATES in place
    # instead of appending a duplicate.
    messages = state.get("messages", [])
    last_ai_msg = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            last_ai_msg = msg
            break

    result = {
        "final_answer": final_answer,
        "sources": cited_sources,
        "success": True,
        "reasoning_steps": [{
            "type": "response",
            "content": f"Synthesize: {len(cited_sources)} cited / {len(unique_sources)} retrieved, answer length={len(final_answer)}",
        }],
        "guardrail_metadata": guardrail_metadata,
        "metadata": {
            "synthesize_latency_ms": latency_ms,
            "source_count": len(cited_sources),
            "source_retrieved_count": len(unique_sources),
        },
    }

    if last_ai_msg and last_ai_msg.content != final_answer:
        # Content changed (guardrails added disclaimer) → update existing message by ID
        result["messages"] = [AIMessage(content=final_answer, id=last_ai_msg.id)]
    elif not last_ai_msg:
        # No AI message from react_loop (edge case) → create new one
        result["messages"] = [AIMessage(content=final_answer)]
    # else: content unchanged → no message update needed

    return result
