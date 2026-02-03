"""Notifications API — In-app notification management.

Endpoints:
    GET   /notifications             — List notifications
    GET   /notifications/unread      — Unread count
    PATCH /notifications/{id}/read   — Mark as read
    POST  /notifications/read-all    — Mark all as read
    WS    /emma/ws/notifications     — Real-time WebSocket push
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from app.core.config import settings
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis channel for real-time notifications
WS_NOTIFICATION_CHANNEL = "emma:notifications:realtime"


def _get_tenant_and_user(
    x_tenant_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    tenant_id = x_tenant_id or (settings.default_tenant_id if settings.single_tenant_mode else None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    user_id = x_user_id or "system"
    return tenant_id, user_id


@router.get("/notifications")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    x_tenant_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """List notifications for the current user."""
    tenant_id, user_id = _get_tenant_and_user(x_tenant_id, x_user_id)
    notifications = await notification_service.get_notifications(
        tenant_id=tenant_id,
        user_id=user_id,
        unread_only=unread_only,
        limit=limit,
    )
    return {"notifications": notifications, "total": len(notifications)}


@router.get("/notifications/unread")
async def unread_count(
    x_tenant_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Get unread notification count."""
    tenant_id, user_id = _get_tenant_and_user(x_tenant_id, x_user_id)
    count = await notification_service.get_unread_count(tenant_id, user_id)
    return {"unread_count": count}


@router.patch("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: str,
    x_tenant_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Mark a notification as read."""
    tenant_id, user_id = _get_tenant_and_user(x_tenant_id, x_user_id)
    success = await notification_service.mark_read(tenant_id, user_id, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.post("/notifications/read-all")
async def mark_all_read(
    x_tenant_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Mark all notifications as read."""
    tenant_id, user_id = _get_tenant_and_user(x_tenant_id, x_user_id)
    count = await notification_service.mark_all_read(tenant_id, user_id)
    return {"marked_read": count}


# =============================================================================
# WebSocket Endpoint for Real-Time Notifications
# =============================================================================

@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket endpoint for real-time notification push.

    Clients connect here to receive notifications in real-time via Redis Pub/Sub.
    Uses single-tenant defaults if no tenant/user specified.
    """
    await websocket.accept()
    logger.info("WebSocket client connected for notifications")

    # Get tenant/user from query params or use defaults
    tenant_id = websocket.query_params.get("tenant_id") or (
        settings.default_tenant_id if settings.single_tenant_mode else None
    )
    user_id = websocket.query_params.get("user_id") or "system"

    if not tenant_id:
        await websocket.close(code=4000, reason="tenant_id required")
        return

    # Connect to Redis Pub/Sub
    redis_client = aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )
    pubsub = redis_client.pubsub()

    try:
        # Subscribe to notification channel
        await pubsub.subscribe(WS_NOTIFICATION_CHANNEL)
        logger.info(f"Subscribed to {WS_NOTIFICATION_CHANNEL} for tenant {tenant_id}")

        # Keep connection alive and forward messages
        while True:
            try:
                # Check for new messages (non-blocking with timeout)
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=5.0,
                )

                if message and message["type"] == "message":
                    try:
                        notification = json.loads(message["data"])
                        # Filter by tenant/user
                        if notification.get("tenant_id") == tenant_id:
                            if notification.get("user_id") == user_id or notification.get("user_id") == "system":
                                await websocket.send_json(notification)
                    except json.JSONDecodeError:
                        pass

                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        await pubsub.unsubscribe(WS_NOTIFICATION_CHANNEL)
        await pubsub.close()
        await redis_client.close()
        logger.info("WebSocket cleanup complete")
