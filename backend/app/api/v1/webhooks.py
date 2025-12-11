"""
Webhook handlers for external services integration.

NOTE: Clerk webhooks REMOVED - using JIT provisioning instead.
Users are created automatically on first authenticated request.
"""
import logging
from datetime import datetime
from typing import Any, Dict
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", tags=["webhooks"])
async def webhook_health():
    """Health check endpoint for webhook infrastructure."""
    return {
        "status": "ok",
        "service": "nexus-webhooks",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "Clerk webhooks disabled - using JIT provisioning"
    }
