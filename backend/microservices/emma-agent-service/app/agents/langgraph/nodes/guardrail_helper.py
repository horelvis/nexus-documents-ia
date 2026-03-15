"""
Guardrail Helper — shared validation for synthesis nodes.

Called by synthesize_react, synthesize_swarm, and classify (fast-path).
Returns (final_content, metadata_dict) after applying guardrail results.
"""

import logging
from typing import Any, Dict, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

SECTOR_FALLBACK_MESSAGES = {
    "medical": (
        "⚕️ No puedo proporcionar esta información en el contexto sanitario. "
        "Consulte con un profesional sanitario cualificado."
    ),
    "legal": "⚖️ No puedo generar esta respuesta. Consulte con un profesional jurídico.",
    "documental": "No puedo generar esta respuesta. Reformule su consulta.",
}

DEFAULT_FALLBACK = "No puedo generar esta respuesta."


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
            fallback = SECTOR_FALLBACK_MESSAGES.get(sector, DEFAULT_FALLBACK)
            return fallback, metadata

        if result.redacted_content:
            content = result.redacted_content

        if result.disclaimers:
            content += "\n\n---\n" + "\n".join(result.disclaimers)

        return content, metadata

    except Exception as e:
        logger.error(f"Guardrail validation failed (non-blocking): {e}")
        return content, empty_metadata
