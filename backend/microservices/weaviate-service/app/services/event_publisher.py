"""Lightweight event publisher for weaviate-service.

Publishes events to the shared Redis Streams bus without depending
on emma-agent-service schemas. Uses the same stream key and format.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

STREAM_KEY = "emma:events"
MAX_STREAM_LEN = 10000

_redis_client: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        redis_url = getattr(settings, "redis_url", None) or "redis://redis:6379"
        _redis_client = aioredis.from_url(redis_url, decode_responses=False)
    return _redis_client


async def publish_event(
    event_type: str,
    tenant_id: str,
    payload: Dict[str, Any],
    source_service: str = "weaviate-service",
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """Publish an event to the Emma reactive event bus.

    Returns the stream message ID, or None if publishing fails.
    This is fire-and-forget — failures are logged but don't raise.
    """
    try:
        r = await _get_redis()
        data = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "tenant_id": tenant_id,
            "payload": json.dumps(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_service": source_service,
            "correlation_id": correlation_id or "",
        }
        msg_id = await r.xadd(STREAM_KEY, data, maxlen=MAX_STREAM_LEN, approximate=True)
        logger.info(f"Published event {event_type} for tenant {tenant_id}")
        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id
    except Exception as e:
        logger.warning(f"Failed to publish event {event_type}: {e}")
        return None


async def close_publisher():
    """Close the Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
