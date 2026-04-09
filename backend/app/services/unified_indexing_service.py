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
import os
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

# Data Learning imports for intelligent context enrichment
from app.services.data_learning import (
    FolderStructureAnalyzer,
    MetadataIntelligenceService,
    RelationshipLearner,
    IndexingStrategyOptimizer,
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
            getattr(settings, 'MICROSERVICES_API_KEY', None)
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

        # Phase 3: Index folder hierarchy to knowledge graph (all connector types)
        folder_stats = {"skipped": True}
        try:
            connector = await self._get_connector(db, connector_id)
            if connector:
                adapter = (
                    ConnectorAdapterFactory.get_adapter(connector)
                    if ConnectorAdapterFactory.is_supported(connector.connector_type)
                    else None
                )
                folder_stats = await self._index_folders_to_knowledge_tree(
                    connector=connector,
                    db=db,
                    adapter=adapter,
                )
        except Exception as e:
            logger.warning(f"[{connector_id}] Folder indexing phase failed: {e}")
            folder_stats = {"error": str(e)}

        return {
            "sync": sync_result.to_dict(),
            "index": index_result.to_dict(),
            "folder_indexing": folder_stats,
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
        Index a single document through the Weaviate pipeline with learned context.

        This method integrates the Data Learning System to provide:
        1. Folder context: Semantic meaning of the document's folder path
        2. Property mappings: Normalized metadata with search weights
        3. Indexing strategy: Optimal chunking and embedding configuration
        4. Relationships: Associations to other documents for KG expansion

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

        # Track actual processing time (not queue wait time)
        processing_start_time = time.time()

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
                owner_id=indexed_doc.owner_id,
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

            # Step 2: Get learned context from Data Learning System
            learned_context = await self._get_learned_context(
                db=db,
                connector_id=connector.id,
                indexed_doc=indexed_doc,
                adapter=adapter,
            )

            # Step 3: Get indexing strategy for this document type
            indexing_strategy = await self._get_indexing_strategy(
                db=db,
                connector_id=connector.id,
                document_type=indexed_doc.source_metadata.get("alfresco_node_type") if indexed_doc.source_metadata else None,
                mime_type=indexed_doc.mime_type,
            )

            # Step 4: Send to Weaviate Service for indexing
            logger.debug(f"Sending to Weaviate pipeline ({len(content)} bytes)")

            weaviate_result = await self._send_to_weaviate_pipeline(
                document_id=str(indexed_doc.id),
                file_bytes=content,
                filename=indexed_doc.title,
                mime_type=indexed_doc.mime_type,
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
                learned_context=learned_context,
                indexing_strategy=indexing_strategy,
            )

            # Step 5: Update IndexedDocument with results and learned context
            if weaviate_result.get("success"):
                indexed_doc.indexing_status = "indexed"
                indexed_doc.weaviate_id = weaviate_result.get("weaviate_id")
                indexed_doc.weaviate_collection = weaviate_result.get("collection")
                indexed_doc.indexed_at = datetime.now(timezone.utc)
                indexed_doc.indexing_error = None

                # Track actual processing duration (for accurate time estimates)
                indexed_doc.indexing_duration_seconds = time.time() - processing_start_time

                # Store learned context for future retrieval expansion
                indexed_doc.learned_context = learned_context

                # Compute content hash
                import hashlib
                indexed_doc.content_hash = hashlib.sha256(content).hexdigest()

                await db.commit()

                # Index to structural knowledge graph (non-blocking)
                await self._index_to_knowledge_tree(
                    indexed_doc=indexed_doc,
                    connector=connector,
                    learned_context=learned_context,
                )

                logger.info(
                    f"Indexed {indexed_doc.title} → Weaviate ID: {indexed_doc.weaviate_id}"
                )
                return True
            else:
                error_msg = weaviate_result.get("error", "Unknown error")
                indexed_doc.indexing_status = "failed"
                indexed_doc.indexing_error = error_msg[:500]
                indexed_doc.indexing_duration_seconds = time.time() - processing_start_time
                await db.commit()

                logger.error(f"Indexing failed for {indexed_doc.title}: {error_msg}")
                return False

        except Exception as e:
            indexed_doc.indexing_status = "failed"
            indexed_doc.indexing_error = str(e)[:500]
            indexed_doc.indexing_duration_seconds = time.time() - processing_start_time
            await db.commit()
            raise

    async def _get_learned_context(
        self,
        db: AsyncSession,
        connector_id: UUID,
        indexed_doc: IndexedDocument,
        adapter: ConnectorAdapter,
    ) -> Dict[str, Any]:
        """
        Get learned context for a document from Data Learning services.

        Combines:
        - Folder semantics: department, year, classification from path
        - Property mappings: normalized metadata with search weights
        - Relationships: associations to other documents

        Args:
            db: Database session
            connector_id: Connector UUID
            indexed_doc: IndexedDocument record
            adapter: Connector adapter for fetching associations

        Returns:
            Dict with learned context for Weaviate indexing
        """
        learned_context = {
            "folder_semantics": {},
            "property_weights": {},
            "relationships": [],
            "semantic_type": None,
            "domain": None,
        }

        try:
            # 1. Get folder context from path
            if indexed_doc.external_path:
                folder_analyzer = FolderStructureAnalyzer(db)
                folder_context = await folder_analyzer.get_folder_context(
                    connector_id=connector_id,
                    path=indexed_doc.external_path,
                )
                if folder_context and folder_context.semantics:
                    learned_context["folder_semantics"] = folder_context.semantics
                    learned_context["folder_pattern_id"] = str(folder_context.pattern_id) if folder_context.pattern_id else None
                    learned_context["folder_confidence"] = folder_context.confidence

            # 2. Get normalized metadata with property weights
            if indexed_doc.source_metadata:
                metadata_service = MetadataIntelligenceService(db)
                normalized = await metadata_service.get_normalized_metadata(
                    connector_id=connector_id,
                    raw_metadata=indexed_doc.source_metadata,
                    document_type=indexed_doc.source_metadata.get("alfresco_node_type"),
                )
                learned_context["property_weights"] = normalized.get("weights", {})
                learned_context["normalized_properties"] = normalized.get("properties", {})

            # 3. Get relationships (if adapter supports it and has associations)
            if hasattr(adapter, 'fetch_node_associations'):
                try:
                    associations = await adapter.fetch_node_associations(indexed_doc.external_id)
                    if associations:
                        relationship_learner = RelationshipLearner(db)
                        relationships = await relationship_learner.extract_document_relationships(
                            connector_id=connector_id,
                            document_external_id=indexed_doc.external_id,
                            associations=associations,
                        )
                        learned_context["relationships"] = relationships
                except Exception as e:
                    logger.warning(f"Failed to fetch associations for {indexed_doc.external_id}: {e}")

            # 4. Get semantic type from content model
            if indexed_doc.source_metadata and indexed_doc.source_metadata.get("alfresco_node_type"):
                from app.db.models import ConnectorContentModel
                cm_result = await db.execute(
                    select(ConnectorContentModel).where(ConnectorContentModel.connector_id == connector_id)
                )
                content_model = cm_result.scalar_one_or_none()
                if content_model and content_model.type_semantics:
                    node_type = indexed_doc.source_metadata.get("alfresco_node_type")
                    type_semantics = content_model.type_semantics.get(node_type, {})
                    learned_context["semantic_type"] = type_semantics.get("semantic_type")
                    learned_context["domain"] = type_semantics.get("domain")

        except Exception as e:
            logger.warning(f"Failed to get learned context for {indexed_doc.id}: {e}")

        return learned_context

    async def _get_indexing_strategy(
        self,
        db: AsyncSession,
        connector_id: UUID,
        document_type: Optional[str],
        mime_type: Optional[str],
    ) -> Dict[str, Any]:
        """
        Get the best indexing strategy for a document.

        Args:
            db: Database session
            connector_id: Connector UUID
            document_type: Document type (e.g., gdapm:expediente)
            mime_type: MIME type (e.g., application/pdf)

        Returns:
            Dict with indexing strategy configuration
        """
        strategy_dict = {
            "chunking_type": "semantic",  # Default
            "chunking_config": {"target_chunk_size": 512, "overlap": 50},
            "embedding_fields": ["content", "title"],
            "extract_entities": True,
            "entity_types": ["PERSON", "ORG", "DATE", "MONEY"],
            "extract_to_knowledge_graph": True,
        }

        try:
            optimizer = IndexingStrategyOptimizer(db)
            strategy = await optimizer.get_strategy_for_document(
                connector_id=connector_id,
                document_type=document_type,
                mime_type=mime_type,
            )

            if strategy:
                strategy_dict = {
                    "chunking_type": strategy.chunking_type,
                    "chunking_config": strategy.chunking_config or {},
                    "embedding_fields": strategy.embedding_fields or ["content", "title"],
                    "embedding_weights": strategy.embedding_weights,
                    "extract_entities": strategy.extract_entities,
                    "entity_types": strategy.entity_types,
                    "extract_to_knowledge_graph": strategy.extract_to_knowledge_graph,
                }

        except Exception as e:
            logger.warning(f"Failed to get indexing strategy: {e}")

        return strategy_dict

    async def _send_to_weaviate_pipeline(
        self,
        document_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: Optional[str],
        owner_id: str,
        metadata: Dict[str, Any],
        acl: Dict[str, Any],
        learned_context: Optional[Dict[str, Any]] = None,
        indexing_strategy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send document to Weaviate Service for indexing with learned context.

        Calls POST /index/from-connector endpoint with enriched payload
        including learned context from the Data Learning System.

        Args:
            document_id: PostgreSQL document UUID
            file_bytes: Raw file content
            filename: Original filename
            mime_type: MIME type
            owner_id: Owner UUID
            metadata: Additional metadata
            acl: Access control list
            learned_context: Learned context from Data Learning System
                - folder_semantics: {department, year, classification, ...}
                - property_weights: {field: weight}
                - relationships: [{type, target_id, strength}, ...]
                - semantic_type: Document semantic type
                - domain: Document domain (legal, hr, finance, ...)
            indexing_strategy: Indexing strategy configuration
                - chunking_type: semantic, legal_sections, markdown_headers, ...
                - chunking_config: {target_chunk_size, overlap, ...}
                - embedding_fields: Fields to include in embedding
                - extract_entities: Whether to extract named entities
                - entity_types: Types of entities to extract

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
            "owner_id": owner_id,
            "metadata": metadata,
            "acl": acl,
        }

        # Add learned context if available
        if learned_context:
            payload["learned_context"] = learned_context

        # Add indexing strategy if available
        if indexing_strategy:
            payload["indexing_strategy"] = indexing_strategy

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        ) as client:
            try:
                response = await client.post(
                    f"{self.weaviate_service_url}/weaviate/index/from-connector",
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

    async def _index_to_knowledge_tree(
        self,
        indexed_doc: IndexedDocument,
        connector: Connector,
        learned_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Index document to the structural knowledge graph via Knowledge Tree Service.

        Non-blocking: all errors are caught and logged. Document indexing
        never fails due to graph errors.
        """
        kt_url = os.getenv("KNOWLEDGE_TREE_SERVICE_URL")
        if not kt_url:
            return

        try:
            payload = {
                "document_id": str(indexed_doc.id),
                "file_path": indexed_doc.external_path or indexed_doc.title,
                "connector_metadata": indexed_doc.source_metadata or {},
                "learned_context": learned_context or {},
                "weaviate_document_id": str(indexed_doc.weaviate_id) if indexed_doc.weaviate_id else None,
                "connector_id": str(connector.id),
                "connector_type": connector.connector_type,
            }

            headers = {"Content-Type": "application/json"}
            api_key = getattr(settings, "MICROSERVICES_API_KEY", None)
            if api_key:
                headers["X-API-Key"] = api_key

            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.post(
                    f"{kt_url}/tree/index",
                    headers=headers,
                    json=payload,
                )
                if response.status_code == 200:
                    result = response.json()
                    logger.debug(
                        f"Indexed to knowledge tree: {indexed_doc.title} → "
                        f"{result.get('node_type', 'unknown')}"
                    )
                else:
                    logger.warning(
                        f"Knowledge tree indexing returned {response.status_code} "
                        f"for {indexed_doc.title}: {response.text[:200]}"
                    )
        except Exception as e:
            logger.warning(f"Knowledge tree indexing failed for {indexed_doc.title}: {e}")

    async def _index_folders_to_knowledge_tree(
        self,
        connector: Connector,
        db: AsyncSession,
        adapter: Optional["ConnectorAdapter"] = None,
    ) -> Dict[str, Any]:
        """
        Index folder hierarchy to the structural knowledge graph.

        Two-tier universal strategy:
        - Tier 1 (all connectors): Derive folders from indexed_documents.external_path
        - Tier 2 (Alfresco only): Enrich with connector-specific metadata (aspects, properties)

        Non-blocking: all errors are caught and logged.

        Returns:
            Stats dict with tier1/tier2/success/errors/total counts.
        """
        kt_url = os.getenv("KNOWLEDGE_TREE_SERVICE_URL")
        if not kt_url:
            return {"skipped": True, "reason": "KNOWLEDGE_TREE_SERVICE_URL not set"}

        stats = {"tier1_success": 0, "tier1_errors": 0, "tier2_success": 0, "tier2_errors": 0, "total": 0}

        headers = {"Content-Type": "application/json"}
        api_key = getattr(settings, "MICROSERVICES_API_KEY", None)
        if api_key:
            headers["X-API-Key"] = api_key

        # --- Tier 1: Derive folders from indexed document paths (universal) ---
        try:
            tier1_folders = await self._derive_folders_from_paths(db, connector)
            stats["total"] += len(tier1_folders)

            if tier1_folders:
                logger.info(
                    f"[{connector.id}] Tier 1: Indexing {len(tier1_folders)} folders "
                    f"derived from document paths"
                )

                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    for folder_payload in tier1_folders:
                        try:
                            response = await client.post(
                                f"{kt_url}/tree/index",
                                headers=headers,
                                json=folder_payload,
                            )
                            if response.status_code == 200:
                                stats["tier1_success"] += 1
                            else:
                                stats["tier1_errors"] += 1
                                logger.debug(
                                    f"Tier 1 folder index failed ({response.status_code}): "
                                    f"{folder_payload.get('file_path')}"
                                )
                        except Exception as e:
                            stats["tier1_errors"] += 1
                            logger.debug(f"Tier 1 folder index error: {e}")

        except Exception as e:
            logger.warning(f"[{connector.id}] Tier 1 folder derivation failed: {e}")
            stats["tier1_errors"] += 1

        # --- Tier 2: Alfresco enrichment (connector-specific metadata) ---
        if (
            connector.connector_type == "alfresco"
            and adapter is not None
            and hasattr(adapter, "list_all_folders_recursive")
        ):
            try:
                folders = await adapter.list_all_folders_recursive(max_depth=10)
                stats["total"] += len(folders)
                logger.info(
                    f"[{connector.id}] Tier 2: Enriching with {len(folders)} "
                    f"Alfresco folders (aspects, properties)"
                )

                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    for folder in folders:
                        try:
                            connector_metadata = {
                                "alfresco_node_type": folder.get("nodeType"),
                                "alfresco_aspects": folder.get("aspectNames", []),
                                "alfresco_parent_id": folder.get("parentId"),
                                "alfresco_creator": folder.get("creator"),
                                "alfresco_properties": folder.get("customProperties", {}),
                                "is_folder": True,
                                "folder_name": folder.get("name"),
                            }

                            payload = {
                                "document_id": folder.get("id", ""),
                                "file_path": folder.get("path", ""),
                                "connector_metadata": connector_metadata,
                                "learned_context": {},
                                "connector_id": str(connector.id),
                                "connector_type": connector.connector_type,
                            }

                            response = await client.post(
                                f"{kt_url}/tree/index",
                                headers=headers,
                                json=payload,
                            )
                            if response.status_code == 200:
                                stats["tier2_success"] += 1
                            else:
                                stats["tier2_errors"] += 1
                                logger.debug(
                                    f"Tier 2 folder index failed ({response.status_code}): "
                                    f"{folder.get('name')}"
                                )
                        except Exception as e:
                            stats["tier2_errors"] += 1
                            logger.debug(f"Tier 2 folder index error for {folder.get('name')}: {e}")

            except Exception as e:
                logger.warning(f"[{connector.id}] Tier 2 Alfresco enrichment failed: {e}")
                stats["tier2_errors"] += 1

        total_success = stats["tier1_success"] + stats["tier2_success"]
        total_errors = stats["tier1_errors"] + stats["tier2_errors"]
        logger.info(
            f"[{connector.id}] Folder indexing complete: "
            f"{total_success}/{stats['total']} success, {total_errors} errors "
            f"(tier1={stats['tier1_success']}, tier2={stats['tier2_success']})"
        )
        return stats

    async def _derive_folders_from_paths(
        self,
        db: AsyncSession,
        connector: Connector,
    ) -> List[Dict[str, Any]]:
        """
        Derive folder hierarchy from indexed document paths (Tier 1 — universal).

        Queries DISTINCT external_path from indexed_documents, extracts all
        intermediate folder segments, deduplicates, and returns payloads
        sorted by depth (shallowest first → parents created before children).

        Returns:
            List of folder payload dicts ready for POST /tree/index.
        """
        # Get distinct paths for this connector
        result = await db.execute(
            select(IndexedDocument.external_path)
            .where(
                and_(
                    IndexedDocument.connector_id == connector.id,
                    IndexedDocument.indexing_status == "indexed",
                    IndexedDocument.external_path.isnot(None),
                    IndexedDocument.external_path != "",
                )
            )
            .distinct()
        )
        paths = [row[0] for row in result.fetchall()]

        if not paths:
            return []

        # Extract all intermediate folders from document paths
        folder_paths: set = set()
        for path in paths:
            normalized = path.replace("\\", "/")
            parts = [p for p in normalized.split("/") if p]
            # Remove filename (last segment) — keep only folder segments
            folder_parts = parts[:-1]
            # Add all intermediate paths: /a, /a/b, /a/b/c
            for i in range(1, len(folder_parts) + 1):
                folder_path = "/" + "/".join(folder_parts[:i])
                folder_paths.add(folder_path)

        if not folder_paths:
            return []

        # Sort by depth (shallowest first) to create parents before children
        sorted_folders = sorted(folder_paths, key=lambda p: p.count("/"))

        # Build payloads
        payloads = []
        for folder_path in sorted_folders:
            folder_name = folder_path.rsplit("/", 1)[-1]
            payloads.append({
                "document_id": f"folder:{folder_path}",
                "file_path": folder_path,
                "connector_metadata": {
                    "is_folder": True,
                    "folder_name": folder_name,
                },
                "learned_context": {},
                "connector_id": str(connector.id),
                "connector_type": connector.connector_type,
            })

        return payloads

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
            .where(User.is_active == True)
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
            # Update source_metadata with connector-specific metadata (Alfresco properties, etc.)
            if document.custom_metadata:
                existing_doc.source_metadata = document.custom_metadata
            return {"new": 0, "updated": 1}
        else:
            # Create new
            new_doc = IndexedDocument(
                connector_id=connector.id,
                connector_type=document.connector_type.value if document.connector_type else None,
                external_id=document.external_id,
                external_url=document.external_url,
                external_path=document.external_path,
                owner_id=owner_id,
                title=document.title,
                description=document.description,
                mime_type=document.mime_type,
                file_extension=document.file_extension,
                size_bytes=document.size_bytes,
                # Store ALL connector-specific metadata (Alfresco properties, aspects, etc.)
                source_metadata=document.custom_metadata if document.custom_metadata else None,
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
