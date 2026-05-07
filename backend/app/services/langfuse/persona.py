"""Adapter from Main API to Langfuse for pushing agent persona prompts.

Architecture: the Langfuse SDK is only installed in the
``emma-agent-service`` microservice. Main API delegates to a thin
internal HTTP endpoint there (``POST /internal/prompts/push-persona``)
which is wired in Phase 2 of this feature.

Until that endpoint exists, this adapter behaves as a NO-OP that logs
a warning. When ``EMMA_INTERNAL_URL`` is configured AND the endpoint
responds 2xx, push happens for real.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LangfusePersonaAdapter:
    """Pushes ``agent_<slug>_persona`` to Langfuse via emma-agent-service."""

    def __init__(self, *, base_url: Optional[str] = None) -> None:
        # Reuse the existing EMMA_SERVICE_URL (already configured for the
        # Main-API → emma-agent-service hop).
        self._base_url = (base_url or getattr(settings, "EMMA_SERVICE_URL", "")).rstrip("/")
        self._api_key = getattr(settings, "MICROSERVICES_API_KEY", "")

    async def push_persona(self, *, slug: str, instructions: str) -> None:
        """Best-effort push. Raises only on hard 4xx/5xx from emma."""
        if not self._base_url:
            logger.warning(
                "LangfusePersonaAdapter: EMMA_SERVICE_URL not set; "
                "push of agent_%s_persona skipped",
                slug,
            )
            return

        url = f"{self._base_url}/internal/prompts/push-persona"
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(
                url,
                headers={"X-API-Key": self._api_key},
                json={"slug": slug, "instructions": instructions},
            )
        r.raise_for_status()
        logger.info("Pushed agent_%s_persona via emma (len=%d)", slug, len(instructions))
