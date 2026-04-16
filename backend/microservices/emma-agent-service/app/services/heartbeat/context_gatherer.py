"""Context Gatherer — Collects tenant data for Heartbeat evaluation.

Gathers data from:
- PostgreSQL (indexed_documents, document_analyses, signature_requests)
- Weaviate Service (collections, recent indexing)
- Redis (session activity, query patterns)

The resulting TenantContext is passed to the InsightEvaluator for
LLM-based insight generation.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.heartbeat import (
    AnomalyInfo,
    ContractInfo,
    DocumentSummary,
    TenantContext,
    UserActivityStats,
)

logger = logging.getLogger(__name__)


class ContextGatherer:
    """Gathers tenant context from PostgreSQL, Weaviate, and Redis."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
        return self._redis

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def gather(self) -> TenantContext:
        """Gather all context for the deployment.

        Returns:
            TenantContext with all available data
        """
        now = datetime.now(timezone.utc)

        # Gather data in parallel where possible
        context = TenantContext(
            gathered_at=now,
        )

        # Gather from different sources (best effort)
        try:
            docs_24h, docs_7d, by_collection, total = await self._gather_document_stats()
            context.documents_indexed_24h = docs_24h
            context.documents_indexed_7d = docs_7d
            context.documents_by_collection = by_collection
            context.total_documents = total
        except Exception as e:
            logger.warning(f"Failed to gather document stats: {e}")

        try:
            exp_7d, exp_30d = await self._gather_expiring_contracts()
            context.contracts_expiring_7d = exp_7d
            context.contracts_expiring_30d = exp_30d
        except Exception as e:
            logger.warning(f"Failed to gather contract expirations: {e}")

        try:
            context.user_activity = await self._gather_user_activity()
        except Exception as e:
            logger.warning(f"Failed to gather user activity: {e}")

        try:
            pending, stale = await self._gather_pending_items()
            context.pending_analyses = pending
            context.stale_analyses_7d = stale
        except Exception as e:
            logger.warning(f"Failed to gather pending items: {e}")

        try:
            context.anomalies = await self._gather_anomalies()
            context.duplicate_documents = sum(
                1 for a in context.anomalies if a.anomaly_type == "duplicate"
            )
            context.indexing_failures_24h = sum(
                1 for a in context.anomalies if a.anomaly_type == "indexing_failure"
            )
        except Exception as e:
            logger.warning(f"Failed to gather anomalies: {e}")

        try:
            last_insight, today_count, hour_count = await self._gather_delivery_stats()
            context.last_insight_delivered_at = last_insight
            context.insights_delivered_today = today_count
            context.insights_delivered_this_hour = hour_count
        except Exception as e:
            logger.warning(f"Failed to gather delivery stats: {e}")

        return context

    async def _gather_document_stats(
        self,
    ) -> tuple[List[DocumentSummary], int, Dict[str, int], int]:
        """Gather document statistics from main API."""
        docs_24h: List[DocumentSummary] = []
        docs_7d = 0
        by_collection: Dict[str, int] = {}
        total = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get recent documents via main API stats endpoint
                response = await client.get(
                    f"{settings.api_url}/api/v1/stats/deployment",
                    headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                )

                if response.status_code == 200:
                    data = response.json()
                    total = data.get("total_documents", 0)
                    by_collection = data.get("by_collection", {})
                    docs_7d = data.get("indexed_7d", 0)

                    # Get recent documents for 24h summary
                    for doc in data.get("recent_documents", [])[:20]:
                        indexed_at_str = doc.get("indexed_at")
                        indexed_at = None
                        if indexed_at_str:
                            try:
                                indexed_at = datetime.fromisoformat(indexed_at_str.replace("Z", "+00:00"))
                            except Exception:
                                pass

                        docs_24h.append(DocumentSummary(
                            id=doc.get("id", ""),
                            title=doc.get("title", doc.get("filename", "Unknown")),
                            collection=doc.get("collection"),
                            indexed_at=indexed_at,
                            metadata=doc.get("metadata", {}),
                        ))

        except httpx.HTTPError as e:
            logger.warning(f"HTTP error gathering document stats: {e}")
        except Exception as e:
            logger.warning(f"Error gathering document stats: {e}")

        return docs_24h, docs_7d, by_collection, total

    async def _gather_expiring_contracts(
        self,
    ) -> tuple[List[ContractInfo], List[ContractInfo]]:
        """Gather expiring contracts from document metadata."""
        exp_7d: List[ContractInfo] = []
        exp_30d: List[ContractInfo] = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{settings.api_url}/api/v1/stats/contracts/expiring",
                    params={"days": 30},
                    headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                )

                if response.status_code == 200:
                    data = response.json()
                    now = datetime.now(timezone.utc)

                    for contract in data.get("contracts", []):
                        expiry_str = contract.get("expiry_date")
                        if not expiry_str:
                            continue

                        try:
                            expiry_date = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                            days_until = (expiry_date - now).days

                            info = ContractInfo(
                                document_id=contract.get("document_id", ""),
                                title=contract.get("title", ""),
                                counterparty=contract.get("counterparty"),
                                expiry_date=expiry_date,
                                days_until_expiry=days_until,
                                contract_type=contract.get("contract_type"),
                            )

                            if days_until <= 7:
                                exp_7d.append(info)
                            elif days_until <= 30:
                                exp_30d.append(info)
                        except Exception:
                            continue

        except httpx.HTTPError as e:
            logger.debug(f"Contracts endpoint not available: {e}")
        except Exception as e:
            logger.warning(f"Error gathering contract expirations: {e}")

        return exp_7d, exp_30d

    async def _gather_user_activity(self) -> UserActivityStats:
        """Gather user activity from Redis session data."""
        stats = UserActivityStats()

        try:
            r = await self._get_redis()

            # Get session activity (queries in last 24h)
            session_key = "emma:activity:*"
            now = datetime.now(timezone.utc)
            cutoff_24h = (now - timedelta(hours=24)).timestamp()

            # Scan for activity keys
            active_users = set()
            total_queries = 0
            topics: Dict[str, int] = {}

            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match=session_key, count=100)
                for key in keys:
                    try:
                        data = await r.hgetall(key)
                        if data:
                            last_active = float(data.get("last_active", 0))
                            if last_active >= cutoff_24h:
                                user_id = data.get("user_id")
                                if user_id:
                                    active_users.add(user_id)
                                total_queries += int(data.get("query_count", 0))

                                # Track topics
                                for topic in data.get("topics", "").split(","):
                                    if topic:
                                        topics[topic] = topics.get(topic, 0) + 1
                    except Exception:
                        continue

                if cursor == 0:
                    break

            stats.active_users_24h = len(active_users)
            stats.total_queries_24h = total_queries
            stats.top_queried_topics = sorted(topics.keys(), key=lambda t: topics[t], reverse=True)[:10]

        except Exception as e:
            logger.warning(f"Error gathering user activity: {e}")

        return stats

    async def _gather_pending_items(self) -> tuple[int, int]:
        """Gather pending analyses and signatures."""
        pending = 0
        stale = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Check main API for pending analyses
                response = await client.get(
                    f"{settings.api_url}/api/v1/stats/analyses/pending",
                    headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                )

                if response.status_code == 200:
                    data = response.json()
                    pending = data.get("pending_count", 0)
                    stale = data.get("stale_count", 0)  # Pending for >7 days

        except httpx.HTTPError:
            pass  # Endpoint may not exist
        except Exception as e:
            logger.warning(f"Error gathering pending items: {e}")

        return pending, stale

    async def _gather_anomalies(self) -> List[AnomalyInfo]:
        """Gather anomalies (duplicates, failures) from main API."""
        anomalies: List[AnomalyInfo] = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{settings.api_url}/api/v1/stats/anomalies/recent",
                    params={"hours": 24},
                    headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                )

                if response.status_code == 200:
                    data = response.json()
                    for anomaly in data.get("anomalies", []):
                        anomalies.append(AnomalyInfo(
                            anomaly_type=anomaly.get("type", "unknown"),
                            description=anomaly.get("description", ""),
                            document_ids=anomaly.get("document_ids", []),
                        ))

        except httpx.HTTPError:
            pass  # Endpoint may not exist
        except Exception as e:
            logger.warning(f"Error gathering anomalies: {e}")

        return anomalies

    async def _gather_delivery_stats(
        self,
    ) -> tuple[Optional[datetime], int, int]:
        """Get insight delivery stats for rate limiting."""
        last_insight: Optional[datetime] = None
        today_count = 0
        hour_count = 0

        try:
            r = await self._get_redis()
            stats_key = "emma:heartbeat:delivery"

            data = await r.hgetall(stats_key)
            if data:
                if data.get("last_insight_at"):
                    try:
                        last_insight = datetime.fromisoformat(data["last_insight_at"])
                    except Exception:
                        pass
                today_count = int(data.get("today_count", 0))
                hour_count = int(data.get("hour_count", 0))

        except Exception as e:
            logger.warning(f"Error gathering delivery stats: {e}")

        return last_insight, today_count, hour_count


# Global singleton
context_gatherer = ContextGatherer()
