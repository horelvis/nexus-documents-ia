"""
Predictive Analysis Cache — Redis-backed storage for factors and results.

Key format (single-tenant; tenant_id segment removed in Plan 3):
    predictive:{session_id}:factors  → List[WeightedFactor]  (TTL: 1h)
    predictive:result:{session_id}   → PredictionResult      (TTL: 7d)
    predictive:meta:{session_id}     → session metadata      (TTL: 1h)

Note: method signatures retain ``tenant_id`` for backwards compatibility
with subgraph callers (Wave 6 scope). The argument is accepted but ignored.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

import redis.asyncio as redis

from app.core.config import settings
from app.schemas.predictive_analysis import WeightedFactor, PredictionResult

logger = logging.getLogger(__name__)


class PredictiveCache:
    """Redis-backed cache for predictive analysis sessions."""

    FACTORS_PREFIX = "predictive"
    RESULT_PREFIX = "predictive:result"
    META_PREFIX = "predictive:meta"

    DEFAULT_FACTORS_TTL = 3600      # 1 hour
    DEFAULT_RESULT_TTL = 604800     # 7 days

    def __init__(
        self,
        redis_url: Optional[str] = None,
        factors_ttl: int = DEFAULT_FACTORS_TTL,
        result_ttl: int = DEFAULT_RESULT_TTL,
    ):
        self._redis_url = redis_url or settings.redis_url
        self._factors_ttl = factors_ttl
        self._result_ttl = result_ttl
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url, encoding="utf-8", decode_responses=True
            )
            logger.info("✅ PredictiveCache connected to Redis")

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _factors_key(self, session_id: str) -> str:
        return f"{self.FACTORS_PREFIX}:{session_id}:factors"

    def _result_key(self, session_id: str) -> str:
        return f"{self.RESULT_PREFIX}:{session_id}"

    def _meta_key(self, session_id: str) -> str:
        return f"{self.META_PREFIX}:{session_id}"

    # =========================================================================
    # Factors (ordered list, append-only)
    # =========================================================================

    async def add_weighted_factor(
        self, _tenant_id_unused: str, session_id: str, factor: WeightedFactor
    ) -> int:
        await self.connect()
        key = self._factors_key(session_id)
        factor_json = json.dumps(factor.to_dict())
        count = await self._redis.rpush(key, factor_json)
        await self._redis.expire(key, self._factors_ttl)
        logger.info(
            f"📝 Added weighted factor #{factor.extraction_order} "
            f"(weight={factor.weight:.2f}, outcome={factor.outcome}) "
            f"to session {session_id[:16]}..."
        )
        return count

    async def get_weighted_factors(
        self, _tenant_id_unused: str, session_id: str
    ) -> List[WeightedFactor]:
        await self.connect()
        key = self._factors_key(session_id)
        factors_json = await self._redis.lrange(key, 0, -1)
        factors = []
        for fj in factors_json:
            try:
                data = json.loads(fj)
                factors.append(WeightedFactor.from_dict(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"⚠️ Failed to deserialize factor: {e}")
        return factors

    async def get_factors_count(self, _tenant_id_unused: str, session_id: str) -> int:
        await self.connect()
        key = self._factors_key(session_id)
        return await self._redis.llen(key)

    # =========================================================================
    # Result (final prediction)
    # =========================================================================

    async def store_result(
        self, _tenant_id_unused: str, session_id: str, result: PredictionResult
    ) -> None:
        await self.connect()
        key = self._result_key(session_id)
        result_dict = result.model_dump()
        result_dict["created_at"] = result_dict["created_at"].isoformat() if hasattr(result_dict["created_at"], "isoformat") else str(result_dict["created_at"])
        # Serialize WeightedFactor objects
        result_dict["factors"] = [f.to_dict() if hasattr(f, "to_dict") else f for f in result.factors]
        await self._redis.set(key, json.dumps(result_dict, default=str), ex=self._result_ttl)
        logger.info(f"📝 Stored prediction result for session {session_id[:16]}...")

    async def get_result(
        self, _tenant_id_unused: str, session_id: str
    ) -> Optional[PredictionResult]:
        await self.connect()
        key = self._result_key(session_id)
        data = await self._redis.get(key)
        if data:
            parsed = json.loads(data)
            parsed["factors"] = [WeightedFactor.from_dict(f) for f in parsed.get("factors", [])]
            return PredictionResult(**parsed)
        return None

    # =========================================================================
    # Session metadata
    # =========================================================================

    async def store_session_metadata(
        self, _tenant_id_unused: str, session_id: str, metadata: dict
    ) -> None:
        await self.connect()
        key = self._meta_key(session_id)
        await self._redis.set(key, json.dumps(metadata, default=str), ex=self._factors_ttl)

    async def get_session_metadata(
        self, _tenant_id_unused: str, session_id: str
    ) -> dict:
        await self.connect()
        key = self._meta_key(session_id)
        data = await self._redis.get(key)
        return json.loads(data) if data else {}

    # =========================================================================
    # Session management
    # =========================================================================

    async def clear_session(self, _tenant_id_unused: str, session_id: str) -> bool:
        await self.connect()
        keys = [
            self._factors_key(session_id),
            self._result_key(session_id),
            self._meta_key(session_id),
        ]
        await self._redis.delete(*keys)
        logger.info(f"🗑️ Cleared predictive session {session_id[:16]}...")
        return True

    async def extend_ttl(self, _tenant_id_unused: str, session_id: str) -> bool:
        await self.connect()
        key = self._factors_key(session_id)
        return await self._redis.expire(key, self._factors_ttl)

    async def get_ttl_remaining(
        self, _tenant_id_unused: str, session_id: str
    ) -> Optional[int]:
        await self.connect()
        key = self._factors_key(session_id)
        ttl = await self._redis.ttl(key)
        return ttl if ttl > 0 else None


# =============================================================================
# Singleton (with asyncio.Lock for race-safe initialization)
# =============================================================================

_predictive_cache: Optional[PredictiveCache] = None
_predictive_cache_lock: Optional["asyncio.Lock"] = None


def _get_cache_lock() -> "asyncio.Lock":
    """Lazy lock creation (must be called inside a running event loop)."""
    global _predictive_cache_lock
    if _predictive_cache_lock is None:
        import asyncio
        _predictive_cache_lock = asyncio.Lock()
    return _predictive_cache_lock


def get_predictive_cache() -> PredictiveCache:
    """Get the singleton PredictiveCache (sync — init is cheap, no I/O)."""
    global _predictive_cache
    if _predictive_cache is None:
        _predictive_cache = PredictiveCache()
    return _predictive_cache


async def get_predictive_cache_async() -> PredictiveCache:
    """Get the singleton PredictiveCache (async — race-safe)."""
    global _predictive_cache
    if _predictive_cache is None:
        async with _get_cache_lock():
            if _predictive_cache is None:
                _predictive_cache = PredictiveCache()
    return _predictive_cache


async def initialize_predictive_cache() -> PredictiveCache:
    cache = get_predictive_cache()
    await cache.connect()
    return cache
