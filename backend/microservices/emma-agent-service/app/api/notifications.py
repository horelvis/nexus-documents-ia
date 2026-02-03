"""Notifications API — In-app notification management.

Endpoints:
    GET   /notifications           — List notifications
    GET   /notifications/unread    — Unread count
    PATCH /notifications/{id}/read — Mark as read
    POST  /notifications/read-all  — Mark all as read
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import settings
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)
router = APIRouter()


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
