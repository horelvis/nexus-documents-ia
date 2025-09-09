"""
Optimized document service with caching, async operations, and performance monitoring
"""
import logging
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.cache import (
    cache, cached_query, async_cached_query,
    invalidate_document_related_cache, document_cache_key
)
from app.core.metrics import performance_monitor, async_time_function
from app.core.async_optimizer import AsyncOptimizer
from app.services.query_optimizer import QueryOptimizer
from app.db.models import Document, DocumentView, Tag
from app.core.config import settings

logger = logging.getLogger(__name__)


class OptimizedDocumentService:
    """Optimized document service with performance enhancements"""

    def __init__(self, db: Session, tenant_id: str, user_id: Optional[str] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.query_optimizer = QueryOptimizer(db)
        self.async_optimizer = AsyncOptimizer()

    @async_time_function("document_list", {"service": "optimized_document"})
    @async_cached_query(ttl=300)  # Cache for 5 minutes
    async def get_documents_list(self, limit: int = 50, offset: int = 0,
                                include_views: bool = False) -> List[Document]:
        """
        Get paginated list of documents with optimized queries.
        Uses caching and eager loading to prevent N+1 queries.
        """
        start_time = time.time()

        try:
            documents = self.query_optimizer.get_documents_with_relations(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                limit=limit,
                offset=offset,
                include_views=include_views,
                include_tags=True
            )

            # Monitor performance
            performance_monitor.monitor_database_query(
                "get_documents_list",
                time.time() - start_time
            )

            return documents

        except Exception as e:
            logger.error(f"Error getting documents list: {str(e)}")
            raise

    @async_time_function("document_search", {"service": "optimized_document"})
    async def search_documents(self, query: str, limit: int = 50) -> List[Document]:
        """
        Search documents with optimized queries and caching.
        """
        # Create cache key for search results
        cache_key = document_cache_key(
            f"search_{hash(query)}",
            f"limit_{limit}"
        )

        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug("Search cache hit")
            return cached_result

        start_time = time.time()

        try:
            documents = self.query_optimizer.search_documents_optimized(
                tenant_id=self.tenant_id,
                search_term=query,
                limit=limit
            )

            # Cache the results
            cache.set(cache_key, documents, ttl=600)  # 10 minutes

            # Monitor performance
            performance_monitor.monitor_database_query(
                "search_documents",
                time.time() - start_time
            )

            return documents

        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            raise

    @async_time_function("document_stats", {"service": "optimized_document"})
    @async_cached_query(ttl=300)  # Cache for 5 minutes
    async def get_document_stats(self) -> Dict[str, Any]:
        """
        Get document statistics with optimized queries.
        """
        start_time = time.time()

        try:
            stats = self.query_optimizer.get_tenant_stats_optimized(self.tenant_id)

            # Add additional computed stats
            stats['avg_views_per_document'] = (
                stats['total_views_30d'] / stats['document_count']
                if stats['document_count'] > 0 else 0
            )

            # Monitor performance
            performance_monitor.monitor_database_query(
                "get_document_stats",
                time.time() - start_time
            )

            return stats

        except Exception as e:
            logger.error(f"Error getting document stats: {str(e)}")
            raise

    @async_time_function("recent_activity", {"service": "optimized_document"})
    async def get_recent_activity(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent document activity with optimized queries.
        """
        cache_key = document_cache_key("recent_activity", f"days_{days}")

        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        start_time = time.time()

        try:
            activity = self.query_optimizer.get_recent_activity_optimized(
                tenant_id=self.tenant_id,
                days=days,
                limit=100
            )

            # Cache the results
            cache.set(cache_key, activity, ttl=600)  # 10 minutes

            # Monitor performance
            performance_monitor.monitor_database_query(
                "get_recent_activity",
                time.time() - start_time
            )

            return activity

        except Exception as e:
            logger.error(f"Error getting recent activity: {str(e)}")
            raise

    @async_time_function("document_by_tag", {"service": "optimized_document"})
    async def get_documents_by_tag(self, tag_name: str, limit: int = 20) -> List[Document]:
        """
        Get documents by tag with optimized queries.
        """
        cache_key = document_cache_key(f"tag_{tag_name}", f"limit_{limit}")

        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        start_time = time.time()

        try:
            documents = self.query_optimizer.get_documents_by_tag_optimized(
                tenant_id=self.tenant_id,
                tag_name=tag_name,
                limit=limit
            )

            # Cache the results
            cache.set(cache_key, documents, ttl=600)  # 10 minutes

            # Monitor performance
            performance_monitor.monitor_database_query(
                "get_documents_by_tag",
                time.time() - start_time
            )

            return documents

        except Exception as e:
            logger.error(f"Error getting documents by tag: {str(e)}")
            raise

    async def invalidate_document_cache(self, document_id: str) -> None:
        """
        Invalidate all cache entries related to a document.
        Should be called when document is updated or deleted.
        """
        invalidate_document_related_cache(document_id)

        # Also invalidate related caches
        await self._invalidate_related_caches()

    async def _invalidate_related_caches(self) -> None:
        """
        Invalidate caches that might be affected by document changes.
        """
        # Invalidate tenant stats cache
        cache.delete(f"tenant:{self.tenant_id}:stats")

        # Invalidate user document lists if applicable
        if self.user_id:
            cache.delete(f"user:{self.user_id}:recent_docs")

    async def batch_update_metrics(self, document_ids: List[str]) -> None:
        """
        Batch update document metrics efficiently.
        """
        if not document_ids:
            return

        start_time = time.time()

        try:
            self.query_optimizer.batch_update_document_metrics(document_ids)

            # Invalidate affected caches
            for doc_id in document_ids:
                await self.invalidate_document_cache(doc_id)

            # Monitor performance
            performance_monitor.monitor_database_query(
                "batch_update_metrics",
                time.time() - start_time
            )

            logger.info(f"Batch updated metrics for {len(document_ids)} documents")

        except Exception as e:
            logger.error(f"Error in batch metrics update: {str(e)}")
            raise

    async def get_popular_documents(self, limit: int = 10) -> List[Document]:
        """
        Get most popular documents based on view count and recency.
        """
        cache_key = document_cache_key("popular", f"limit_{limit}")

        # Try cache first
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        start_time = time.time()

        try:
            # Get documents with metrics, ordered by relevance score
            documents = self.query_optimizer.get_documents_with_relations(
                tenant_id=self.tenant_id,
                limit=limit,
                offset=0,
                include_views=False,
                include_tags=False,
                include_metrics=True
            )

            # Sort by relevance score (computed in the model)
            documents.sort(key=lambda d: d.metrics.relevance_score if d.metrics else 0, reverse=True)

            # Cache the results
            cache.set(cache_key, documents, ttl=1800)  # 30 minutes

            # Monitor performance
            performance_monitor.monitor_database_query(
                "get_popular_documents",
                time.time() - start_time
            )

            return documents

        except Exception as e:
            logger.error(f"Error getting popular documents: {str(e)}")
            raise

    async def parallel_process_documents(self, document_ids: List[str],
                                       processor_func) -> List[Any]:
        """
        Process multiple documents in parallel using async optimization.
        """
        async with self.async_optimizer as optimizer:
            results = await optimizer.batch_process(
                items=document_ids,
                processor=processor_func,
                batch_size=5  # Process 5 documents at a time
            )

        return results

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for this service instance.
        """
        return {
            'cache_stats': cache.get_stats(),
            'query_optimizer_stats': {
                'tenant_id': self.tenant_id,
                'user_id': self.user_id
            }
        }