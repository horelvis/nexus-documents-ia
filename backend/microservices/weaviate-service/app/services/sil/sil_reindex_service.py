"""
SIL Reindex Service

Handles re-indexing of documents to the Structural Intelligence Layer.
This service coordinates:
- Clearing existing SIL data (for full reindex)
- Indexing documents to Weaviate StructuralDocument collection
- Indexing documents to Apache AGE structural graph

Usage from API:
    from app.services.sil import sil_reindex_service

    result = await sil_reindex_service.reindex_documents(
        tenant_id="tenant-123",
        full_reindex=True,
    )
"""

import logging
import httpx
import os
from typing import Optional, Dict, Any, List
from datetime import datetime

from .structural_extractor import structural_extractor
from .structural_collection import structural_collection
from .structural_graph import structural_graph

logger = logging.getLogger(__name__)


def get_main_backend_url() -> str:
    """Get the main backend API URL."""
    return os.getenv("MAIN_BACKEND_URL", "http://localhost:8000")


def get_api_key() -> str:
    """Get microservices API key."""
    return os.getenv("MICROSERVICES_API_KEY", "")


class SILReindexService:
    """
    Service for re-indexing documents to SIL.

    Coordinates the reindex process between Weaviate and Apache AGE.
    """

    def __init__(self):
        self._extractor = structural_extractor
        self._collection = structural_collection
        self._graph = structural_graph

    async def reindex_documents(
        self,
        tenant_id: str,
        full_reindex: bool = False,
        limit: Optional[int] = None,
        connector_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Re-index documents to the structural graph.

        This method:
        1. Optionally clears existing data (full_reindex=True)
        2. Fetches documents from the main backend
        3. Processes each document through SIL indexing

        Args:
            tenant_id: Tenant identifier
            full_reindex: If True, clear existing data first
            limit: Maximum documents to process
            connector_id: Optional filter by connector

        Returns:
            Dictionary with reindex statistics
        """
        logger.info(f"Starting SIL reindex for tenant {tenant_id} (full={full_reindex})")

        result = {
            "success": False,
            "total_documents": 0,
            "documents_processed": 0,
            "documents_skipped": 0,
            "errors": 0,
            "message": "",
        }

        try:
            # Step 1: Clear existing data if full reindex
            if full_reindex:
                logger.info("Clearing existing SIL data...")
                await self._collection.clear_collection(tenant_id=tenant_id)
                await self._graph.clear_graph(tenant_id=tenant_id)

            # Step 2: Get already indexed documents (for incremental mode)
            already_indexed = set()
            if not full_reindex:
                already_indexed = set(await self._graph.get_document_ids(tenant_id=tenant_id))
                logger.info(f"Found {len(already_indexed)} documents already indexed")

            # Step 3: Fetch documents from main backend
            documents = await self._fetch_documents_from_backend(
                tenant_id=tenant_id,
                limit=limit,
                connector_id=connector_id,
            )

            if documents is None:
                result["message"] = "Could not fetch documents from main backend"
                return result

            result["total_documents"] = len(documents)

            # Step 4: Filter to only new documents (if incremental)
            if not full_reindex:
                documents = [
                    doc for doc in documents
                    if str(doc.get("id")) not in already_indexed
                ]
                result["documents_skipped"] = result["total_documents"] - len(documents)

            if not documents:
                result["success"] = True
                result["message"] = "No new documents to index"
                return result

            # Step 5: Process each document
            for doc in documents:
                success = await self._index_document(doc, tenant_id)
                if success:
                    result["documents_processed"] += 1
                else:
                    result["errors"] += 1

            result["success"] = True
            result["message"] = f"Reindex completed: {result['documents_processed']} processed, {result['errors']} errors"

            logger.info(result["message"])
            return result

        except Exception as e:
            logger.error(f"Reindex failed: {e}")
            result["message"] = str(e)
            return result

    async def _fetch_documents_from_backend(
        self,
        tenant_id: str,
        limit: Optional[int] = None,
        connector_id: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch indexed documents from the main backend.

        Calls the main backend API to get documents that need indexing.
        """
        backend_url = get_main_backend_url()
        api_key = get_api_key()

        try:
            async with httpx.AsyncClient() as client:
                params = {
                    "tenant_id": tenant_id,
                    "status": "indexed",
                }
                if limit:
                    params["limit"] = limit
                if connector_id:
                    params["connector_id"] = connector_id

                # Try to call the internal backend API for indexed documents
                # Internal API uses X-API-Key header for authentication
                response = await client.get(
                    f"{backend_url}/api/v1/internal/connectors/indexed-documents",
                    params=params,
                    headers={"X-API-Key": api_key} if api_key else {},
                    timeout=60.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Fetched {data.get('total', 0)} documents from backend")
                    return data.get("documents", data) if isinstance(data, dict) else data
                elif response.status_code == 404:
                    # Endpoint might not exist yet
                    logger.warning(
                        "Backend endpoint /api/v1/internal/connectors/indexed-documents not found. "
                        "Use the CLI script instead: python scripts/index_structural_metadata.py"
                    )
                    return None
                elif response.status_code == 401:
                    logger.error("Authentication failed. Check MICROSERVICES_API_KEY configuration.")
                    return None
                else:
                    logger.error(f"Backend returned {response.status_code}: {response.text[:200]}")
                    return None

        except httpx.ConnectError:
            logger.error(f"Could not connect to main backend at {backend_url}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch documents from backend: {e}")
            return None

    async def _index_document(
        self,
        document: Dict[str, Any],
        tenant_id: str,
    ) -> bool:
        """
        Index a single document to SIL.

        Args:
            document: Document data from the database
            tenant_id: Tenant identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            document_id = str(document.get("id"))
            external_path = document.get("external_path", "")
            doc_title = document.get("title", "")
            file_extension = document.get("file_extension", "")

            # Extract filename from external_path (includes extension)
            filename = ""
            if external_path:
                filename = external_path.rstrip('/').split('/')[-1]

            # Build enriched connector_metadata with document fields
            # The extractor's _extract_key_properties() looks for these
            connector_metadata = {
                **(document.get("source_metadata") or {}),
                "title": doc_title or filename,  # Prefer title, fallback to filename
                "filename": filename,  # Original filename with extension
                "file_extension": file_extension,
                "mime_type": document.get("mime_type", ""),
            }

            # Extract structural metadata
            metadata = await self._extractor.extract_structural_metadata(
                document_id=document_id,
                file_path=external_path or doc_title,
                connector_metadata=connector_metadata,
                learned_context=document.get("learned_context", {}),
            )

            # Index to Weaviate
            weaviate_id = await self._collection.index_structural_metadata(
                metadata=metadata,
                document_id=document_id,
                weaviate_document_id=str(document.get("weaviate_id")) if document.get("weaviate_id") else None,
                tenant_id=tenant_id,
                connector_id=str(document.get("connector_id")) if document.get("connector_id") else None,
            )

            # Index to graph
            graph_success = await self._graph.add_structural_document(
                document_id=document_id,
                tenant_id=tenant_id,
                metadata=metadata,
                weaviate_document_id=str(document.get("weaviate_id")) if document.get("weaviate_id") else None,
                connector_id=str(document.get("connector_id")) if document.get("connector_id") else None,
            )

            if weaviate_id or graph_success:
                logger.debug(f"Indexed document {document_id} to SIL")
                return True
            else:
                logger.warning(f"Failed to index document {document_id} to both Weaviate and graph")
                return False

        except Exception as e:
            logger.error(f"Failed to index document: {e}")
            return False

    async def reindex_single_document(
        self,
        document_id: str,
        tenant_id: str,
        file_path: Optional[str] = None,
        connector_metadata: Optional[Dict[str, Any]] = None,
        learned_context: Optional[Dict[str, Any]] = None,
        weaviate_document_id: Optional[str] = None,
        connector_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reindex a single document to SIL.

        This is called when a document is updated and needs its structural
        metadata refreshed.

        Args:
            document_id: Document UUID
            tenant_id: Tenant identifier
            file_path: File path for structure inference
            connector_metadata: Metadata from connector
            learned_context: Context from learning system
            weaviate_document_id: Weaviate document collection UUID
            connector_id: Connector ID

        Returns:
            Dictionary with indexing result
        """
        try:
            # Extract structural metadata
            metadata = await self._extractor.extract_structural_metadata(
                document_id=document_id,
                file_path=file_path or "",
                connector_metadata=connector_metadata or {},
                learned_context=learned_context or {},
            )

            # Index to Weaviate (will update if exists)
            weaviate_id = await self._collection.index_structural_metadata(
                metadata=metadata,
                document_id=document_id,
                weaviate_document_id=weaviate_document_id,
                tenant_id=tenant_id,
                connector_id=connector_id,
            )

            # Index to graph
            graph_success = await self._graph.add_structural_document(
                document_id=document_id,
                tenant_id=tenant_id,
                metadata=metadata,
                weaviate_document_id=weaviate_document_id,
                connector_id=connector_id,
            )

            # Get enum values safely
            semantic_type_str = (
                metadata.semantic_type.value
                if hasattr(metadata.semantic_type, 'value')
                else metadata.semantic_type
            ) if metadata.semantic_type else None
            domain_str = (
                metadata.domain.value
                if hasattr(metadata.domain, 'value')
                else metadata.domain
            ) if metadata.domain else None

            return {
                "success": True,
                "document_id": document_id,
                "semantic_type": semantic_type_str,
                "domain": domain_str,
                "indexed_to_weaviate": weaviate_id is not None,
                "indexed_to_graph": graph_success,
                "weaviate_id": weaviate_id,
            }

        except Exception as e:
            logger.error(f"Failed to reindex document {document_id}: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e),
            }


# Global singleton instance
sil_reindex_service = SILReindexService()
