"""
Context Assembly Cache - Caches assembled context ready for LLM

This layer caches the ASSEMBLED CONTEXT (the string that gets sent to the LLM),
not the final response. By caching at this layer, we avoid:
- Document content fetching
- Chunk assembly and ordering
- Token counting and truncation
- Contextual prefix injection

Key insight: The same set of documents, when assembled into context,
produces the same string regardless of the original query. Multiple
different queries might retrieve the same documents.

Example:
- Query A: "What are the payment terms?" → docs [1,2,3] → context_hash_abc
- Query B: "When do I need to pay?" → docs [1,2,3] → context_hash_abc (SAME!)
- Query C: "What are the delivery terms?" → docs [1,4,5] → context_hash_xyz

Performance impact:
- Cache hit: ~5ms (Redis lookup)
- Cache miss: ~50-200ms (fetch docs, assemble, count tokens)
- Expected hit rate: 30-50% for overlapping document sets
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
class CachedContext:
    """Cached assembled context ready for LLM injection"""
    context_string: str  # The actual context text
    total_tokens: int
    doc_count: int
    doc_ids: List[str]  # For cache invalidation tracking
    metadata: Dict[str, Any]  # Assembly metadata (weights, truncation info)
    cached_at: float
    context_hash: str
    chunk_version: str
    index_version: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedContext":
        return cls(**data)


@dataclass
class ContextCacheStats:
    """Statistics for context cache performance"""
    hits: int = 0
    misses: int = 0
    total_queries: int = 0
    avg_hit_latency_ms: float = 0.0
    avg_cached_tokens: float = 0.0
    invalidations: int = 0

    @property
    def hit_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.hits / self.total_queries


class ContextAssemblyCache:
    """
    Redis-based cache for assembled context strings.

    Caches the formatted context that gets injected into LLM prompts.
    Key is based on document IDs + versions (not query), so different
    queries that retrieve the same documents share cached context.

    Configuration (env vars):
        CONTEXT_CACHE_ENABLED: Enable/disable (default: true)
        CONTEXT_CACHE_TTL_SECONDS: TTL in seconds (default: 1800 = 30 min)
        CONTEXT_CACHE_MAX_SIZE_MB: Max cached context size (default: 100MB)
    """

    KEY_PREFIX = "context:"
    DOC_INDEX_PREFIX = "context:docindex:"  # Maps doc_id -> context keys

    def __init__(
        self,
        ttl_seconds: int = 1800,  # 30 minutes default
        max_context_size_mb: int = 100,
    ):
        self._redis: Optional[redis.Redis] = None
        self._initialized = False
        self.ttl_seconds = ttl_seconds
        self.max_context_size_mb = max_context_size_mb
        self._stats = ContextCacheStats()

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
            logger.info(f"🗄️ ContextAssemblyCache initialized (ttl={self.ttl_seconds}s)")
        except Exception as e:
            logger.warning(f"⚠️ ContextAssemblyCache initialization failed: {e}")
            self._initialized = False

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._initialized = False

    def _build_cache_key(
        self,
        doc_ids: List[str],
        tenant_id: str,
        chunk_version: str,
        index_version: str,
        model_type: str = "sglang",
    ) -> str:
        """
        Build deterministic cache key from document set + versions.

        Key insight: The context only depends on WHICH documents and
        HOW they're chunked/indexed, not on the original query.
        """
        # Sort doc_ids for consistent key regardless of retrieval order
        sorted_ids = sorted(doc_ids)

        key_components = {
            "docs": sorted_ids,
            "tenant": tenant_id,
            "chunk_v": chunk_version,
            "index_v": index_version,
            "model": model_type,
        }

        key_json = json.dumps(key_components, sort_keys=True)
        key_hash = hashlib.sha256(key_json.encode()).hexdigest()[:24]

        return f"{self.KEY_PREFIX}{tenant_id}:{key_hash}"

    def _doc_index_key(self, tenant_id: str, doc_id: str) -> str:
        """Key for tracking which context caches include a document"""
        return f"{self.DOC_INDEX_PREFIX}{tenant_id}:{doc_id}"

    async def get(
        self,
        doc_ids: List[str],
        tenant_id: str,
        chunk_version: str,
        index_version: str,
        model_type: str = "sglang",
    ) -> Optional[CachedContext]:
        """
        Get cached context if available.

        Args:
            doc_ids: List of document IDs in the context
            tenant_id: Tenant identifier
            chunk_version: Version of chunking strategy
            index_version: Version of Weaviate index
            model_type: LLM model type (affects context format)

        Returns:
            CachedContext if cache hit, None otherwise
        """
        if not self._initialized or not self._redis:
            return None

        if not doc_ids:
            return None

        self._stats.total_queries += 1
        start_time = time.time()

        try:
            cache_key = self._build_cache_key(
                doc_ids, tenant_id, chunk_version, index_version, model_type
            )

            cached_json = await self._redis.get(cache_key)
            if not cached_json:
                self._stats.misses += 1
                return None

            cached_data = json.loads(cached_json)
            result = CachedContext.from_dict(cached_data)

            # Version check
            if result.chunk_version != chunk_version or result.index_version != index_version:
                logger.info(f"🔄 Context cache invalidated: version mismatch")
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
            self._stats.avg_cached_tokens = (
                (self._stats.avg_cached_tokens * (n - 1) + result.total_tokens) / n
            )

            logger.debug(f"✅ Context cache HIT: {result.total_tokens} tokens, "
                        f"{result.doc_count} docs in {latency_ms:.1f}ms")
            return result

        except Exception as e:
            logger.warning(f"⚠️ ContextAssemblyCache.get error: {e}")
            self._stats.misses += 1
            return None

    async def set(
        self,
        doc_ids: List[str],
        tenant_id: str,
        context_string: str,
        total_tokens: int,
        metadata: Dict[str, Any],
        chunk_version: str,
        index_version: str,
        model_type: str = "sglang",
    ) -> bool:
        """
        Store assembled context in cache.

        Args:
            doc_ids: Document IDs included in context
            tenant_id: Tenant identifier
            context_string: The assembled context text
            total_tokens: Token count of context
            metadata: Assembly metadata
            chunk_version: Version of chunking strategy
            index_version: Version of Weaviate index
            model_type: LLM model type

        Returns:
            True if cached successfully
        """
        if not self._initialized or not self._redis:
            return False

        if not doc_ids or not context_string:
            return False

        # Check size limit (rough estimate: 4 bytes per char)
        context_size_mb = len(context_string) * 4 / (1024 * 1024)
        if context_size_mb > self.max_context_size_mb / 10:  # Don't cache huge contexts
            logger.debug(f"⚠️ Context too large to cache: {context_size_mb:.1f}MB")
            return False

        try:
            cache_key = self._build_cache_key(
                doc_ids, tenant_id, chunk_version, index_version, model_type
            )

            cached_context = CachedContext(
                context_string=context_string,
                total_tokens=total_tokens,
                doc_count=len(doc_ids),
                doc_ids=doc_ids,
                metadata=metadata,
                cached_at=time.time(),
                context_hash=cache_key.split(":")[-1],
                chunk_version=chunk_version,
                index_version=index_version,
            )

            # Store with TTL
            await self._redis.setex(
                cache_key,
                self.ttl_seconds,
                json.dumps(cached_context.to_dict())
            )

            # Build reverse index: doc_id -> cache_keys
            # This allows efficient invalidation when a document changes
            for doc_id in doc_ids:
                doc_index_key = self._doc_index_key(tenant_id, doc_id)
                await self._redis.sadd(doc_index_key, cache_key)
                await self._redis.expire(doc_index_key, self.ttl_seconds * 2)

            logger.debug(f"📝 Cached context: {total_tokens} tokens, {len(doc_ids)} docs")
            return True

        except Exception as e:
            logger.warning(f"⚠️ ContextAssemblyCache.set error: {e}")
            return False

    async def invalidate_by_documents(
        self,
        tenant_id: str,
        doc_ids: List[str],
    ) -> int:
        """
        Invalidate all context caches that include any of the specified documents.

        This uses the reverse index (doc_id -> cache_keys) for O(1) lookup
        instead of scanning all cache entries.

        Called when documents are updated or deleted.
        """
        if not self._initialized or not self._redis:
            return 0

        try:
            count = 0
            all_cache_keys = set()

            # Collect all cache keys referencing these documents
            for doc_id in doc_ids:
                doc_index_key = self._doc_index_key(tenant_id, doc_id)
                cache_keys = await self._redis.smembers(doc_index_key)
                all_cache_keys.update(cache_keys)
                # Clean up the doc index
                await self._redis.delete(doc_index_key)

            # Delete all affected cache entries
            if all_cache_keys:
                count = await self._redis.delete(*all_cache_keys)

            if count > 0:
                logger.info(f"🔄 Invalidated {count} context cache entries "
                           f"referencing {len(doc_ids)} documents")
                self._stats.invalidations += count

            return count

        except Exception as e:
            logger.warning(f"⚠️ ContextAssemblyCache.invalidate_by_documents error: {e}")
            return 0

    async def invalidate_tenant(self, tenant_id: str) -> int:
        """
        Invalidate all context caches for a tenant.

        Called when tenant's index is rebuilt or chunking strategy changes.
        """
        if not self._initialized or not self._redis:
            return 0

        try:
            # Delete all context cache keys for tenant
            pattern = f"{self.KEY_PREFIX}{tenant_id}:*"
            cursor = 0
            count = 0

            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    count += await self._redis.delete(*keys)
                if cursor == 0:
                    break

            # Delete all doc index keys for tenant
            doc_pattern = f"{self.DOC_INDEX_PREFIX}{tenant_id}:*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=doc_pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

            if count > 0:
                logger.info(f"🔄 Invalidated {count} context cache entries for tenant {tenant_id}")
                self._stats.invalidations += count

            return count

        except Exception as e:
            logger.warning(f"⚠️ ContextAssemblyCache.invalidate_tenant error: {e}")
            return 0

    async def get_stats(self) -> ContextCacheStats:
        """Get cache statistics"""
        return self._stats


# Global instance
context_cache = ContextAssemblyCache(
    ttl_seconds=int(settings.rag_cache_ttl_seconds / 2),  # ~30 min (semantic is 1 hour)
    max_context_size_mb=100,
)
