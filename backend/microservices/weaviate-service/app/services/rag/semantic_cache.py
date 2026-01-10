"""
Semantic Cache for RAG Pipeline

Caches RAG responses based on semantic similarity of queries, not exact match.
Uses Redis for storage and embedding cosine similarity for matching.

Key benefits:
- ~47% cache hit rate for similar queries
- Reduces latency from ~4.7s to ~80ms for cached responses
- Reduces LLM API costs by ~50%

Reference: "I Rebuilt My RAG Pipeline 11 Times" - Semantic Caching section
"""

import os
import json
import logging
import hashlib
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import redis.asyncio as redis
import httpx

from ...core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """Cached RAG response"""
    answer: str
    sources: List[Dict[str, Any]]
    confidence_score: float
    query_analysis: Dict[str, Any]
    context_info: Dict[str, Any]
    cached_at: float
    original_query: str
    cache_hit: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CacheStats:
    """Cache performance statistics"""
    hits: int = 0
    misses: int = 0
    total_queries: int = 0
    avg_similarity_on_hit: float = 0.0
    cache_size: int = 0

    @property
    def hit_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.hits / self.total_queries


class SemanticCache:
    """
    Redis-based semantic cache for RAG responses.

    Uses embedding similarity to find cached responses for semantically
    similar queries, not just exact matches.

    Configuration:
        RAG_CACHE_ENABLED: Enable/disable caching (default: true)
        RAG_CACHE_SIMILARITY_THRESHOLD: Cosine similarity threshold (default: 0.92)
        RAG_CACHE_TTL_SECONDS: Cache TTL in seconds (default: 3600)
        RAG_CACHE_MAX_ENTRIES: Maximum cache entries per tenant (default: 1000)
    """

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        ttl_seconds: int = 3600,
        max_entries_per_tenant: int = 1000,
    ):
        self._redis: Optional[redis.Redis] = None
        self._initialized = False
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.max_entries_per_tenant = max_entries_per_tenant
        self._stats = CacheStats()
        self._tei_url = settings.tei_url

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
            # Test connection
            await self._redis.ping()
            self._initialized = True
            logger.info(f"SemanticCache initialized (threshold={self.similarity_threshold}, ttl={self.ttl_seconds}s)")
        except Exception as e:
            logger.warning(f"Failed to initialize SemanticCache: {e}. Caching disabled.")
            self._initialized = False

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._initialized = False

    def _cache_key(self, tenant_id: str, user_id: str, scope: str, query_hash: str) -> str:
        """
        Generate cache key for a query with user isolation.

        SECURITY: user_id is included to prevent cross-user cache pollution.
        Each user has their own cache namespace to ensure ACL-filtered
        results are not shared between users with different permissions.
        """
        return f"rag:cache:{tenant_id}:{user_id}:{scope}:{query_hash}"

    def _index_key(self, tenant_id: str, user_id: str, scope: str) -> str:
        """
        Key for user's cache index (list of all cached query hashes).

        SECURITY: Isolated per user to prevent enumeration of other users' queries.
        """
        return f"rag:cache:index:{tenant_id}:{user_id}:{scope}"

    def _query_hash(self, query: str) -> str:
        """Generate deterministic hash for a query"""
        return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]

    async def get(
        self,
        query: str,
        query_embedding: List[float],
        tenant_id: str,
        user_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> Optional[CachedResponse]:
        """
        Check cache for semantically similar queries.

        Args:
            query: The user's query
            query_embedding: Pre-computed embedding for the query
            tenant_id: Tenant identifier for isolation
            user_id: User identifier for ACL-aware caching (REQUIRED for security)

        Returns:
            CachedResponse if a similar query is found, None otherwise

        SECURITY: Cache is isolated per user to prevent cross-user data exposure.
        If user_id is None, caching is disabled to prevent security issues.
        """
        if not self._initialized or not self._redis:
            return None

        # SECURITY: Require user_id for cache isolation
        if not user_id:
            logger.warning("⚠️ Cache lookup skipped: user_id not provided (security requirement)")
            return None

        self._stats.total_queries += 1

        try:
            scope_value = scope or "default"
            # Get all cached entries for this user within tenant
            index_key = self._index_key(tenant_id, user_id, scope_value)
            cached_hashes = await self._redis.lrange(index_key, 0, -1)

            best_match: Optional[CachedResponse] = None
            best_similarity = 0.0

            for query_hash in cached_hashes:
                cache_key = self._cache_key(tenant_id, user_id, scope_value, query_hash)
                cached_data = await self._redis.hgetall(cache_key)

                if not cached_data:
                    # Expired or removed entry, clean up index
                    await self._redis.lrem(index_key, 1, query_hash)
                    continue

                # Compare embeddings
                try:
                    cached_embedding = json.loads(cached_data.get("embedding", "[]"))
                    if not cached_embedding:
                        continue

                    similarity = self._cosine_similarity(query_embedding, cached_embedding)

                    if similarity > self.similarity_threshold and similarity > best_similarity:
                        best_similarity = similarity
                        best_match = CachedResponse(
                            answer=cached_data["answer"],
                            sources=json.loads(cached_data.get("sources", "[]")),
                            confidence_score=float(cached_data.get("confidence_score", 0.5)),
                            query_analysis=json.loads(cached_data.get("query_analysis", "{}")),
                            context_info=json.loads(cached_data.get("context_info", "{}")),
                            cached_at=float(cached_data.get("cached_at", 0)),
                            original_query=cached_data.get("original_query", ""),
                            cache_hit=True,
                        )
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Error parsing cached entry {query_hash}: {e}")
                    continue

            if best_match:
                self._stats.hits += 1
                # Update running average of similarity on hits
                n = self._stats.hits
                self._stats.avg_similarity_on_hit = (
                    (self._stats.avg_similarity_on_hit * (n - 1) + best_similarity) / n
                )
                logger.info(
                    f"Cache HIT: similarity={best_similarity:.3f}, "
                    f"original='{best_match.original_query[:50]}...'"
                )
                return best_match

            self._stats.misses += 1
            return None

        except Exception as e:
            logger.warning(f"Cache lookup error: {e}")
            self._stats.misses += 1
            return None

    async def set(
        self,
        query: str,
        query_embedding: List[float],
        tenant_id: str,
        user_id: Optional[str],
        answer: str,
        sources: List[Dict[str, Any]],
        confidence_score: float,
        query_analysis: Dict[str, Any],
        context_info: Dict[str, Any],
        scope: Optional[str] = None,
    ) -> bool:
        """
        Store a RAG response in the cache.

        Args:
            query: The original query
            query_embedding: Embedding for the query
            tenant_id: Tenant identifier
            user_id: User identifier for ACL-aware caching (REQUIRED for security)
            answer: Generated answer
            sources: Source documents used
            confidence_score: Answer confidence
            query_analysis: Query analysis metadata
            context_info: Context assembly metadata

        Returns:
            True if cached successfully, False otherwise

        SECURITY: Cache is isolated per user. Cached responses from one user
        are never returned to another user, even if queries are identical.
        """
        if not self._initialized or not self._redis:
            return False

        # SECURITY: Require user_id for cache isolation
        if not user_id:
            logger.warning("⚠️ Cache set skipped: user_id not provided (security requirement)")
            return False

        try:
            scope_value = scope or "default"
            query_hash = self._query_hash(query)
            cache_key = self._cache_key(tenant_id, user_id, scope_value, query_hash)
            index_key = self._index_key(tenant_id, user_id, scope_value)

            # Prepare cache entry
            cache_data = {
                "query": query,
                "embedding": json.dumps(query_embedding),
                "answer": answer,
                "sources": json.dumps(sources),
                "confidence_score": str(confidence_score),
                "query_analysis": json.dumps(query_analysis),
                "context_info": json.dumps(context_info),
                "cached_at": str(time.time()),
                "original_query": query,
            }

            # Store entry
            await self._redis.hset(cache_key, mapping=cache_data)
            await self._redis.expire(cache_key, self.ttl_seconds)

            # Add to index (if not already present)
            await self._redis.lrem(index_key, 0, query_hash)  # Remove duplicates
            await self._redis.lpush(index_key, query_hash)

            # Enforce max entries limit per user (FIFO eviction)
            index_len = await self._redis.llen(index_key)
            if index_len > self.max_entries_per_tenant:
                # Remove oldest entries
                to_remove = await self._redis.lrange(
                    index_key,
                    self.max_entries_per_tenant,
                    -1
                )
                for old_hash in to_remove:
                    old_key = self._cache_key(tenant_id, user_id, scope_value, old_hash)
                    await self._redis.delete(old_key)
                await self._redis.ltrim(index_key, 0, self.max_entries_per_tenant - 1)

            logger.debug(f"Cached response for query: '{query[:50]}...'")
            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def invalidate(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        query: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> int:
        """
        Invalidate cache entries.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier (required for user-specific invalidation)
            query: Optional specific query to invalidate (None = all for user)
            scope: Optional scope filter

        Returns:
            Number of entries invalidated

        Note: If user_id is None, this is a no-op for security. To invalidate
        all users' cache (e.g., when a document is updated), you need to
        invalidate per-user or implement a document-based invalidation strategy.
        """
        if not self._initialized or not self._redis:
            return 0

        # SECURITY: Require user_id for invalidation
        if not user_id:
            logger.warning("⚠️ Cache invalidation skipped: user_id not provided")
            return 0

        scope_value = scope or "default"

        try:
            if query:
                # Invalidate specific query for user
                query_hash = self._query_hash(query)
                cache_key = self._cache_key(tenant_id, user_id, scope_value, query_hash)
                index_key = self._index_key(tenant_id, user_id, scope_value)

                deleted = await self._redis.delete(cache_key)
                await self._redis.lrem(index_key, 0, query_hash)
                return deleted

            # Invalidate all entries for user within tenant
            index_key = self._index_key(tenant_id, user_id, scope_value)
            cached_hashes = await self._redis.lrange(index_key, 0, -1)

            count = 0
            for query_hash in cached_hashes:
                cache_key = self._cache_key(tenant_id, user_id, scope_value, query_hash)
                count += await self._redis.delete(cache_key)

            await self._redis.delete(index_key)
            logger.info(f"Invalidated {count} cache entries for user {user_id} in tenant {tenant_id}")
            return count

        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
            return 0

    async def invalidate_by_document(
        self,
        tenant_id: str,
        document_id: str,
    ) -> int:
        """
        Invalidate all cache entries that reference a specific document.

        SECURITY: When a document's ACL changes, we must invalidate any cached
        response that used that document as a source. This prevents stale
        cached responses from being returned to users who no longer have access.

        This method scans all cache entries for the tenant and removes those
        whose sources contain the specified document_id.

        Args:
            tenant_id: Tenant identifier
            document_id: Document ID whose ACL changed

        Returns:
            Number of cache entries invalidated

        Note: This is an expensive operation (O(n) where n = total cached entries)
        but is necessary for security. It's called infrequently (only when ACL changes).
        """
        if not self._initialized or not self._redis:
            return 0

        try:
            # Find all cache keys for this tenant (across all users and scopes)
            # Pattern: rag:cache:{tenant_id}:*
            pattern = f"rag:cache:{tenant_id}:*"
            cursor = 0
            invalidated = 0

            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)

                for key in keys:
                    # Skip index keys
                    if ":index:" in key:
                        continue

                    try:
                        # Get the sources from this cache entry
                        sources_json = await self._redis.hget(key, "sources")
                        if sources_json:
                            sources = json.loads(sources_json)
                            # Check if any source has this document_id
                            for source in sources:
                                if source.get("id") == document_id:
                                    await self._redis.delete(key)
                                    invalidated += 1
                                    logger.debug(f"Invalidated cache entry referencing document {document_id}")
                                    break
                    except (json.JSONDecodeError, TypeError):
                        continue

                if cursor == 0:
                    break

            if invalidated > 0:
                logger.info(
                    f"🔄 Invalidated {invalidated} cache entries referencing document {document_id} "
                    f"in tenant {tenant_id}"
                )

            return invalidated

        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
            return 0

    async def get_stats(self, tenant_id: Optional[str] = None) -> CacheStats:
        """Get cache statistics"""
        stats = CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            total_queries=self._stats.total_queries,
            avg_similarity_on_hit=self._stats.avg_similarity_on_hit,
        )

        if self._initialized and self._redis and tenant_id:
            try:
                index_key = self._index_key(tenant_id)
                stats.cache_size = await self._redis.llen(index_key)
            except Exception:
                pass

        return stats

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors"""
        if not a or not b or len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from TEI (Text Embeddings Inference)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._tei_url}/embed",
                    json={
                        "inputs": text,
                        "truncate": True
                    }
                )
                if response.status_code == 200:
                    embeddings = response.json()
                    # TEI returns a list of embeddings, we want the first one
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]
        except Exception as e:
            logger.warning(f"Failed to get embedding: {e}")
        return None


# Global instance
semantic_cache = SemanticCache(
    similarity_threshold=float(os.environ.get("RAG_CACHE_SIMILARITY_THRESHOLD", "0.92")),
    ttl_seconds=int(os.environ.get("RAG_CACHE_TTL_SECONDS", "3600")),
    max_entries_per_tenant=int(os.environ.get("RAG_CACHE_MAX_ENTRIES", "1000")),
)
