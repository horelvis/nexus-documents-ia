"""
Cache Version Manager - Intelligent invalidation based on component versions

This module tracks versions of all components that affect cache validity:
- Embedding model version (changes how vectors are computed)
- Chunking strategy version (changes how documents are split)
- Index version (increments on reindex)
- Document versions (track individual document changes)

When any component version changes, affected caches are invalidated.
This prevents stale data from being returned after system updates.

Key design decisions:
1. Atomic version increments using Redis INCR
2. Version history for debugging (last 10 changes)
3. Event hooks for cache invalidation coordination
4. Tenant isolation in all version tracking

Example flow:
1. Admin triggers reindex for tenant_123
2. VersionManager.bump_index_version("tenant_123")
3. This bumps index version from "4" to "5"
4. All retrieval/context caches with version "4" become invalid
5. Next query gets fresh results, cached with version "5"
"""

import json
import logging
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime

import redis.asyncio as redis

from ....core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """Version information for cache validation"""
    embedding_model: str
    chunk_strategy: str
    index_version: str
    last_reindex: Optional[str]

    def to_dict(self) -> Dict[str, str]:
        return {
            "embedding_model": self.embedding_model,
            "chunk_strategy": self.chunk_strategy,
            "index_version": self.index_version,
            "last_reindex": self.last_reindex or "",
        }


# Type for invalidation callbacks
InvalidationCallback = Callable[[str, List[str]], Awaitable[int]]


class CacheVersionManager:
    """
    Manages version tracking for cache invalidation.

    Tracks versions at multiple levels:
    - Global: Embedding model, default chunking strategy
    - Tenant: Index version, tenant-specific settings
    - Document: Individual document update timestamps

    Configuration (env vars):
        CACHE_VERSION_PREFIX: Redis key prefix (default: "version:")
        CACHE_VERSION_HISTORY_SIZE: Number of version changes to track (default: 10)
    """

    PREFIX = "version:"
    HISTORY_PREFIX = "version:history:"
    DOC_VERSION_PREFIX = "version:doc:"

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._initialized = False
        self._invalidation_callbacks: List[InvalidationCallback] = []

        # Default versions (from settings)
        self._default_embedding_model = settings.embedding_model
        self._default_chunk_strategy = "semantic-v1"

    async def initialize(self):
        """Initialize Redis connection"""
        if self._initialized:
            return

        try:
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
            await self._redis.ping()
            self._initialized = True
            logger.info("🔖 CacheVersionManager initialized")
        except Exception as e:
            logger.warning(f"⚠️ CacheVersionManager initialization failed: {e}")
            self._initialized = False

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._initialized = False

    def register_invalidation_callback(self, callback: InvalidationCallback):
        """
        Register a callback to be called when documents are invalidated.

        Callbacks receive (tenant_id, doc_ids) and should return count invalidated.
        """
        self._invalidation_callbacks.append(callback)

    # =========================================================================
    # Version Getters
    # =========================================================================

    async def get_versions(self, tenant_id: str) -> VersionInfo:
        """
        Get current versions for all cache-affecting components.

        Returns default values if Redis unavailable or keys don't exist.
        """
        if not self._initialized or not self._redis:
            return VersionInfo(
                embedding_model=self._default_embedding_model,
                chunk_strategy=self._default_chunk_strategy,
                index_version="0",
                last_reindex=None,
            )

        try:
            keys = [
                f"{self.PREFIX}{tenant_id}:embedding_model",
                f"{self.PREFIX}{tenant_id}:chunk_strategy",
                f"{self.PREFIX}{tenant_id}:index_version",
                f"{self.PREFIX}{tenant_id}:last_reindex",
            ]

            values = await self._redis.mget(keys)

            return VersionInfo(
                embedding_model=values[0] or self._default_embedding_model,
                chunk_strategy=values[1] or self._default_chunk_strategy,
                index_version=values[2] or "0",
                last_reindex=values[3],
            )

        except Exception as e:
            logger.warning(f"⚠️ get_versions error: {e}")
            return VersionInfo(
                embedding_model=self._default_embedding_model,
                chunk_strategy=self._default_chunk_strategy,
                index_version="0",
                last_reindex=None,
            )

    async def get_index_version(self, tenant_id: str) -> str:
        """Get current index version for a tenant"""
        if not self._initialized or not self._redis:
            return "0"

        try:
            version = await self._redis.get(f"{self.PREFIX}{tenant_id}:index_version")
            return version or "0"
        except Exception as e:
            logger.warning(f"⚠️ get_index_version error: {e}")
            return "0"

    async def get_chunk_version(self, tenant_id: str) -> str:
        """Get current chunking strategy version for a tenant"""
        if not self._initialized or not self._redis:
            return self._default_chunk_strategy

        try:
            version = await self._redis.get(f"{self.PREFIX}{tenant_id}:chunk_strategy")
            return version or self._default_chunk_strategy
        except Exception as e:
            logger.warning(f"⚠️ get_chunk_version error: {e}")
            return self._default_chunk_strategy

    # =========================================================================
    # Version Setters (with history tracking)
    # =========================================================================

    async def _record_version_change(
        self,
        tenant_id: str,
        component: str,
        old_version: str,
        new_version: str,
        reason: str,
    ):
        """Record a version change in history (for debugging)"""
        if not self._redis:
            return

        try:
            history_key = f"{self.HISTORY_PREFIX}{tenant_id}"
            change = {
                "component": component,
                "old": old_version,
                "new": new_version,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self._redis.lpush(history_key, json.dumps(change))
            await self._redis.ltrim(history_key, 0, 9)  # Keep last 10 changes
        except Exception:
            pass  # History is best-effort

    async def bump_index_version(self, tenant_id: str, reason: str = "reindex") -> str:
        """
        Increment index version for a tenant.

        Called when:
        - Full reindex is performed
        - Bulk document operations complete
        - Index schema changes

        Returns the new version.
        """
        if not self._initialized or not self._redis:
            return "0"

        try:
            key = f"{self.PREFIX}{tenant_id}:index_version"
            old_version = await self._redis.get(key) or "0"

            # Atomic increment
            new_version = await self._redis.incr(key)
            new_version_str = str(new_version)

            # Record timestamp
            await self._redis.set(
                f"{self.PREFIX}{tenant_id}:last_reindex",
                datetime.utcnow().isoformat()
            )

            # Record in history
            await self._record_version_change(
                tenant_id, "index", old_version, new_version_str, reason
            )

            logger.info(f"🔖 Bumped index version for tenant {tenant_id}: "
                       f"{old_version} → {new_version_str} ({reason})")

            return new_version_str

        except Exception as e:
            logger.warning(f"⚠️ bump_index_version error: {e}")
            return "0"

    async def set_chunk_strategy(
        self,
        tenant_id: str,
        strategy: str,
        reason: str = "config_change"
    ) -> bool:
        """
        Set chunking strategy version for a tenant.

        Called when admin changes chunking settings.
        This invalidates all context caches for the tenant.
        """
        if not self._initialized or not self._redis:
            return False

        try:
            key = f"{self.PREFIX}{tenant_id}:chunk_strategy"
            old_strategy = await self._redis.get(key) or self._default_chunk_strategy

            await self._redis.set(key, strategy)

            await self._record_version_change(
                tenant_id, "chunk_strategy", old_strategy, strategy, reason
            )

            logger.info(f"🔖 Set chunk strategy for tenant {tenant_id}: "
                       f"{old_strategy} → {strategy} ({reason})")

            return True

        except Exception as e:
            logger.warning(f"⚠️ set_chunk_strategy error: {e}")
            return False

    async def set_embedding_model(
        self,
        tenant_id: str,
        model: str,
        reason: str = "model_upgrade"
    ) -> bool:
        """
        Set embedding model version for a tenant.

        Called when embedding model is upgraded.
        This should trigger a full reindex!
        """
        if not self._initialized or not self._redis:
            return False

        try:
            key = f"{self.PREFIX}{tenant_id}:embedding_model"
            old_model = await self._redis.get(key) or self._default_embedding_model

            await self._redis.set(key, model)

            await self._record_version_change(
                tenant_id, "embedding_model", old_model, model, reason
            )

            logger.warning(f"🔖 EMBEDDING MODEL CHANGED for tenant {tenant_id}: "
                          f"{old_model} → {model}. REINDEX REQUIRED!")

            return True

        except Exception as e:
            logger.warning(f"⚠️ set_embedding_model error: {e}")
            return False

    # =========================================================================
    # Document-level Version Tracking
    # =========================================================================

    async def mark_documents_updated(
        self,
        tenant_id: str,
        doc_ids: List[str],
        reason: str = "document_update"
    ) -> int:
        """
        Mark documents as updated, triggering cache invalidation.

        Called when:
        - Documents are created/updated/deleted
        - Document ACLs change
        - Document content is modified

        Returns total number of cache entries invalidated.
        """
        if not self._initialized or not self._redis:
            return 0

        if not doc_ids:
            return 0

        try:
            # Update document version timestamps
            now = time.time()
            pipe = self._redis.pipeline()
            for doc_id in doc_ids:
                key = f"{self.DOC_VERSION_PREFIX}{tenant_id}:{doc_id}"
                pipe.set(key, str(now))
                pipe.expire(key, 86400 * 7)  # Keep for 7 days
            await pipe.execute()

            # Notify registered caches to invalidate
            total_invalidated = 0
            for callback in self._invalidation_callbacks:
                try:
                    count = await callback(tenant_id, doc_ids)
                    total_invalidated += count
                except Exception as e:
                    logger.warning(f"⚠️ Invalidation callback error: {e}")

            logger.info(f"🔄 Marked {len(doc_ids)} documents updated, "
                       f"invalidated {total_invalidated} cache entries ({reason})")

            return total_invalidated

        except Exception as e:
            logger.warning(f"⚠️ mark_documents_updated error: {e}")
            return 0

    async def get_document_version(self, tenant_id: str, doc_id: str) -> Optional[str]:
        """Get last update timestamp for a document"""
        if not self._initialized or not self._redis:
            return None

        try:
            key = f"{self.DOC_VERSION_PREFIX}{tenant_id}:{doc_id}"
            return await self._redis.get(key)
        except Exception:
            return None

    # =========================================================================
    # History and Debugging
    # =========================================================================

    async def get_version_history(
        self,
        tenant_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent version changes for a tenant (for debugging)"""
        if not self._initialized or not self._redis:
            return []

        try:
            history_key = f"{self.HISTORY_PREFIX}{tenant_id}"
            items = await self._redis.lrange(history_key, 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as e:
            logger.warning(f"⚠️ get_version_history error: {e}")
            return []

    async def get_cache_health(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get overall cache health information for a tenant.

        Useful for admin dashboard monitoring.
        """
        versions = await self.get_versions(tenant_id)
        history = await self.get_version_history(tenant_id, limit=5)

        return {
            "tenant_id": tenant_id,
            "current_versions": versions.to_dict(),
            "recent_changes": history,
            "initialized": self._initialized,
            "callbacks_registered": len(self._invalidation_callbacks),
        }


# Global instance
cache_version_manager = CacheVersionManager()
