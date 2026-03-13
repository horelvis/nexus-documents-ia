"""
Context Compression for ReAct Loop

Compresses old ToolMessage observations to keep the LLM context within budget.
Qwen3-14B has ~16K effective tokens. After 3+ tool calls, accumulated observations
can overflow context. This module provides extractive compression (~0ms, no LLM)
of older observations while preserving the most recent ones intact.

Strategy: Keep recent N tool results verbatim. For older ones, extract a compact
summary with result count, top match, and first 200 chars. This preserves the
information the LLM needs for reasoning while reducing tokens by ~80%.

Usage:
    from app.agents.langgraph.context_compressor import compress_tool_observations

    compressed = compress_tool_observations(messages, budget=6000, preserve_recent=2)
    if compressed is not None:
        messages = compressed  # Use compressed version
"""

import logging
import re
from typing import List, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)

# Approximate token estimation: ~3 chars per token for Spanish/multilingual text.
# 4 was too optimistic and caused context overflow with Qwen3.5 (16K context).
_CHARS_PER_TOKEN = 3


def estimate_message_tokens(messages: List[BaseMessage]) -> int:
    """Estimate total tokens across all messages.

    Uses a rough heuristic of ~4 chars per token for Spanish/mixed text.
    This avoids importing a tokenizer and is fast enough for budget decisions.
    """
    total_chars = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total_chars += len(content)
        # Tool calls in AIMessages add overhead
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            total_chars += sum(len(str(tc)) for tc in msg.tool_calls)
    return total_chars // _CHARS_PER_TOKEN


def _estimate_tokens(text: str) -> int:
    """Estimate tokens for a single text string."""
    return len(text) // _CHARS_PER_TOKEN


def _compress_observation(content: str, tool_call_id: str) -> str:
    """Compress a single tool observation to a compact summary.

    Extracts key information:
    - Result count (from "Se encontraron N resultados" pattern)
    - First result title/header
    - First 200 chars of content
    """
    lines = content.strip().split("\n")

    # Try to extract result count
    count_match = re.search(r"Se encontraron? (\d+) resultado", content)
    result_count = count_match.group(1) if count_match else "?"

    # Try to extract first result title (bold markdown)
    first_title = ""
    for line in lines:
        title_match = re.match(r"\*\*\d+\.\s+(.+?)\*\*", line)
        if title_match:
            first_title = title_match.group(1)[:80]
            break

    # Build compressed version
    parts = [f"[Resumen] {result_count} resultados."]
    if first_title:
        parts.append(f"Top: {first_title}.")

    # Add truncated content for context
    clean = content[:200].replace("\n", " ").strip()
    if len(content) > 200:
        clean += "..."
    parts.append(clean)

    return " ".join(parts)


def compress_tool_observations(
    messages: List[BaseMessage],
    budget: int = 6000,
    preserve_recent: int = 2,
) -> Optional[List[BaseMessage]]:
    """Compress old ToolMessage observations if context exceeds budget.

    Args:
        messages: Current message list from state.
        budget: Token budget threshold. Only compress if estimated tokens exceed this.
        preserve_recent: Number of most recent ToolMessages to keep verbatim.

    Returns:
        Compressed message list if compression was applied, None otherwise.
        Returning None signals to the caller that no compression was needed.
    """
    # Estimate current token usage for ToolMessages only
    tool_messages = [(i, msg) for i, msg in enumerate(messages) if isinstance(msg, ToolMessage)]

    if len(tool_messages) <= preserve_recent:
        return None  # Not enough messages to compress

    tool_token_total = sum(_estimate_tokens(msg.content or "") for _, msg in tool_messages)

    if tool_token_total <= budget:
        return None  # Within budget, no compression needed

    # Identify which ToolMessages to compress (all except last N)
    compress_indices = {idx for idx, _ in tool_messages[:-preserve_recent]}

    compressed_messages = []
    compressed_count = 0
    saved_tokens = 0

    for i, msg in enumerate(messages):
        if i in compress_indices:
            original_content = msg.content or ""
            compressed_content = _compress_observation(original_content, msg.tool_call_id)
            saved_tokens += _estimate_tokens(original_content) - _estimate_tokens(compressed_content)
            compressed_messages.append(
                ToolMessage(content=compressed_content, tool_call_id=msg.tool_call_id)
            )
            compressed_count += 1
        else:
            compressed_messages.append(msg)

    if compressed_count > 0:
        logger.info(
            f"🗜️ Compressed {compressed_count} tool observations, "
            f"saved ~{saved_tokens} tokens"
        )
        return compressed_messages

    return None


def trim_messages_to_token_budget(
    llm_messages: List[dict],
    token_budget: int,
    preserve_recent: int = 4,
) -> List[dict]:
    """Trim dict-format LLM messages to fit within a token budget.

    Unlike compress_tool_observations (which compresses BaseMessage tool content),
    this operates on the final dict-format messages and does aggressive trimming:

    1. System messages are always preserved (but large tool observations in them are compressed).
    2. The most recent `preserve_recent` non-system messages are kept verbatim.
    3. Older messages are dropped from the beginning (preserving tool_call/result pairs).
    4. If still over budget, older tool message contents are truncated to 500 chars.

    Args:
        llm_messages: List of dicts with role/content keys.
        token_budget: Maximum tokens allowed for the entire message list.
        preserve_recent: Number of most recent non-system messages to keep verbatim.

    Returns:
        Trimmed message list that fits within budget.
    """
    def _est_tokens(msgs):
        total = 0
        for m in msgs:
            total += len(m.get("content", "") or "") // _CHARS_PER_TOKEN
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    total += len(str(tc.get("function", {}))) // _CHARS_PER_TOKEN
            total += 4  # per-message overhead
        return total

    current_tokens = _est_tokens(llm_messages)
    if current_tokens <= token_budget:
        return llm_messages  # Already within budget

    logger.info(
        f"🗜️ Token budget trim: {current_tokens} tokens > {token_budget} budget"
    )

    # Step 1: Separate system and non-system messages
    system_msgs = [m for m in llm_messages if m.get("role") == "system"]
    non_system = [m for m in llm_messages if m.get("role") != "system"]

    # Step 2: Compress all tool-role messages that are NOT in the recent window
    safe_count = min(preserve_recent, len(non_system))
    for i in range(len(non_system) - safe_count):
        msg = non_system[i]
        if msg.get("role") == "tool" and len(msg.get("content", "")) > 500:
            original_len = len(msg["content"])
            msg["content"] = _compress_observation(msg["content"], msg.get("tool_call_id", ""))
            logger.debug(f"  Compressed old tool msg {i}: {original_len} → {len(msg['content'])} chars")

    # Step 2b: Cap any individual tool message that exceeds per-message budget.
    # Even "recent" tool messages must be capped if they alone exceed ~40% of total budget.
    per_msg_char_limit = (token_budget * _CHARS_PER_TOKEN) // 3  # ~33% of budget in chars
    for msg in non_system:
        if msg.get("role") == "tool" and len(msg.get("content", "")) > per_msg_char_limit:
            original_len = len(msg["content"])
            msg["content"] = msg["content"][:per_msg_char_limit] + (
                f"\n\n[Truncado: se muestran {per_msg_char_limit} de {original_len} caracteres]"
            )
            logger.info(f"  Capped large tool msg: {original_len} → {len(msg['content'])} chars")

    # Recalculate
    result = system_msgs + non_system
    current_tokens = _est_tokens(result)
    if current_tokens <= token_budget:
        logger.info(f"🗜️ After tool compression: {current_tokens} tokens (fits budget)")
        return result

    # Step 3: Drop oldest non-system messages until within budget
    # Keep dropping from the front, but ALWAYS preserve the first user message
    # (SGLang/vLLM requires at least one "user" role message)

    # Find and protect the first user message
    first_user_idx = None
    for i, msg in enumerate(non_system):
        if msg.get("role") == "user":
            first_user_idx = i
            break

    # Extract and protect the first user message before trimming
    protected_user_msg = None
    if first_user_idx is not None:
        protected_user_msg = non_system[first_user_idx]

    while len(non_system) > safe_count and _est_tokens(system_msgs + non_system) > token_budget:
        # Never drop the protected user message
        if non_system[0] is protected_user_msg:
            # Skip it — try dropping the next one instead
            if len(non_system) > 1:
                non_system.pop(1)
            else:
                break  # Only the user message left, can't drop more
            continue
        # Don't start by dropping a tool message (would orphan it)
        if non_system[0].get("role") == "tool":
            non_system.pop(0)
            continue
        # If next message is assistant with tool_calls, drop it + its tool results
        if non_system[0].get("role") == "assistant" and non_system[0].get("tool_calls"):
            tool_call_ids = {
                tc.get("id", "") for tc in non_system[0].get("tool_calls", [])
            }
            non_system.pop(0)
            # Drop associated tool results
            while non_system and non_system[0].get("role") == "tool" and non_system[0].get("tool_call_id", "") in tool_call_ids:
                if non_system[0] is protected_user_msg:
                    break
                non_system.pop(0)
        else:
            non_system.pop(0)

    # Safety: ensure at least one user message exists
    if not any(m.get("role") == "user" for m in non_system):
        if protected_user_msg:
            non_system.insert(0, protected_user_msg)
        else:
            # Last resort: inject a minimal user message
            non_system.insert(0, {"role": "user", "content": "Continúa."})

    result = system_msgs + non_system
    final_tokens = _est_tokens(result)
    logger.info(
        f"🗜️ After trim: {final_tokens} tokens, {len(result)} messages "
        f"(dropped {len(llm_messages) - len(result)} messages)"
    )
    return result
