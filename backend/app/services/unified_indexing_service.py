"""
Unified Indexing Service

Orchestrates the complete document ingestion flow:
1. Discovery: Find documents via connector sync (metadata → PostgreSQL)
2. Download: Fetch content from source systems
3. Index: Process through IndexingPipeline → Weaviate

This is the "glue" that connects:
- ConnectorAdapters (source-specific logic)
- IndexedDocument table (metadata tracking)
- Weaviate Service IndexingPipeline (vector indexing)

The service closes the GAP in the current architecture where documents
get stuck in "pending" status because nothing processes them.

Usage:
    from app.services.unified_indexing_service import unified_indexing_service

    # Index all pending documents for a connector
    result = await unified_indexing_service.index_pending_documents(
        connector_id=UUID("..."),
        batch_size=10,
    )

    # Full sync: discover + index in one operation
    result = await unified_indexing_service.sync_and_index(
        connector_id=UUID("..."),
        full_sync=True,
    )
"""
import asyncio
import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Connector, IndexedDocument, User
from app.schemas.unified_document import (
    IndexingBatchResult,
    IndexingStatus,
    SyncResult,
    UnifiedDocument,
)
from app.services.connectors import (
    ConnectorAdapterFactory,
    ConnectorAdapter,
    ConnectorError,
    ConnectorConnectionError,
)

logger = logging.getLogger(__name__)


class UnifiedIndexingService:
    """
    Unified service for document ingestion from connectors.

    Coordinates:
    1. Connector adapters for source access
    2. PostgreSQL for metadata tracking
    3. Weaviate Service for vector indexing

    Thread-safe and can be used from Celery tasks or API handlers.
    """

    def __init__(
        self,
        weaviate_service_url: Optional[str] = None,
        weaviate_api_key: Optional[str] = None,
    ):
        """
        Initialize the unified indexing service.

        Args:
            weaviate_service_url: URL of weaviate-service (default from settings)
            weaviate_api_key: API key for weaviate-service (default from settings)
        """
        self.weaviate_service_url = (
            weaviate_service_url or
            getattr(settings, 'WEAVIATE_SERVICE_URL', 'http://weaviate-service:8007')
        )
        self.weaviate_api_key = (
            weaviate_api_key or
            getattr(settings, 'INTERNAL_API_KEY', None)
        )

        # Configuration
        self.default_batch_size = 10
        self.max_retries = 3
        self.retry_delay_seconds = 5
        self.download_timeout_seconds = 300  # 5 minutes

    async def sync_documents(
        self,
        connector_id: UUID,
        db: AsyncSession,
        full_sync: bool = False,
    ) -> SyncResult:
        """
        Sync document metadata from connector to PostgreSQL.

        This performs the DISCOVERY phase:
        - Calls connector.list_documents() with pagination
        - Creates/updates IndexedDocument records with status="pending"
        - Does NOT download content or index to Weaviate

        Args:
            connector_id: Connector UUID
            db: Database session
            full_sync: If True, sync all documents (ignore modified_after)

        Returns:
            SyncResult with statistics
        """
        start_time = time.time()

        # Get connector
        connector = await self._get_connector(db, connector_id)
        if not connector:
            return SyncResult(
                success=False,
                errors=[{"type": "not_found", "message": "Connector not found"}]
            )

        if not connector.is_active or not connector.sync_enabled:
            return SyncResult(
                success=False,
                errors=[{"type": "disabled", "message": "Connector is disabled"}]
            )

        # Get adapter
        try:
            adapter = ConnectorAdapterFactory.get_adapter(connector)
        except ValueError as e:
            return SyncResult(
                success=False,
                errors=[{"type": "unsupported", "message": str(e)}]
            )

        # Get owner ID (admin who created the connector)
        owner_id = await self._get_owner_id(db, connector)
        if not owner_id:
            return SyncResult(
                success=False,
                errors=[{"type": "no_owner", "message": "No owner found for documents"}]
            )

        # Determine modified_after for incremental sync
        modified_after = None
        if not full_sync:
            modified_after = connector.last_health_check  # Proxy for last sync

        # Sync with pagination
        result = SyncResult(success=True)
        skip = 0
        max_items = 100
        has_more = True

        while has_more:
            try:
                documents, has_more = await adapter.list_documents(
                    modified_after=modified_after,
                    skip=skip,
                    max_items=max_items,
                )

                result.items_found += len(documents)
                skip += len(documents)

                # Process each document
                for doc in documents:
                    try:
                        stats = await self._upsert_indexed_document(
                            db=db,
                            connector=connector,
                            document=doc,
                            owner_id=owner_id,
                        )
                        result.items_new += stats.get("new", 0)
                        result.items_updated += stats.get("updated", 0)
                    except Exception as e:
                        result.items_failed += 1
                        result.errors.append({
                            "external_id": doc.external_id,
                            "error": str(e),
                        })

                # Commit batch
                await db.commit()

            except ConnectorError as e:
                result.success = False
                result.errors.append({
                    "type": "connector_error",
                    "error": str(e),
                    "details": e.details,
                })
                break
            except Exception as e:
                result.success = False
                result.errors.append({
                    "type": "sync_error",
                    "error": str(e),
                })
                break

        # Update connector health status
        connector.last_health_check = datetime.now(timezone.utc)
        connector.health_status = "healthy" if result.success else "degraded"
        connector.health_message = (
            f"Synced {result.items_new} new, {result.items_updated} updated, "
            f"{result.items_failed} failed"
        )
        await db.commit()

        result.sync_duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"[{connector_id}] Sync completed: found={result.items_found}, "
            f"new={result.items_new}, updated={result.items_updated}, "
            f"failed={result.items_failed}"
        )

        return result

    async def index_pending_documents(
        self,
        connector_id: UUID,
        db: AsyncSession,
        batch_size: int = 10,
        max_documents: Optional[int] = None,
    ) -> IndexingBatchResult:
        """
        Index pending documents to Weaviate.

        This performs the INDEXING phase:
        1. Query IndexedDocument with status="pending"
        2. Download content via connector adapter
        3. Send to Weaviate Service IndexingPipeline
        4. Update status to "indexed" with weaviate_id

        Args:
            connector_id: Connector UUID
            db: Database session
            batch_size: Number of documents to process per batch
            max_documents: Maximum total documents to process (None = all)

        Returns:
            IndexingBatchResult with statistics
        """
        start_time = time.time()
        result = IndexingBatchResult()

        # Get connector
        connector = await self._get_connector(db, connector_id)
        if not connector:
            result.errors.append({"type": "not_found", "message": "Connector not found"})
            return result

        if not connector.is_active:
            result.errors.append({"type": "disabled", "message": "Connector is disabled"})
            return result

        # Get adapter
        try:
            adapter = ConnectorAdapterFactory.get_adapter(connector)
        except ValueError as e:
            result.errors.append({"type": "unsupported", "message": str(e)})
            return result

        # Query pending documents
        pending_query = (
            select(IndexedDocument)
            .where(
                and_(
                    IndexedDocument.connector_id == connector_id,
                    IndexedDocument.indexing_status == "pending",
                )
            )
            .order_by(IndexedDocument.created_at)
            .limit(max_documents or 1000)
        )

        pending_result = await db.execute(pending_query)
        pending_docs = pending_result.scalars().all()
        result.total_documents = len(pending_docs)

        if not pending_docs:
            logger.info(f"[{connector_id}] No pending documents to index")
            return result

        logger.info(f"[{connector_id}] Found {len(pending_docs)} pending documents")

        # Process in batches
        for i in range(0, len(pending_docs), batch_size):
            batch = pending_docs[i:i + batch_size]
            logger.info(
                f"[{connector_id}] Processing batch {i // batch_size + 1} "
                f"({len(batch)} documents)"
            )

            for doc in batch:
                try:
                    success = await self._index_single_document(
                        adapter=adapter,
                        indexed_doc=doc,
                        connector=connector,
                        db=db,
                    )
                    if success:
                        result.documents_indexed += 1
                    else:
                        result.documents_failed += 1

                except Exception as e:
                    logger.error(f"Error indexing document {doc.id}: {e}")
                    result.documents_failed += 1
                    result.errors.append({
                        "document_id": str(doc.id),
                        "external_id": doc.external_id,
                        "error": str(e),
                    })

                    # Mark as failed
                    doc.indexing_status = "failed"
                    doc.indexing_error = str(e)[:500]
                    await db.commit()

        result.batch_duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"[{connector_id}] Indexing completed: indexed={result.documents_indexed}, "
            f"failed={result.documents_failed}, skipped={result.documents_skipped}"
        )

        return result

    async def sync_and_index(
        self,
        connector_id: UUID,
        db: AsyncSession,
        full_sync: bool = False,
        index_batch_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Full sync + index operation in one call.

        Combines sync_documents() and index_pending_documents().

        Args:
            connector_id: Connector UUID
            db: Database session
            full_sync: Force full resync
            index_batch_size: Batch size for indexing

        Returns:
            Combined results from both operations
        """
        # Phase 1: Sync metadata
        logger.info(f"[{connector_id}] Starting sync phase...")
        sync_result = await self.sync_documents(
            connector_id=connector_id,
            db=db,
            full_sync=full_sync,
        )

        if not sync_result.success:
            return {
                "sync": sync_result.to_dict(),
                "index": None,
                "success": False,
            }

        # Phase 2: Index pending
        logger.info(f"[{connector_id}] Starting index phase...")
        index_result = await self.index_pending_documents(
            connector_id=connector_id,
            db=db,
            batch_size=index_batch_size,
        )

        return {
            "sync": sync_result.to_dict(),
            "index": index_result.to_dict(),
            "success": True,
        }

    async def _index_single_document(
        self,
        adapter: ConnectorAdapter,
        indexed_doc: IndexedDocument,
        connector: Connector,
        db: AsyncSession,
    ) -> bool:
        """
        Index a single document through the Weaviate pipeline.

        Args:
            adapter: Connector adapter for downloading
            indexed_doc: IndexedDocument record
            connector: Connector model
            db: Database session

        Returns:
            True if successful
        """
        # Mark as processing
        indexed_doc.indexing_status = "processing"
        await db.commit()

        try:
            # Step 1: Download content
            logger.debug(f"Downloading {indexed_doc.title} ({indexed_doc.size_bytes} bytes)")

            # Create UnifiedDocument from IndexedDocument
            doc = UnifiedDocument(
                document_id=indexed_doc.id,
                connector_id=connector.id,
                connector_type=connector.connector_type,
                external_id=indexed_doc.external_id,
                external_url=indexed_doc.external_url,
                external_path=indexed_doc.external_path,
                filename=indexed_doc.title,  # Use title as filename
                mime_type=indexed_doc.mime_type,
                file_extension=indexed_doc.file_extension,
                size_bytes=indexed_doc.size_bytes,
                title=indexed_doc.title,
                description=indexed_doc.description,
                tenant_id=indexed_doc.tenant_id,
                owner_id=indexed_doc.owner_id,
                is_tenant_public=indexed_doc.is_tenant_public,
            )

            # Download with retry
            content = None
            for attempt in range(self.max_retries):
                try:
                    content = await adapter.download_content(doc)
                    break
                except (TimeoutError, ConnectorConnectionError) as e:
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"Download attempt {attempt + 1} failed, retrying: {e}"
                        )
                        await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))
                    else:
                        raise

            if not content:
                raise ValueError("Failed to download content after retries")

            # Step 2: Send to Weaviate Service for indexing
            logger.debug(f"Sending to Weaviate pipeline ({len(content)} bytes)")

            weaviate_result = await self._send_to_weaviate_pipeline(
                document_id=str(indexed_doc.id),
                file_bytes=content,
                filename=indexed_doc.title,
                mime_type=indexed_doc.mime_type,
                tenant_id=str(indexed_doc.tenant_id),
                owner_id=str(indexed_doc.owner_id),
                metadata={
                    "external_id": indexed_doc.external_id,
                    "external_url": indexed_doc.external_url,
                    "external_path": indexed_doc.external_path,
                    "connector_id": str(connector.id),
                    "connector_type": connector.connector_type,
                    "source_created_at": indexed_doc.source_created_at.isoformat() if indexed_doc.source_created_at else None,
                    "source_modified_at": indexed_doc.source_modified_at.isoformat() if indexed_doc.source_modified_at else None,
                },
                acl={
                    "is_tenant_public": indexed_doc.is_tenant_public,
                    "shared_with_users": indexed_doc.shared_with_users or [],
                    "shared_with_groups": indexed_doc.shared_with_groups or [],
                },
            )

            # Step 3: Update IndexedDocument with results
            if weaviate_result.get("success"):
                indexed_doc.indexing_status = "indexed"
                indexed_doc.weaviate_id = weaviate_result.get("weaviate_id")
                indexed_doc.weaviate_collection = weaviate_result.get("collection")
                indexed_doc.indexed_at = datetime.now(timezone.utc)
                indexed_doc.indexing_error = None

                # Compute content hash
                import hashlib
                indexed_doc.content_hash = hashlib.sha256(content).hexdigest()

                await db.commit()

                logger.info(
                    f"Indexed {indexed_doc.title} → Weaviate ID: {indexed_doc.weaviate_id}"
                )
                return True
            else:
                error_msg = weaviate_result.get("error", "Unknown error")
                indexed_doc.indexing_status = "failed"
                indexed_doc.indexing_error = error_msg[:500]
                await db.commit()

                logger.error(f"Indexing failed for {indexed_doc.title}: {error_msg}")
                return False

        except Exception as e:
            indexed_doc.indexing_status = "failed"
            indexed_doc.indexing_error = str(e)[:500]
            await db.commit()
            raise

    async def _send_to_weaviate_pipeline(
        self,
        document_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: Optional[str],
        tenant_id: str,
        owner_id: str,
        metadata: Dict[str, Any],
        acl: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send document to Weaviate Service for indexing.

        Calls POST /index/from-connector endpoint.

        Args:
            document_id: PostgreSQL document UUID
            file_bytes: Raw file content
            filename: Original filename
            mime_type: MIME type
            tenant_id: Tenant UUID
            owner_id: Owner UUID
            metadata: Additional metadata
            acl: Access control list

        Returns:
            Dict with success status and weaviate_id
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self.weaviate_api_key:
            headers["X-API-Key"] = self.weaviate_api_key

        # Encode file as base64
        file_base64 = base64.b64encode(file_bytes).decode("utf-8")

        payload = {
            "document_id": document_id,
            "file_bytes_base64": file_base64,
            "filename": filename,
            "mime_type": mime_type,
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "metadata": metadata,
            "acl": acl,
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        ) as client:
            try:
                response = await client.post(
                    f"{self.weaviate_service_url}/index/from-connector",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(f"Weaviate pipeline error: {e.response.status_code}")
                return {
                    "success": False,
                    "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                }
            except Exception as e:
                logger.error(f"Weaviate pipeline error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                }

    async def _get_connector(
        self,
        db: AsyncSession,
        connector_id: UUID,
    ) -> Optional[Connector]:
        """Get connector by ID."""
        result = await db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        return result.scalar_one_or_none()

    async def _get_owner_id(
        self,
        db: AsyncSession,
        connector: Connector,
    ) -> Optional[UUID]:
        """Get owner ID for documents (creator or first admin)."""
        if connector.created_by_id:
            return connector.created_by_id

        # Fallback: find any admin user
        result = await db.execute(
            select(User)
            .where(
                and_(
                    User.tenant_id == connector.tenant_id,
                    User.is_active == True,
                )
            )
            .limit(1)
        )
        user = result.scalar_one_or_none()
        return user.id if user else None

    async def _upsert_indexed_document(
        self,
        db: AsyncSession,
        connector: Connector,
        document: UnifiedDocument,
        owner_id: UUID,
    ) -> Dict[str, int]:
        """
        Create or update IndexedDocument record.

        Returns:
            Dict with "new" and "updated" counts
        """
        # Check if exists
        existing = await db.execute(
            select(IndexedDocument).where(
                and_(
                    IndexedDocument.connector_id == connector.id,
                    IndexedDocument.external_id == document.external_id,
                )
            )
        )
        existing_doc = existing.scalar_one_or_none()

        if existing_doc:
            # Update existing
            existing_doc.title = document.title
            existing_doc.description = document.description
            existing_doc.external_path = document.external_path
            existing_doc.external_url = document.external_url
            existing_doc.mime_type = document.mime_type
            existing_doc.file_extension = document.file_extension
            existing_doc.size_bytes = document.size_bytes
            existing_doc.source_modified_at = document.source_modified_at
            existing_doc.updated_at = datetime.now(timezone.utc)
            return {"new": 0, "updated": 1}
        else:
            # Create new
            new_doc = IndexedDocument(
                tenant_id=connector.tenant_id,
                connector_id=connector.id,
                external_id=document.external_id,
                external_url=document.external_url,
                external_path=document.external_path,
                owner_id=owner_id,
                is_tenant_public=document.is_tenant_public,
                title=document.title,
                description=document.description,
                mime_type=document.mime_type,
                file_extension=document.file_extension,
                size_bytes=document.size_bytes,
                source_created_at=document.source_created_at,
                source_modified_at=document.source_modified_at,
                indexing_status="pending",
            )
            db.add(new_doc)
            return {"new": 1, "updated": 0}


# Singleton instance
unified_indexing_service = UnifiedIndexingService()


# Convenience functions
async def sync_connector_documents(
    connector_id: UUID,
    db: AsyncSession,
    full_sync: bool = False,
) -> SyncResult:
    """Sync document metadata from connector."""
    return await unified_indexing_service.sync_documents(
        connector_id=connector_id,
        db=db,
        full_sync=full_sync,
    )


async def index_pending_connector_documents(
    connector_id: UUID,
    db: AsyncSession,
    batch_size: int = 10,
) -> IndexingBatchResult:
    """Index pending documents to Weaviate."""
    return await unified_indexing_service.index_pending_documents(
        connector_id=connector_id,
        db=db,
        batch_size=batch_size,
    )
