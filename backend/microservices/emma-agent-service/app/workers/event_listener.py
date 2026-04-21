"""Event Listener Worker — Async consumer for Emma Reactive events.

Runs as a standalone process that listens to Redis Streams and dispatches
events to the Trigger Engine for evaluation and action execution.

Usage:
    python -m app.workers.event_listener

This process is started by the emma-reactive-worker Docker service.
"""
import asyncio
import logging
import os
import signal
import sys

import httpx

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.config import settings
from app.services.event_bus import event_bus
from app.schemas.events import EmmaEvent

KTS_URL = os.getenv("KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
KTS_API_KEY = getattr(settings, "microservices_api_key", "") or os.getenv("MICROSERVICES_API_KEY", "")

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("emma.event_listener")

CONSUMER_GROUP = os.getenv("EVENT_CONSUMER_GROUP", "emma_reactive")
CONSUMER_NAME = os.getenv("EVENT_CONSUMER_NAME", f"worker-{os.getpid()}")

# Shutdown flag
_shutdown = asyncio.Event()


async def _auto_index_to_falkordb(event: EmmaEvent):
    """Index document to FalkorDB knowledge graph via KTS.

    Called for every document.indexed event. Fire-and-forget: failures
    are logged but never block the event pipeline.
    """
    payload = event.payload
    doc_id = payload.get("doc_id", "")
    if not doc_id:
        return

    kts_payload = {
        "document_id": doc_id,
        "file_path": payload.get("file_path", ""),
        "connector_metadata": {
            "title": payload.get("title", ""),
            "domain": payload.get("domain", ""),
            "semantic_type": payload.get("semantic_type", ""),
        },
        "connector_id": payload.get("connector_id") or None,
        "connector_type": payload.get("connector_type") or None,
    }

    headers = {"Content-Type": "application/json"}
    if KTS_API_KEY:
        headers["X-API-Key"] = KTS_API_KEY

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.post(
                f"{KTS_URL}/tree/index",
                headers=headers,
                json=kts_payload,
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"Auto-indexed {payload.get('title', doc_id)} to FalkorDB "
                    f"(success={result.get('success')})"
                )
            else:
                logger.warning(
                    f"KTS auto-index returned {response.status_code} for {doc_id}: "
                    f"{response.text[:200]}"
                )
    except Exception as e:
        logger.warning(f"KTS auto-index failed for {doc_id}: {e}")


async def handle_event(event: EmmaEvent, msg_id: str):
    """Process a single event through the trigger engine."""
    logger.info(f"Processing event: {event.event_type} id={msg_id}")

    # Auto-index to FalkorDB on document.indexed (before triggers)
    if event.event_type == "document.indexed":
        await _auto_index_to_falkordb(event)

    try:
        # Import trigger engine lazily to avoid circular imports
        from app.services.trigger_engine import trigger_engine
        await trigger_engine.evaluate_event(event)
    except ImportError:
        # Trigger engine not yet implemented (Phase 3) — log and continue
        logger.debug(f"Trigger engine not available, skipping event {event.event_type}")
    except Exception as e:
        logger.error(f"Error processing event {event.event_type}: {e}", exc_info=True)

    # Always ack so the event doesn't block the consumer group
    await event_bus.ack(msg_id, CONSUMER_GROUP)


async def run_listener():
    """Main event loop — subscribe and process events."""
    logger.info(f"Starting event listener (group={CONSUMER_GROUP}, consumer={CONSUMER_NAME})")

    health = await event_bus.health_check()
    logger.info(f"Event bus health: {health}")

    async for event, msg_id in event_bus.subscribe(CONSUMER_GROUP, CONSUMER_NAME):
        if _shutdown.is_set():
            break
        await handle_event(event, msg_id)

    logger.info("Event listener shutting down")
    await event_bus.close()


def _signal_handler():
    """Handle shutdown signals."""
    logger.info("Received shutdown signal")
    _shutdown.set()


def main():
    """Entry point for the event listener worker."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        loop.run_until_complete(run_listener())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
