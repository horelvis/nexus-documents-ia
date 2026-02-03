"""Lightweight event publisher for background-worker.

Publishes events to the shared Redis Streams bus.
Uses synchronous redis since Celery tasks run in sync context.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis

from worker_app.core.config import settings

logger = logging.getLogger(__name__)

STREAM_KEY = "emma:events"
MAX_STREAM_LEN = 10000

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    return _redis_client


def publish_event(
    event_type: str,
    tenant_id: str,
    payload: Dict[str, Any],
    source_service: str = "background-worker",
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """Publish an event synchronously (for use in Celery tasks)."""
    try:
        r = _get_redis()
        data = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "tenant_id": tenant_id,
            "payload": json.dumps(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_service": source_service,
            "correlation_id": correlation_id or "",
        }
        msg_id = r.xadd(STREAM_KEY, data, maxlen=MAX_STREAM_LEN, approximate=True)
        logger.info(f"Published event {event_type} for tenant {tenant_id}")
        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id
    except Exception as e:
        logger.warning(f"Failed to publish event {event_type}: {e}")
        return None
