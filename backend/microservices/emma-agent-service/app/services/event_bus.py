"""Event Bus — Redis Streams based event system for Emma Reactive.

Provides publish/subscribe/ack over Redis Streams with consumer groups.
Each microservice publishes events; the emma-reactive-worker consumes them.

Usage:
    from app.services.event_bus import event_bus

    # Publish
    await event_bus.publish(EmmaEvent(
        event_type="document.indexed",
        tenant_id="tenant-123",
        payload={"doc_id": "abc", "collection": "contracts"},
    ))

    # Subscribe (used by event_listener worker)
    async for event, msg_id in event_bus.subscribe("emma_reactive"):
        await process(event)
        await event_bus.ack(msg_id, "emma_reactive")
"""
import asyncio
import json
import logging
from typing import AsyncIterator, Callable, Dict, List, Optional, Tuple

import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.events import EmmaEvent

logger = logging.getLogger(__name__)

# Stream key prefix — all events go through this stream
STREAM_KEY = "emma:events"
# Max stream length (auto-trimmed by Redis)
MAX_STREAM_LEN = 10000
# Block timeout for XREADGROUP (ms)
READ_BLOCK_MS = 5000


class EventBus:
    """Redis Streams based event bus for inter-service communication."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=False,  # We handle decoding ourselves
            )
        return self._redis

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    # ── Publishing ────────────────────────────────────────────────────

    async def publish(self, event: EmmaEvent) -> str:
        """Publish an event to the stream. Returns the stream message ID."""
        r = await self._get_redis()
        stream_data = event.to_stream_dict()
        msg_id = await r.xadd(
            STREAM_KEY,
            stream_data,
            maxlen=MAX_STREAM_LEN,
            approximate=True,
        )
        logger.info(f"Published {event.event_type} [{event.tenant_id}] → {msg_id}")
        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id

    # ── Subscribing (consumer group) ─────────────────────────────────

    async def ensure_consumer_group(self, group_name: str):
        """Create consumer group if it doesn't exist."""
        r = await self._get_redis()
        try:
            await r.xgroup_create(STREAM_KEY, group_name, id="0", mkstream=True)
            logger.info(f"Created consumer group '{group_name}' on stream '{STREAM_KEY}'")
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            # Group already exists — fine

    async def subscribe(
        self,
        group_name: str,
        consumer_name: str = "worker-1",
    ) -> AsyncIterator[Tuple[EmmaEvent, str]]:
        """Yield (event, message_id) tuples from the stream.

        Uses XREADGROUP for at-least-once delivery semantics.
        """
        r = await self._get_redis()
        await self.ensure_consumer_group(group_name)

        while True:
            try:
                results = await r.xreadgroup(
                    group_name,
                    consumer_name,
                    {STREAM_KEY: ">"},
                    count=10,
                    block=READ_BLOCK_MS,
                )
                if not results:
                    continue

                for stream_name, messages in results:
                    for msg_id, data in messages:
                        try:
                            event = EmmaEvent.from_stream_dict(data)
                            mid = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                            yield event, mid
                        except Exception as e:
                            logger.error(f"Failed to parse event {msg_id}: {e}")
                            # Ack bad messages so they don't block the group
                            await self.ack(
                                msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                                group_name,
                            )

            except asyncio.CancelledError:
                logger.info("Event subscription cancelled")
                break
            except Exception as e:
                logger.error(f"Error reading from stream: {e}")
                await asyncio.sleep(2)

    async def ack(self, msg_id: str, group_name: str):
        """Acknowledge a message as processed."""
        r = await self._get_redis()
        await r.xack(STREAM_KEY, group_name, msg_id)

    # ── Utilities ────────────────────────────────────────────────────

    async def stream_info(self) -> Dict:
        """Get stream metadata for health checks."""
        r = await self._get_redis()
        try:
            info = await r.xinfo_stream(STREAM_KEY)
            return {
                "length": info.get(b"length", 0) if isinstance(info, dict) else 0,
                "groups": await r.xinfo_groups(STREAM_KEY),
            }
        except aioredis.ResponseError:
            return {"length": 0, "groups": []}

    async def health_check(self) -> Dict:
        """Check Redis connectivity."""
        try:
            r = await self._get_redis()
            await r.ping()
            info = await self.stream_info()
            return {"status": "healthy", "stream": info}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global singleton
event_bus = EventBus()
