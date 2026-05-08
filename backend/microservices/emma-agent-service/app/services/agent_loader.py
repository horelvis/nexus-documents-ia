"""Loads an agent's full configuration (DB row + Langfuse persona + cache).

Cache is best-effort Redis with 60s TTL. On Redis unavailability the
loader still works (fetches every time).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from app.agents.llm_types import ModelRole

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 60


@dataclass
class LoadedAgent:
    """Resolved agent ready for invoke_agent tool execution."""

    id: str
    slug: str
    name: str
    color: str
    icon: str
    is_active: bool
    model_role: ModelRole
    temperature: float
    scope: dict
    persona_style: str
    persona_language: str
    persona_instructions: str  # resolved from Langfuse


class _MainAPI(Protocol):
    async def get_agent_by_slug(self, slug: str) -> Optional[dict]: ...


class _Langfuse(Protocol):
    async def get_prompt(self, name: str, *, label: str = "production") -> str: ...


class _Redis(Protocol):
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ex: int = ...) -> None: ...


class AgentLoader:
    """Resolves an agent slug → ``LoadedAgent`` (persona + scope)."""

    def __init__(self, main_api: _MainAPI, langfuse: _Langfuse, redis: Optional[_Redis] = None) -> None:
        self.main_api = main_api
        self.langfuse = langfuse
        self.redis = redis

    async def load_by_slug(self, slug: str) -> Optional[LoadedAgent]:
        cache_key = f"agent_loader:{slug}"
        if self.redis is not None:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return self._row_to_loaded(data, persona_instructions=data["_persona_instructions"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentLoader cache read failed for slug=%s: %s", slug, exc)

        row = await self.main_api.get_agent_by_slug(slug)
        if row is None or not row.get("is_active"):
            return None

        instructions = await self.langfuse.get_prompt(
            f"agent_{slug}_persona", label="production"
        )

        loaded = self._row_to_loaded(row, persona_instructions=instructions)
        if self.redis is not None:
            try:
                cache_payload = {**row, "_persona_instructions": instructions}
                await self.redis.set(cache_key, json.dumps(cache_payload), ex=CACHE_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentLoader cache write failed for slug=%s: %s", slug, exc)
        return loaded

    @staticmethod
    def _row_to_loaded(row: dict, *, persona_instructions: str) -> LoadedAgent:
        persona = row.get("persona") or {}
        # Cross-service enum mismatch: Main API stores uppercase ('CHAT',
        # 'PLANNER'); the microservice ModelRole values are lowercase
        # ('chat', 'planner'). Normalise + fall back to CHAT on unknowns.
        raw_role = str(row.get("model_role") or "CHAT").lower()
        try:
            model_role = ModelRole(raw_role)
        except ValueError:
            model_role = ModelRole.CHAT
        return LoadedAgent(
            id=str(row["id"]),
            slug=row["slug"],
            name=row["name"],
            color=row.get("color", "blue"),
            icon=row.get("icon", "IconRobot"),
            is_active=bool(row["is_active"]),
            model_role=model_role,
            temperature=float(row.get("temperature", 0.5)),
            scope=row.get("scope") or {},
            persona_style=persona.get("style", "concise"),
            persona_language=persona.get("language", "es"),
            persona_instructions=persona_instructions,
        )
