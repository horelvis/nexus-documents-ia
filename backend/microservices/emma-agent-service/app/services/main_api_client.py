"""HTTP client to the Main API for cross-service reads.

Used by ``AgentLoader`` to resolve a slug → DB row, and by the
agent usage counter to bump ``agents.usage_count`` after a successful
``invoke_agent`` call.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MainAPIClient:
    """Async client; authenticates with the shared MICROSERVICES_API_KEY header."""

    def __init__(self) -> None:
        # ``settings.api_url`` defaults to "http://api:8000" inside docker network.
        self._base_url = settings.api_url.rstrip("/")
        self._headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}

    async def get_agent_by_slug(self, slug: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{self._base_url}/api/v1/agents",
                params={"slug": slug, "active": True},
                headers=self._headers,
            )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            if row.get("slug") == slug:
                return row
        return None

    async def list_active_agents(self, *, limit: int = 50) -> list[dict]:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{self._base_url}/api/v1/agents",
                params={"active": True, "order_by": "usage_count"},
                headers=self._headers,
            )
        r.raise_for_status()
        rows = r.json()
        return rows[:limit]

    async def increment_agent_usage(self, agent_id: str) -> None:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.post(
                f"{self._base_url}/api/v1/agents/{agent_id}/usage",
                headers=self._headers,
            )
        if r.status_code not in (200, 204):
            logger.warning(
                "Agent usage increment HTTP %s for id=%s body=%s",
                r.status_code,
                agent_id,
                r.text[:200],
            )
