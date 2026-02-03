"""Celery tasks for Connector synchronization (new model using Connector table)."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID
from contextlib import asynccontextmanager

import httpx
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.models import Connector, UserDocumentSync, IndexedDocument, User
from app.schemas.connector import AlfrescoConfig

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _create_fresh_engine():
    """Create a fresh async engine for the current event loop.

    IMPORTANT: Do NOT cache the engine across asyncio.run() calls!
    Each asyncio.run() creates a new event loop, and asyncpg connections
    are bound to the loop they were created in.
    """
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
    """Get async database session for use in Celery tasks."""
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


# =============================================================================
# Alfresco Sync Implementation with AFTS Filters
# =============================================================================

class AlfrescoSyncService:
    """
    Service for syncing documents from Alfresco using AFTS filters.

    Uses the Alfresco Search API with AFTS (Alfresco Full Text Search) queries
    to filter documents by type, aspect, path, MIME type, etc.
    """

    def __init__(self, config: AlfrescoConfig, timeout: int = 60):
        self.config = config
        self.timeout = timeout
        self.base_url = config.url.rstrip("/")
        self.api_path = config.api_path
        self.search_api_path = config.search_api_path

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Alfresco."""
        import base64
        auth_str = f"{self.config.username}:{self.config.password}"
        auth_bytes = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {auth_bytes}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def search_documents(
        self,
        modified_after: Optional[datetime] = None,
        max_items: int = 100,
        skip_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Search for documents using AFTS query built from config filters.

        Args:
            modified_after: Only return documents modified after this date
            max_items: Maximum number of results to return
            skip_count: Number of results to skip (for pagination)

        Returns:
            Dict with search results and pagination info
        """
        # Build AFTS query from configuration
        afts_query = self.config.build_sync_afts_query()

        # Add date filter if specified
        if modified_after:
            date_str = modified_after.strftime("%Y-%m-%dT%H:%M:%S")
            afts_query = f"({afts_query}) AND @cm\\:modified:['{date_str}' TO MAX]"

        logger.info(f"Executing AFTS query: {afts_query}")

        search_body = {
            "query": {
                "query": afts_query,
                "language": "afts"
            },
            "paging": {
                "maxItems": max_items,
                "skipCount": skip_count
            },
            "include": ["properties", "path", "aspectNames"],
            "sort": [{"type": "FIELD", "field": "cm:modified", "ascending": True}],
        }

        async with httpx.AsyncClient(
            headers=self._get_auth_headers(),
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(self.timeout),
                write=30.0,
                pool=5.0
            )
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.search_api_path}/search",
                json=search_body
            )
            response.raise_for_status()
            return response.json()

    async def get_document_content(self, node_id: str) -> bytes:
        """
        Download document content from Alfresco.

        Args:
            node_id: The Alfresco node UUID

        Returns:
            Document content as bytes
        """
        async with httpx.AsyncClient(
            headers=self._get_auth_headers(),
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(self.config.download_timeout_seconds or 300),
                write=30.0,
                pool=5.0
            )
        ) as client:
            response = await client.get(
                f"{self.base_url}{self.api_path}/nodes/{node_id}/content"
            )
            response.raise_for_status()
            return response.content

    async def sync_documents(
        self,
        tenant_id: UUID,
        connector_id: UUID,
        owner_id: UUID,
        db: AsyncSession,
        full_sync: bool = False,
        last_sync: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Sync documents from Alfresco to the database.

        Args:
            tenant_id: Tenant UUID
            connector_id: Connector UUID
            owner_id: Owner user UUID (for service account, documents belong to admin)
            db: Database session
            full_sync: Force full sync instead of incremental
            last_sync: Last successful sync time (for incremental)

        Returns:
            Dict with sync statistics
        """
        stats = {
            "items_found": 0,
            "items_new": 0,
            "items_updated": 0,
            "items_failed": 0,
            "items_deleted": 0,
            "errors": [],
        }

        modified_after = None if full_sync else last_sync
        skip_count = 0
        max_items = self.config.max_results or 100
        has_more = True

        while has_more:
            try:
                result = await self.search_documents(
                    modified_after=modified_after,
                    max_items=max_items,
                    skip_count=skip_count,
                )

                entries = result.get("list", {}).get("entries", [])
                pagination = result.get("list", {}).get("pagination", {})

                stats["items_found"] += len(entries)
                has_more = pagination.get("hasMoreItems", False)
                skip_count += len(entries)

                for entry_wrapper in entries:
                    entry = entry_wrapper.get("entry", {})
                    try:
                        await self._process_document(
                            entry=entry,
                            tenant_id=tenant_id,
                            connector_id=connector_id,
                            owner_id=owner_id,
                            db=db,
                            stats=stats,
                        )
                    except Exception as e:
                        stats["items_failed"] += 1
                        stats["errors"].append({
                            "node_id": entry.get("id"),
                            "name": entry.get("name"),
                            "error": str(e),
                        })
                        logger.error(f"Error processing document {entry.get('name')}: {e}")

                # Commit batch
                await db.commit()

            except httpx.HTTPStatusError as e:
                logger.error(f"Alfresco API error: {e.response.status_code}")
                stats["errors"].append({
                    "type": "api_error",
                    "status_code": e.response.status_code,
                    "error": str(e),
                })
                break
            except Exception as e:
                logger.exception(f"Error during sync: {e}")
                stats["errors"].append({
                    "type": "sync_error",
                    "error": str(e),
                })
                break

        return stats

    async def _process_document(
        self,
        entry: Dict[str, Any],
        tenant_id: UUID,
        connector_id: UUID,
        owner_id: UUID,
        db: AsyncSession,
        stats: Dict[str, Any],
    ) -> None:
        """
        Process a single document from Alfresco search results.

        Creates or updates the IndexedDocument record.
        """
        node_id = entry.get("id")
        name = entry.get("name")
        properties = entry.get("properties", {})
        path_info = entry.get("path", {})
        content_info = entry.get("content", {})

        # Build external path
        path_elements = path_info.get("elements", [])
        path_parts = [elem.get("name", "") for elem in path_elements]
        external_path = "/" + "/".join(path_parts) if path_parts else "/"

        # Get document metadata
        title = properties.get("cm:title") or name
        description = properties.get("cm:description")
        mime_type = content_info.get("mimeType")
        size_bytes = content_info.get("sizeInBytes", 0)

        # Extract file extension
        file_extension = None
        if name and "." in name:
            file_extension = name.rsplit(".", 1)[-1].lower()

        # Build external URL
        external_url = f"{self.base_url}/share/page/document-details?nodeRef=workspace://SpacesStore/{node_id}"

        # Check if document already exists
        existing = await db.execute(
            select(IndexedDocument).where(
                and_(
                    IndexedDocument.connector_id == connector_id,
                    IndexedDocument.external_id == node_id,
                )
            )
        )
        existing_doc = existing.scalar_one_or_none()

        if existing_doc:
            # Update existing document
            existing_doc.title = title
            existing_doc.description = description
            existing_doc.external_path = external_path
            existing_doc.external_url = external_url
            existing_doc.mime_type = mime_type
            existing_doc.size_bytes = size_bytes
            existing_doc.file_extension = file_extension
            existing_doc.source_modified_at = datetime.fromisoformat(
                properties.get("cm:modified", "").replace("Z", "+00:00")
            ) if properties.get("cm:modified") else None
            existing_doc.updated_at = datetime.now(timezone.utc)
            stats["items_updated"] += 1
        else:
            # Create new document
            source_created = None
            if properties.get("cm:created"):
                try:
                    source_created = datetime.fromisoformat(
                        properties.get("cm:created").replace("Z", "+00:00")
                    )
                except:
                    pass

            source_modified = None
            if properties.get("cm:modified"):
                try:
                    source_modified = datetime.fromisoformat(
                        properties.get("cm:modified").replace("Z", "+00:00")
                    )
                except:
                    pass

            new_doc = IndexedDocument(
                tenant_id=tenant_id,
                connector_id=connector_id,
                external_id=node_id,
                external_url=external_url,
                external_path=external_path,
                owner_id=owner_id,
                is_tenant_public=True,  # Service account = public to tenant
                title=title,
                description=description,
                mime_type=mime_type,
                file_extension=file_extension,
                size_bytes=size_bytes,
                source_created_at=source_created,
                source_modified_at=source_modified,
                indexing_status="pending",
            )
            db.add(new_doc)
            stats["items_new"] += 1


# =============================================================================
# Celery Tasks
# =============================================================================

async def _sync_connector(
    connector_id: str,
    full_sync: bool = False,
) -> Dict[str, Any]:
    """
    Execute synchronization for a single connector.

    Args:
        connector_id: Connector UUID as string
        full_sync: Force full resync

    Returns:
        Dict with sync results
    """
    try:
        async with get_async_db_session() as db:
            # Get connector
            stmt = select(Connector).where(Connector.id == UUID(connector_id))
            result = await db.execute(stmt)
            connector = result.scalar_one_or_none()

            if not connector:
                logger.error(f"Connector {connector_id} not found")
                return {"success": False, "error": "Connector not found"}

            if not connector.is_active:
                logger.info(f"Connector {connector_id} is not active, skipping")
                return {"success": False, "error": "Connector not active"}

            if not connector.sync_enabled:
                logger.info(f"Connector {connector_id} sync is disabled, skipping")
                return {"success": False, "error": "Sync disabled"}

            # Currently only support Alfresco
            if connector.connector_type != "alfresco":
                logger.warning(f"Connector type {connector.connector_type} sync not yet implemented")
                return {"success": False, "error": f"Sync not implemented for {connector.connector_type}"}

            # Parse Alfresco config
            try:
                alfresco_config = AlfrescoConfig(**connector.config)
            except Exception as e:
                logger.error(f"Invalid Alfresco config: {e}")
                return {"success": False, "error": f"Invalid config: {e}"}

            # Get owner for documents (the admin who created the connector, or first admin)
            owner_id = connector.created_by_id
            if not owner_id:
                # Find any admin user for this tenant
                admin_result = await db.execute(
                    select(User).where(
                        and_(
                            User.tenant_id == connector.tenant_id,
                            User.is_active == True,
                        )
                    ).limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                if admin_user:
                    owner_id = admin_user.id
                else:
                    return {"success": False, "error": "No owner found for documents"}

            # Get last sync time from UserDocumentSync or connector stats
            last_sync = None
            if not full_sync:
                # Use last_health_check as proxy for last sync time
                # In a full implementation, we'd track this separately
                last_sync = connector.last_health_check

            # Execute sync
            sync_service = AlfrescoSyncService(
                config=alfresco_config,
                timeout=alfresco_config.timeout_seconds or 60,
            )

            stats = await sync_service.sync_documents(
                tenant_id=connector.tenant_id,
                connector_id=connector.id,
                owner_id=owner_id,
                db=db,
                full_sync=full_sync,
                last_sync=last_sync,
            )

            # Update connector health status
            connector.last_health_check = datetime.now(timezone.utc)
            connector.health_status = "healthy" if stats["items_failed"] == 0 else "degraded"
            connector.health_message = (
                f"Synced {stats['items_new']} new, {stats['items_updated']} updated, "
                f"{stats['items_failed']} failed"
            )

            await db.commit()

            logger.info(
                f"Connector sync completed: {connector_id} - "
                f"found={stats['items_found']}, new={stats['items_new']}, "
                f"updated={stats['items_updated']}, failed={stats['items_failed']}"
            )

            # ================================================================
            # NexusRouter Post-Sync Hook
            # Notify router about new documents for potential retraining
            # ================================================================
            new_docs = stats['items_new'] + stats['items_updated']
            if new_docs > 0:
                try:
                    from worker_app.tasks.router_tasks import increment_docs_since_train_task
                    increment_docs_since_train_task.delay(new_docs)
                    logger.info(f"📊 NexusRouter notified: {new_docs} new/updated documents")
                except ImportError:
                    logger.debug("NexusRouter tasks not available, skipping notification")
                except Exception as e:
                    logger.warning(f"Failed to notify NexusRouter: {e}")

            stats["success"] = True

            # Emit connector.synced event to the reactive event bus
            try:
                from worker_app.services.event_publisher import publish_event
                publish_event(
                    event_type="connector.synced",
                    tenant_id=str(connector.tenant_id),
                    payload={
                        "connector_id": str(connector_id),
                        "connector_type": connector.connector_type,
                        "docs_new": stats["items_new"],
                        "docs_updated": stats["items_updated"],
                        "docs_failed": stats["items_failed"],
                        "status": "healthy" if stats["items_failed"] == 0 else "degraded",
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to emit connector.synced event: {e}")

            return stats

    except Exception as exc:
        logger.exception(f"Error syncing connector {connector_id}: {exc}")
        return {"success": False, "error": str(exc)}


@celery_app.task(name="connectors.sync_connector", bind=True, max_retries=3)
def sync_connector_task(
    self,
    connector_id: str,
    full_sync: bool = False,
) -> Dict[str, Any]:
    """
    Celery task to sync a single connector.

    Args:
        connector_id: Connector UUID as string
        full_sync: Force full resync

    Returns:
        Dict with sync results
    """
    try:
        return _run_async(_sync_connector(connector_id, full_sync))
    except Exception as exc:
        logger.exception(f"Connector sync task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _sync_scheduled_connectors() -> Dict[str, Any]:
    """
    Find and sync all connectors due for scheduled sync.

    Returns:
        Dict with batch sync results
    """
    processed = 0
    successes = 0
    failures = 0

    try:
        async with get_async_db_session() as db:
            # Get connectors due for sync
            # Conditions:
            # 1. is_active = True
            # 2. sync_enabled = True
            # 3. last_health_check is None OR older than sync_interval_hours
            now = datetime.now(timezone.utc)

            stmt = select(Connector).where(
                and_(
                    Connector.is_active == True,
                    Connector.sync_enabled == True,
                    or_(
                        Connector.last_health_check.is_(None),
                        Connector.last_health_check < now - timedelta(hours=1),  # At least 1 hour old
                    )
                )
            ).limit(20)

            result = await db.execute(stmt)
            connectors = result.scalars().all()

            if not connectors:
                logger.debug("No connectors due for scheduled sync")
                return {"processed": 0, "successes": 0, "failures": 0}

            logger.info(f"Found {len(connectors)} connectors due for sync")

            for connector in connectors:
                # Check if enough time has passed based on sync_interval_hours
                if connector.last_health_check:
                    hours_since_sync = (now - connector.last_health_check).total_seconds() / 3600
                    if hours_since_sync < connector.sync_interval_hours:
                        continue

                processed += 1
                try:
                    # Dispatch individual sync task
                    sync_connector_task.delay(str(connector.id))
                    successes += 1
                except Exception as e:
                    logger.error(f"Error dispatching sync for connector {connector.id}: {e}")
                    failures += 1

    except Exception as exc:
        logger.exception(f"Error in scheduled connector sync batch: {exc}")
        return {"processed": processed, "successes": successes, "failures": failures, "error": str(exc)}

    return {
        "processed": processed,
        "successes": successes,
        "failures": failures,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="connectors.sync_scheduled")
def sync_scheduled_connectors_task() -> Dict[str, Any]:
    """
    Celery beat task to trigger scheduled connector syncs.

    This runs periodically and dispatches individual sync tasks
    for connectors that are due.
    """
    return _run_async(_sync_scheduled_connectors())


async def _cleanup_orphaned_connector_documents(connector_id: str) -> Dict[str, Any]:
    """
    Clean up documents for a deleted connector.

    Args:
        connector_id: Connector UUID as string

    Returns:
        Dict with cleanup results
    """
    deleted_count = 0

    try:
        async with get_async_db_session() as db:
            # Get all documents for this connector
            stmt = select(IndexedDocument).where(
                IndexedDocument.connector_id == UUID(connector_id)
            )
            result = await db.execute(stmt)
            documents = result.scalars().all()

            for doc in documents:
                # Mark as orphaned or delete
                # For now, just mark the status
                doc.indexing_status = "orphaned"
                deleted_count += 1

            await db.commit()

            # TODO: Also clean up from Weaviate vector database
            logger.info(f"Marked {deleted_count} documents as orphaned for connector {connector_id}")

    except Exception as exc:
        logger.exception(f"Error cleaning up connector documents: {exc}")
        return {"deleted": 0, "error": str(exc)}

    return {"deleted": deleted_count, "connector_id": connector_id}


@celery_app.task(name="connectors.cleanup_documents")
def cleanup_connector_documents_task(connector_id: str) -> Dict[str, Any]:
    """
    Celery task to clean up documents after connector deletion.

    Args:
        connector_id: Deleted connector UUID

    Returns:
        Dict with cleanup results
    """
    return _run_async(_cleanup_orphaned_connector_documents(connector_id))


# =============================================================================
# NEW: Unified Indexing Tasks (using UnifiedIndexingService)
# =============================================================================

async def _index_pending_documents(
    connector_id: str,
    batch_size: int = 10,
    max_documents: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Index pending documents from a connector to Weaviate.

    This is the CRITICAL task that closes the GAP:
    - Takes documents with indexing_status="pending"
    - Downloads content from source (Alfresco, etc.)
    - Sends to Weaviate Service IndexingPipeline
    - Updates status to "indexed" with weaviate_id

    Args:
        connector_id: Connector UUID as string
        batch_size: Number of documents to process per batch
        max_documents: Max documents to process (None = all pending)

    Returns:
        Dict with indexing statistics
    """
    # Import here to avoid circular imports
    from app.services.unified_indexing_service import unified_indexing_service

    try:
        async with get_async_db_session() as db:
            result = await unified_indexing_service.index_pending_documents(
                connector_id=UUID(connector_id),
                db=db,
                batch_size=batch_size,
                max_documents=max_documents,
            )
            return result.to_dict()

    except Exception as exc:
        logger.exception(f"Error indexing pending documents for {connector_id}: {exc}")
        return {"success": False, "error": str(exc)}


@celery_app.task(name="connectors.index_pending", bind=True, max_retries=3)
def index_pending_documents_task(
    self,
    connector_id: str,
    batch_size: int = 10,
    max_documents: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Celery task to index pending documents to Weaviate.

    This task should be called after sync_connector_task completes,
    or can be scheduled independently to process pending documents.

    Args:
        connector_id: Connector UUID as string
        batch_size: Documents per batch
        max_documents: Max documents to process

    Returns:
        Dict with indexing results
    """
    try:
        return _run_async(_index_pending_documents(connector_id, batch_size, max_documents))
    except Exception as exc:
        logger.exception(f"Index pending task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _sync_and_index_connector(
    connector_id: str,
    full_sync: bool = False,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Full sync + index operation.

    Combines metadata sync from source with indexing to Weaviate.

    Args:
        connector_id: Connector UUID
        full_sync: Force full resync
        batch_size: Indexing batch size

    Returns:
        Combined results
    """
    from app.services.unified_indexing_service import unified_indexing_service

    try:
        async with get_async_db_session() as db:
            result = await unified_indexing_service.sync_and_index(
                connector_id=UUID(connector_id),
                db=db,
                full_sync=full_sync,
                index_batch_size=batch_size,
            )
            return result

    except Exception as exc:
        logger.exception(f"Error in sync_and_index for {connector_id}: {exc}")
        return {"success": False, "error": str(exc)}


@celery_app.task(name="connectors.sync_and_index", bind=True, max_retries=3)
def sync_and_index_connector_task(
    self,
    connector_id: str,
    full_sync: bool = False,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Celery task for complete sync + index operation.

    Use this for manual "Sync Now" operations from the UI.

    Args:
        connector_id: Connector UUID
        full_sync: Force full resync
        batch_size: Indexing batch size

    Returns:
        Combined sync and index results
    """
    try:
        return _run_async(_sync_and_index_connector(connector_id, full_sync, batch_size))
    except Exception as exc:
        logger.exception(f"Sync and index task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _index_all_pending_connectors() -> Dict[str, Any]:
    """
    Index pending documents for ALL active connectors.

    This is meant to be scheduled via Celery Beat to continuously
    process pending documents across all connectors.

    Returns:
        Dict with per-connector results
    """
    from app.services.unified_indexing_service import unified_indexing_service

    results = {
        "processed_connectors": 0,
        "total_indexed": 0,
        "total_failed": 0,
        "connector_results": [],
    }

    try:
        async with get_async_db_session() as db:
            # Find connectors with pending documents
            from sqlalchemy import func

            stmt = (
                select(IndexedDocument.connector_id, func.count(IndexedDocument.id))
                .where(IndexedDocument.indexing_status == "pending")
                .group_by(IndexedDocument.connector_id)
                .having(func.count(IndexedDocument.id) > 0)
                .limit(10)  # Process max 10 connectors per run
            )

            pending_result = await db.execute(stmt)
            connectors_with_pending = pending_result.all()

            for connector_id, pending_count in connectors_with_pending:
                logger.info(
                    f"Processing connector {connector_id} with {pending_count} pending documents"
                )

                try:
                    result = await unified_indexing_service.index_pending_documents(
                        connector_id=connector_id,
                        db=db,
                        batch_size=10,
                        max_documents=50,  # Limit per connector per run
                    )

                    results["processed_connectors"] += 1
                    results["total_indexed"] += result.documents_indexed
                    results["total_failed"] += result.documents_failed
                    results["connector_results"].append({
                        "connector_id": str(connector_id),
                        "indexed": result.documents_indexed,
                        "failed": result.documents_failed,
                    })

                except Exception as e:
                    logger.error(f"Error processing connector {connector_id}: {e}")
                    results["connector_results"].append({
                        "connector_id": str(connector_id),
                        "error": str(e),
                    })

    except Exception as exc:
        logger.exception(f"Error in index_all_pending_connectors: {exc}")
        results["error"] = str(exc)

    return results


@celery_app.task(name="connectors.index_all_pending")
def index_all_pending_connectors_task() -> Dict[str, Any]:
    """
    Celery beat task to index pending documents across all connectors.

    This should be scheduled to run every 15-30 minutes to continuously
    process pending documents.

    Returns:
        Dict with per-connector results
    """
    return _run_async(_index_all_pending_connectors())
