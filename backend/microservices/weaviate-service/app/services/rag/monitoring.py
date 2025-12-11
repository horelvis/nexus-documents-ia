"""
RAG Pipeline Monitoring

Production monitoring for RAG queries including:
- Query logging with retrieval scores
- Latency tracking per stage
- User feedback collection
- Retrieval quality metrics
- Cache performance metrics

Reference: "My production system crashed at 2 AM" - The Metrics That Matter section
"""

import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Metrics for a single RAG query"""
    query_id: str
    timestamp: float
    tenant_id: str
    user_id: Optional[str]

    # Query info
    query: str
    query_tokens: int = 0
    intent: str = ""

    # Retrieval metrics
    num_results: int = 0
    top_score: float = 0.0
    avg_score: float = 0.0
    dense_results: int = 0
    sparse_results: int = 0
    rrf_fused_results: int = 0

    # Latency breakdown (ms)
    total_latency_ms: float = 0.0
    cache_check_ms: float = 0.0
    query_analysis_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0
    context_assembly_ms: float = 0.0
    generation_ms: float = 0.0

    # Cache info
    cache_hit: bool = False
    cache_similarity: float = 0.0

    # Response quality
    confidence_score: float = 0.0
    num_citations: int = 0
    has_unsupported_claims: bool = False

    # User feedback (optional, collected later)
    user_feedback: Optional[int] = None  # 1-5 rating
    feedback_comment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AggregatedMetrics:
    """Aggregated metrics over a time period"""
    period_start: float
    period_end: float
    total_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    # Latency percentiles
    latency_p50_ms: float = 0.0
    latency_p90_ms: float = 0.0
    latency_p99_ms: float = 0.0

    # Retrieval quality
    avg_top_score: float = 0.0
    avg_num_results: float = 0.0
    zero_result_queries: int = 0

    # Response quality
    avg_confidence: float = 0.0
    avg_user_rating: float = 0.0
    rated_queries: int = 0

    @property
    def cache_hit_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.cache_hits / self.total_queries


class RAGMonitor:
    """
    Production monitoring for RAG pipeline.

    Tracks:
    - Query performance metrics
    - Retrieval quality
    - Cache effectiveness
    - User feedback

    Usage:
        monitor = RAGMonitor()
        metrics = monitor.start_query(tenant_id, user_id, query)
        # ... run pipeline stages ...
        metrics.retrieval_ms = retrieval_time
        monitor.end_query(metrics)
    """

    def __init__(self, max_history: int = 10000):
        self._queries: List[QueryMetrics] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

        # Real-time counters
        self._total_queries = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_latency = 0.0
        self._latencies: List[float] = []

        # Per-tenant metrics
        self._tenant_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"queries": 0, "cache_hits": 0, "avg_latency": 0.0}
        )

    def start_query(
        self,
        tenant_id: str,
        user_id: Optional[str],
        query: str,
    ) -> QueryMetrics:
        """Start tracking a new query"""
        import uuid

        metrics = QueryMetrics(
            query_id=str(uuid.uuid4()),
            timestamp=time.time(),
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            query_tokens=len(query.split()),  # Rough estimate
        )

        return metrics

    async def end_query(self, metrics: QueryMetrics):
        """Finalize and log query metrics"""
        async with self._lock:
            # Update counters
            self._total_queries += 1
            self._total_latency += metrics.total_latency_ms

            if metrics.cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

            # Track latencies for percentiles
            self._latencies.append(metrics.total_latency_ms)
            if len(self._latencies) > self._max_history:
                self._latencies = self._latencies[-self._max_history:]

            # Update tenant metrics
            tenant = self._tenant_metrics[metrics.tenant_id]
            tenant["queries"] += 1
            if metrics.cache_hit:
                tenant["cache_hits"] += 1
            # Running average
            n = tenant["queries"]
            tenant["avg_latency"] = (
                (tenant["avg_latency"] * (n - 1) + metrics.total_latency_ms) / n
            )

            # Store query metrics
            self._queries.append(metrics)
            if len(self._queries) > self._max_history:
                self._queries = self._queries[-self._max_history:]

            # Log for monitoring systems
            self._log_query(metrics)

    def _log_query(self, metrics: QueryMetrics):
        """Log query for monitoring/alerting systems"""
        log_entry = {
            "event": "rag_query",
            "query_id": metrics.query_id,
            "tenant_id": metrics.tenant_id,
            "latency_ms": metrics.total_latency_ms,
            "cache_hit": metrics.cache_hit,
            "num_results": metrics.num_results,
            "top_score": metrics.top_score,
            "confidence": metrics.confidence_score,
            "intent": metrics.intent,
        }

        # Log at appropriate level based on performance
        if metrics.total_latency_ms > 5000:
            logger.warning(f"Slow RAG query: {json.dumps(log_entry)}")
        elif metrics.num_results == 0:
            logger.warning(f"Zero results RAG query: {json.dumps(log_entry)}")
        else:
            logger.info(f"RAG query: {json.dumps(log_entry)}")

    async def record_feedback(
        self,
        query_id: str,
        rating: int,
        comment: Optional[str] = None,
    ):
        """Record user feedback for a query"""
        async with self._lock:
            for metrics in reversed(self._queries):
                if metrics.query_id == query_id:
                    metrics.user_feedback = rating
                    metrics.feedback_comment = comment
                    logger.info(
                        f"Feedback recorded: query_id={query_id}, rating={rating}"
                    )
                    return True
        return False

    def get_aggregated_metrics(
        self,
        tenant_id: Optional[str] = None,
        last_n_queries: int = 1000,
    ) -> AggregatedMetrics:
        """Get aggregated metrics for monitoring dashboards"""
        # Filter queries
        queries = self._queries[-last_n_queries:]
        if tenant_id:
            queries = [q for q in queries if q.tenant_id == tenant_id]

        if not queries:
            return AggregatedMetrics(
                period_start=time.time(),
                period_end=time.time(),
            )

        # Calculate metrics
        latencies = [q.total_latency_ms for q in queries]
        latencies.sort()

        cache_hits = sum(1 for q in queries if q.cache_hit)
        zero_results = sum(1 for q in queries if q.num_results == 0)

        rated = [q for q in queries if q.user_feedback is not None]

        return AggregatedMetrics(
            period_start=queries[0].timestamp,
            period_end=queries[-1].timestamp,
            total_queries=len(queries),
            cache_hits=cache_hits,
            cache_misses=len(queries) - cache_hits,
            latency_p50_ms=latencies[len(latencies) // 2] if latencies else 0.0,
            latency_p90_ms=latencies[int(len(latencies) * 0.9)] if latencies else 0.0,
            latency_p99_ms=latencies[int(len(latencies) * 0.99)] if latencies else 0.0,
            avg_top_score=sum(q.top_score for q in queries) / len(queries),
            avg_num_results=sum(q.num_results for q in queries) / len(queries),
            zero_result_queries=zero_results,
            avg_confidence=sum(q.confidence_score for q in queries) / len(queries),
            avg_user_rating=sum(q.user_feedback for q in rated) / len(rated) if rated else 0.0,
            rated_queries=len(rated),
        )

    def get_tenant_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get summary metrics for a specific tenant"""
        return dict(self._tenant_metrics.get(tenant_id, {}))

    def get_global_summary(self) -> Dict[str, Any]:
        """Get global summary metrics"""
        cache_hit_rate = (
            self._cache_hits / self._total_queries
            if self._total_queries > 0 else 0.0
        )
        avg_latency = (
            self._total_latency / self._total_queries
            if self._total_queries > 0 else 0.0
        )

        return {
            "total_queries": self._total_queries,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": f"{cache_hit_rate:.1%}",
            "avg_latency_ms": round(avg_latency, 1),
            "tenants_active": len(self._tenant_metrics),
        }

    def get_slow_queries(
        self,
        threshold_ms: float = 3000,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent slow queries for debugging"""
        slow = [
            q for q in self._queries
            if q.total_latency_ms > threshold_ms
        ]
        return [q.to_dict() for q in slow[-limit:]]

    def get_zero_result_queries(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent queries with zero results for analysis"""
        zero = [q for q in self._queries if q.num_results == 0]
        return [q.to_dict() for q in zero[-limit:]]


# Global instance
rag_monitor = RAGMonitor()
