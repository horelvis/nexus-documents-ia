"""
User Facts Service — Cross-session persistent memory for Emma.

Stores and retrieves user facts (name, department, preferences) across
chat sessions. Facts survive session expiry and are scoped to (tenant, user).

Architecture:
    READ:  Redis cache (1h TTL) → PostgreSQL fallback
    WRITE: PostgreSQL UPSERT → Redis cache invalidation

Usage:
    service = get_user_facts_service()
    facts = await service.get_user_facts(tenant_id, user_id)
    prompt_section = await service.format_facts_for_prompt(tenant_id, user_id)
    await service.save_fact(tenant_id, user_id, "identity", "name", "Carlos", 1.0, "declared")
"""

import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

FACTS_CACHE_PREFIX = "emma:facts:"
FACTS_CACHE_TTL = int(getattr(settings, "user_memory_cache_ttl", 3600))


class UserFactsService:
    """CRUD + cache for persistent user facts."""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[aioredis.Redis] = None

    # ─── Connection management ────────────────────────────────────────

    def _get_db_url(self) -> str:
        db_url = settings.database_url
        if "postgresql+asyncpg://" in db_url:
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        return db_url

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._get_db_url(),
                min_size=1,
                max_size=3,
                command_timeout=15,
            )
        return self._pool

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
        return self._redis

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    # ─── Cache helpers ────────────────────────────────────────────────

    def _cache_key(self, tenant_id: str, user_id: str) -> str:
        return f"{FACTS_CACHE_PREFIX}{tenant_id}:{user_id}"

    async def _invalidate_cache(self, tenant_id: str, user_id: str) -> None:
        try:
            r = await self._get_redis()
            await r.delete(self._cache_key(tenant_id, user_id))
        except Exception as e:
            logger.warning(f"Failed to invalidate facts cache: {e}")

    # ─── READ operations ──────────────────────────────────────────────

    async def get_user_facts(
        self, tenant_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Get all active facts for a user. Redis-cached with PostgreSQL fallback.

        Returns:
            List of fact dicts: [{category, fact_key, fact_value, confidence, source}]
        """
        if not user_id:
            return []

        # Try Redis cache first
        try:
            r = await self._get_redis()
            cached = await r.get(self._cache_key(tenant_id, user_id))
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug(f"Facts cache miss or error: {e}")

        # PostgreSQL fallback
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, category, fact_key, fact_value, confidence, source, source_query,
                           created_at, updated_at
                    FROM emma_user_memory_facts
                    WHERE tenant_id = $1::uuid AND user_id = $2 AND is_active = true
                    ORDER BY category, fact_key
                    """,
                    tenant_id,
                    user_id,
                )

            facts = [
                {
                    "id": str(row["id"]),
                    "category": row["category"],
                    "fact_key": row["fact_key"],
                    "fact_value": row["fact_value"],
                    "confidence": row["confidence"],
                    "source": row["source"],
                }
                for row in rows
            ]

            # Populate cache
            try:
                r = await self._get_redis()
                await r.set(
                    self._cache_key(tenant_id, user_id),
                    json.dumps(facts),
                    ex=FACTS_CACHE_TTL,
                )
            except Exception:
                pass

            return facts

        except Exception as e:
            logger.error(f"Failed to load user facts from DB: {e}")
            return []

    async def format_facts_for_prompt(
        self, tenant_id: str, user_id: str
    ) -> str:
        """Format user facts as a prompt section for LLM injection.

        Returns empty string if no facts or feature disabled.

        Example output:
            ## Memoria del usuario
            - Nombre: Carlos
            - Departamento: Legal
            - Prefiere respuestas en español
        """
        if not getattr(settings, "user_memory_enabled", True):
            return ""

        facts = await self.get_user_facts(tenant_id, user_id)
        if not facts:
            return ""

        # Group by category for readability
        categories = {
            "identity": "Identidad",
            "work": "Trabajo",
            "preference": "Preferencias",
            "interest": "Intereses",
        }

        lines = ["## Memoria del usuario"]
        for fact in facts:
            cat_label = categories.get(fact["category"], fact["category"])
            key = fact["fact_key"].replace("_", " ").capitalize()
            value = fact["fact_value"]
            confidence = fact.get("confidence", 1.0)

            if confidence >= 0.8:
                lines.append(f"- {key}: {value}")
            else:
                lines.append(f"- {key}: {value} (inferido)")

        # Enforce max facts limit
        max_facts = getattr(settings, "user_memory_max_facts", 50)
        if len(lines) > max_facts + 1:  # +1 for header
            lines = lines[: max_facts + 1]
            lines.append("- (...más hechos omitidos)")

        return "\n".join(lines)

    # ─── WRITE operations ─────────────────────────────────────────────

    async def save_fact(
        self,
        tenant_id: str,
        user_id: str,
        category: str,
        fact_key: str,
        fact_value: str,
        confidence: float = 1.0,
        source: str = "declared",
        source_query: Optional[str] = None,
    ) -> bool:
        """Save or update a user fact via UPSERT.

        If a fact with the same (tenant, user, category, key) exists and is active,
        it updates the value. Otherwise, it inserts a new row.

        Returns True on success.
        """
        if not user_id or not fact_key or not fact_value:
            return False

        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO emma_user_memory_facts
                        (tenant_id, user_id, category, fact_key, fact_value,
                         confidence, source, source_query, is_active)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, true)
                    ON CONFLICT (tenant_id, user_id, category, fact_key)
                        WHERE is_active = true
                    DO UPDATE SET
                        fact_value = EXCLUDED.fact_value,
                        confidence = GREATEST(emma_user_memory_facts.confidence, EXCLUDED.confidence),
                        source = CASE
                            WHEN EXCLUDED.source = 'declared' THEN 'declared'
                            ELSE emma_user_memory_facts.source
                        END,
                        source_query = COALESCE(EXCLUDED.source_query, emma_user_memory_facts.source_query),
                        updated_at = now()
                    """,
                    tenant_id,
                    user_id,
                    category,
                    fact_key,
                    fact_value,
                    confidence,
                    source,
                    source_query,
                )

            await self._invalidate_cache(tenant_id, user_id)
            logger.info(f"Saved fact [{category}/{fact_key}] for user {user_id[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to save user fact: {e}")
            return False

    async def delete_fact(
        self, tenant_id: str, user_id: str, fact_id: str
    ) -> bool:
        """Soft-delete a single fact by ID."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE emma_user_memory_facts
                    SET is_active = false, updated_at = now()
                    WHERE id = $1::uuid AND tenant_id = $2::uuid AND user_id = $3
                    """,
                    fact_id,
                    tenant_id,
                    user_id,
                )

            await self._invalidate_cache(tenant_id, user_id)
            return "UPDATE 1" in result

        except Exception as e:
            logger.error(f"Failed to delete fact: {e}")
            return False

    async def clear_user_facts(
        self, tenant_id: str, user_id: str
    ) -> int:
        """Hard-delete ALL facts for a user (GDPR right-to-erasure).

        Returns number of facts deleted.
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM emma_user_memory_facts
                    WHERE tenant_id = $1::uuid AND user_id = $2
                    """,
                    tenant_id,
                    user_id,
                )

            await self._invalidate_cache(tenant_id, user_id)

            # Parse "DELETE N" result
            count = int(result.split()[-1]) if result else 0
            logger.info(f"GDPR: cleared {count} facts for user {user_id[:8]}...")
            return count

        except Exception as e:
            logger.error(f"Failed to clear user facts: {e}")
            return 0


# ─── Singleton ────────────────────────────────────────────────────────

_user_facts_service: Optional[UserFactsService] = None


def get_user_facts_service() -> UserFactsService:
    """Get the global UserFactsService singleton."""
    global _user_facts_service
    if _user_facts_service is None:
        _user_facts_service = UserFactsService()
    return _user_facts_service
