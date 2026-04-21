"""Notification Service — Multi-channel notification dispatcher.

Supports:
- in_app: Stored in Redis inbox + pushed via WebSocket
- email: Sent via SMTP (delegates to background worker)
- webhook: HTTP POST to configured URL
- slack: Sent to dedicated notification channels via Slack API

Notifications are created by trigger executions, system events,
or manual API calls.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
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
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{user_id}"
        await r.lpush(inbox_key, json.dumps(notification))
        await r.ltrim(inbox_key, 0, 499)  # Keep last 500 notifications

        # Push to WebSocket channel for real-time delivery
        await r.publish(WS_NOTIFICATION_CHANNEL, json.dumps(notification))

        logger.info(f"Notification created: {title} → user {user_id}")
        return notification

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch notifications for a user."""
        r = await self._get_redis()
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{user_id}"
        raw_items = await r.lrange(inbox_key, 0, limit - 1)

        notifications = [json.loads(item) for item in raw_items]
        if unread_only:
            notifications = [n for n in notifications if not n.get("is_read")]
        return notifications

    async def mark_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a notification as read."""
        r = await self._get_redis()
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{user_id}"
        items = await r.lrange(inbox_key, 0, -1)

        for i, raw in enumerate(items):
            notif = json.loads(raw)
            if notif.get("id") == notification_id:
                notif["is_read"] = True
                await r.lset(inbox_key, i, json.dumps(notif))
                return True
        return False

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        r = await self._get_redis()
        inbox_key = f"{NOTIFICATIONS_KEY_PREFIX}:{user_id}"
        items = await r.lrange(inbox_key, 0, -1)
        count = 0

        for i, raw in enumerate(items):
            notif = json.loads(raw)
            if not notif.get("is_read"):
                notif["is_read"] = True
                await r.lset(inbox_key, i, json.dumps(notif))
                count += 1
        return count

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications."""
        notifications = await self.get_notifications(user_id, unread_only=True, limit=500)
        return len(notifications)

    # ── Trigger Integration ──────────────────────────────────────────

    async def send_trigger_notification(
        self,
        trigger_name: str,
        event: EmmaEvent,
        channels: List[str],
    ):
        """Send notification about a trigger match (before execution)."""
        for channel in channels:
            if channel == "in_app":
                await self.create_notification(
                    user_id="system",  # Will be routed to all admins
                    title=f"🔔 Trigger activado: {trigger_name}",
                    body=f"Evento {event.event_type} coincidió con el trigger '{trigger_name}'.",
                    notification_type="trigger_match",
                    metadata={"event": event.model_dump()},
                )
            elif channel == "slack":
                await self._send_slack_notification(
                    title=f"🔔 Trigger activado: {trigger_name}",
                    body=f"Evento `{event.event_type}` coincidió con el trigger '{trigger_name}'.",
                    priority="normal",
                    metadata={"event_type": event.event_type},
                )

    async def send_trigger_result(
        self,
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
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{settings.background_worker_url}/api/send_email",
                            json={
                                "subject": f"Emma: {trigger_name} — {status}",
                                "body": f"Trigger execution {status}",
                            },
                            headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
                        )
                except Exception as e:
                    logger.warning(f"Failed to send email notification: {e}")

            elif channel == "slack":
                # Send to dedicated Slack notification channels
                await self._send_slack_notification(
                    title=f"{emoji} Resultado: {trigger_name}",
                    body=f"Trigger '{trigger_name}' completado con estado: {status}",
                    priority="high" if status == "failed" else "normal",
                    metadata={"execution_id": execution.get("id")},
                )

    # ── Slack Integration ──────────────────────────────────────────────

    async def _get_notification_channels(self, channel_type: str = "slack") -> List[Dict[str, Any]]:
        """Get channels marked as notification channels.

        Queries Redis directly to find channels with config.is_notification_channel=true.
        """
        try:
            from cryptography.fernet import Fernet

            r = await self._get_redis()

            # Get channel encryption key
            key = getattr(settings, "credentials_encryption_key", None)
            if not key:
                import os
                key = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")

            fernet = Fernet(key.encode()) if key else None

            # Query all channels (single-tenant: global index)
            CHANNELS_PREFIX = "emma:channels"
            channel_ids = await r.smembers(f"{CHANNELS_PREFIX}:index")

            notification_channels = []
            for cid in channel_ids:
                data = await r.get(f"{CHANNELS_PREFIX}:{cid}")
                if data:
                    ch = json.loads(data)
                    # Check if it's a notification channel of the right type
                    if (
                        ch.get("channel_type") == channel_type
                        and ch.get("is_active", False)
                        and ch.get("config", {}).get("is_notification_channel", False)
                    ):
                        # Decrypt credentials
                        encrypted = ch.get("credentials_encrypted", "")
                        if encrypted and fernet:
                            try:
                                ch["credentials_decrypted"] = fernet.decrypt(encrypted.encode()).decode()
                            except Exception:
                                ch["credentials_decrypted"] = encrypted
                        else:
                            ch["credentials_decrypted"] = encrypted
                        notification_channels.append(ch)

            return notification_channels

        except Exception as e:
            logger.warning(f"Failed to fetch notification channels: {e}")
        return []

    async def _send_slack_notification(
        self,
        title: str,
        body: str,
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Send a notification to all Slack notification channels.

        Finds channels marked with config.is_notification_channel=true and sends
        the notification to the configured default_channel (e.g., #emma-alerts).
        """
        from app.channels.slack_channel import SlackChannel

        channels = await self._get_notification_channels("slack")

        if not channels:
            logger.debug("No Slack notification channels configured")
            return

        for channel_data in channels:
            try:
                config = channel_data.get("config", {})
                credentials = channel_data.get("credentials_decrypted", "")
                default_channel = config.get("default_channel", "")

                if not default_channel:
                    logger.warning(f"Slack notification channel {channel_data['id']} has no default_channel")
                    continue

                # Create channel instance
                slack = SlackChannel(
                    channel_id=channel_data["id"],
                    config=config,
                    credentials=credentials,
                )

                # Format message with emoji based on priority
                priority_emoji = {
                    "critical": "🚨",
                    "high": "⚠️",
                    "normal": "📢",
                    "low": "ℹ️",
                }.get(priority, "📢")

                message = f"{priority_emoji} *{title}*\n{body}"

                if metadata:
                    # Add action link if present
                    if metadata.get("execution_id"):
                        message += f"\n\n_Execution ID: `{metadata['execution_id']}`_"

                # Send to the default channel
                result = await slack.send_message(to=default_channel, content=message)

                if result.get("success"):
                    logger.info(f"Slack notification sent to {default_channel}: {title}")
                else:
                    logger.warning(f"Slack notification failed: {result.get('error')}")

            except Exception as e:
                logger.error(f"Failed to send Slack notification: {e}", exc_info=True)

    async def send_to_slack_channels(
        self,
        title: str,
        body: str,
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Public method to send notifications to Slack channels.

        Use this for direct Slack notifications outside of trigger results.
        """
        await self._send_slack_notification(
            title=title,
            body=body,
            priority=priority,
            metadata=metadata,
        )


# Global singleton
notification_service = NotificationService()
