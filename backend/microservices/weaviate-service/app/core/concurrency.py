"""
Concurrency Control for LLM Workloads.

Controls access to shared resources (LLM, analysis pipeline) to ensure:
- Fair resource distribution
- Graceful handling of high load scenarios
"""
import asyncio
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyStats:
    """Global concurrency statistics."""
    global_active: int = 0
    global_queued: int = 0
    total_processed: int = 0
    total_rejected: int = 0
    total_wait_time_ms: float = 0


class ConcurrencyManager:
    """
    Manages concurrency for LLM and analysis operations.

    Uses asyncio.Semaphore for local concurrency control and
    Redis for distributed coordination (when scaled horizontally).

    Architecture:
    ```
    Request → GlobalLimiter → LLM
                    │
                    ▼
              max N global
    ```
    """

    def __init__(self):
        self._global_semaphore: Optional[asyncio.Semaphore] = None
        self._stats = ConcurrencyStats()
        self._redis: Optional[redis.Redis] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize concurrency manager."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            self._global_semaphore = asyncio.Semaphore(settings.llm_max_concurrent)

            try:
                self._redis = redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis.ping()
                logger.info(f"ConcurrencyManager connected to Redis")
            except Exception as e:
                logger.warning(f"Redis not available, using local semaphores only: {e}")
                self._redis = None

            self._initialized = True
            logger.info(
                f"ConcurrencyManager initialized: "
                f"global_max={settings.llm_max_concurrent}"
            )

    @asynccontextmanager
    async def acquire_llm_slot(self, operation: str = "analysis"):
        """
        Acquire a slot for LLM operation.

        Args:
            operation: Description of the operation (for logging)

        Raises:
            asyncio.TimeoutError: If slot not available within timeout

        Usage:
            async with concurrency_manager.acquire_llm_slot("document_analysis"):
                result = await llm.generate(...)
        """
        await self.initialize()

        start_time = time.time()
        self._stats.global_queued += 1

        try:
            try:
                await asyncio.wait_for(
                    self._global_semaphore.acquire(),
                    timeout=settings.llm_queue_timeout
                )
            except asyncio.TimeoutError:
                self._stats.total_rejected += 1
                logger.warning(
                    f"Timeout waiting for global slot ({operation})"
                )
                raise

            wait_time = (time.time() - start_time) * 1000
            self._stats.global_queued -= 1
            self._stats.global_active += 1
            self._stats.total_wait_time_ms += wait_time

            if wait_time > 1000:
                logger.info(
                    f"Acquired LLM slot after {wait_time:.0f}ms "
                    f"({operation}) [active: {self._stats.global_active}/{settings.llm_max_concurrent}]"
                )

            if self._redis:
                try:
                    await self._redis.incr("weaviate:concurrency:global_active")
                except Exception:
                    pass

            try:
                yield
            finally:
                self._global_semaphore.release()

                self._stats.global_active -= 1
                self._stats.total_processed += 1

                if self._redis:
                    try:
                        await self._redis.decr("weaviate:concurrency:global_active")
                    except Exception:
                        pass

        except asyncio.TimeoutError:
            self._stats.global_queued -= 1
            raise

    async def get_stats(self) -> Dict:
        """Get current concurrency statistics."""
        await self.initialize()

        return {
            "global": {
                "active": self._stats.global_active,
                "queued": self._stats.global_queued,
                "max_concurrent": settings.llm_max_concurrent,
                "total_processed": self._stats.total_processed,
                "total_rejected": self._stats.total_rejected,
            },
        }

    async def get_queue_position(self) -> int:
        """Estimate queue position for a new request."""
        await self.initialize()

        if self._stats.global_active < settings.llm_max_concurrent:
            return 0

        return self._stats.global_queued + 1


# Singleton instance
_concurrency_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """Get singleton concurrency manager."""
    global _concurrency_manager
    if _concurrency_manager is None:
        _concurrency_manager = ConcurrencyManager()
    return _concurrency_manager
