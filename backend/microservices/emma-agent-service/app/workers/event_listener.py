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

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.config import settings
from app.services.event_bus import event_bus
from app.schemas.events import EmmaEvent

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("emma.event_listener")

CONSUMER_GROUP = os.getenv("EVENT_CONSUMER_GROUP", "emma_reactive")
CONSUMER_NAME = os.getenv("EVENT_CONSUMER_NAME", f"worker-{os.getpid()}")

# Shutdown flag
_shutdown = asyncio.Event()


async def handle_event(event: EmmaEvent, msg_id: str):
    """Process a single event through the trigger engine."""
    logger.info(f"Processing event: {event.event_type} [{event.tenant_id}] id={msg_id}")

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
