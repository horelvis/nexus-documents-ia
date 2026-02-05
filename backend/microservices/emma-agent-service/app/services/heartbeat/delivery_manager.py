"""Delivery Manager — Rate limiting and notification dispatch for insights.

Handles:
- Quiet hours enforcement (no notifications during configured hours)
- Rate limiting (max per day, per hour, minimum interval)
- Channel selection based on priority and configuration
- Batching low-priority insights into daily digests
"""
import logging
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.heartbeat import (
    HeartbeatConfig,
    InsightStatus,
    InsightUrgency,
    ProactiveInsight,
    ProactiveInsightCreate,
)
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class DeliveryManager:
    """Manages insight delivery with rate limiting and quiet hours."""

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

    async def deliver_insights(
        self,
        insights: List[ProactiveInsightCreate],
        config: HeartbeatConfig,
        tenant_id: str,
    ) -> Tuple[List[ProactiveInsight], List[ProactiveInsightCreate]]:
        """Deliver insights respecting rate limits and quiet hours.

        Args:
            insights: Insights to deliver (already sorted by priority)
            config: Heartbeat configuration for the tenant
            tenant_id: Tenant ID

        Returns:
            Tuple of (delivered_insights, deferred_insights)
        """
        now = datetime.now(timezone.utc)
        delivered: List[ProactiveInsight] = []
        deferred: List[ProactiveInsightCreate] = []

        # Check quiet hours
        if self._is_quiet_hours(now, config):
            logger.info(f"Quiet hours active for tenant {tenant_id}, deferring all insights")
            return [], insights

        # Get current delivery stats
        stats = await self._get_delivery_stats(tenant_id)

        for insight in insights:
            # Check rate limits
            can_deliver, reason = self._check_rate_limits(stats, config, now)

            if not can_deliver:
                logger.debug(f"Rate limit hit: {reason}")
                # Batch low-priority for digest
                if config.batch_low_priority and insight.urgency == InsightUrgency.LOW:
                    deferred.append(insight)
                elif insight.urgency in (InsightUrgency.CRITICAL, InsightUrgency.HIGH):
                    # High priority bypasses some limits
                    if stats["today_count"] < config.max_insights_per_day * 1.5:
                        delivered_insight = await self._deliver_single(
                            insight, config, tenant_id
                        )
                        if delivered_insight:
                            delivered.append(delivered_insight)
                            await self._update_delivery_stats(tenant_id, now)
                            stats["today_count"] += 1
                            stats["hour_count"] += 1
                    else:
                        deferred.append(insight)
                else:
                    deferred.append(insight)
                continue

            # Deliver the insight
            delivered_insight = await self._deliver_single(insight, config, tenant_id)
            if delivered_insight:
                delivered.append(delivered_insight)
                await self._update_delivery_stats(tenant_id, now)
                stats["today_count"] += 1
                stats["hour_count"] += 1
                stats["last_insight_at"] = now

        return delivered, deferred

    def _is_quiet_hours(self, now: datetime, config: HeartbeatConfig) -> bool:
        """Check if current time is within quiet hours."""
        try:
            start_parts = config.quiet_hours_start.split(":")
            end_parts = config.quiet_hours_end.split(":")

            start_time = time(int(start_parts[0]), int(start_parts[1]))
            end_time = time(int(end_parts[0]), int(end_parts[1]))
            current_time = now.time()

            # Handle overnight quiet hours (e.g., 22:00 - 08:00)
            if start_time > end_time:
                return current_time >= start_time or current_time < end_time
            else:
                return start_time <= current_time < end_time

        except Exception as e:
            logger.warning(f"Error parsing quiet hours: {e}")
            return False

    def _check_rate_limits(
        self,
        stats: Dict[str, Any],
        config: HeartbeatConfig,
        now: datetime,
    ) -> Tuple[bool, str]:
        """Check if delivery is allowed based on rate limits.

        Returns:
            Tuple of (can_deliver, reason_if_not)
        """
        # Check daily limit
        if stats["today_count"] >= config.max_insights_per_day:
            return False, f"Daily limit reached ({config.max_insights_per_day})"

        # Check hourly limit
        if stats["hour_count"] >= config.max_insights_per_hour:
            return False, f"Hourly limit reached ({config.max_insights_per_hour})"

        # Check minimum interval
        last_at = stats.get("last_insight_at")
        if last_at:
            if isinstance(last_at, str):
                try:
                    last_at = datetime.fromisoformat(last_at)
                except Exception:
                    last_at = None

            if last_at:
                elapsed_minutes = (now - last_at).total_seconds() / 60
                if elapsed_minutes < config.min_interval_minutes:
                    return False, f"Minimum interval not met ({config.min_interval_minutes}m)"

        return True, ""

    async def _deliver_single(
        self,
        insight: ProactiveInsightCreate,
        config: HeartbeatConfig,
        tenant_id: str,
    ) -> Optional[ProactiveInsight]:
        """Deliver a single insight via configured channels."""
        now = datetime.now(timezone.utc)

        # Create the insight object
        insight_id = str(uuid.uuid4())
        delivered_insight = ProactiveInsight(
            id=insight_id,
            tenant_id=tenant_id,
            insight_type=insight.insight_type,
            title=insight.title,
            summary=insight.summary,
            details=insight.details,
            priority_score=insight.priority_score,
            urgency=insight.urgency,
            confidence=insight.confidence,
            related_documents=insight.related_documents,
            suggested_actions=insight.suggested_actions,
            reasoning=insight.reasoning,
            status=InsightStatus.DELIVERED,
            delivered_at=now,
            created_at=now,
            expires_at=insight.expires_at,
        )

        # Deliver via channels in priority order
        # Note: We deliver to ALL channels in priority list, not just the first one
        delivered = False
        for channel in config.channel_priority:
            try:
                if channel == "in_app":
                    await self._deliver_in_app(delivered_insight, tenant_id)
                    delivered = True
                elif channel == "slack":
                    await self._deliver_slack(delivered_insight, tenant_id)
                    delivered = True
                elif channel == "email":
                    await self._deliver_email(delivered_insight, tenant_id, config)
                    delivered = True
                # Continue to deliver to other channels (multi-channel delivery)
            except Exception as e:
                logger.warning(f"Failed to deliver via {channel}: {e}")
                continue

        if not delivered:
            logger.warning(f"Failed to deliver insight {insight_id} via any channel")
            return None

        # Store insight in Redis for retrieval
        await self._store_insight(delivered_insight, tenant_id)

        return delivered_insight

    async def _deliver_in_app(
        self,
        insight: ProactiveInsight,
        tenant_id: str,
    ):
        """Deliver insight as in-app notification via WebSocket."""
        # Map urgency to notification priority
        priority_map = {
            InsightUrgency.CRITICAL: "urgent",
            InsightUrgency.HIGH: "high",
            InsightUrgency.MEDIUM: "normal",
            InsightUrgency.LOW: "low",
        }

        # Use urgency value for lookup
        urgency_value = insight.urgency if isinstance(insight.urgency, str) else insight.urgency.value
        priority = priority_map.get(InsightUrgency(urgency_value), "normal")

        await notification_service.create_notification(
            tenant_id=tenant_id,
            user_id="system",  # Broadcast to all tenant users
            title=f"Emma Insight: {insight.title}",
            body=insight.summary,
            notification_type="proactive_insight",
            priority=priority,
            action_url=f"/emma/insights/{insight.id}",
            metadata={
                "insight_id": insight.id,
                "insight_type": insight.insight_type,
                "urgency": urgency_value,
                "related_documents": insight.related_documents,
            },
        )

    async def _deliver_email(
        self,
        insight: ProactiveInsight,
        tenant_id: str,
        config: HeartbeatConfig,
    ):
        """Send email to configured recipients via background worker.

        Reads email_recipients from HeartbeatConfig and sends an email
        to each recipient using the background worker's email task.
        """
        import httpx

        recipients = config.email_recipients
        if not recipients:
            logger.debug(f"No email recipients configured for tenant {tenant_id}")
            return

        # Build email content
        urgency_value = insight.urgency if isinstance(insight.urgency, str) else insight.urgency.value
        urgency_emoji = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "📋",
            "low": "ℹ️",
        }.get(urgency_value, "📋")

        subject = f"{urgency_emoji} Emma Insight: {insight.title}"

        # Call background worker for each recipient
        for email in recipients:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{settings.background_worker_url}/tasks/email/send",
                        json={
                            "to_email": email,
                            "subject": subject,
                            "template_name": "emma_insight",
                            "template_data": {
                                "title": insight.title,
                                "summary": insight.summary,
                                "urgency": urgency_value,
                                "insight_type": insight.insight_type,
                                "priority_score": insight.priority_score,
                                "related_documents": insight.related_documents,
                                "tenant_id": tenant_id,
                            },
                        },
                        headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
                    )
                logger.info(f"Email queued for {email} (insight {insight.id})")
            except Exception as e:
                logger.warning(f"Failed to queue email for {email}: {e}")

    async def _deliver_slack(
        self,
        insight: ProactiveInsight,
        tenant_id: str,
    ):
        """Deliver insight to Slack notification channels."""
        # Map urgency to priority string
        urgency_value = insight.urgency if isinstance(insight.urgency, str) else insight.urgency.value
        priority_map = {
            "critical": "critical",
            "high": "high",
            "medium": "normal",
            "low": "low",
        }
        priority = priority_map.get(urgency_value, "normal")

        # Use notification service's Slack delivery
        await notification_service.send_to_slack_channels(
            tenant_id=tenant_id,
            title=f"🔮 {insight.title}",
            body=insight.summary or "",
            priority=priority,
            metadata={
                "insight_id": insight.id,
                "insight_type": insight.insight_type,
                "urgency": urgency_value,
            },
        )
        logger.info(f"Slack notification sent for insight {insight.id}")

    async def _store_insight(
        self,
        insight: ProactiveInsight,
        tenant_id: str,
    ):
        """Store delivered insight in Redis for retrieval."""
        r = await self._get_redis()

        # Store insight data
        key = f"emma:insights:{tenant_id}:{insight.id}"
        await r.hset(key, mapping={
            "id": insight.id,
            "insight_type": insight.insight_type,
            "title": insight.title,
            "summary": insight.summary or "",
            "priority_score": str(insight.priority_score),
            "urgency": insight.urgency if isinstance(insight.urgency, str) else insight.urgency.value,
            "status": insight.status if isinstance(insight.status, str) else insight.status.value,
            "delivered_at": insight.delivered_at.isoformat() if insight.delivered_at else "",
            "created_at": insight.created_at.isoformat(),
        })
        await r.expire(key, 86400 * 7)  # 7 days TTL

        # Add to tenant's insight list
        list_key = f"emma:insights:{tenant_id}:list"
        await r.lpush(list_key, insight.id)
        await r.ltrim(list_key, 0, 99)  # Keep last 100

    async def _get_delivery_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get current delivery statistics for rate limiting."""
        r = await self._get_redis()
        key = f"emma:heartbeat:delivery:{tenant_id}"

        data = await r.hgetall(key)
        now = datetime.now(timezone.utc)

        # Parse or initialize stats
        stats = {
            "today_count": int(data.get("today_count", 0)),
            "hour_count": int(data.get("hour_count", 0)),
            "last_insight_at": data.get("last_insight_at"),
            "today_date": data.get("today_date"),
            "hour_timestamp": data.get("hour_timestamp"),
        }

        # Reset counters if day/hour changed
        today = now.strftime("%Y-%m-%d")
        current_hour = now.strftime("%Y-%m-%d-%H")

        if stats["today_date"] != today:
            stats["today_count"] = 0
            stats["today_date"] = today

        if stats["hour_timestamp"] != current_hour:
            stats["hour_count"] = 0
            stats["hour_timestamp"] = current_hour

        return stats

    async def _update_delivery_stats(self, tenant_id: str, now: datetime):
        """Update delivery statistics after sending an insight."""
        r = await self._get_redis()
        key = f"emma:heartbeat:delivery:{tenant_id}"

        today = now.strftime("%Y-%m-%d")
        current_hour = now.strftime("%Y-%m-%d-%H")

        await r.hset(key, mapping={
            "today_count": await r.hincrby(key, "today_count", 0) + 1,
            "hour_count": await r.hincrby(key, "hour_count", 0) + 1,
            "last_insight_at": now.isoformat(),
            "today_date": today,
            "hour_timestamp": current_hour,
        })
        await r.hincrby(key, "today_count", 1)
        await r.hincrby(key, "hour_count", 1)

        # Set TTL to expire at end of day
        await r.expireat(key, int((now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()))

    async def get_pending_insights(
        self,
        tenant_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get list of recent insights for a tenant."""
        r = await self._get_redis()

        list_key = f"emma:insights:{tenant_id}:list"
        insight_ids = await r.lrange(list_key, 0, limit - 1)

        insights = []
        for insight_id in insight_ids:
            key = f"emma:insights:{tenant_id}:{insight_id}"
            data = await r.hgetall(key)
            if data:
                insights.append(data)

        return insights


# Global singleton
delivery_manager = DeliveryManager()
