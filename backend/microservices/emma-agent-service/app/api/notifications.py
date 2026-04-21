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

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from app.core.auth_headers import extract_user_id
from app.core.config import settings
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis channel for real-time notifications
WS_NOTIFICATION_CHANNEL = "emma:notifications:realtime"


def _require_user_id(user_id: Optional[str]) -> str:
    if not user_id:
        return "system"
    return user_id


@router.get("/notifications")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    user_id: Optional[str] = Depends(extract_user_id),
):
    """List notifications for the current user."""
    uid = _require_user_id(user_id)
    notifications = await notification_service.get_notifications(
        user_id=uid,
        unread_only=unread_only,
        limit=limit,
    )
    return {"notifications": notifications, "total": len(notifications)}


@router.get("/notifications/unread")
async def unread_count(
    user_id: Optional[str] = Depends(extract_user_id),
):
    """Get unread notification count."""
    uid = _require_user_id(user_id)
    count = await notification_service.get_unread_count(uid)
    return {"unread_count": count}


@router.patch("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: str,
    user_id: Optional[str] = Depends(extract_user_id),
):
    """Mark a notification as read."""
    uid = _require_user_id(user_id)
    success = await notification_service.mark_read(uid, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.post("/notifications/read-all")
async def mark_all_read(
    user_id: Optional[str] = Depends(extract_user_id),
):
    """Mark all notifications as read."""
    uid = _require_user_id(user_id)
    count = await notification_service.mark_all_read(uid)
    return {"marked_read": count}


# =============================================================================
# WebSocket Endpoint for Real-Time Notifications
# =============================================================================

@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket endpoint for real-time notification push.

    Clients connect here to receive notifications in real-time via Redis Pub/Sub.
    """
    await websocket.accept()
    logger.info("WebSocket client connected for notifications")

    # Get user from query params or use default
    user_id = websocket.query_params.get("user_id") or "system"

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
        logger.info(f"Subscribed to {WS_NOTIFICATION_CHANNEL} for user {user_id}")

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
                        # Filter by user
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
