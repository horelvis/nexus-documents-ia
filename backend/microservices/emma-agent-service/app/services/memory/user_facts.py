"""
User Facts Service — Cross-session persistent memory for Emma.

Stores and retrieves user facts (name, department, preferences) across
chat sessions. Facts survive session expiry and are scoped to user only
(single-tenant deployment — tenant dimension removed).

Architecture (Phase 2 — LangGraph Store):
    PRIMARY:  AsyncPostgresStore (cross-thread memory, shared psycopg3 pool)
    FALLBACK: asyncpg + Redis (legacy, used when Store unavailable)

Store namespace scheme:
    ("user_facts", user_id) → key: "{category}/{fact_key}"
    value: {category, fact_key, fact_value, confidence, source, source_query}

Usage:
    service = get_user_facts_service()
    facts = await service.get_user_facts(user_id)
    prompt_section = await service.format_facts_for_prompt(user_id)
    await service.save_fact(user_id, "identity", "name", "Carlos", 1.0, "declared")
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

FACTS_CACHE_PREFIX = "emma:facts:"
FACTS_CACHE_TTL = int(getattr(settings, "user_memory_cache_ttl", 3600))


class UserFactsService:
    """CRUD + cache for persistent user facts.

    Prefers LangGraph AsyncPostgresStore when available (Phase 2).
    Falls back to direct asyncpg + Redis when Store is not initialized.
    """

    def __init__(self):
        self._pool = None  # asyncpg pool (legacy fallback)
        self._redis = None  # aioredis (legacy fallback)

    # ─── Store access ──────────────────────────────────────────────────

    async def _get_store(self):
        """Get the AsyncPostgresStore singleton (None if unavailable)."""
        try:
            from app.core.checkpointer import get_store
            return await get_store()
        except Exception:
            return None

    def _namespace(self, user_id: str) -> tuple:
        """Build Store namespace tuple for a user's facts."""
        return ("user_facts", user_id)

    def _store_key(self, category: str, fact_key: str) -> str:
        """Build Store key from category and fact_key."""
        return f"{category}/{fact_key}"

    # ─── Legacy connection management (fallback) ───────────────────────

    def _get_db_url(self) -> str:
        db_url = settings.database_url
        if "postgresql+asyncpg://" in db_url:
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        return db_url

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self._get_db_url(),
                min_size=1,
                max_size=3,
                command_timeout=15,
            )
        return self._pool

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
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

    # ─── Cache helpers (legacy) ────────────────────────────────────────

    def _cache_key(self, user_id: str) -> str:
        return f"{FACTS_CACHE_PREFIX}{user_id}"

    async def _invalidate_cache(self, user_id: str) -> None:
        try:
            r = await self._get_redis()
            await r.delete(self._cache_key(user_id))
        except Exception as e:
            logger.debug(f"Failed to invalidate facts cache: {e}")

    # ─── READ operations ──────────────────────────────────────────────

    async def get_user_facts(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        """Get all active facts for a user.

        Uses LangGraph Store (asearch) when available, falls back to
        Redis cache → PostgreSQL.

        Returns:
            List of fact dicts: [{id, category, fact_key, fact_value, confidence, source}]
        """
        if not user_id:
            return []

        # Try LangGraph Store first
        store = await self._get_store()
        if store is not None:
            return await self._get_facts_from_store(store, user_id)

        # Legacy fallback: Redis → PostgreSQL
        return await self._get_facts_legacy(user_id)

    async def _get_facts_from_store(
        self, store, user_id: str
    ) -> List[Dict[str, Any]]:
        """Read all facts from LangGraph Store via asearch()."""
        try:
            ns = self._namespace(user_id)
            max_facts = getattr(settings, "user_memory_max_facts", 50)
            items = await store.asearch(ns, limit=max_facts)

            facts = []
            for item in items:
                val = item.value
                if not val or not val.get("fact_value"):
                    continue
                facts.append({
                    "id": item.key,  # Store key is the identifier
                    "category": val.get("category", ""),
                    "fact_key": val.get("fact_key", ""),
                    "fact_value": val.get("fact_value", ""),
                    "confidence": val.get("confidence", 1.0),
                    "source": val.get("source", "declared"),
                })

            return sorted(facts, key=lambda f: (f["category"], f["fact_key"]))

        except Exception as e:
            logger.error(f"Store read failed, trying legacy: {e}")
            return await self._get_facts_legacy(user_id)

    async def _get_facts_legacy(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        """Legacy: Redis cache → PostgreSQL fallback."""
        # Try Redis cache
        try:
            r = await self._get_redis()
            cached = await r.get(self._cache_key(user_id))
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
                    WHERE user_id = $1 AND is_active = true
                    ORDER BY category, fact_key
                    """,
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
                    self._cache_key(user_id),
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
        self, user_id: str
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

        facts = await self.get_user_facts(user_id)
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
        user_id: str,
        category: str,
        fact_key: str,
        fact_value: str,
        confidence: float = 1.0,
        source: str = "declared",
        source_query: Optional[str] = None,
    ) -> bool:
        """Save or update a user fact.

        Uses LangGraph Store when available, falls back to PostgreSQL UPSERT.
        Store semantics: aput() is idempotent (same key overwrites).
        Confidence maximization: keeps max of existing vs new.

        Returns True on success.
        """
        if not user_id or not fact_key or not fact_value:
            return False

        store = await self._get_store()
        if store is not None:
            return await self._save_fact_store(
                store, user_id, category, fact_key,
                fact_value, confidence, source, source_query,
            )

        return await self._save_fact_legacy(
            user_id, category, fact_key,
            fact_value, confidence, source, source_query,
        )

    async def _save_fact_store(
        self, store, user_id: str,
        category: str, fact_key: str, fact_value: str,
        confidence: float, source: str, source_query: Optional[str],
    ) -> bool:
        """Save fact to LangGraph Store with confidence maximization."""
        try:
            ns = self._namespace(user_id)
            key = self._store_key(category, fact_key)

            # Check existing for confidence maximization
            existing = await store.aget(ns, key)
            if existing and existing.value:
                old_conf = existing.value.get("confidence", 0)
                confidence = max(old_conf, confidence)
                # Declared source wins
                if source != "declared" and existing.value.get("source") == "declared":
                    source = "declared"

            await store.aput(ns, key, {
                "category": category,
                "fact_key": fact_key,
                "fact_value": fact_value,
                "confidence": confidence,
                "source": source,
                "source_query": source_query,
            })

            logger.info(f"Saved fact [{category}/{fact_key}] for user {user_id[:8]}... (Store)")
            return True

        except Exception as e:
            logger.error(f"Store save failed, trying legacy: {e}")
            return await self._save_fact_legacy(
                user_id, category, fact_key,
                fact_value, confidence, source, source_query,
            )

    async def _save_fact_legacy(
        self, user_id: str,
        category: str, fact_key: str, fact_value: str,
        confidence: float, source: str, source_query: Optional[str],
    ) -> bool:
        """Legacy: PostgreSQL UPSERT + Redis invalidation."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO emma_user_memory_facts
                        (user_id, category, fact_key, fact_value,
                         confidence, source, source_query, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, true)
                    ON CONFLICT (user_id, category, fact_key)
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
                    user_id,
                    category,
                    fact_key,
                    fact_value,
                    confidence,
                    source,
                    source_query,
                )

            await self._invalidate_cache(user_id)
            logger.info(f"Saved fact [{category}/{fact_key}] for user {user_id[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to save user fact: {e}")
            return False

    async def delete_fact(
        self, user_id: str, fact_id: str
    ) -> bool:
        """Delete a single fact by ID.

        Store: adelete() by key (fact_id is the Store key).
        Legacy: soft-delete (is_active=false) by UUID.
        """
        store = await self._get_store()
        if store is not None:
            return await self._delete_fact_store(store, user_id, fact_id)
        return await self._delete_fact_legacy(user_id, fact_id)

    async def _delete_fact_store(
        self, store, user_id: str, fact_id: str
    ) -> bool:
        """Delete from Store. fact_id is the Store key (e.g. 'identity/name')."""
        try:
            ns = self._namespace(user_id)
            await store.adelete(ns, fact_id)
            logger.info(f"Deleted fact [{fact_id}] for user {user_id[:8]}... (Store)")
            return True
        except Exception as e:
            logger.error(f"Store delete failed: {e}")
            return False

    async def _delete_fact_legacy(
        self, user_id: str, fact_id: str
    ) -> bool:
        """Legacy: soft-delete by UUID."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE emma_user_memory_facts
                    SET is_active = false, updated_at = now()
                    WHERE id = $1::uuid AND user_id = $2
                    """,
                    fact_id,
                    user_id,
                )

            await self._invalidate_cache(user_id)
            return "UPDATE 1" in result

        except Exception as e:
            logger.error(f"Failed to delete fact: {e}")
            return False

    async def clear_user_facts(
        self, user_id: str
    ) -> int:
        """Hard-delete ALL facts for a user (GDPR right-to-erasure).

        Returns number of facts deleted.
        """
        store = await self._get_store()
        if store is not None:
            return await self._clear_facts_store(store, user_id)
        return await self._clear_facts_legacy(user_id)

    async def _clear_facts_store(
        self, store, user_id: str
    ) -> int:
        """Delete all facts from Store for a user."""
        try:
            ns = self._namespace(user_id)
            items = await store.asearch(ns, limit=200)
            count = 0
            for item in items:
                await store.adelete(ns, item.key)
                count += 1

            logger.info(f"GDPR: cleared {count} facts for user {user_id[:8]}... (Store)")
            return count

        except Exception as e:
            logger.error(f"Store clear failed, trying legacy: {e}")
            return await self._clear_facts_legacy(user_id)

    async def _clear_facts_legacy(
        self, user_id: str
    ) -> int:
        """Legacy: hard DELETE from PostgreSQL."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM emma_user_memory_facts
                    WHERE user_id = $1
                    """,
                    user_id,
                )

            await self._invalidate_cache(user_id)

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
