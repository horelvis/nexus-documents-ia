"""
Retrieval Cache - Caches vector search results (doc IDs + scores)

This layer caches the OUTPUT of vector search operations, NOT the final response.
By caching at this layer, we avoid:
- Expensive vector similarity computations
- Network round-trips to Weaviate
- Re-ranking computations

Key design decisions:
1. User-isolated: Cache keys include user_id for ACL-aware caching
2. Embedding-based keys: Uses truncated embedding for deterministic matching
3. TTL-based invalidation: Short TTL (5-15 min) since search results can change
4. Event-based invalidation: On document CRUD operations
5. Single-tenant deployment (on-premise) — legacy tenant_id kwargs are
   accepted-and-ignored for backwards compat with Wave-3 upstream callers.

Performance impact:
- Cache hit: ~10ms (Redis lookup)
- Cache miss: ~100-500ms (full vector search)
- Expected hit rate: 40-60% for repeated/similar queries
"""

import json
import logging
import time
import hashlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

import redis.asyncio as redis

from ....core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CachedRetrievalResult:
    """Cached retrieval results (document IDs + scores only, not content)"""
    doc_ids: List[str]
    scores: List[float]
    metadata: Dict[str, Any]  # Search metadata (RRF weights, etc.)
    cached_at: float
    query_hash: str
    version: str  # Index version when cached

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedRetrievalResult":
        return cls(**data)


@dataclass
class RetrievalCacheStats:
    """Statistics for retrieval cache performance"""
    hits: int = 0
    misses: int = 0
    total_queries: int = 0
    avg_hit_latency_ms: float = 0.0
    invalidations: int = 0

    @property
    def hit_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.hits / self.total_queries


class RetrievalCache:
    """
    Redis-based cache for vector search results.

    Caches the list of (doc_id, score) pairs from retrieval, NOT the document content.
    This allows the Context Assembly layer to fetch only the needed documents.

    Configuration (env vars):
        RETRIEVAL_CACHE_ENABLED: Enable/disable (default: true)
        RETRIEVAL_CACHE_TTL_SECONDS: TTL in seconds (default: 300 = 5 min)
        RETRIEVAL_CACHE_MAX_ENTRIES: Max entries per user (default: 500)
    """

    KEY_PREFIX = "retrieval:"
    INDEX_PREFIX = "retrieval:index:"
    VERSION_KEY = "retrieval:version:"

    def __init__(
        self,
        ttl_seconds: int = 300,  # 5 minutes default
        max_entries_per_user: int = 500,
    ):
        self._redis: Optional[redis.Redis] = None
        self._initialized = False
        self.ttl_seconds = ttl_seconds
        self.max_entries_per_user = max_entries_per_user
        self._stats = RetrievalCacheStats()

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
            logger.info(f"🗄️ RetrievalCache initialized (ttl={self.ttl_seconds}s)")
        except Exception as e:
            logger.warning(f"⚠️ RetrievalCache initialization failed: {e}")
            self._initialized = False

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._initialized = False

    def _build_cache_key(
        self,
        query_embedding: List[float],
        user_id: str,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        include_public: bool = True,
    ) -> str:
        """
        Build deterministic cache key from search parameters.

        SECURITY: Includes user_id to prevent cross-user cache pollution.
        ACL-filtered results for one user should never be returned to another.
        """
        # Use truncated, rounded embedding for key stability
        # Full embedding is 1024 dims, we use first 64 for key (enough for uniqueness)
        truncated_emb = [round(x, 5) for x in query_embedding[:64]]

        key_components = {
            "emb": truncated_emb,
            "user": user_id,
            "collection": collection_name or "default",
            "top_k": top_k,
            "public": include_public,
        }

        key_json = json.dumps(key_components, sort_keys=True)
        key_hash = hashlib.sha256(key_json.encode()).hexdigest()[:24]

        return f"{self.KEY_PREFIX}{user_id}:{key_hash}"

    def _index_key(self, user_id: str) -> str:
        """Index key for tracking user's cached queries"""
        return f"{self.INDEX_PREFIX}{user_id}"

    async def get(
        self,
        query_embedding: List[float],
        user_id: str,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        include_public: bool = True,
        current_version: Optional[str] = None,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> Optional[CachedRetrievalResult]:
        """
        Get cached retrieval results if available.

        Args:
            query_embedding: Query embedding vector
            user_id: User identifier (REQUIRED for ACL isolation)
            collection_name: Optional collection filter
            top_k: Number of results requested
            include_public: Whether public knowledge is included
            current_version: Current index version (for invalidation check)
            tenant_id: DEPRECATED, ignored (single-tenant deployment)

        Returns:
            CachedRetrievalResult if cache hit, None otherwise
        """
        if not self._initialized or not self._redis:
            return None

        if not user_id:
            logger.warning("⚠️ RetrievalCache.get: user_id required for ACL safety")
            return None

        self._stats.total_queries += 1
        start_time = time.time()

        try:
            cache_key = self._build_cache_key(
                query_embedding, user_id,
                collection_name, top_k, include_public
            )

            cached_json = await self._redis.get(cache_key)
            if not cached_json:
                self._stats.misses += 1
                return None

            cached_data = json.loads(cached_json)
            result = CachedRetrievalResult.from_dict(cached_data)

            # Version check: invalidate if index has been updated
            if current_version and result.version != current_version:
                logger.info(f"🔄 Retrieval cache invalidated: version mismatch "
                           f"(cached={result.version}, current={current_version})")
                await self._redis.delete(cache_key)
                self._stats.misses += 1
                self._stats.invalidations += 1
                return None

            # Update stats
            self._stats.hits += 1
            latency_ms = (time.time() - start_time) * 1000
            n = self._stats.hits
            self._stats.avg_hit_latency_ms = (
                (self._stats.avg_hit_latency_ms * (n - 1) + latency_ms) / n
            )

            logger.debug(f"✅ Retrieval cache HIT: {len(result.doc_ids)} docs in {latency_ms:.1f}ms")
            return result

        except Exception as e:
            logger.warning(f"⚠️ RetrievalCache.get error: {e}")
            self._stats.misses += 1
            return None

    async def set(
        self,
        query_embedding: List[float],
        user_id: str,
        doc_ids: List[str],
        scores: List[float],
        metadata: Dict[str, Any],
        collection_name: Optional[str] = None,
        top_k: int = 10,
        include_public: bool = True,
        version: str = "0",
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> bool:
        """
        Store retrieval results in cache.

        Args:
            query_embedding: Query embedding used for search
            user_id: User identifier (REQUIRED for ACL isolation)
            doc_ids: List of retrieved document IDs
            scores: Corresponding relevance scores
            metadata: Search metadata (RRF weights, selection info, etc.)
            collection_name: Collection searched
            top_k: Number of results
            include_public: Whether public knowledge was included
            version: Current index version
            tenant_id: DEPRECATED, ignored (single-tenant deployment)

        Returns:
            True if cached successfully
        """
        if not self._initialized or not self._redis:
            return False

        if not user_id:
            logger.warning("⚠️ RetrievalCache.set: user_id required for ACL safety")
            return False

        try:
            cache_key = self._build_cache_key(
                query_embedding, user_id,
                collection_name, top_k, include_public
            )

            result = CachedRetrievalResult(
                doc_ids=doc_ids,
                scores=scores,
                metadata=metadata,
                cached_at=time.time(),
                query_hash=cache_key.split(":")[-1],
                version=version,
            )

            # Store with TTL
            await self._redis.setex(
                cache_key,
                self.ttl_seconds,
                json.dumps(result.to_dict())
            )

            # Track in user's index (for cleanup)
            index_key = self._index_key(user_id)
            await self._redis.lpush(index_key, cache_key)
            await self._redis.expire(index_key, self.ttl_seconds * 2)  # Longer TTL for index

            # Enforce max entries per user
            index_len = await self._redis.llen(index_key)
            if index_len > self.max_entries_per_user:
                # Remove oldest entries
                old_keys = await self._redis.lrange(
                    index_key, self.max_entries_per_user, -1
                )
                for old_key in old_keys:
                    await self._redis.delete(old_key)
                await self._redis.ltrim(index_key, 0, self.max_entries_per_user - 1)

            logger.debug(f"📝 Cached retrieval: {len(doc_ids)} docs for user {user_id[:8]}...")
            return True

        except Exception as e:
            logger.warning(f"⚠️ RetrievalCache.set error: {e}")
            return False

    async def invalidate_user(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> int:
        """
        Invalidate all cached retrievals for a user.

        Called when user's ACL changes (role assignment, etc.)
        """
        if not self._initialized or not self._redis:
            return 0

        try:
            index_key = self._index_key(user_id)
            cache_keys = await self._redis.lrange(index_key, 0, -1)

            count = 0
            for cache_key in cache_keys:
                count += await self._redis.delete(cache_key)

            await self._redis.delete(index_key)

            if count > 0:
                logger.info(f"🔄 Invalidated {count} retrieval cache entries for user {user_id[:8]}...")
                self._stats.invalidations += count

            return count

        except Exception as e:
            logger.warning(f"⚠️ RetrievalCache.invalidate_user error: {e}")
            return 0

    async def invalidate_all(
        self,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> int:
        """
        Invalidate all cached retrievals (entire index rebuild or bulk update).
        """
        if not self._initialized or not self._redis:
            return 0

        try:
            # Find all retrieval cache keys
            pattern = f"{self.KEY_PREFIX}*"
            cursor = 0
            count = 0

            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                # Filter out index keys — we handle those separately
                data_keys = [k for k in keys if not k.startswith(self.INDEX_PREFIX)]
                if data_keys:
                    count += await self._redis.delete(*data_keys)
                if cursor == 0:
                    break

            # Also clean up index keys
            index_pattern = f"{self.INDEX_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=index_pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

            if count > 0:
                logger.info(f"🔄 Invalidated {count} retrieval cache entries (all)")
                self._stats.invalidations += count

            return count

        except Exception as e:
            logger.warning(f"⚠️ RetrievalCache.invalidate_all error: {e}")
            return 0

    # Backwards-compatible alias — callers still use invalidate_tenant()
    async def invalidate_tenant(
        self,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> int:
        """Deprecated alias for invalidate_all()."""
        return await self.invalidate_all()

    async def invalidate_by_documents(
        self,
        tenant_id: Optional[str] = None,  # legacy positional arg (accepted-and-ignored)
        doc_ids: Optional[List[str]] = None,
    ) -> int:
        """
        Invalidate cache entries that include specific documents.

        Called when documents are updated or deleted. Scans all cache entries
        and removes those containing any of the specified document IDs.

        Signature kept compatible with the version_manager invalidation callback
        contract `(tenant_id, doc_ids)`. The tenant_id arg is ignored.

        Note: This is O(n) but is called infrequently (on document CRUD).
        """
        if not self._initialized or not self._redis:
            return 0

        # Handle both call styles:
        #   invalidate_by_documents(doc_ids=[...])              — new
        #   invalidate_by_documents(_SINGLE_TENANT, [...])      — legacy callback
        if doc_ids is None and isinstance(tenant_id, list):
            doc_ids = tenant_id
        if not doc_ids:
            return 0

        try:
            pattern = f"{self.KEY_PREFIX}*"
            cursor = 0
            count = 0
            doc_ids_set = set(doc_ids)

            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)

                for key in keys:
                    # Skip index keys
                    if key.startswith(self.INDEX_PREFIX):
                        continue

                    try:
                        cached_json = await self._redis.get(key)
                        if cached_json:
                            cached_data = json.loads(cached_json)
                            cached_doc_ids = set(cached_data.get("doc_ids", []))

                            # If any cached doc_id is in our invalidation set
                            if cached_doc_ids & doc_ids_set:
                                await self._redis.delete(key)
                                count += 1
                    except (json.JSONDecodeError, TypeError):
                        continue

                if cursor == 0:
                    break

            if count > 0:
                logger.info(f"🔄 Invalidated {count} retrieval cache entries "
                           f"referencing {len(doc_ids)} documents")
                self._stats.invalidations += count

            return count

        except Exception as e:
            logger.warning(f"⚠️ RetrievalCache.invalidate_by_documents error: {e}")
            return 0

    async def get_stats(self) -> RetrievalCacheStats:
        """Get cache statistics"""
        return self._stats


# Global instance
retrieval_cache = RetrievalCache(
    ttl_seconds=int(settings.rag_cache_ttl_seconds / 12),  # ~5 min (semantic is 1 hour)
    max_entries_per_user=500,
)
