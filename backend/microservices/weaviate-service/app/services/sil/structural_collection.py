"""
Structural Document Collection for Weaviate

Manages the StructuralDocument collection which stores ONLY structural metadata
about documents (not content). This enables:
- Semantic search over document structure
- Fast structural queries without reading content
- Integration with Apache AGE for graph-based reasoning

Key Properties:
- document_id: Link to original document
- semantic_type: contract, invoice, report, etc.
- domain: legal, hr, finance, etc.
- folder_path: Full path in hierarchy
- structural_description: Text description for embedding
- importance: Calculated importance score
- temporal fields: valid_from, valid_to, created_at, modified_at
"""

import logging
import weaviate
import weaviate.classes.config as wvc
from typing import Optional, List, Dict, Any
from datetime import datetime

from .schemas import StructuralMetadata, SemanticType, DomainType
from .structural_embedder import structural_embedder

logger = logging.getLogger(__name__)


# Collection name constant
STRUCTURAL_DOCUMENTS_COLLECTION = "StructuralDocument"


class StructuralCollectionService:
    """
    Manages the StructuralDocument collection in Weaviate.

    This collection stores ONLY structural metadata (not content),
    enabling fast structural queries and semantic search over
    document hierarchy and relationships.
    """

    def __init__(self, weaviate_client: Optional[weaviate.WeaviateClient] = None):
        self._client = weaviate_client
        self._collection = None
        self._initialized = False

    def set_client(self, client: weaviate.WeaviateClient) -> None:
        """Set the Weaviate client (called by WeaviateService)."""
        self._client = client
        self._initialized = False
        self._collection = None

    async def initialize(self) -> None:
        """Initialize the collection, creating if necessary."""
        if self._initialized and self._collection:
            return

        if not self._client:
            raise ValueError("Weaviate client not set. Call set_client() first.")

        try:
            # Check if collection exists
            if self._client.collections.exists(STRUCTURAL_DOCUMENTS_COLLECTION):
                self._collection = self._client.collections.get(STRUCTURAL_DOCUMENTS_COLLECTION)
                logger.info(f"✅ StructuralDocument collection exists")
            else:
                # Create the collection
                await self._create_collection()

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize StructuralDocument collection: {e}")
            raise

    async def _create_collection(self) -> None:
        """Create the StructuralDocument collection with full schema."""
        logger.info("📦 Creating StructuralDocument collection...")

        self._collection = self._client.collections.create(
            name=STRUCTURAL_DOCUMENTS_COLLECTION,
            description="Structural metadata for documents (no content)",

            # Properties
            properties=[
                # ========== Core identifiers ==========
                wvc.Property(
                    name="document_id",
                    data_type=wvc.DataType.TEXT,
                    description="Original document UUID (link to Document table)",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="weaviate_document_id",
                    data_type=wvc.DataType.TEXT,
                    description="Weaviate document collection UUID (link to chunks)",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="tenant_id",
                    data_type=wvc.DataType.TEXT,
                    description="Tenant identifier for multi-tenancy",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="connector_id",
                    data_type=wvc.DataType.TEXT,
                    description="Connector that indexed this document",
                    skip_vectorization=True,
                ),

                # ========== Structural classification ==========
                wvc.Property(
                    name="semantic_type",
                    data_type=wvc.DataType.TEXT,
                    description="Semantic type: contract, invoice, report, etc.",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="domain",
                    data_type=wvc.DataType.TEXT,
                    description="Business domain: legal, hr, finance, etc.",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="importance",
                    data_type=wvc.DataType.NUMBER,
                    description="Calculated importance score (0.0-1.0)",
                    skip_vectorization=True,
                ),

                # ========== Hierarchy and location ==========
                wvc.Property(
                    name="folder_path",
                    data_type=wvc.DataType.TEXT,
                    description="Full path in folder hierarchy",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="folder_hierarchy",
                    data_type=wvc.DataType.TEXT_ARRAY,
                    description="Array of folder names from root to document",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="site_name",
                    data_type=wvc.DataType.TEXT,
                    description="SharePoint site or connector source name",
                    skip_vectorization=True,
                ),

                # ========== Structural description (for embedding) ==========
                wvc.Property(
                    name="structural_description",
                    data_type=wvc.DataType.TEXT,
                    description="Human-readable structural description for embedding",
                    # This property IS vectorized
                ),

                # ========== Extracted key properties ==========
                wvc.Property(
                    name="prop_title",
                    data_type=wvc.DataType.TEXT,
                    description="Document title",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="prop_client",
                    data_type=wvc.DataType.TEXT,
                    description="Client/customer name if detected",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="prop_year",
                    data_type=wvc.DataType.TEXT,
                    description="Year associated with document",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="prop_author",
                    data_type=wvc.DataType.TEXT,
                    description="Document author if available",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="prop_version",
                    data_type=wvc.DataType.TEXT,
                    description="Document version if available",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="prop_status",
                    data_type=wvc.DataType.TEXT,
                    description="Document status (draft, approved, etc.)",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="prop_expiry_date",
                    data_type=wvc.DataType.DATE,
                    description="Expiry date for contracts, etc.",
                ),

                # ========== Folder semantics (learned) ==========
                wvc.Property(
                    name="folder_department",
                    data_type=wvc.DataType.TEXT,
                    description="Department inferred from folder",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="folder_purpose",
                    data_type=wvc.DataType.TEXT,
                    description="Purpose of folder (e.g., 'client contracts')",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="folder_confidentiality",
                    data_type=wvc.DataType.TEXT,
                    description="Confidentiality level from folder context",
                    skip_vectorization=True,
                ),

                # ========== Temporal properties ==========
                wvc.Property(
                    name="valid_from",
                    data_type=wvc.DataType.DATE,
                    description="When document became valid in structure",
                ),
                wvc.Property(
                    name="valid_to",
                    data_type=wvc.DataType.DATE,
                    description="When document was removed (null=current)",
                ),
                wvc.Property(
                    name="created_at",
                    data_type=wvc.DataType.DATE,
                    description="When document was added to system",
                ),
                wvc.Property(
                    name="modified_at",
                    data_type=wvc.DataType.DATE,
                    description="When structural metadata was last updated",
                ),
                wvc.Property(
                    name="source_modified_at",
                    data_type=wvc.DataType.DATE,
                    description="Last modification date from source system",
                ),

                # ========== Relationship hints ==========
                wvc.Property(
                    name="related_document_ids",
                    data_type=wvc.DataType.TEXT_ARRAY,
                    description="IDs of structurally related documents",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="version_of_id",
                    data_type=wvc.DataType.TEXT,
                    description="ID of document this is a version of",
                    skip_vectorization=True,
                ),
                wvc.Property(
                    name="version_number",
                    data_type=wvc.DataType.INT,
                    description="Version number if part of version chain",
                ),
            ],

            # No automatic vectorizer - we provide embeddings
            vectorizer_config=wvc.Configure.Vectorizer.none(),

            # Vector index configuration
            vector_index_config=wvc.Configure.VectorIndex.hnsw(
                distance_metric=wvc.VectorDistances.COSINE,
                ef_construction=128,
                max_connections=64,
            ),
        )

        logger.info("✅ StructuralDocument collection created successfully")

    async def index_structural_metadata(
        self,
        metadata: StructuralMetadata,
        document_id: str,
        weaviate_document_id: Optional[str] = None,
        tenant_id: str = "",
        connector_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Index structural metadata for a document.

        Args:
            metadata: Extracted structural metadata
            document_id: Original document UUID
            weaviate_document_id: UUID in document chunks collection
            tenant_id: Tenant identifier
            connector_id: Connector that indexed this

        Returns:
            UUID of the created Weaviate object, or None on failure
        """
        await self.initialize()

        try:
            # Generate embedding for structural description
            embedding = await structural_embedder.embed_structural_description(metadata)

            if not embedding:
                logger.warning(f"Could not generate embedding for document {document_id}")
                # Continue without embedding - BM25 will still work

            # Prepare properties
            now = datetime.utcnow()

            properties = {
                "document_id": document_id,
                "weaviate_document_id": weaviate_document_id or "",
                "tenant_id": tenant_id,
                "connector_id": connector_id or "",

                "semantic_type": metadata.semantic_type.value if metadata.semantic_type else "",
                "domain": metadata.domain.value if metadata.domain else "",
                "importance": metadata.importance,

                "folder_path": metadata.folder_path or "",
                "folder_hierarchy": metadata.folder_hierarchy or [],
                "site_name": metadata.site_name or "",

                "structural_description": metadata.structural_description or "",

                # Key properties
                "prop_title": metadata.key_properties.get("title", ""),
                "prop_client": metadata.key_properties.get("client", ""),
                "prop_year": metadata.key_properties.get("year", ""),
                "prop_author": metadata.key_properties.get("author", ""),
                "prop_version": metadata.key_properties.get("version", ""),
                "prop_status": metadata.key_properties.get("status", ""),

                # Folder semantics
                "folder_department": metadata.folder_semantics.get("department", ""),
                "folder_purpose": metadata.folder_semantics.get("purpose", ""),
                "folder_confidentiality": metadata.folder_semantics.get("confidentiality", ""),

                # Temporal
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
                "modified_at": now,

                # Relationships
                "related_document_ids": [r.get("target_id", "") for r in metadata.relationships if r.get("target_id")],
                "version_of_id": metadata.key_properties.get("version_of", ""),
            }

            # Handle expiry date if present
            expiry = metadata.key_properties.get("expiry_date")
            if expiry:
                try:
                    if isinstance(expiry, str):
                        properties["prop_expiry_date"] = datetime.fromisoformat(expiry)
                    elif isinstance(expiry, datetime):
                        properties["prop_expiry_date"] = expiry
                except (ValueError, TypeError):
                    pass

            # Handle source modified date
            source_modified = metadata.key_properties.get("modified_time")
            if source_modified:
                try:
                    if isinstance(source_modified, str):
                        properties["source_modified_at"] = datetime.fromisoformat(source_modified.replace("Z", "+00:00"))
                    elif isinstance(source_modified, datetime):
                        properties["source_modified_at"] = source_modified
                except (ValueError, TypeError):
                    pass

            # Insert into collection
            if embedding:
                result = self._collection.data.insert(
                    properties=properties,
                    vector=embedding,
                )
            else:
                result = self._collection.data.insert(
                    properties=properties,
                )

            logger.info(f"✅ Indexed structural metadata for document {document_id}")
            return str(result)

        except Exception as e:
            logger.error(f"Failed to index structural metadata for {document_id}: {e}")
            return None

    async def search_structural(
        self,
        query: str,
        tenant_id: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search structural documents by semantic similarity.

        Args:
            query: Natural language query about structure
            tenant_id: Tenant identifier
            limit: Maximum results to return
            filters: Additional property filters

        Returns:
            List of matching structural documents with scores
        """
        await self.initialize()

        try:
            # Generate query embedding
            query_embedding = await structural_embedder.embed_query_for_structural_search(query)

            if not query_embedding:
                logger.warning("Could not generate query embedding, falling back to BM25")
                return await self._bm25_search(query, tenant_id, limit, filters)

            # Build filter
            Filter = weaviate.classes.query.Filter
            combined_filter = Filter.by_property("tenant_id").equal(tenant_id)

            if filters:
                for key, value in filters.items():
                    if value is not None:
                        if isinstance(value, list):
                            for v in value:
                                combined_filter = combined_filter & Filter.by_property(key).equal(v)
                        else:
                            combined_filter = combined_filter & Filter.by_property(key).equal(value)

            # Vector search
            results = self._collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                filters=combined_filter,
                return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
            )

            # Format results
            formatted = []
            for obj in results.objects:
                formatted.append({
                    "id": str(obj.uuid),
                    "properties": obj.properties,
                    "score": 1.0 - (obj.metadata.distance or 0.0),  # Convert distance to score
                })

            return formatted

        except Exception as e:
            logger.error(f"Structural search failed: {e}")
            return []

    async def _bm25_search(
        self,
        query: str,
        tenant_id: str,
        limit: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Fallback BM25 search when embeddings unavailable."""
        try:
            Filter = weaviate.classes.query.Filter
            combined_filter = Filter.by_property("tenant_id").equal(tenant_id)

            if filters:
                for key, value in filters.items():
                    if value is not None:
                        combined_filter = combined_filter & Filter.by_property(key).equal(value)

            results = self._collection.query.bm25(
                query=query,
                limit=limit,
                filters=combined_filter,
                return_metadata=weaviate.classes.query.MetadataQuery(score=True),
            )

            formatted = []
            for obj in results.objects:
                formatted.append({
                    "id": str(obj.uuid),
                    "properties": obj.properties,
                    "score": obj.metadata.score or 0.0,
                })

            return formatted

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    async def get_by_document_id(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get structural metadata by original document ID."""
        await self.initialize()

        try:
            Filter = weaviate.classes.query.Filter
            results = self._collection.query.fetch_objects(
                filters=(
                    Filter.by_property("document_id").equal(document_id) &
                    Filter.by_property("tenant_id").equal(tenant_id)
                ),
                limit=1,
            )

            if results.objects:
                obj = results.objects[0]
                return {
                    "id": str(obj.uuid),
                    "properties": obj.properties,
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get structural metadata for {document_id}: {e}")
            return None

    async def update_structural_metadata(
        self,
        document_id: str,
        tenant_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Update structural metadata for a document.

        Args:
            document_id: Original document UUID
            tenant_id: Tenant identifier
            updates: Dictionary of properties to update

        Returns:
            True if successful, False otherwise
        """
        await self.initialize()

        try:
            # Find existing object
            existing = await self.get_by_document_id(document_id, tenant_id)
            if not existing:
                logger.warning(f"No structural metadata found for document {document_id}")
                return False

            # Update modified_at
            updates["modified_at"] = datetime.utcnow()

            # If structural_description is updated, regenerate embedding
            if "structural_description" in updates:
                from .schemas import StructuralMetadata
                temp_metadata = StructuralMetadata(
                    structural_description=updates["structural_description"]
                )
                new_embedding = await structural_embedder.embed_structural_description(temp_metadata)

                if new_embedding:
                    self._collection.data.update(
                        uuid=existing["id"],
                        properties=updates,
                        vector=new_embedding,
                    )
                else:
                    self._collection.data.update(
                        uuid=existing["id"],
                        properties=updates,
                    )
            else:
                self._collection.data.update(
                    uuid=existing["id"],
                    properties=updates,
                )

            logger.info(f"✅ Updated structural metadata for document {document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update structural metadata for {document_id}: {e}")
            return False

    async def mark_document_removed(
        self,
        document_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Mark a document as removed (set valid_to timestamp).

        This preserves the structural metadata for temporal queries
        while indicating the document is no longer current.
        """
        return await self.update_structural_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            updates={"valid_to": datetime.utcnow()},
        )

    async def get_collection_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics about the structural collection."""
        await self.initialize()

        try:
            # Get aggregate stats
            if tenant_id:
                Filter = weaviate.classes.query.Filter
                result = self._collection.aggregate.over_all(
                    filters=Filter.by_property("tenant_id").equal(tenant_id),
                    total_count=True,
                )
            else:
                result = self._collection.aggregate.over_all(
                    total_count=True,
                )

            return {
                "collection_name": STRUCTURAL_DOCUMENTS_COLLECTION,
                "total_documents": result.total_count,
                "tenant_id": tenant_id,
            }

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {
                "collection_name": STRUCTURAL_DOCUMENTS_COLLECTION,
                "error": str(e),
            }


# Global singleton instance
structural_collection = StructuralCollectionService()
