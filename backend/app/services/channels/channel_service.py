"""
Service for managing Information Channels.

Provides CRUD operations for channels and coordinates sync operations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    InformationChannel,
    ChannelCredential,
    ChannelDocument,
    ChannelSyncLog,
    User,
)
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelType,
    ChannelVisibility,
    SyncLogResponse,
    SyncTriggerType,
    ChannelDocumentResponse,
)

logger = logging.getLogger(__name__)


class ChannelService:
    """
    Service for Information Channel management.

    Handles:
    - CRUD operations for channels
    - Channel visibility and access control
    - Sync status tracking
    - Document indexing coordination
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Channel CRUD
    # =========================================================================

    async def create_channel(
        self,
        user_id: UUID,
        channel_type: ChannelType,
        name: str,
        description: Optional[str] = None,
        visibility: ChannelVisibility = ChannelVisibility.PERSONAL,
        configuration: Dict[str, Any] = None,
        sync_interval_minutes: int = 60,
    ) -> InformationChannel:
        """
        Create a new information channel.

        Args:
            user_id: User creating the channel
            channel_type: Type of channel (gmail, google_drive, external_db)
            name: Display name
            description: Optional description
            visibility: personal or global
            configuration: Type-specific configuration
            sync_interval_minutes: Sync frequency (0 = manual only)

        Returns:
            The created InformationChannel
        """
        channel = InformationChannel(
            created_by=user_id,
            name=name,
            description=description,
            channel_type=channel_type.value,
            visibility=visibility.value,
            configuration=configuration or {},
            sync_interval_minutes=sync_interval_minutes,
            is_active=True,
        )

        # Calculate next sync time if interval > 0
        if sync_interval_minutes > 0:
            channel.next_sync_at = datetime.now(timezone.utc) + timedelta(
                minutes=sync_interval_minutes
            )

        self.db.add(channel)
        await self.db.commit()

        # Re-fetch with credential relationship loaded to avoid lazy-load issues
        stmt = (
            select(InformationChannel)
            .options(selectinload(InformationChannel.credential))
            .where(InformationChannel.id == channel.id)
        )
        result = await self.db.execute(stmt)
        channel = result.scalar_one()

        logger.info(
            f"Created channel {channel.id} ({channel_type.value}) for user {user_id}"
        )
        return channel

    async def get_channel(
        self,
        channel_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Optional[InformationChannel]:
        """
        Get a channel by ID with access control.

        Args:
            channel_id: Channel UUID
            user_id: User ID for personal channel access check

        Returns:
            The channel if found and accessible, None otherwise
        """
        stmt = (
            select(InformationChannel)
            .options(selectinload(InformationChannel.credential))
            .where(InformationChannel.id == channel_id)
        )
        result = await self.db.execute(stmt)
        channel = result.scalar_one_or_none()

        if not channel:
            return None

        # Check access for personal channels
        if channel.visibility == "personal" and user_id:
            if channel.created_by != user_id:
                return None

        return channel

    async def list_channels(
        self,
        user_id: UUID,
        channel_type: Optional[ChannelType] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[InformationChannel], int]:
        """
        List channels accessible to a user.

        Users can see:
        - All global channels
        - Personal channels they created

        Args:
            user_id: Requesting user ID
            channel_type: Filter by type
            is_active: Filter by active status
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (channels list, total count)
        """
        # Base filter: global visibility OR owned by user
        access_filter = or_(
            InformationChannel.visibility == "tenant",
            InformationChannel.created_by == user_id,
        )

        # Build count query
        count_stmt = select(func.count(InformationChannel.id)).where(access_filter)

        # Apply optional filters
        filters = [access_filter]
        if channel_type:
            filters.append(InformationChannel.channel_type == channel_type.value)
        if is_active is not None:
            filters.append(InformationChannel.is_active == is_active)

        # Count with filters
        count_stmt = select(func.count(InformationChannel.id)).where(and_(*filters))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar()

        # Fetch channels
        stmt = (
            select(InformationChannel)
            .options(selectinload(InformationChannel.credential))
            .where(and_(*filters))
            .order_by(InformationChannel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        channels = list(result.scalars().all())

        return channels, total

    async def update_channel(
        self,
        channel_id: UUID,
        user_id: UUID,
        update_data: ChannelUpdate,
    ) -> Optional[InformationChannel]:
        """
        Update a channel.

        Only the channel creator can update it.

        Args:
            channel_id: Channel to update
            user_id: User making the update
            update_data: Fields to update

        Returns:
            Updated channel or None if not found/unauthorized
        """
        channel = await self.get_channel(channel_id, user_id)
        if not channel:
            return None

        # Only creator can update
        if channel.created_by != user_id:
            logger.warning(f"User {user_id} tried to update channel {channel_id} owned by {channel.created_by}")
            return None

        # Apply updates
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if field == "visibility" and value:
                setattr(channel, field, value.value if hasattr(value, "value") else value)
            elif value is not None:
                setattr(channel, field, value)

        # Recalculate next sync if interval changed
        if "sync_interval_minutes" in update_dict:
            if channel.sync_interval_minutes > 0:
                channel.next_sync_at = datetime.now(timezone.utc) + timedelta(
                    minutes=channel.sync_interval_minutes
                )
            else:
                channel.next_sync_at = None

        await self.db.commit()
        await self.db.refresh(channel)

        logger.info(f"Updated channel {channel_id}")
        return channel

    async def delete_channel(
        self,
        channel_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Delete a channel and all associated data.

        Only the channel creator can delete it.
        This also deletes:
        - Credentials
        - Document references (Weaviate documents should be cleaned separately)
        - Sync logs

        Args:
            channel_id: Channel to delete
            user_id: User requesting deletion

        Returns:
            True if deleted, False if not found/unauthorized
        """
        channel = await self.get_channel(channel_id, user_id)
        if not channel:
            return False

        # Only creator can delete
        if channel.created_by != user_id:
            logger.warning(f"User {user_id} tried to delete channel {channel_id} owned by {channel.created_by}")
            return False

        # Get Weaviate IDs for cleanup (caller should handle Weaviate deletion)
        weaviate_ids = await self._get_channel_weaviate_ids(channel_id)

        # Delete channel (cascades to credentials, documents, sync_logs)
        await self.db.delete(channel)
        await self.db.commit()

        logger.info(f"Deleted channel {channel_id} with {len(weaviate_ids)} documents")
        return True

    # =========================================================================
    # Sync Operations
    # =========================================================================

    async def start_sync(
        self,
        channel_id: UUID,
        trigger_type: SyncTriggerType = SyncTriggerType.MANUAL,
    ) -> ChannelSyncLog:
        """
        Start a sync operation and create log entry.

        Args:
            channel_id: Channel to sync
            trigger_type: How the sync was triggered

        Returns:
            The created sync log entry
        """
        sync_log = ChannelSyncLog(
            channel_id=channel_id,
            started_at=datetime.now(timezone.utc),
            status="running",
            trigger_type=trigger_type.value,
        )
        self.db.add(sync_log)

        # Update channel status
        stmt = (
            update(InformationChannel)
            .where(InformationChannel.id == channel_id)
            .values(last_sync_status="running")
        )
        await self.db.execute(stmt)
        await self.db.commit()
        await self.db.refresh(sync_log)

        return sync_log

    async def complete_sync(
        self,
        sync_log_id: UUID,
        status: str,
        items_found: int = 0,
        items_new: int = 0,
        items_updated: int = 0,
        items_deleted: int = 0,
        items_failed: int = 0,
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Complete a sync operation and update status.

        Args:
            sync_log_id: The sync log entry ID
            status: Final status (success, partial, failed)
            items_*: Counts of processed items
            error_message: Error message if failed
            error_details: Detailed error info
        """
        now = datetime.now(timezone.utc)

        # Update sync log
        stmt = (
            update(ChannelSyncLog)
            .where(ChannelSyncLog.id == sync_log_id)
            .values(
                completed_at=now,
                status=status,
                items_found=items_found,
                items_new=items_new,
                items_updated=items_updated,
                items_deleted=items_deleted,
                items_failed=items_failed,
                error_message=error_message,
                error_details=error_details,
            )
            .returning(ChannelSyncLog.channel_id)
        )
        result = await self.db.execute(stmt)
        channel_id = result.scalar_one()

        # Update channel status
        total_docs = await self._count_channel_documents(channel_id)
        next_sync = None
        channel_stmt = select(InformationChannel).where(InformationChannel.id == channel_id)
        channel_result = await self.db.execute(channel_stmt)
        channel = channel_result.scalar_one()

        if channel.sync_interval_minutes > 0:
            next_sync = now + timedelta(minutes=channel.sync_interval_minutes)

        update_stmt = (
            update(InformationChannel)
            .where(InformationChannel.id == channel_id)
            .values(
                last_sync_at=now,
                last_sync_status=status,
                last_sync_error=error_message,
                documents_indexed=total_docs,
                next_sync_at=next_sync,
            )
        )
        await self.db.execute(update_stmt)
        await self.db.commit()

    async def get_sync_history(
        self,
        channel_id: UUID,
        limit: int = 20,
    ) -> List[ChannelSyncLog]:
        """
        Get sync history for a channel.

        Args:
            channel_id: Channel UUID
            limit: Max entries to return

        Returns:
            List of sync log entries, newest first
        """
        # Verify channel exists
        channel_stmt = select(InformationChannel).where(
            InformationChannel.id == channel_id,
        )
        channel_result = await self.db.execute(channel_stmt)
        if not channel_result.scalar_one_or_none():
            return []

        stmt = (
            select(ChannelSyncLog)
            .where(ChannelSyncLog.channel_id == channel_id)
            .order_by(ChannelSyncLog.started_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Document Operations
    # =========================================================================

    async def upsert_document(
        self,
        channel_id: UUID,
        external_id: str,
        content_hash: str,
        title: Optional[str] = None,
        external_url: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        source_created_at: Optional[datetime] = None,
        source_modified_at: Optional[datetime] = None,
    ) -> Tuple[ChannelDocument, bool]:
        """
        Create or update a channel document reference.

        Args:
            channel_id: Channel this document belongs to
            external_id: External system identifier
            content_hash: SHA-256 hash of content
            title: Document title
            external_url: Link to original
            source_metadata: Type-specific metadata
            source_created_at: When created in source
            source_modified_at: When modified in source

        Returns:
            Tuple of (document, is_new) - is_new is True if created, False if updated
        """
        # Check if exists
        stmt = select(ChannelDocument).where(
            ChannelDocument.channel_id == channel_id,
            ChannelDocument.external_id == external_id,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Check if content changed
            if existing.content_hash == content_hash:
                return existing, False

            # Update existing
            existing.content_hash = content_hash
            existing.title = title or existing.title
            existing.external_url = external_url or existing.external_url
            existing.source_metadata = source_metadata or existing.source_metadata
            existing.source_modified_at = source_modified_at
            existing.status = "pending"  # Re-index needed
            await self.db.commit()
            await self.db.refresh(existing)
            return existing, False
        else:
            # Create new
            doc = ChannelDocument(
                channel_id=channel_id,
                external_id=external_id,
                content_hash=content_hash,
                title=title,
                external_url=external_url,
                source_metadata=source_metadata,
                source_created_at=source_created_at,
                source_modified_at=source_modified_at,
                status="pending",
            )
            self.db.add(doc)
            await self.db.commit()
            await self.db.refresh(doc)
            return doc, True

    async def mark_document_indexed(
        self,
        document_id: UUID,
        weaviate_id: str,
    ) -> None:
        """Mark a document as successfully indexed."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(ChannelDocument)
            .where(ChannelDocument.id == document_id)
            .values(
                weaviate_id=weaviate_id,
                status="indexed",
                error_message=None,
                last_indexed_at=now,
                first_indexed_at=func.coalesce(
                    ChannelDocument.first_indexed_at, now
                ),
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def mark_document_failed(
        self,
        document_id: UUID,
        error_message: str,
    ) -> None:
        """Mark a document as failed to index."""
        stmt = (
            update(ChannelDocument)
            .where(ChannelDocument.id == document_id)
            .values(status="failed", error_message=error_message)
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def get_pending_documents(
        self,
        channel_id: UUID,
        limit: int = 100,
    ) -> List[ChannelDocument]:
        """Get documents pending indexing for a channel."""
        stmt = (
            select(ChannelDocument)
            .where(
                ChannelDocument.channel_id == channel_id,
                ChannelDocument.status == "pending",
            )
            .order_by(ChannelDocument.created_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_channel_documents(
        self,
        channel_id: UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ChannelDocument], int]:
        """
        List documents from a channel.

        Args:
            channel_id: Channel UUID
            status: Filter by status
            page: Page number
            page_size: Items per page

        Returns:
            Tuple of (documents, total count)
        """
        filters = [ChannelDocument.channel_id == channel_id]
        if status:
            filters.append(ChannelDocument.status == status)

        count_stmt = select(func.count(ChannelDocument.id)).where(and_(*filters))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar()

        stmt = (
            select(ChannelDocument)
            .where(and_(*filters))
            .order_by(ChannelDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        documents = list(result.scalars().all())

        return documents, total

    # =========================================================================
    # Scheduled Sync Support
    # =========================================================================

    async def get_channels_due_for_sync(
        self,
        limit: int = 50,
    ) -> List[InformationChannel]:
        """
        Get channels that are due for scheduled sync.

        Args:
            limit: Max channels to return

        Returns:
            List of channels ready to sync
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(InformationChannel)
            .where(
                InformationChannel.is_active == True,
                InformationChannel.next_sync_at <= now,
                InformationChannel.sync_interval_minutes > 0,
                # Handle NULL: NULL != 'running' returns NULL, not True
                or_(
                    InformationChannel.last_sync_status != "running",
                    InformationChannel.last_sync_status == None,
                ),
            )
            .order_by(InformationChannel.next_sync_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_channel_weaviate_ids(self, channel_id: UUID) -> List[str]:
        """Get all Weaviate IDs for a channel's documents."""
        stmt = (
            select(ChannelDocument.weaviate_id)
            .where(
                ChannelDocument.channel_id == channel_id,
                ChannelDocument.weaviate_id.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def _count_channel_documents(self, channel_id: UUID) -> int:
        """Count indexed documents for a channel."""
        stmt = select(func.count(ChannelDocument.id)).where(
            ChannelDocument.channel_id == channel_id,
            ChannelDocument.status == "indexed",
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    def channel_to_response(
        self,
        channel: InformationChannel,
    ) -> ChannelResponse:
        """Convert channel model to response schema."""
        return ChannelResponse(
            id=channel.id,
            created_by=channel.created_by,
            name=channel.name,
            description=channel.description,
            channel_type=ChannelType(channel.channel_type),
            visibility=ChannelVisibility(channel.visibility),
            configuration=channel.configuration or {},
            is_active=channel.is_active,
            last_sync_at=channel.last_sync_at,
            last_sync_status=channel.last_sync_status,
            last_sync_error=channel.last_sync_error,
            documents_indexed=channel.documents_indexed or 0,
            sync_interval_minutes=channel.sync_interval_minutes,
            next_sync_at=channel.next_sync_at,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
            oauth_email=channel.credential.oauth_email if channel.credential else None,
            has_credentials=channel.credential is not None,
        )
