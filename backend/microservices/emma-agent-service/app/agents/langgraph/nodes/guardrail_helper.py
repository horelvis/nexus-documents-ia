"""
Guardrail Helper — shared validation for synthesis nodes.

Called by synthesize_react, synthesize_swarm, and classify (fast-path).
Returns (final_content, metadata_dict) after applying guardrail results.
"""

import logging
from typing import Any, Dict, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

async def _get_guardrail_fallback(sector: str) -> str:
    """Get guardrail blocked-content message from Langfuse."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    # Try sector-specific first, then default
    name = f"emma_guardrail_sector_{sector}" if sector else "emma_guardrail_default"
    try:
        prompt = await client.get_prompt(name)
        return prompt.content
    except Exception:
        prompt = await client.get_prompt("emma_guardrail_default")
        return prompt.content


async def apply_guardrails(
    content: str,
    state: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate content against sector-aware guardrails.

    Args:
        content: LLM-generated response text.
        state: LangGraph state dict (needs 'sector', 'tenant_id').

    Returns:
        (final_content, metadata_dict) where metadata_dict has:
          guardrail_blocked: bool
          guardrail_redacted: bool
          guardrail_warnings: list[str]
    """
    empty_metadata = {
        "guardrail_blocked": False,
        "guardrail_redacted": False,
        "guardrail_warnings": [],
    }

    if not settings.guardrails_enabled:
        return content, empty_metadata

    try:
        from app.services.guardrail_service import get_guardrail_service

        service = get_guardrail_service()
        sector = state.get("sector")
        tenant_id = state.get("tenant_id")

        result = await service.validate(
            content=content,
            agent_name="synthesize",
            tenant_id=tenant_id,
            sector=sector,
        )

        metadata = {
            "guardrail_blocked": result.should_block,
            "guardrail_redacted": result.redacted_content is not None,
            "guardrail_warnings": [
                r.guardrail_name for r in result.results if r.matched
            ],
        }

        if result.should_block:
            fallback = await _get_guardrail_fallback(sector)
            return fallback, metadata

        if result.redacted_content:
            content = result.redacted_content

        if result.disclaimers:
            content += "\n\n---\n" + "\n".join(result.disclaimers)

        return content, metadata

    except Exception as e:
        logger.error(f"Guardrail validation failed (non-blocking): {e}")
        return content, empty_metadata
