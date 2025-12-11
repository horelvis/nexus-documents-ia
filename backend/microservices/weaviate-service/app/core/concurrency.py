"""
Concurrency Control for SaaS Multi-Tenant Workloads.

Controls access to shared resources (LLM, analysis pipeline) to ensure:
- Fair resource distribution across tenants
- No single tenant can monopolize the system
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
class TenantStats:
    """Statistics for a single tenant."""
    active_analyses: int = 0
    total_analyses: int = 0
    total_wait_time_ms: float = 0
    last_analysis_time: float = 0


@dataclass
class ConcurrencyStats:
    """Global concurrency statistics."""
    global_active: int = 0
    global_queued: int = 0
    tenants: Dict[str, TenantStats] = field(default_factory=dict)
    total_processed: int = 0
    total_rejected: int = 0


class ConcurrencyManager:
    """
    Manages concurrency for LLM and analysis operations.

    Uses asyncio.Semaphore for local concurrency control and
    Redis for distributed coordination (when scaled horizontally).

    Architecture:
    ```
    Request → TenantLimiter → GlobalLimiter → LLM
                  │                 │
                  ▼                 ▼
            max 2/tenant      max 4 global
    ```
    """

    def __init__(self):
        self._global_semaphore: Optional[asyncio.Semaphore] = None
        self._tenant_semaphores: Dict[str, asyncio.Semaphore] = {}
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

            # Create global semaphore
            self._global_semaphore = asyncio.Semaphore(settings.llm_max_concurrent)

            # Connect to Redis for distributed coordination
            try:
                self._redis = redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis.ping()
                logger.info(f"✅ ConcurrencyManager connected to Redis")
            except Exception as e:
                logger.warning(f"⚠️ Redis not available, using local semaphores only: {e}")
                self._redis = None

            self._initialized = True
            logger.info(
                f"✅ ConcurrencyManager initialized: "
                f"global_max={settings.llm_max_concurrent}, "
                f"per_tenant_max={settings.analysis_max_per_tenant}"
            )

    def _get_tenant_semaphore(self, tenant_id: str) -> asyncio.Semaphore:
        """Get or create semaphore for a tenant."""
        if tenant_id not in self._tenant_semaphores:
            self._tenant_semaphores[tenant_id] = asyncio.Semaphore(
                settings.analysis_max_per_tenant
            )
        return self._tenant_semaphores[tenant_id]

    def _get_tenant_stats(self, tenant_id: str) -> TenantStats:
        """Get or create stats for a tenant."""
        if tenant_id not in self._stats.tenants:
            self._stats.tenants[tenant_id] = TenantStats()
        return self._stats.tenants[tenant_id]

    @asynccontextmanager
    async def acquire_llm_slot(self, tenant_id: str, operation: str = "analysis"):
        """
        Acquire a slot for LLM operation with tenant isolation.

        Args:
            tenant_id: Tenant requesting the slot
            operation: Description of the operation (for logging)

        Raises:
            asyncio.TimeoutError: If slot not available within timeout

        Usage:
            async with concurrency_manager.acquire_llm_slot(tenant_id, "document_analysis"):
                result = await llm.generate(...)
        """
        await self.initialize()

        start_time = time.time()
        tenant_stats = self._get_tenant_stats(tenant_id)
        tenant_sem = self._get_tenant_semaphore(tenant_id)

        self._stats.global_queued += 1

        try:
            # First acquire tenant slot (fair per-tenant limiting)
            if settings.tenant_isolation_enabled:
                try:
                    acquired = await asyncio.wait_for(
                        tenant_sem.acquire(),
                        timeout=settings.llm_queue_timeout / 2
                    )
                except asyncio.TimeoutError:
                    self._stats.total_rejected += 1
                    logger.warning(
                        f"⏱️ Tenant {tenant_id[:8]} timeout waiting for tenant slot "
                        f"({operation})"
                    )
                    raise

            # Then acquire global slot
            try:
                await asyncio.wait_for(
                    self._global_semaphore.acquire(),
                    timeout=settings.llm_queue_timeout
                )
            except asyncio.TimeoutError:
                if settings.tenant_isolation_enabled:
                    tenant_sem.release()
                self._stats.total_rejected += 1
                logger.warning(
                    f"⏱️ Tenant {tenant_id[:8]} timeout waiting for global slot "
                    f"({operation})"
                )
                raise

            # Track stats
            wait_time = (time.time() - start_time) * 1000
            self._stats.global_queued -= 1
            self._stats.global_active += 1
            tenant_stats.active_analyses += 1
            tenant_stats.total_wait_time_ms += wait_time

            if wait_time > 1000:  # Log if waited more than 1 second
                logger.info(
                    f"🔄 Tenant {tenant_id[:8]} acquired LLM slot after {wait_time:.0f}ms "
                    f"({operation}) [active: {self._stats.global_active}/{settings.llm_max_concurrent}]"
                )

            # Update Redis for distributed tracking (if available)
            if self._redis:
                try:
                    await self._redis.hincrby("weaviate:concurrency:active", tenant_id, 1)
                    await self._redis.incr("weaviate:concurrency:global_active")
                except Exception:
                    pass  # Non-critical

            try:
                yield
            finally:
                # Release slots
                self._global_semaphore.release()
                if settings.tenant_isolation_enabled:
                    tenant_sem.release()

                # Update stats
                self._stats.global_active -= 1
                tenant_stats.active_analyses -= 1
                tenant_stats.total_analyses += 1
                tenant_stats.last_analysis_time = time.time()
                self._stats.total_processed += 1

                # Update Redis
                if self._redis:
                    try:
                        await self._redis.hincrby("weaviate:concurrency:active", tenant_id, -1)
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
            "per_tenant": {
                "max_per_tenant": settings.analysis_max_per_tenant,
                "active_tenants": len([
                    t for t, s in self._stats.tenants.items()
                    if s.active_analyses > 0
                ]),
            },
            "tenants": {
                tid: {
                    "active": stats.active_analyses,
                    "total": stats.total_analyses,
                    "avg_wait_ms": (
                        stats.total_wait_time_ms / stats.total_analyses
                        if stats.total_analyses > 0 else 0
                    ),
                }
                for tid, stats in list(self._stats.tenants.items())[-10:]  # Last 10 tenants
            }
        }

    async def is_tenant_at_limit(self, tenant_id: str) -> bool:
        """Check if tenant is at their concurrency limit."""
        await self.initialize()
        stats = self._get_tenant_stats(tenant_id)
        return stats.active_analyses >= settings.analysis_max_per_tenant

    async def get_queue_position(self, tenant_id: str) -> int:
        """Estimate queue position for a new request."""
        await self.initialize()

        # Simple estimation based on current load
        if self._stats.global_active < settings.llm_max_concurrent:
            return 0  # No queue

        return self._stats.global_queued + 1


# Singleton instance
_concurrency_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """Get singleton concurrency manager."""
    global _concurrency_manager
    if _concurrency_manager is None:
        _concurrency_manager = ConcurrencyManager()
    return _concurrency_manager
