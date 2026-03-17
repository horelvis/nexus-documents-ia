"""
CRAG Quality Gate — Corrective RAG for ReAct Loop

Implements two quality gates that catch common failure modes:

Gate 1 — Step-0 No-Tools:
  When the LLM skips tool calling on step 0 for a query that should trigger
  search (document_query, legal_query, analysis), inject a corrective message
  forcing it to use tools. This prevents the LLM from hallucinating answers
  without consulting any data source.

Gate 2 — Low-Quality Terminate:
  When the LLM calls terminate() with a low-quality answer (too short,
  no sources, "no encontré" without searching), block the terminate and
  inject a retry message. This prevents premature termination with vague
  or unsupported answers.

Both gates are heuristic (0ms, no LLM call) and allow max 1 retry each
to avoid infinite loops. The retry count is tracked via metadata.

Reference: Corrective RAG (CRAG) — Yan et al., 2024
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Patterns for extracting specific data from LLM answers ──
# Numbers with 3+ digits (invoice numbers, amounts, IDs) — excludes years and common numbers
_SPECIFIC_NUMBER_RE = re.compile(r'\b(\d{3,})\b')
# Money amounts like "1.234,56€" or "1,234.56"
_MONEY_RE = re.compile(r'(\d[\d.,]+)\s*[€$]|[€$]\s*(\d[\d.,]+)')
# Invoice/document number patterns like "FRA-1234", "FAC/2025/001"
_DOC_NUMBER_RE = re.compile(r'(?:FRA|FAC|ALB|NOM|CONT)[\s\-/]*(\d{2,}[\-/]?\d*)', re.IGNORECASE)

# Numbers to ignore (years, common counts, percentages)
_IGNORE_NUMBERS = {str(y) for y in range(1900, 2100)} | {"100", "200", "300", "500", "1000"}


def _extract_specific_data(text: str) -> Set[str]:
    """Extract specific numerical data points from text.

    Returns set of number strings that represent concrete, verifiable data
    (invoice numbers, amounts, IDs) — NOT generic counts or years.
    """
    data = set()

    # Extract 3+ digit numbers (invoice numbers, amounts, IDs)
    for m in _SPECIFIC_NUMBER_RE.finditer(text):
        num = m.group(1)
        if num not in _IGNORE_NUMBERS and not num.startswith("0"):
            data.add(num)

    # Extract money amounts
    for m in _MONEY_RE.finditer(text):
        amount = m.group(1) or m.group(2)
        if amount:
            data.add(amount)

    # Extract document/invoice number patterns
    for m in _DOC_NUMBER_RE.finditer(text):
        data.add(m.group(0))

    return data


def _detect_fabricated_data(
    answer: str,
    messages: Any,
) -> List[str]:
    """Detect data in the answer that doesn't appear in any tool observation.

    Scans all ToolMessage contents from the conversation to build a corpus
    of grounded data, then checks if the answer contains specific numbers
    that aren't in that corpus.

    Args:
        answer: The LLM's proposed final answer.
        messages: Conversation messages (list of BaseMessage).

    Returns:
        List of fabricated data points, empty if answer is grounded.
    """
    answer_data = _extract_specific_data(answer)
    if not answer_data:
        return []

    # Build corpus from all ToolMessage contents in conversation
    corpus_parts = []
    try:
        for msg in messages:
            # Check for ToolMessage by class name (avoid import dependency)
            if type(msg).__name__ == "ToolMessage" and hasattr(msg, "content"):
                corpus_parts.append(str(msg.content))
    except (TypeError, AttributeError):
        return []  # Can't inspect messages

    corpus = " ".join(corpus_parts)
    if not corpus:
        return []

    # Check which data points in the answer don't appear in observations
    fabricated = []
    for datum in answer_data:
        if datum not in corpus:
            fabricated.append(datum)

    # Only flag if we have significant fabrication (>= 2 ungrounded data points)
    # A single number could be a legitimate calculation (e.g., "3 facturas" from counting)
    if len(fabricated) >= 2:
        return fabricated

    return []

# Intents that require tool usage (search, analysis)
_TOOL_REQUIRED_INTENTS = {"document_query", "legal_query", "analysis"}

# Phrases indicating the LLM gave up without searching
_GAVE_UP_PHRASES = [
    "no encontré",
    "no he encontrado",
    "no tengo acceso",
    "no puedo acceder",
    "no dispongo",
    "no tengo información",
    "no puedo buscar",
    "lo siento, no",
]

# Corrective messages loaded from Langfuse (quality_corrective section)
# Loaded lazily on first use via _get_corrective_msg()

async def _get_corrective_msg(key: str) -> str:
    """Load a corrective message from Langfuse."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    prompt = await client.get_prompt(f"emma_quality_corrective_{key}")
    return prompt.content


async def assess_step0_no_tools(
    intent: str,
    step: int,
    has_tool_calls: bool,
    metadata: Dict[str, Any],
) -> Tuple[bool, str]:
    """Gate 1: Check if step 0 skipped tools for a search-requiring intent.

    Args:
        intent: Classified intent from classify_node.
        step: Current step number (0-indexed).
        has_tool_calls: Whether the LLM produced tool calls.
        metadata: State metadata (for tracking retries).

    Returns:
        (should_retry, corrective_message) — if should_retry is True,
        the caller should inject the corrective message and continue the loop.
    """
    if step != 0:
        return False, ""
    if has_tool_calls:
        return False, ""
    if intent not in _TOOL_REQUIRED_INTENTS:
        return False, ""
    if metadata.get("quality_gate_step0_retried"):
        return False, ""  # Already retried once

    logger.warning(
        f"⚠️ Quality Gate 1: Step 0 no-tools for intent '{intent}' — injecting retry"
    )
    return True, await _get_corrective_msg("no_tools")


async def assess_terminate_quality(
    answer: str,
    sources: List[Dict[str, Any]],
    intent: str,
    step: int,
    max_steps: int,
    metadata: Dict[str, Any],
    tool_calls_history: Optional[List[Dict[str, Any]]] = None,
    messages: Any = None,
) -> Tuple[bool, str]:
    """Gate 2: Check if the terminate answer meets minimum quality.

    Heuristics (all fast, no LLM):
    - Answer < 50 chars for document/legal query → too short
    - 0 sources for document/legal query → unsupported
    - Contains "no encontré" but no prior search tool calls → didn't try
    - Fabricated data — specific numbers in answer not in tool results
    - Max 1 retry per conversation (tracked via metadata)

    Args:
        answer: The terminate answer text.
        sources: Accumulated sources from tool results.
        intent: Classified intent.
        step: Current step number.
        max_steps: Maximum allowed steps.
        metadata: State metadata for retry tracking.
        tool_calls_history: History of tool calls made so far.
        messages: Conversation messages for faithfulness checking.

    Returns:
        (should_retry, corrective_message)
    """
    # Don't gate conversational or identity intents
    if intent not in _TOOL_REQUIRED_INTENTS:
        return False, ""

    # Don't retry if already retried or near max steps
    if metadata.get("quality_gate_terminate_retried"):
        return False, ""
    if step >= max_steps - 1:
        return False, ""  # Last step, can't retry

    # Heuristic 1: Answer too short
    if len(answer.strip()) < 50:
        logger.warning(
            f"⚠️ Quality Gate 2: Answer too short ({len(answer)} chars) "
            f"for intent '{intent}'"
        )
        return True, await _get_corrective_msg("low_quality")

    # Heuristic 2: No sources for document/legal query
    if not sources and intent in ("document_query", "legal_query"):
        search_tools = {"smart_search", "search_jurisprudence", "web_search"}
        has_searched = False
        if tool_calls_history:
            has_searched = any(
                tc.get("name") in search_tools for tc in tool_calls_history
            )

        if not has_searched:
            logger.warning(
                f"⚠️ Quality Gate 2: No sources and no search performed "
                f"for intent '{intent}'"
            )
            return True, await _get_corrective_msg("low_quality")

    # Heuristic 3: "No encontré" without prior search
    answer_lower = answer.lower()
    if any(phrase in answer_lower for phrase in _GAVE_UP_PHRASES):
        search_tools = {"smart_search", "search_jurisprudence", "web_search"}
        has_searched = False
        if tool_calls_history:
            has_searched = any(
                tc.get("name") in search_tools for tc in tool_calls_history
            )

        if not has_searched:
            logger.warning(
                f"⚠️ Quality Gate 2: Gave-up phrase detected without searching"
            )
            return True, await _get_corrective_msg("low_quality")

    # Heuristic 4: Low retrieval confidence (from retrieval_guard)
    retrieval_quality = metadata.get("last_retrieval_quality")
    if retrieval_quality and retrieval_quality.get("confidence") == "low":
        if not metadata.get("quality_gate_retrieval_retried"):
            logger.warning(
                f"⚠️ Quality Gate 4: Low retrieval confidence — "
                f"top_score={retrieval_quality.get('top_score', 0):.3f}, "
                f"entity_coverage={retrieval_quality.get('entity_coverage', 0):.2f}"
            )
            return True, await _get_corrective_msg("low_retrieval")

    # Heuristic 5: Faithfulness — detect fabricated specifics
    if messages and intent in _TOOL_REQUIRED_INTENTS:
        if not metadata.get("quality_gate_faithfulness_retried"):
            fabricated = _detect_fabricated_data(answer, messages)
            if fabricated:
                logger.warning(
                    f"⚠️ Quality Gate 5: Fabricated data detected — "
                    f"{fabricated[:3]}"
                )
                return True, await _get_corrective_msg("faithfulness")

    return False, ""
