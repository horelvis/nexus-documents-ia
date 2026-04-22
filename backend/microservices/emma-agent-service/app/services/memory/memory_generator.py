"""
Memory Generator — Planner LLM generates document memories

Takes document text + metadata and produces a compact memory:
summary (2-3 sentences), key entities, key topics.

Uses the PLANNER model (4B, fast) since this is structured extraction,
not quality text generation. Each memory costs ~200 input tokens +
~150 output tokens = ~350 total per document.

The generated memory is stored in the knowledge graph via the
knowledge-tree-service Memory Bank API.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum document text to send to planner (4B model has limited context)
_MAX_TEXT_CHARS = 8000

async def _get_memory_prompts(
    filename: str, semantic_type: str, text: str, text_len: int
) -> tuple:
    """Load memory generator prompts from Langfuse."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    system = await client.get_prompt("emma_memory_generator_system")
    user = await client.get_prompt(
        "emma_memory_generator_user",
        variables={
            "filename": filename,
            "semantic_type": semantic_type,
            "text_len": str(text_len),
            "text": text,
        },
    )
    return system.content, user.content


async def generate_document_memory(
    document_text: str,
    filename: str = "",
    semantic_type: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Generate a compact memory for a document using the planner LLM.

    Args:
        document_text: Full or partial document text
        filename: Document filename for context
        semantic_type: Document type (factura, contrato, etc.)

    Returns:
        Dict with summary, key_entities, key_topics or None on failure
    """
    if not document_text or len(document_text.strip()) < 50:
        logger.debug("Memory generator: text too short, skipping")
        return None

    # Truncate to planner context limit
    text = document_text[:_MAX_TEXT_CHARS]

    try:
        system_prompt, user_prompt = await _get_memory_prompts(
            filename=filename or "desconocido",
            semantic_type=semantic_type or "desconocido",
            text=text,
            text_len=len(text),
        )

        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        model = get_planner_model().bind(temperature=0.1, max_tokens=500)
        response = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        content = (response.content or "").strip()
        if not content:
            logger.warning("Memory generator: empty LLM response")
            return None

        # Clean thinking tags
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if "<think>" in content:
            content = content[:content.find("<think>")].strip()

        # Extract JSON from response
        memory = _extract_json(content)
        if memory is None:
            logger.warning(f"Memory generator: failed to parse JSON from response: {content[:200]}")
            return None

        # Validate and normalize
        return _normalize_memory(memory)

    except Exception as e:
        logger.warning(f"Memory generator: LLM call failed: {e}")
        return None


async def generate_and_store_memory(
    document_id: str,
    document_text: str,
    filename: str = "",
    semantic_type: str = "",
) -> Dict[str, Any]:
    """
    Generate a memory and store it in the knowledge graph.

    Combines generation + storage in one call for convenience.
    Returns the result from the knowledge-tree store API.
    """
    memory = await generate_document_memory(
        document_text=document_text,
        filename=filename,
        semantic_type=semantic_type,
    )

    if memory is None:
        return {"success": False, "error": "Memory generation failed"}

    try:
        from app.clients.knowledge_tree_client import get_knowledge_tree_client
        client = get_knowledge_tree_client()

        result = await client.store_memory(
            document_id=document_id,
            summary=memory["summary"],
            key_entities=memory["key_entities"],
            key_topics=memory["key_topics"],
            semantic_type=semantic_type or None,
        )

        if result.get("success"):
            logger.info(
                f"Memory stored for doc {document_id}: "
                f"{len(memory['summary'])} chars, "
                f"{len(memory['key_entities'])} entities, "
                f"{len(memory['key_topics'])} topics"
            )
        return result

    except Exception as e:
        logger.warning(f"Memory storage failed for {document_id}: {e}")
        return {"success": False, "error": str(e)}


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object from LLM response text."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _normalize_memory(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate and normalize a raw memory dict from LLM."""
    summary = (raw.get("summary") or "").strip()
    if not summary or len(summary) < 10:
        return None

    # Truncate overly long summaries
    if len(summary) > 500:
        summary = summary[:497] + "..."

    key_entities = raw.get("key_entities", [])
    if not isinstance(key_entities, list):
        key_entities = []
    key_entities = [str(e).strip() for e in key_entities if e][:10]

    key_topics = raw.get("key_topics", [])
    if not isinstance(key_topics, list):
        key_topics = []
    key_topics = [str(t).strip() for t in key_topics if t][:8]

    return {
        "summary": summary,
        "key_entities": key_entities,
        "key_topics": key_topics,
    }
