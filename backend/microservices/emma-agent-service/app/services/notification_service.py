"""Notification Service — Multi-channel notification dispatcher.

Supports:
- in_app: Stored in DB + pushed via WebSocket
- email: Sent via SMTP (delegates to background worker)
- webhook: HTTP POST to configured URL

Notifications are created by trigger executions, system events,
or manual API calls.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.events import EmmaEvent

logger = logging.getLogger(__name__)

# Redis channel for real-time WebSocket push
WS_NOTIFICATION_CHANNEL = "emma:notifications:realtime"
NOTIFICATIONS_KEY_PREFIX = "emma:notifications"


class NotificationService:
    """Dispatches notifications across multiple channels."""

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

    async def create_notification(
        self,
        tenant_id: str,
        user_id: str,
        title: str,
        body: str,
        notification_type: str = "info",
        priority: str = "normal",
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and store a notification, then push via WebSocket."""
        notification = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "notification_type": notification_type,
            "title": title,
            "body": body,
            "metadata": metadata or {},
            "action_url": action_url,
            "is_read": False,
            "priority": priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        r = await self._get_redis()

        # Store in Redis list (per-user inbox)
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{tenant_id}:{user_id}"
        await r.lpush(inbox_key, json.dumps(notification))
        await r.ltrim(inbox_key, 0, 499)  # Keep last 500 notifications

        # Push to WebSocket channel for real-time delivery
        await r.publish(WS_NOTIFICATION_CHANNEL, json.dumps(notification))

        logger.info(f"Notification created: {title} → user {user_id}")
        return notification

    async def get_notifications(
        self,
        tenant_id: str,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch notifications for a user."""
        r = await self._get_redis()
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{tenant_id}:{user_id}"
        raw_items = await r.lrange(inbox_key, 0, limit - 1)

        notifications = [json.loads(item) for item in raw_items]
        if unread_only:
            notifications = [n for n in notifications if not n.get("is_read")]
        return notifications

    async def mark_read(self, tenant_id: str, user_id: str, notification_id: str) -> bool:
        """Mark a notification as read."""
        r = await self._get_redis()
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{tenant_id}:{user_id}"
        items = await r.lrange(inbox_key, 0, -1)

        for i, raw in enumerate(items):
            notif = json.loads(raw)
            if notif.get("id") == notification_id:
                notif["is_read"] = True
                await r.lset(inbox_key, i, json.dumps(notif))
                return True
        return False

    async def mark_all_read(self, tenant_id: str, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        r = await self._get_redis()
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{tenant_id}:{user_id}"
        items = await r.lrange(inbox_key, 0, -1)
        count = 0

        for i, raw in enumerate(items):
            notif = json.loads(raw)
            if not notif.get("is_read"):
                notif["is_read"] = True
                await r.lset(inbox_key, i, json.dumps(notif))
                count += 1
        return count

    async def get_unread_count(self, tenant_id: str, user_id: str) -> int:
        """Get count of unread notifications."""
        notifications = await self.get_notifications(tenant_id, user_id, unread_only=True, limit=500)
        return len(notifications)

    # ── Trigger Integration ──────────────────────────────────────────

    async def send_trigger_notification(
        self,
        tenant_id: str,
        trigger_name: str,
        event: EmmaEvent,
        channels: List[str],
    ):
        """Send notification about a trigger match (before execution)."""
        for channel in channels:
            if channel == "in_app":
                await self.create_notification(
                    tenant_id=tenant_id,
                    user_id="system",  # Will be routed to all admins
                    title=f"🔔 Trigger activado: {trigger_name}",
                    body=f"Evento {event.event_type} coincidió con el trigger '{trigger_name}'.",
                    notification_type="trigger_match",
                    metadata={"event": event.model_dump()},
                )

    async def send_trigger_result(
        self,
        tenant_id: str,
        trigger_name: str,
        execution: Dict[str, Any],
        channels: List[str],
    ):
        """Send notification about a completed trigger execution."""
        status = execution.get("status", "unknown")
        emoji = "✅" if status == "completed" else "❌"

        for channel in channels:
            if channel == "in_app":
                await self.create_notification(
                    tenant_id=tenant_id,
                    user_id="system",
                    title=f"{emoji} Resultado: {trigger_name}",
                    body=f"Trigger '{trigger_name}' completado con estado: {status}",
                    notification_type="trigger_result",
                    priority="high" if status == "failed" else "normal",
                    metadata={"execution_id": execution.get("id")},
                )
            elif channel == "email":
                # Delegate to background worker email task
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{settings.background_worker_url}/api/send_email",
                            json={
                                "subject": f"Emma: {trigger_name} — {status}",
                                "body": f"Trigger execution {status}",
                                "tenant_id": tenant_id,
                            },
                            headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                        )
                except Exception as e:
                    logger.warning(f"Failed to send email notification: {e}")


# Global singleton
notification_service = NotificationService()
