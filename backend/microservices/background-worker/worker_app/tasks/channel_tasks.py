"""Celery tasks for Information Channel synchronization."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.models import InformationChannel
from app.services.channels import (
    ChannelService,
    ChannelCredentialService,
    GoogleDriveChannelService,
    GmailChannelService,
)
from app.schemas.channel import SyncTriggerType

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _create_fresh_engine():
    """Create a fresh async engine for the current event loop.

    IMPORTANT: Do NOT cache the engine across asyncio.run() calls!
    Each asyncio.run() creates a new event loop, and asyncpg connections
    are bound to the loop they were created in.
    """
    # Build async database URI
    db_uri = settings.SQLALCHEMY_DATABASE_URI
    if "postgresql://" in db_uri and "+asyncpg" not in db_uri:
        async_uri = db_uri.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_uri = db_uri

    return create_async_engine(
        async_uri,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


@asynccontextmanager
async def get_async_db_session():
    """Get async database session for use in Celery tasks.

    Creates a fresh engine for each call to avoid event loop conflicts.
    """
    engine = _create_fresh_engine()
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        await engine.dispose()


def _run_async(coro):
    """Run an async coroutine in the Celery task context."""
    return asyncio.run(coro)


async def _sync_channel(
    channel_id: str,
    sync_log_id: Optional[str] = None,
    full_sync: bool = False,
) -> Dict[str, Any]:
    """
    Execute synchronization for a single channel.

    Args:
        channel_id: Channel UUID as string
        sync_log_id: Optional sync log ID (if already started)
        full_sync: Force full resync

    Returns:
        Dict with sync results
    """
    try:
        async with get_async_db_session() as db:
            # Get channel
            stmt = select(InformationChannel).where(
                InformationChannel.id == UUID(channel_id)
            )
            result = await db.execute(stmt)
            channel = result.scalar_one_or_none()

            if not channel:
                logger.error(f"Channel {channel_id} not found")
                return {"success": False, "error": "Channel not found"}

            if not channel.is_active:
                logger.info(f"Channel {channel_id} is not active, skipping")
                return {"success": False, "error": "Channel not active"}

            # Initialize services with async session
            channel_service = ChannelService(db)
            credential_service = ChannelCredentialService(db)

            # Start sync log if not provided
            if not sync_log_id:
                sync_log = await channel_service.start_sync(
                    channel_id=UUID(channel_id),
                    trigger_type=SyncTriggerType.SCHEDULED,
                )
                sync_log_id = str(sync_log.id)

            # Execute sync based on channel type
            stats = {"success": False, "error": "Unknown channel type"}

            if channel.channel_type == "google_drive":
                gdrive_service = GoogleDriveChannelService(
                    db=db,
                    channel_service=channel_service,
                    credential_service=credential_service,
                )
                stats = await gdrive_service.sync_channel(channel, full_sync=full_sync)
                stats["success"] = True

            elif channel.channel_type == "gmail":
                gmail_service = GmailChannelService(
                    db=db,
                    channel_service=channel_service,
                    credential_service=credential_service,
                )
                stats = await gmail_service.sync_channel(channel, full_sync=full_sync)
                stats["success"] = True

            elif channel.channel_type == "external_db":
                # TODO: Implement external database sync
                stats = {"success": False, "error": "External DB sync not yet implemented"}

            # Complete sync log
            status = "success" if stats.get("success") else "failed"
            if stats.get("items_failed", 0) > 0 and stats.get("items_new", 0) + stats.get("items_updated", 0) > 0:
                status = "partial"

            await channel_service.complete_sync(
                sync_log_id=UUID(sync_log_id),
                status=status,
                items_found=stats.get("items_found", 0),
                items_new=stats.get("items_new", 0),
                items_updated=stats.get("items_updated", 0),
                items_deleted=stats.get("items_deleted", 0),
                items_failed=stats.get("items_failed", 0),
                error_message=stats.get("error") if not stats.get("success") else None,
                error_details={"errors": stats.get("errors", [])} if stats.get("errors") else None,
            )

            logger.info(
                f"Channel sync completed: {channel_id} - "
                f"new={stats.get('items_new', 0)}, "
                f"updated={stats.get('items_updated', 0)}, "
                f"failed={stats.get('items_failed', 0)}"
            )

            return stats

    except Exception as exc:
        logger.exception(f"Error syncing channel {channel_id}: {exc}")

        # Try to mark sync as failed
        if sync_log_id:
            try:
                async with get_async_db_session() as db:
                    channel_service = ChannelService(db)
                    await channel_service.complete_sync(
                        sync_log_id=UUID(sync_log_id),
                        status="failed",
                        error_message=str(exc),
                    )
            except Exception:
                pass

        return {"success": False, "error": str(exc)}


@celery_app.task(name="channels.sync_channel", bind=True, max_retries=3)
def sync_channel_task(
    self,
    channel_id: str,
    sync_log_id: Optional[str] = None,
    full_sync: bool = False,
) -> Dict[str, Any]:
    """
    Celery task to sync a single channel.

    Args:
        channel_id: Channel UUID as string
        sync_log_id: Optional sync log ID
        full_sync: Force full resync

    Returns:
        Dict with sync results
    """
    try:
        return _run_async(_sync_channel(channel_id, sync_log_id, full_sync))
    except Exception as exc:
        logger.exception(f"Channel sync task failed: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _sync_scheduled_channels() -> Dict[str, Any]:
    """
    Find and sync all channels due for scheduled sync.

    Returns:
        Dict with batch sync results
    """
    processed = 0
    successes = 0
    failures = 0

    try:
        async with get_async_db_session() as db:
            channel_service = ChannelService(db)
            channels = await channel_service.get_channels_due_for_sync(limit=20)

            if not channels:
                logger.debug("No channels due for scheduled sync")
                return {"processed": 0, "successes": 0, "failures": 0}

            logger.info(f"Found {len(channels)} channels due for sync")

            for channel in channels:
                processed += 1
                try:
                    # Dispatch individual sync task
                    sync_channel_task.delay(str(channel.id))
                    successes += 1
                except Exception as e:
                    logger.error(f"Error dispatching sync for channel {channel.id}: {e}")
                    failures += 1

    except Exception as exc:
        logger.exception(f"Error in scheduled sync batch: {exc}")
        return {"processed": processed, "successes": successes, "failures": failures, "error": str(exc)}

    return {
        "processed": processed,
        "successes": successes,
        "failures": failures,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="channels.sync_scheduled")
def sync_scheduled_channels_task() -> Dict[str, Any]:
    """
    Celery beat task to trigger scheduled channel syncs.

    This runs periodically and dispatches individual sync tasks
    for channels that are due.
    """
    return _run_async(_sync_scheduled_channels())


async def _cleanup_orphaned_documents(channel_id: str) -> Dict[str, Any]:
    """
    Clean up Weaviate documents for a deleted channel.

    Args:
        channel_id: Channel UUID as string

    Returns:
        Dict with cleanup results
    """
    # TODO: Implement Weaviate cleanup
    # This should delete all documents in Weaviate that have
    # channel_id matching the deleted channel
    logger.info(f"Cleanup orphaned documents for channel {channel_id}")
    return {"deleted": 0, "channel_id": channel_id}


@celery_app.task(name="channels.cleanup_documents")
def cleanup_channel_documents_task(channel_id: str) -> Dict[str, Any]:
    """
    Celery task to clean up documents after channel deletion.

    Args:
        channel_id: Deleted channel UUID

    Returns:
        Dict with cleanup results
    """
    return _run_async(_cleanup_orphaned_documents(channel_id))
