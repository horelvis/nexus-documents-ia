"""
Meta Agent Archive — Redis-backed strategy storage.

Follows the PredictiveCache pattern: sorted sets for fast lookup,
JSON strings for full data, and lazy connection management.

Redis key scheme:
    meta:archive:{intent}:{sector}   → Sorted Set (score=composite, value=strategy_id)
    meta:strategy:{id}               → String (JSON ArchiveEntry)
    meta:code:{code_hash}            → String (strategy_id for dedup)
    meta:default:{intent}:{sector}   → String (default strategy_id)
    meta:search:jobs                  → List (SearchJob records)
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from app.core.config import settings
from .schemas import ArchiveEntry, StrategyCandidate, EvaluationMetrics, SearchJob

logger = logging.getLogger(__name__)


class StrategyArchive:
    """Redis-backed archive for discovered strategies."""

    PREFIX = "meta"
    DEFAULT_TTL = 604800 * 4  # 28 days

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or settings.redis_url
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url, encoding="utf-8", decode_responses=True
            )

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    # ─── Key helpers ──────────────────────────────────────────────────────────

    def _archive_key(self, intent: str, sector: Optional[str] = None) -> str:
        s = sector or "generic"
        return f"{self.PREFIX}:archive:{intent}:{s}"

    def _strategy_key(self, strategy_id: str) -> str:
        return f"{self.PREFIX}:strategy:{strategy_id}"

    def _code_hash_key(self, code_hash: str) -> str:
        return f"{self.PREFIX}:code:{code_hash}"

    def _default_key(self, intent: str, sector: Optional[str] = None) -> str:
        s = sector or "generic"
        return f"{self.PREFIX}:default:{intent}:{s}"

    def _jobs_key(self) -> str:
        return f"{self.PREFIX}:search:jobs"

    # ─── CRUD ────────────────────────────────────────────────────────────────

    async def add_entry(self, entry: ArchiveEntry) -> bool:
        """Store a strategy with its score. Returns False if duplicate code."""
        await self.connect()

        code_hash = entry.strategy.code_hash
        if not code_hash:
            logger.warning("Strategy has no code_hash, skipping dedup check")
        else:
            existing = await self._redis.get(self._code_hash_key(code_hash))
            if existing:
                logger.debug(f"Duplicate code_hash {code_hash[:16]}... → {existing}")
                return False

        sid = entry.strategy.id
        intent = entry.strategy.intent_target
        sector = entry.strategy.sector_target
        score = entry.metrics.composite_score

        pipe = self._redis.pipeline()
        # Store full entry
        pipe.set(
            self._strategy_key(sid),
            entry.model_dump_json(),
            ex=self.DEFAULT_TTL,
        )
        # Add to sorted set
        pipe.zadd(self._archive_key(intent, sector), {sid: score})
        pipe.expire(self._archive_key(intent, sector), self.DEFAULT_TTL)
        # Dedup index
        if code_hash:
            pipe.set(self._code_hash_key(code_hash), sid, ex=self.DEFAULT_TTL)
        await pipe.execute()

        logger.info(
            f"Archived strategy {sid[:8]}... ({entry.strategy.name}) "
            f"score={score:.4f} intent={intent}"
        )
        return True

    async def get_entry(self, strategy_id: str) -> Optional[ArchiveEntry]:
        """Get a strategy entry by ID."""
        await self.connect()
        data = await self._redis.get(self._strategy_key(strategy_id))
        if data:
            return ArchiveEntry.model_validate_json(data)
        return None

    async def get_best_strategy(
        self, intent: str, sector: Optional[str] = None
    ) -> Optional[ArchiveEntry]:
        """Get the highest-scoring active strategy for intent+sector."""
        await self.connect()

        # Try default first
        default_id = await self._redis.get(self._default_key(intent, sector))
        if default_id:
            entry = await self.get_entry(default_id)
            if entry and entry.is_active:
                return entry

        # Fall back to top-scoring
        key = self._archive_key(intent, sector)
        top = await self._redis.zrevrange(key, 0, 0)
        if top:
            return await self.get_entry(top[0])
        return None

    async def get_default_strategy(
        self, intent: str, sector: Optional[str] = None
    ) -> Optional[ArchiveEntry]:
        """Get the explicitly promoted default strategy."""
        await self.connect()
        default_id = await self._redis.get(self._default_key(intent, sector))
        if default_id:
            entry = await self.get_entry(default_id)
            if entry and entry.is_active:
                return entry
        return None

    async def get_top_strategies(
        self, intent: str, sector: Optional[str] = None, limit: int = 5
    ) -> List[ArchiveEntry]:
        """Get top-K strategies by score."""
        await self.connect()
        key = self._archive_key(intent, sector)
        ids = await self._redis.zrevrange(key, 0, limit - 1)
        entries = []
        for sid in ids:
            entry = await self.get_entry(sid)
            if entry:
                entries.append(entry)
        return entries

    async def get_random_active(
        self, intent: str, sector: Optional[str] = None
    ) -> Optional[ArchiveEntry]:
        """Get a random active strategy (for epsilon-greedy exploration)."""
        await self.connect()
        key = self._archive_key(intent, sector)
        all_ids = await self._redis.zrange(key, 0, -1)
        if not all_ids:
            return None

        random.shuffle(all_ids)
        for sid in all_ids:
            entry = await self.get_entry(sid)
            if entry and entry.is_active:
                return entry
        return None

    async def promote_to_default(
        self, strategy_id: str, validation_score: Optional[float] = None
    ) -> bool:
        """Promote a strategy to default for its intent+sector.

        If validation_score is provided, only promotes if >= 85% of discovery score.
        """
        await self.connect()
        entry = await self.get_entry(strategy_id)
        if not entry:
            return False

        if validation_score is not None:
            discovery = entry.metrics.composite_score
            if discovery > 0 and validation_score < 0.85 * discovery:
                logger.warning(
                    f"Strategy {strategy_id[:8]}... validation score "
                    f"({validation_score:.4f}) < 85% of discovery ({discovery:.4f}). "
                    f"Not promoting."
                )
                return False

        intent = entry.strategy.intent_target
        sector = entry.strategy.sector_target

        from datetime import datetime
        entry.is_default = True
        entry.promoted_at = datetime.utcnow().isoformat()

        pipe = self._redis.pipeline()
        pipe.set(self._default_key(intent, sector), strategy_id, ex=self.DEFAULT_TTL)
        pipe.set(
            self._strategy_key(strategy_id),
            entry.model_dump_json(),
            ex=self.DEFAULT_TTL,
        )
        await pipe.execute()

        logger.info(f"Promoted strategy {strategy_id[:8]}... to default for {intent}/{sector}")
        return True

    async def deactivate_strategy(self, strategy_id: str) -> bool:
        """Remove strategy from online selection."""
        await self.connect()
        entry = await self.get_entry(strategy_id)
        if not entry:
            return False

        entry.is_active = False
        entry.is_default = False
        await self._redis.set(
            self._strategy_key(strategy_id),
            entry.model_dump_json(),
            ex=self.DEFAULT_TTL,
        )

        # Remove from default if it was default
        intent = entry.strategy.intent_target
        sector = entry.strategy.sector_target
        default_id = await self._redis.get(self._default_key(intent, sector))
        if default_id == strategy_id:
            await self._redis.delete(self._default_key(intent, sector))

        return True

    # ─── Production feedback ─────────────────────────────────────────────────

    async def record_production_use(
        self,
        strategy_id: str,
        latency_s: float,
        thumbs_up: bool = False,
        thumbs_down: bool = False,
    ) -> None:
        """Record a production usage event for a strategy."""
        await self.connect()
        entry = await self.get_entry(strategy_id)
        if not entry:
            return

        entry.production_uses += 1
        if thumbs_up:
            entry.production_thumbs_up += 1
        if thumbs_down:
            entry.production_thumbs_down += 1

        # Rolling average latency
        n = entry.production_uses
        entry.production_avg_latency_s = (
            entry.production_avg_latency_s * (n - 1) + latency_s
        ) / n

        await self._redis.set(
            self._strategy_key(strategy_id),
            entry.model_dump_json(),
            ex=self.DEFAULT_TTL,
        )

    # ─── Stats ───────────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """Get archive-wide statistics."""
        await self.connect()
        cursor = "0"
        total = 0
        by_intent: Dict[str, int] = {}

        while cursor != 0:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match=f"{self.PREFIX}:archive:*", count=100
            )
            for key in keys:
                # key format: meta:archive:{intent}:{sector}
                parts = key.split(":")
                if len(parts) >= 3:
                    intent = parts[2]
                    count = await self._redis.zcard(key)
                    total += count
                    by_intent[intent] = by_intent.get(intent, 0) + count

        return {
            "total_strategies": total,
            "by_intent": by_intent,
        }

    # ─── Search jobs ─────────────────────────────────────────────────────────

    async def store_search_job(self, job: SearchJob) -> None:
        """Store a search job record."""
        await self.connect()
        job_key = f"{self.PREFIX}:search:job:{job.job_id}"
        await self._redis.set(job_key, job.model_dump_json(), ex=self.DEFAULT_TTL)
        await self._redis.lpush(self._jobs_key(), job.job_id)
        await self._redis.ltrim(self._jobs_key(), 0, 49)  # Keep last 50

    async def get_search_job(self, job_id: str) -> Optional[SearchJob]:
        """Get a search job by ID."""
        await self.connect()
        data = await self._redis.get(f"{self.PREFIX}:search:job:{job_id}")
        if data:
            return SearchJob.model_validate_json(data)
        return None

    async def get_search_history(self, limit: int = 10) -> List[SearchJob]:
        """Get recent search job history."""
        await self.connect()
        job_ids = await self._redis.lrange(self._jobs_key(), 0, limit - 1)
        jobs = []
        for jid in job_ids:
            job = await self.get_search_job(jid)
            if job:
                jobs.append(job)
        return jobs


# =============================================================================
# Singleton
# =============================================================================

_archive: Optional[StrategyArchive] = None


def get_strategy_archive() -> StrategyArchive:
    """Get the singleton StrategyArchive (sync — init is cheap)."""
    global _archive
    if _archive is None:
        _archive = StrategyArchive()
    return _archive
