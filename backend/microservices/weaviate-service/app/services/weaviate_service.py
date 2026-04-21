"""Weaviate service implementation — embeddings via intelligence-docs-service.

Single-org refactor: collections are fixed (Nouxcube_documents,
Nouxcube_knowledge, Nouxcube_visual, TrustGraphEntities, OntologyTerms,
PublicKnowledge). ACL is enforced by the ``roles`` TEXT_ARRAY property +
the ``EVERYONE`` sentinel.
"""
import weaviate
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import uuid

from app.core.config import settings
from app.core.auth_headers import allowed_roles, EVERYONE_ROLE
from app.schemas.weaviate import (
    DocumentCreate, DocumentResponse, SearchRequest, SearchResponse,
    CollectionInfo, VectorQuery
)
from weaviate.exceptions import UnexpectedStatusCodeException
from app.clients import intelligence_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixed collection names (single-org deployment)
#
# Naming convention: "Nouxcube_<lowercase>" with underscore, matching the
# pre-existing reference in app/services/nexus_router/data_collector.py:175
# and the backend/app/core/security.py constants introduced in Plan 2.
# ---------------------------------------------------------------------------
DOCUMENTS_COLLECTION = "Nouxcube_documents"
KNOWLEDGE_COLLECTION = "Nouxcube_knowledge"
VISUAL_COLLECTION = "Nouxcube_visual"


# ---------------------------------------------------------------------------
# Embedding with short-lived TTL cache (deduplicates parallel queries)
# ---------------------------------------------------------------------------
_EMBED_CACHE_TTL = 5.0  # seconds
_embed_cache: Dict[Tuple[str, str], Tuple[float, list[float]]] = {}
_EMBED_CACHE_MAX = 64


def _prune_embed_cache() -> None:
    if len(_embed_cache) <= _EMBED_CACHE_MAX:
        return
    now = time.monotonic()
    expired = [k for k, (ts, _) in _embed_cache.items() if now - ts > _EMBED_CACHE_TTL]
    for k in expired:
        del _embed_cache[k]


async def generate_embedding(text: str, task: str = "") -> list[float] | None:
    """Generate embedding via intelligence-docs-service (with TTL dedup cache)."""
    key = (text, task)
    cached = _embed_cache.get(key)
    if cached is not None:
        ts, vec = cached
        if time.monotonic() - ts < _EMBED_CACHE_TTL:
            return vec
        del _embed_cache[key]

    result = await intelligence_client.embed(text, task=task)
    if result is not None:
        _prune_embed_cache()
        _embed_cache[key] = (time.monotonic(), result)
    return result


async def generate_embedding_batch(texts: list[str], task: str = "") -> list[list[float]] | None:
    """Generate embeddings for multiple texts via intelligence-docs-service."""
    return await intelligence_client.embed_batch(texts, task=task)


def _roles_filter(user_roles: List[str]):
    """Build the single-clause roles ACL filter.

    ``allowed_roles()`` folds in the EVERYONE wildcard so one
    ``contains_any`` call covers both private and public documents.
    """
    return weaviate.classes.query.Filter.by_property("roles").contains_any(
        allowed_roles(user_roles or [])
    )


class WeaviateService:
    """Service for Weaviate operations (single-org)."""

    def __init__(self):
        self.client = None
        self.embedding_model = None
        self._embedding_checked = False
        self._initialized = False

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------

    def _build_property_filter(self, key: str, value: Any):
        """Create filter for property supporting list/dict inputs."""
        if value is None:
            return None

        if isinstance(value, dict):
            operator = value.get("operator") or value.get("op")
            values = value.get("values")
            single_value = value.get("value")

            if operator in {"in", "contains_any"} or isinstance(values, (list, tuple, set)):
                candidate_values_raw = values or single_value or []
                if isinstance(candidate_values_raw, (list, tuple, set)):
                    candidate_values = list(candidate_values_raw)
                elif candidate_values_raw:
                    candidate_values = [candidate_values_raw]
                else:
                    candidate_values = []
                return self._build_property_filter(key, candidate_values)

            if single_value is not None:
                value = single_value
            else:
                return None

        if isinstance(value, (list, tuple, set)):
            items = [item for item in value if item is not None]
            if not items:
                return None

            combined = None
            for item in items:
                condition = weaviate.classes.query.Filter.by_property(key).equal(item)
                combined = condition if combined is None else combined | condition
            return combined

        return weaviate.classes.query.Filter.by_property(key).equal(value)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        """Initialize Weaviate client."""
        if self._initialized and self.client:
            return
        try:
            url_without_protocol = settings.weaviate_url.replace("http://", "").replace("https://", "")
            if ":" in url_without_protocol:
                host = url_without_protocol.split(":")[0]
                port = int(url_without_protocol.split(":")[1])
            else:
                host = url_without_protocol
                port = 8080

            self.client = weaviate.connect_to_local(host=host, port=port)

            if self.client.is_ready():
                logger.info(f"✅ Connected to Weaviate at {settings.weaviate_url}")
            else:
                raise Exception("Weaviate not ready")

            await self._check_embedding_service()
            self._initialized = True

        except Exception as e:
            logger.error(f"❌ Failed to initialize Weaviate: {e}")
            self._initialized = False
            raise

    async def _check_embedding_service(self) -> bool:
        if self._embedding_checked:
            return True
        try:
            test_embedding = await generate_embedding("test connection")
            if test_embedding:
                self.embedding_model = "intelligence-docs-service"
                self._embedding_checked = True
                dims = len(test_embedding)
                logger.info(f"✅ Using intelligence-docs-service embeddings ({dims} dims)")
                return True
            else:
                logger.warning("⚠️ intelligence-docs-service returned empty embedding")
                return False
        except Exception as e:
            logger.warning(f"⚠️ intelligence-docs-service not available: {e}")
            return False

    async def cleanup(self):
        if self.client:
            self.client = None
            logger.info("✅ Weaviate client cleaned up")
        self._initialized = False

    # ------------------------------------------------------------------
    # Collections — schema creation
    # ------------------------------------------------------------------

    async def create_collection(
        self,
        collection_name: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new Weaviate documents collection.

        The schema uses the single ``roles`` TEXT_ARRAY property for ACL:
        documents tagged with any role the caller holds (or the
        ``EVERYONE`` sentinel) are visible.
        """
        try:
            description = (schema or {}).get(
                "description", f"Collection for documents: {collection_name}"
            )

            self.client.collections.create(
                name=collection_name,
                description=description,
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(
                        name="title",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document title",
                    ),
                    weaviate.classes.config.Property(
                        name="content",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document content",
                    ),
                    weaviate.classes.config.Property(
                        name="document_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="PostgreSQL document ID",
                    ),
                    weaviate.classes.config.Property(
                        name="roles",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="KeyCloak roles allowed to view (plus EVERYONE sentinel)",
                        index_filterable=True,
                    ),
                    weaviate.classes.config.Property(
                        name="document_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Type of document",
                    ),
                    weaviate.classes.config.Property(
                        name="tags",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Document tags",
                    ),
                    weaviate.classes.config.Property(
                        name="created_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Creation timestamp",
                    ),
                    weaviate.classes.config.Property(
                        name="updated_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Last update timestamp",
                    ),
                    # Position properties for PDF annotation
                    weaviate.classes.config.Property(name="page_start", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="page_end", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="char_start", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="char_end", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="chunk_index", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="bbox_start_x0", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_start_y0", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_start_x1", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_start_y1", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_end_x0", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_end_y0", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_end_x1", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_end_y1", data_type=weaviate.classes.config.DataType.NUMBER),
                    # Channel / connector metadata (no ACL role — ACL is via ``roles``)
                    weaviate.classes.config.Property(name="channel_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="owner_user_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="source_type", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="external_id", data_type=weaviate.classes.config.DataType.TEXT),
                    # Folder hierarchy
                    weaviate.classes.config.Property(name="folder_path", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(
                        name="folder_hierarchy",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                    ),
                    weaviate.classes.config.Property(name="connector_id", data_type=weaviate.classes.config.DataType.TEXT),
                    # Enrichment properties
                    weaviate.classes.config.Property(
                        name="domain",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        skip_vectorization=True,
                    ),
                    weaviate.classes.config.Property(
                        name="semantic_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        skip_vectorization=True,
                    ),
                    weaviate.classes.config.Property(
                        name="quality_score",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                    ),
                    weaviate.classes.config.Property(
                        name="associated_person",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        skip_vectorization=True,
                    ),
                ],
            )
            result = {"class": collection_name, "status": "created"}
            logger.info(f"✅ Created collection: {collection_name}")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to create collection {collection_name}: {e}")
            raise

    _ENRICHMENT_PROPERTIES = {
        "domain": (weaviate.classes.config.DataType.TEXT, True),
        "semantic_type": (weaviate.classes.config.DataType.TEXT, True),
        "quality_score": (weaviate.classes.config.DataType.NUMBER, False),
        "associated_person": (weaviate.classes.config.DataType.TEXT, True),
        "parent_chunk_id": (weaviate.classes.config.DataType.TEXT, True),
        "parent_content": (weaviate.classes.config.DataType.TEXT, True),
        "child_index": (weaviate.classes.config.DataType.INT, False),
        "chunk_context": (weaviate.classes.config.DataType.TEXT, True),
    }

    async def ensure_enrichment_properties(self, collection_name: str) -> None:
        """Idempotent migration: add enrichment properties to an existing collection."""
        try:
            collection = self.client.collections.get(collection_name)
            existing_props = {p.name for p in collection.config.get().properties}

            for prop_name, (data_type, skip_vec) in self._ENRICHMENT_PROPERTIES.items():
                if prop_name in existing_props:
                    continue
                logger.info(f"🔧 Adding enrichment property '{prop_name}' to {collection_name}")
                kwargs = {"name": prop_name, "data_type": data_type}
                if skip_vec:
                    kwargs["skip_vectorization"] = True
                collection.config.add_property(
                    weaviate.classes.config.Property(**kwargs)
                )
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure enrichment properties on {collection_name}: {e}")

    async def ensure_collection_exists(self, collection_name: str) -> bool:
        try:
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                await self.ensure_enrichment_properties(collection_name)
                return True

            logger.info(f"🔧 Creating collection: {collection_name}")
            await self.create_collection(collection_name)
            return True

        except Exception as e:
            logger.error(f"❌ Failed to ensure collection {collection_name} exists: {e}")
            return False

    # =========================================================================
    # KNOWLEDGE GRAPH COLLECTION METHODS
    # =========================================================================

    def get_knowledge_collection_name(self) -> str:
        """Single-org knowledge collection name."""
        return KNOWLEDGE_COLLECTION

    async def create_knowledge_collection(self) -> Dict[str, Any]:
        """Create the knowledge collection for storing extracted entities."""
        collection_name = KNOWLEDGE_COLLECTION

        try:
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                logger.info(f"✅ Knowledge collection {collection_name} already exists")
                return {"class": collection_name, "status": "exists"}

            self.client.collections.create(
                name=collection_name,
                description="Knowledge entities extracted from documents",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(name="entity_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="entity_type", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="entity_value", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="entity_label", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="context_text", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="domain", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="source_document_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="confidence", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(
                        name="related_entity_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                    ),
                    weaviate.classes.config.Property(
                        name="related_document_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                    ),
                    weaviate.classes.config.Property(
                        name="roles",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Roles allowed to view (plus EVERYONE sentinel)",
                        index_filterable=True,
                    ),
                    weaviate.classes.config.Property(name="attributes", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="created_at", data_type=weaviate.classes.config.DataType.DATE),
                ],
            )

            logger.info(f"✅ Created knowledge collection: {collection_name}")
            return {"class": collection_name, "status": "created"}

        except Exception as e:
            logger.error(f"❌ Failed to create knowledge collection {collection_name}: {e}")
            raise

    async def add_knowledge_entity(
        self,
        entity_id: str,
        entity_type: str,
        entity_value: str,
        context_text: str,
        entity_label: Optional[str] = None,
        domain: Optional[str] = None,
        source_document_id: Optional[str] = None,
        confidence: float = 0.0,
        related_entity_ids: Optional[List[str]] = None,
        related_document_ids: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None,
    ) -> str:
        """Add a knowledge entity. Defaults ``roles`` to ``[EVERYONE]`` if not given."""
        collection_name = KNOWLEDGE_COLLECTION
        await self.create_knowledge_collection()

        try:
            collection = self.client.collections.get(collection_name)
            embedding = await generate_embedding(context_text)

            import json
            entity_data = {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "entity_value": entity_value,
                "entity_label": entity_label or entity_value,
                "context_text": context_text,
                "domain": domain or "general",
                "source_document_id": source_document_id or "",
                "confidence": confidence,
                "related_entity_ids": related_entity_ids or [],
                "related_document_ids": related_document_ids or [],
                "roles": roles or [EVERYONE_ROLE],
                "attributes": json.dumps(attributes or {}),
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            }

            weaviate_uuid = collection.data.insert(
                properties=entity_data,
                vector=embedding,
            )

            logger.info(
                f"✅ Added knowledge entity {entity_id} ({entity_type}): {weaviate_uuid}"
            )
            return str(weaviate_uuid)

        except Exception as e:
            logger.error(f"❌ Failed to add knowledge entity: {e}")
            raise

    async def search_knowledge_entities(
        self,
        query: str,
        user_roles: List[str],
        entity_types: Optional[List[str]] = None,
        domain: Optional[str] = None,
        limit: int = 10,
        min_certainty: float = 0.5,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search knowledge entities semantically with role-based ACL."""
        collection_name = KNOWLEDGE_COLLECTION

        try:
            collections = await self.list_collections()
            if collection_name not in collections and collection_name.capitalize() not in collections:
                logger.warning(f"Knowledge collection {collection_name} does not exist")
                return []

            collection = self.client.collections.get(collection_name)
            query_embedding = await generate_embedding(query)

            filters = []

            if entity_types:
                type_filters = [
                    weaviate.classes.query.Filter.by_property("entity_type").equal(et)
                    for et in entity_types
                ]
                if len(type_filters) == 1:
                    filters.append(type_filters[0])
                else:
                    filters.append(weaviate.classes.query.Filter.any_of(type_filters))

            if domain:
                filters.append(
                    weaviate.classes.query.Filter.by_property("domain").equal(domain)
                )

            if not is_admin:
                filters.append(_roles_filter(user_roles))

            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            response = collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                certainty=min_certainty,
                filters=combined_filter,
                return_metadata=weaviate.classes.query.MetadataQuery(certainty=True, distance=True),
            )

            import json
            results = []
            for obj in response.objects:
                results.append({
                    "entity_id": obj.properties.get("entity_id"),
                    "entity_type": obj.properties.get("entity_type"),
                    "entity_value": obj.properties.get("entity_value"),
                    "entity_label": obj.properties.get("entity_label"),
                    "domain": obj.properties.get("domain"),
                    "source_document_id": obj.properties.get("source_document_id"),
                    "confidence": obj.properties.get("confidence"),
                    "context_text": obj.properties.get("context_text"),
                    "attributes": json.loads(obj.properties.get("attributes", "{}")),
                    "related_entity_ids": obj.properties.get("related_entity_ids", []),
                    "related_document_ids": obj.properties.get("related_document_ids", []),
                    "similarity_score": obj.metadata.certainty if obj.metadata else None,
                    "weaviate_id": str(obj.uuid),
                })

            logger.info(f"🔍 Knowledge search returned {len(results)} entities")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to search knowledge entities: {e}")
            return []

    async def delete_knowledge_entity(self, entity_id: str) -> bool:
        """Delete a knowledge entity by its PostgreSQL entity_id."""
        collection_name = KNOWLEDGE_COLLECTION
        try:
            collection = self.client.collections.get(collection_name)

            response = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("entity_id").equal(entity_id),
                limit=1,
            )

            if response.objects:
                collection.data.delete_by_id(response.objects[0].uuid)
                logger.info(f"✅ Deleted knowledge entity {entity_id}")
                return True

            logger.warning(f"⚠️ Knowledge entity {entity_id} not found")
            return False

        except Exception as e:
            logger.error(f"❌ Failed to delete knowledge entity {entity_id}: {e}")
            return False

    async def delete_knowledge_by_document(self, document_id: str) -> int:
        """Delete all knowledge entities from a specific document."""
        collection_name = KNOWLEDGE_COLLECTION
        try:
            collection = self.client.collections.get(collection_name)

            response = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("source_document_id").equal(document_id),
                limit=1000,
            )

            deleted_count = 0
            for obj in response.objects:
                collection.data.delete_by_id(obj.uuid)
                deleted_count += 1

            logger.info(f"✅ Deleted {deleted_count} knowledge entities from document {document_id}")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ Failed to delete knowledge entities for document {document_id}: {e}")
            return 0

    # =========================================================================
    # VISUAL CONTENT COLLECTION METHODS (Multimodal Embedding Support)
    # =========================================================================

    def get_visual_collection_name(self) -> str:
        """Single-org visual collection name."""
        return VISUAL_COLLECTION

    async def create_visual_collection(self) -> Dict[str, Any]:
        """Create the visual content collection."""
        collection_name = VISUAL_COLLECTION

        try:
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                logger.info(f"✅ Visual collection {collection_name} already exists")
                return {"class": collection_name, "status": "exists"}

            self.client.collections.create(
                name=collection_name,
                description="Visual content embeddings (images, tables, diagrams)",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(name="visual_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="content_type", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="caption", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="document_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(
                        name="roles",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Roles allowed to view (plus EVERYONE sentinel)",
                        index_filterable=True,
                    ),
                    weaviate.classes.config.Property(name="page_number", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="bbox_x0", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_y0", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_x1", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="bbox_y1", data_type=weaviate.classes.config.DataType.NUMBER),
                    weaviate.classes.config.Property(name="width", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="height", data_type=weaviate.classes.config.DataType.INT),
                    weaviate.classes.config.Property(name="embedding_model", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="detection_method", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="created_at", data_type=weaviate.classes.config.DataType.DATE),
                    weaviate.classes.config.Property(name="channel_id", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="owner_user_id", data_type=weaviate.classes.config.DataType.TEXT),
                ],
            )

            logger.info(f"✅ Created visual collection: {collection_name}")
            return {"class": collection_name, "status": "created"}

        except Exception as e:
            logger.error(f"❌ Failed to create visual collection {collection_name}: {e}")
            raise

    async def add_visual_content(
        self,
        document_id: str,
        visual_id: str,
        content_type: str,
        embedding: List[float],
        page_number: int = 0,
        bbox: Optional[tuple] = None,
        caption: Optional[str] = None,
        width: int = 0,
        height: int = 0,
        embedding_model: str = "Qwen/Qwen3-VL-Embedding-2B",
        detection_method: Optional[str] = None,
        roles: Optional[List[str]] = None,
        channel_id: str = "",
        owner_user_id: str = "",
    ) -> str:
        """Add a visual content embedding. Defaults ``roles`` to ``[EVERYONE]``."""
        collection_name = VISUAL_COLLECTION
        await self.create_visual_collection()

        try:
            collection = self.client.collections.get(collection_name)

            visual_data = {
                "visual_id": visual_id,
                "content_type": content_type,
                "caption": caption or "",
                "document_id": document_id,
                "roles": roles or [EVERYONE_ROLE],
                "page_number": page_number,
                "bbox_x0": bbox[0] if bbox else 0.0,
                "bbox_y0": bbox[1] if bbox else 0.0,
                "bbox_x1": bbox[2] if bbox else 0.0,
                "bbox_y1": bbox[3] if bbox else 0.0,
                "width": width,
                "height": height,
                "embedding_model": embedding_model,
                "detection_method": detection_method or "",
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "channel_id": channel_id,
                "owner_user_id": owner_user_id,
            }

            collection.data.insert(
                properties=visual_data,
                uuid=visual_id,
                vector=embedding,
            )

            logger.debug(f"✅ Added visual content {visual_id} ({content_type})")
            return visual_id

        except Exception as e:
            logger.error(f"❌ Failed to add visual content {visual_id}: {e}")
            raise

    async def search_visual_content(
        self,
        query_vector: List[float],
        user_roles: List[str],
        content_types: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        limit: int = 10,
        certainty: float = 0.7,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search visual content using vector similarity with role-based ACL."""
        collection_name = VISUAL_COLLECTION

        try:
            collection = self.client.collections.get(collection_name)

            filters = None if is_admin else _roles_filter(user_roles)

            if content_types:
                type_filter = None
                for ct in content_types:
                    cf = weaviate.classes.query.Filter.by_property("content_type").equal(ct)
                    type_filter = cf if type_filter is None else type_filter | cf
                filters = type_filter if filters is None else filters & type_filter

            if document_ids:
                doc_filter = None
                for doc_id in document_ids:
                    df = weaviate.classes.query.Filter.by_property("document_id").equal(doc_id)
                    doc_filter = df if doc_filter is None else doc_filter | df
                filters = doc_filter if filters is None else filters & doc_filter

            response = collection.query.near_vector(
                near_vector=query_vector,
                filters=filters,
                limit=limit,
                certainty=certainty,
                return_metadata=weaviate.classes.query.MetadataQuery(certainty=True, distance=True),
            )

            results = []
            for obj in response.objects:
                results.append({
                    "visual_id": obj.properties.get("visual_id"),
                    "content_type": obj.properties.get("content_type"),
                    "caption": obj.properties.get("caption"),
                    "document_id": obj.properties.get("document_id"),
                    "page_number": obj.properties.get("page_number"),
                    "bbox": (
                        obj.properties.get("bbox_x0"),
                        obj.properties.get("bbox_y0"),
                        obj.properties.get("bbox_x1"),
                        obj.properties.get("bbox_y1"),
                    ),
                    "width": obj.properties.get("width"),
                    "height": obj.properties.get("height"),
                    "embedding_model": obj.properties.get("embedding_model"),
                    "certainty": obj.metadata.certainty if obj.metadata else None,
                    "distance": obj.metadata.distance if obj.metadata else None,
                })

            logger.info(f"✅ Found {len(results)} visual results")
            return results

        except Exception as e:
            logger.error(f"❌ Visual search failed: {e}")
            return []

    async def delete_visual_by_document(self, document_id: str) -> int:
        """Delete all visual content from a specific document."""
        collection_name = VISUAL_COLLECTION
        try:
            collection = self.client.collections.get(collection_name)

            response = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("document_id").equal(document_id),
                limit=1000,
            )

            deleted_count = 0
            for obj in response.objects:
                collection.data.delete_by_id(obj.uuid)
                deleted_count += 1

            logger.info(f"✅ Deleted {deleted_count} visual embeddings from document {document_id}")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ Failed to delete visual content for document {document_id}: {e}")
            return 0

    # =========================================================================
    # CHUNK EXPANSION METHODS (Long Context RAG)
    # =========================================================================

    async def fetch_chunks_by_indices(
        self,
        collection_name: str,
        document_id: str,
        chunk_indices: List[int],
    ) -> List[Dict[str, Any]]:
        """Fetch specific chunks by document_id and chunk_indices."""
        if not chunk_indices:
            return []

        try:
            collection = self.client.collections.get(collection_name)

            doc_filter = weaviate.classes.query.Filter.by_property("document_id").equal(document_id)

            response = collection.query.fetch_objects(
                filters=doc_filter,
                limit=100,
                return_properties=["content", "chunk_index", "document_id", "title"],
            )

            results = []
            for obj in response.objects:
                chunk_idx = obj.properties.get("chunk_index")
                if chunk_idx is not None and chunk_idx in chunk_indices:
                    results.append({
                        "chunk_index": chunk_idx,
                        "content": obj.properties.get("content", ""),
                        "document_id": obj.properties.get("document_id"),
                        "title": obj.properties.get("title"),
                        "uuid": str(obj.uuid),
                    })

            logger.debug(f"  Fetched {len(results)} adjacent chunks for document {document_id}")
            return results

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch chunks by indices: {e}")
            return []

    async def fetch_objects_by_ids(
        self,
        collection_name: str,
        object_ids: List[str],
    ) -> List[Optional[Dict[str, Any]]]:
        """Fetch multiple objects by their UUIDs (for cache support)."""
        if not object_ids:
            return []

        try:
            collection = self.client.collections.get(collection_name)
            results: List[Optional[Dict[str, Any]]] = []

            batch_size = 100
            for i in range(0, len(object_ids), batch_size):
                batch_ids = object_ids[i:i + batch_size]

                for obj_id in batch_ids:
                    try:
                        obj = collection.query.fetch_object_by_id(
                            uuid=obj_id,
                            return_properties=[
                                "content", "title", "document_type", "roles",
                                "chunk_index", "total_chunks", "document_id",
                                "folder_path", "file_type", "created_at",
                            ],
                        )
                        if obj:
                            results.append({
                                "uuid": str(obj.uuid),
                                "content": obj.properties.get("content", ""),
                                "title": obj.properties.get("title", ""),
                                "document_type": obj.properties.get("document_type"),
                                "roles": obj.properties.get("roles", []),
                                "chunk_index": obj.properties.get("chunk_index", 0),
                                "total_chunks": obj.properties.get("total_chunks", 1),
                                "document_id": obj.properties.get("document_id", ""),
                                "folder_path": obj.properties.get("folder_path"),
                                "file_type": obj.properties.get("file_type"),
                                "created_at": obj.properties.get("created_at"),
                            })
                        else:
                            results.append(None)
                    except Exception:
                        results.append(None)

            logger.debug(f"📄 Fetched {len([r for r in results if r])}/{len(object_ids)} objects by ID")
            return results

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch objects by IDs: {e}")
            return [None] * len(object_ids)

    # =========================================================================
    # DOCUMENT INSERT / QUERY
    # =========================================================================

    async def add_document(
        self,
        collection_name: str,
        document: DocumentCreate,
    ) -> DocumentResponse:
        """Add a document (or its chunks) to the given collection."""
        try:
            if not await self.ensure_collection_exists(collection_name):
                raise Exception(f"Could not create or access collection: {collection_name}")

            doc_id = document.id or str(uuid.uuid4())
            collection = self.client.collections.get(collection_name)

            doc_roles = getattr(document, 'roles', None) or [EVERYONE_ROLE]

            base_properties = {
                "document_id": doc_id,
                "title": document.title,
                "roles": doc_roles,
                "document_type": document.document_type or "document",
                "tags": document.tags or [],
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "channel_id": getattr(document, 'channel_id', '') or '',
                "owner_user_id": getattr(document, 'owner_user_id', '') or '',
                "source_type": getattr(document, 'source_type', 'upload') or 'upload',
                "external_id": getattr(document, 'external_id', '') or '',
                "folder_path": getattr(document, 'folder_path', '') or '',
                "folder_hierarchy": getattr(document, 'folder_hierarchy', []) or [],
                "connector_id": getattr(document, 'connector_id', '') or '',
                "domain": getattr(document, 'domain', '') or '',
                "semantic_type": getattr(document, 'semantic_type', '') or '',
                "quality_score": float(getattr(document, 'quality_score', 0.0) or 0.0),
                "associated_person": getattr(document, 'associated_person', '') or '',
            }

            chunks = getattr(document, 'chunks', None) or []

            if chunks and len(chunks) > 0:
                logger.info(f"📦 Storing {len(chunks)} chunks for document {doc_id}")
                await self._delete_document_chunks(collection_name, doc_id)

                batch_objects = []
                for chunk in chunks:
                    chunk_content = chunk.get("content", "")
                    chunk_metadata = chunk.get("metadata", {})
                    chunk_index = chunk.get("chunk_index", 0)
                    chunk_uuid = str(uuid.uuid4())

                    chunk_properties = {
                        **base_properties,
                        "content": chunk_content,
                        "chunk_index": chunk_index,
                        "char_start": chunk_metadata.get("char_start", 0),
                        "char_end": chunk_metadata.get("char_end", 0),
                        "page_start": chunk_metadata.get("page_start", 0),
                        "page_end": chunk_metadata.get("page_end", 0),
                        "folder_path": chunk_metadata.get("folder_path") or base_properties["folder_path"],
                        "folder_hierarchy": chunk_metadata.get("folder_hierarchy") or base_properties["folder_hierarchy"],
                        "connector_id": chunk_metadata.get("connector_id") or base_properties["connector_id"],
                        "domain": chunk_metadata.get("domain", "") or base_properties.get("domain", ""),
                        "semantic_type": chunk_metadata.get("semantic_type", "") or base_properties.get("semantic_type", ""),
                        "quality_score": float(chunk_metadata.get("quality_score", 0.0) or base_properties.get("quality_score", 0.0)),
                        "associated_person": chunk_metadata.get("associated_person", "") or base_properties.get("associated_person", ""),
                        "parent_chunk_id": chunk_metadata.get("parent_chunk_id", ""),
                        "parent_content": chunk_metadata.get("parent_content", ""),
                        "child_index": chunk_metadata.get("child_index", 0),
                        "chunk_context": chunk_metadata.get("chunk_context", ""),
                    }

                    embedding_vector = None
                    await self._check_embedding_service()
                    try:
                        text_to_embed = f"{document.title} {chunk_content}"
                        embedding_vector = await generate_embedding(text_to_embed)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate chunk embedding: {e}")

                    if embedding_vector:
                        batch_objects.append(weaviate.classes.data.DataObject(
                            properties=chunk_properties,
                            uuid=chunk_uuid,
                            vector=embedding_vector,
                        ))
                    else:
                        batch_objects.append(weaviate.classes.data.DataObject(
                            properties=chunk_properties,
                            uuid=chunk_uuid,
                        ))

                if batch_objects:
                    try:
                        collection.data.insert_many(batch_objects)
                        logger.info(f"✅ Inserted {len(batch_objects)} chunks for document {doc_id}")
                    except Exception as e:
                        logger.error(f"❌ Batch chunk insert failed: {e}")
                        raise

                first_chunk_content = chunks[0].get("content", "")[:500] if chunks else ""

                return DocumentResponse(
                    id=doc_id,
                    title=document.title,
                    content=first_chunk_content + f"... [{len(chunks)} chunks total]",
                    metadata={"chunk_count": len(chunks)},
                    document_type=document.document_type or "document",
                    tags=document.tags or [],
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    vector_id=doc_id,
                    folder_path=base_properties["folder_path"],
                    folder_hierarchy=base_properties["folder_hierarchy"],
                    connector_id=base_properties["connector_id"],
                )

            else:
                doc_data = {
                    **base_properties,
                    "content": document.content,
                }

                embedding_vector = None
                await self._check_embedding_service()
                try:
                    text_to_embed = f"{document.title} {document.content}"
                    embedding_vector = await generate_embedding(text_to_embed)
                    if embedding_vector:
                        logger.info(f"🧮 Generated embedding vector of size {len(embedding_vector)}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not generate embedding: {e}")

                try:
                    if embedding_vector:
                        collection.data.insert(
                            properties=doc_data,
                            uuid=doc_id,
                            vector=embedding_vector,
                        )
                    else:
                        collection.data.insert(
                            properties=doc_data,
                            uuid=doc_id,
                        )
                    logger.info(f"✅ Inserted document {doc_id} to {collection_name}")
                except UnexpectedStatusCodeException as exc:
                    if exc.status_code == 422 and "already exists" in str(exc):
                        logger.info(f"♻️ Document {doc_id} already exists, replacing")
                        if embedding_vector:
                            collection.data.replace(
                                properties=doc_data,
                                uuid=doc_id,
                                vector=embedding_vector,
                            )
                        else:
                            collection.data.replace(
                                properties=doc_data,
                                uuid=doc_id,
                            )
                        logger.info(f"✅ Replaced document {doc_id}")
                    else:
                        raise

                return DocumentResponse(
                    id=doc_id,
                    title=document.title,
                    content=document.content,
                    metadata={},
                    document_type=document.document_type or "document",
                    tags=document.tags or [],
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    vector_id=doc_id,
                    folder_path=base_properties["folder_path"],
                    folder_hierarchy=base_properties["folder_hierarchy"],
                    connector_id=base_properties["connector_id"],
                )

        except Exception as e:
            logger.error(f"❌ Failed to add document to {collection_name}: {e}")
            raise

    async def _delete_document_chunks(self, collection_name: str, document_id: str) -> int:
        """Delete all chunks belonging to a document before re-indexing."""
        try:
            collection = self.client.collections.get(collection_name)

            Filter = weaviate.classes.query.Filter
            doc_filter = Filter.by_property("document_id").equal(document_id)

            result = collection.query.fetch_objects(
                filters=doc_filter,
                limit=1000,
                return_properties=["document_id"],
            )

            if not result.objects:
                return 0

            deleted = 0
            for obj in result.objects:
                try:
                    collection.data.delete_by_id(obj.uuid)
                    deleted += 1
                except Exception:
                    pass

            if deleted > 0:
                logger.info(f"🗑️ Deleted {deleted} existing chunks for document {document_id}")

            return deleted

        except Exception as e:
            logger.warning(f"⚠️ Could not delete existing chunks for {document_id}: {e}")
            return 0

    async def get_document_chunks(
        self,
        collection_name: str,
        document_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all chunks for a document, ordered by chunk_index."""
        await self.initialize()

        if not self.client.collections.exists(collection_name):
            return []

        collection = self.client.collections.get(collection_name)
        Filter = weaviate.classes.query.Filter
        doc_filter = Filter.by_property("document_id").equal(document_id)

        response = collection.query.fetch_objects(
            filters=doc_filter,
            offset=offset,
            limit=limit,
            return_properties=["content", "chunk_index", "document_id", "title"],
        )

        chunks = []
        for obj in response.objects:
            chunks.append({
                "content": obj.properties.get("content", ""),
                "chunk_index": obj.properties.get("chunk_index", 0),
                "document_id": obj.properties.get("document_id", ""),
                "title": obj.properties.get("title", ""),
            })

        chunks.sort(key=lambda c: c.get("chunk_index", 0))
        return chunks

    async def delete_document(self, collection_name: str, document_id: str) -> bool:
        """Delete a document by its document_id property."""
        try:
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist, nothing to delete")
                return True

            collection = self.client.collections.get(collection_name)

            Filter = weaviate.classes.query.Filter
            doc_filter = Filter.by_property("document_id").equal(document_id)

            result = collection.query.fetch_objects(
                filters=doc_filter,
                limit=1,
                return_properties=["document_id"],
            )

            if not result.objects:
                logger.warning(f"⚠️ Document {document_id} not found in {collection_name}")
                return True

            weaviate_uuid = result.objects[0].uuid
            collection.data.delete_by_id(weaviate_uuid)

            logger.info(f"✅ Deleted document {document_id} from {collection_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete document {document_id} from {collection_name}: {e}")
            return False

    async def search_documents(
        self,
        collection_name: str,
        search_request: SearchRequest,
    ) -> SearchResponse:
        """Search documents in the given collection applying the roles ACL."""
        try:
            start_time = datetime.now()
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.info(f"📭 Collection {collection_name} does not exist, returning empty results")
                return SearchResponse(
                    query=search_request.query,
                    results=[],
                    total_results=0,
                    search_time_ms=0,
                    search_type=search_request.search_type or "hybrid",
                )

            collection = self.client.collections.get(collection_name)

            # ------------------------------------------------------------------
            # ACL filter (single clause — allowed_roles() folds in EVERYONE)
            # ------------------------------------------------------------------
            request_roles = getattr(search_request, 'user_roles', None) or []
            is_admin = getattr(search_request, 'is_admin', False)

            if is_admin:
                combined_filters = None
            else:
                combined_filters = _roles_filter(request_roles)

            if search_request.filters:
                for key, value in search_request.filters.items():
                    additional_filter = self._build_property_filter(key, value)
                    if additional_filter is not None:
                        combined_filters = (
                            additional_filter if combined_filters is None
                            else combined_filters & additional_filter
                        )

            Filter = weaviate.classes.query.Filter

            folder_path = getattr(search_request, 'folder_path', None)
            if folder_path:
                folder_filter = Filter.by_property("folder_path").equal(folder_path)
                combined_filters = folder_filter if combined_filters is None else combined_filters & folder_filter
                logger.debug(f"📁 Filtering by exact folder_path: {folder_path}")

            folder_hierarchy_contains = getattr(search_request, 'folder_hierarchy_contains', None)
            if folder_hierarchy_contains:
                hierarchy_filter = Filter.by_property("folder_hierarchy").contains_any([folder_hierarchy_contains])
                combined_filters = hierarchy_filter if combined_filters is None else combined_filters & hierarchy_filter
                logger.debug(f"📁 Filtering by folder_hierarchy_contains: {folder_hierarchy_contains}")

            try:
                _cfg = collection.config.get()
                _schema_props = {p.name for p in _cfg.properties}
            except Exception:
                _cfg = None
                _schema_props = set()

            domain_filter = getattr(search_request, 'domain_filter', None)
            if domain_filter and "domain" in _schema_props:
                f = Filter.by_property("domain").equal(domain_filter)
                combined_filters = f if combined_filters is None else combined_filters & f
                logger.debug(f"🏷️ Filtering by domain: {domain_filter}")

            semantic_type_filter = getattr(search_request, 'semantic_type_filter', None)
            if semantic_type_filter:
                if "semantic_type" in _schema_props:
                    f = Filter.by_property("semantic_type").equal(semantic_type_filter)
                    combined_filters = f if combined_filters is None else combined_filters & f
                    logger.debug(f"🏷️ Filtering by semantic_type: {semantic_type_filter}")

            person_filter = getattr(search_request, 'person_filter', None)
            if person_filter:
                person_conditions = []
                if "associated_person" in _schema_props:
                    person_conditions.append(
                        Filter.by_property("associated_person").like(f"*{person_filter}*")
                    )
                person_conditions.append(
                    Filter.by_property("folder_path").like(f"*{person_filter}*")
                )
                person_combined = person_conditions[0]
                if len(person_conditions) == 2:
                    person_combined = person_conditions[0] | person_conditions[1]
                combined_filters = person_combined if combined_filters is None else combined_filters & person_combined
                logger.debug(f"👤 Filtering by person: {person_filter}")

            min_quality = getattr(search_request, 'min_quality', None)
            if min_quality is not None and "quality_score" in _schema_props:
                f = Filter.by_property("quality_score").greater_or_equal(min_quality)
                combined_filters = f if combined_filters is None else combined_filters & f
                logger.debug(f"⭐ Filtering by min_quality: {min_quality}")

            date_from = getattr(search_request, 'date_from', None)
            if date_from and "created_at" in _schema_props:
                from datetime import datetime as dt
                try:
                    parsed = dt.fromisoformat(date_from)
                    f = Filter.by_property("created_at").greater_or_equal(parsed)
                    combined_filters = f if combined_filters is None else combined_filters & f
                    logger.debug(f"📅 Filtering by date_from: {date_from}")
                except ValueError:
                    logger.warning(f"⚠️ Invalid date_from format: {date_from}")

            date_to = getattr(search_request, 'date_to', None)
            if date_to and "created_at" in _schema_props:
                from datetime import datetime as dt
                try:
                    parsed = dt.fromisoformat(date_to)
                    f = Filter.by_property("created_at").less_or_equal(parsed)
                    combined_filters = f if combined_filters is None else combined_filters & f
                    logger.debug(f"📅 Filtering by date_to: {date_to}")
                except ValueError:
                    logger.warning(f"⚠️ Invalid date_to format: {date_to}")

            _offset = getattr(search_request, 'offset', 0) or 0
            _query_is_empty = not search_request.query or not search_request.query.strip()

            if _query_is_empty and search_request.search_type in ("keyword", "hybrid"):
                response = collection.query.fetch_objects(
                    limit=search_request.limit,
                    offset=_offset,
                    filters=combined_filters,
                    return_metadata=weaviate.classes.query.MetadataQuery(creation_time=True),
                )
            elif search_request.search_type == "vector":
                query_embedding = None
                await self._check_embedding_service()
                try:
                    query_embedding = await generate_embedding(search_request.query)
                except Exception as e:
                    logger.warning(f"⚠️ Could not generate query embedding: {e}")

                if query_embedding:
                    response = collection.query.near_vector(
                        near_vector=query_embedding,
                        limit=search_request.limit,
                        offset=_offset,
                        return_metadata=weaviate.classes.query.MetadataQuery(certainty=True, score=True),
                        filters=combined_filters,
                    )
                else:
                    response = collection.query.bm25(
                        query=search_request.query,
                        limit=search_request.limit,
                        offset=_offset,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                        filters=combined_filters,
                    )
            elif search_request.search_type == "keyword":
                response = collection.query.bm25(
                    query=search_request.query,
                    limit=search_request.limit,
                    offset=_offset,
                    return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                    filters=combined_filters,
                )
            else:  # hybrid
                _has_vectors = _cfg.vector_index_type is not None if _cfg else False
                if not _has_vectors:
                    logger.warning(
                        f"⚠️ Collection {collection_name} has no vector index. "
                        "Re-sync connectors to enable hybrid search."
                    )

                query_embedding = None
                if _has_vectors:
                    await self._check_embedding_service()
                    try:
                        query_embedding = await generate_embedding(search_request.query)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate query embedding for hybrid: {e}")

                if query_embedding:
                    effective_alpha = search_request.alpha if search_request.alpha is not None else 0.7
                    response = collection.query.hybrid(
                        query=search_request.query,
                        vector=query_embedding,
                        limit=search_request.limit,
                        offset=_offset,
                        alpha=effective_alpha,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True, explain_score=True),
                        filters=combined_filters,
                    )
                else:
                    response = collection.query.bm25(
                        query=search_request.query,
                        limit=search_request.limit,
                        offset=_offset,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                        filters=combined_filters,
                    )

            # Filter-only fallback when BM25 returns empty but enrichment filters active
            _has_enrichment = any([
                getattr(search_request, 'semantic_type_filter', None),
                getattr(search_request, 'person_filter', None),
                getattr(search_request, 'domain_filter', None),
            ])
            if len(response.objects) == 0 and _has_enrichment:
                logger.info("🔄 BM25 returned 0 with enrichment filters — retrying with filter-only fetch")
                response = collection.query.fetch_objects(
                    limit=search_request.limit,
                    offset=_offset,
                    filters=combined_filters,
                    return_metadata=weaviate.classes.query.MetadataQuery(creation_time=True),
                )
                logger.info(f"🔄 Filter-only fetch: {len(response.objects)} objects returned")

            documents = []
            for item in response.objects:
                similarity = None
                if hasattr(item, 'metadata') and item.metadata:
                    similarity = getattr(item.metadata, 'certainty', None) or getattr(item.metadata, 'score', None)

                created_at = datetime.now()
                updated_at = datetime.now()

                if item.properties.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(item.properties["created_at"])
                    except Exception:
                        pass

                if item.properties.get("updated_at"):
                    try:
                        updated_at = datetime.fromisoformat(item.properties["updated_at"])
                    except Exception:
                        pass

                doc = DocumentResponse(
                    id=item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                    title=item.properties.get("title", ""),
                    content=item.properties.get("content", ""),
                    metadata=item.properties.get("metadata", {}),
                    document_type=item.properties.get("document_type", ""),
                    tags=item.properties.get("tags", []),
                    created_at=created_at,
                    updated_at=updated_at,
                    similarity_score=similarity,
                    folder_path=item.properties.get("folder_path", ""),
                    folder_hierarchy=item.properties.get("folder_hierarchy", []),
                    connector_id=item.properties.get("connector_id", ""),
                    chunk_index=item.properties.get("chunk_index"),
                    page_number=item.properties.get("page_start"),
                    domain=item.properties.get("domain", ""),
                    semantic_type=item.properties.get("semantic_type", ""),
                    quality_score=item.properties.get("quality_score"),
                    associated_person=item.properties.get("associated_person", ""),
                )
                documents.append(doc)

            search_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return SearchResponse(
                query=search_request.query,
                results=documents,
                total_results=len(documents),
                search_time_ms=search_time,
                search_type=search_request.search_type,
            )

        except Exception as e:
            logger.error(f"❌ Search failed in {collection_name}: {e}")
            raise

    async def get_document_by_id(
        self,
        collection_name: str,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a specific document by its PostgreSQL document ID."""
        try:
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return None

            collection = self.client.collections.get(collection_name)

            import weaviate.classes.query as wq
            response = collection.query.fetch_objects(
                filters=wq.Filter.by_property("document_id").equal(document_id),
                limit=1,
            )

            if response.objects and len(response.objects) > 0:
                item = response.objects[0]
                return {
                    "id": item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                    "title": item.properties.get("title", ""),
                    "content": item.properties.get("content", ""),
                    "metadata": item.properties.get("metadata", {}),
                    "roles": item.properties.get("roles", []),
                    "document_type": item.properties.get("document_type", ""),
                    "tags": item.properties.get("tags", []),
                }

            logger.warning(f"⚠️ Document {document_id} not found in {collection_name}")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document {document_id}: {e}")
            return None

    async def get_document_by_id_across_collections(
        self,
        document_id: str,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find a document by ID across the main documents collection + channels.

        Returns the first document whose ``roles`` intersect the caller's
        ``allowed_roles(user_roles)`` (or any match when ``is_admin``).
        """
        try:
            await self.initialize()
            import weaviate.classes.query as wq

            collections = await self.list_collections()
            if not collections:
                return None

            # Only scan documents-flavoured collections
            candidate = [
                c for c in collections
                if "documents" in c.lower() or "_channel_" in c.lower() or c == DOCUMENTS_COLLECTION
            ]
            if not candidate:
                candidate = collections

            async def search_in_collection(collection_name: str) -> Optional[Dict[str, Any]]:
                try:
                    if not self.client.collections.exists(collection_name):
                        return None
                    collection = self.client.collections.get(collection_name)
                    doc_filter = wq.Filter.by_property("document_id").equal(document_id)

                    response = collection.query.fetch_objects(filters=doc_filter, limit=1)

                    if response.objects and len(response.objects) > 0:
                        item = response.objects[0]
                        return {
                            "id": item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                            "title": item.properties.get("title", ""),
                            "content": item.properties.get("content", ""),
                            "metadata": item.properties.get("metadata", {}),
                            "document_type": item.properties.get("document_type", ""),
                            "tags": item.properties.get("tags", []),
                            "roles": item.properties.get("roles", []),
                            "owner_user_id": item.properties.get("owner_user_id", ""),
                            "_source_collection": collection_name,
                            "_is_channel": "_channel_" in collection_name.lower(),
                        }
                    return None
                except Exception as e:
                    logger.debug(f"Error searching in {collection_name}: {e}")
                    return None

            def has_acl_access(doc: Dict[str, Any]) -> bool:
                if is_admin:
                    return True
                doc_roles = doc.get("roles") or []
                if not doc_roles:
                    # Legacy doc without roles → treat as public
                    return True
                caller_allowed = set(allowed_roles(user_roles or []))
                return any(r in caller_allowed for r in doc_roles)

            results = await asyncio.gather(*[search_in_collection(coll) for coll in candidate])

            for result in results:
                if result:
                    if has_acl_access(result):
                        logger.info(
                            f"✅ Found document {document_id} in {result['_source_collection']} (ACL verified)"
                        )
                        return result
                    else:
                        logger.warning(f"🔐 Document {document_id} found but denied by role ACL")
                        return None

            logger.warning(f"⚠️ Document {document_id} not found in any collection")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document {document_id} across collections: {e}")
            return None

    async def get_document_by_title(
        self,
        collection_name: str,
        title: str,
        user_roles: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Get a specific document by its title with role ACL filtering."""
        try:
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return None

            collection = self.client.collections.get(collection_name)

            import weaviate.classes.query as wq
            response = collection.query.fetch_objects(
                filters=(
                    wq.Filter.by_property("title").like(f"*{title}*") & _roles_filter(user_roles)
                ),
                limit=1,
            )

            if response.objects and len(response.objects) > 0:
                item = response.objects[0]
                logger.info(f"✅ Found document by title: {item.properties.get('title')}")
                return {
                    "id": item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                    "title": item.properties.get("title", ""),
                    "content": item.properties.get("content", ""),
                    "metadata": item.properties.get("metadata", {}),
                    "roles": item.properties.get("roles", []),
                    "document_type": item.properties.get("document_type", ""),
                    "tags": item.properties.get("tags", []),
                }

            logger.warning(f"⚠️ Document with title '{title}' not found")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document by title '{title}': {e}")
            return None

    async def get_document_full_content(
        self,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch and concatenate all chunks of a document from the main collection."""
        try:
            await self.initialize()
            import weaviate.classes.query as wq

            collection_name = DOCUMENTS_COLLECTION

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return None

            collection = self.client.collections.get(collection_name)

            doc_filter = wq.Filter.by_property("document_id").equal(document_id)

            response = collection.query.fetch_objects(
                filters=doc_filter,
                limit=500,
                return_properties=["content", "char_start", "document_id", "title", "document_type", "source_type"],
            )

            if not response.objects:
                logger.warning(f"⚠️ No chunks found for document {document_id}")
                return None

            chunks = sorted(
                response.objects,
                key=lambda x: x.properties.get("char_start", 0) or 0,
            )

            first_chunk = chunks[0]
            title = first_chunk.properties.get("title", "Untitled")
            source_type = first_chunk.properties.get("document_type", "")

            full_content = "\n\n".join(
                chunk.properties.get("content", "") for chunk in chunks
            )
            word_count = len(full_content.split())

            logger.info(
                f"✅ Retrieved full content for document {document_id}: "
                f"{len(chunks)} chunks, {word_count} words"
            )

            return {
                "document_id": document_id,
                "title": title,
                "content": full_content,
                "chunk_count": len(chunks),
                "word_count": word_count,
                "source_type": source_type,
            }

        except Exception as e:
            logger.error(f"❌ Failed to get full content for document {document_id}: {e}")
            return None

    async def update_document_acl(
        self,
        collection_name: str,
        document_id: str,
        roles: List[str],
    ) -> bool:
        """Update the ``roles`` ACL property of a document in Weaviate."""
        try:
            await self.initialize()
            import weaviate.classes.query as wq

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return False

            collection = self.client.collections.get(collection_name)

            response = collection.query.fetch_objects(
                filters=wq.Filter.by_property("document_id").equal(document_id),
                limit=1,
                include_vector=False,
            )

            if not response.objects or len(response.objects) == 0:
                logger.warning(f"⚠️ Document {document_id} not found in {collection_name}")
                return False

            weaviate_uuid = response.objects[0].uuid

            collection.data.update(
                uuid=weaviate_uuid,
                properties={
                    "roles": roles,
                    "updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                },
            )

            logger.info(f"✅ Updated roles ACL for document {document_id}: {roles}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update document ACL {document_id}: {e}")
            return False

    async def get_collection_info(self, collection_name: str) -> CollectionInfo:
        """Get information about a collection."""
        try:
            collection = self.client.collections.get(collection_name)
            config = collection.config.get()
            schema = {
                "description": config.description or "",
                "properties": [
                    {"name": prop.name, "data_type": str(prop.data_type)}
                    for prop in config.properties
                ] if config.properties else [],
                "vectorizer": str(config.vectorizer) if config.vectorizer else None,
            }

            count_result = collection.aggregate.over_all(total_count=True)
            objects_count = count_result.total_count or 0

            return CollectionInfo(
                name=collection_name,
                description=schema.get("description", ""),
                objects_count=objects_count,
                properties=schema.get("properties", []),
                vectorizer=schema.get("vectorizer"),
                created_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"❌ Failed to get info for collection {collection_name}: {e}")
            raise

    async def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            collections_list = self.client.collections.list_all()
            collections = [
                c for c in collections_list.keys()
                if c is not None and isinstance(c, str)
            ]
            return collections
        except Exception as e:
            logger.error(f"❌ Failed to list collections: {e}")
            raise

    async def count_by_semantic_type(
        self,
        semantic_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Count documents by semantic_type using Weaviate aggregate.

        Counts unique document_ids (not chunks) across all non-knowledge/visual
        collections.
        """
        import weaviate.classes.query as wq

        collections = await self.list_collections()
        doc_colls = [
            c for c in collections
            if not any(suffix in c.lower() for suffix in ("_summaries", "knowledge", "visual"))
        ]
        if not doc_colls:
            return {"semantic_type": semantic_type, "count": 0} if semantic_type else {"type_counts": {}}

        try:
            all_doc_ids: Dict[str, set] = {}

            for coll_name in doc_colls:
                try:
                    collection = self.client.collections.get(coll_name)

                    if semantic_type:
                        response = collection.query.fetch_objects(
                            filters=wq.Filter.by_property("semantic_type").equal(semantic_type),
                            limit=10000,
                            return_properties=["document_id"],
                        )
                        if semantic_type not in all_doc_ids:
                            all_doc_ids[semantic_type] = set()
                        for obj in response.objects:
                            doc_id = obj.properties.get("document_id", "")
                            if doc_id:
                                all_doc_ids[semantic_type].add(doc_id)
                    else:
                        response = collection.query.fetch_objects(
                            limit=10000,
                            return_properties=["semantic_type", "document_id"],
                        )
                        for obj in response.objects:
                            st = obj.properties.get("semantic_type", "") or ""
                            doc_id = obj.properties.get("document_id", "")
                            if not st or not doc_id:
                                continue
                            if st not in all_doc_ids:
                                all_doc_ids[st] = set()
                            all_doc_ids[st].add(doc_id)
                except Exception as coll_err:
                    logger.debug(f"Skipping collection {coll_name} for type count: {coll_err}")
                    continue

            if semantic_type:
                count = len(all_doc_ids.get(semantic_type, set()))
                return {"semantic_type": semantic_type, "count": count}
            else:
                type_counts = {st: len(ids) for st, ids in all_doc_ids.items()}
                return {"type_counts": type_counts}

        except Exception as e:
            logger.error(f"count_by_semantic_type failed: {e}")
            return {"error": str(e), "count": 0}

    async def search_across_collections(
        self,
        collections: List[str],
        query: str,
        user_roles: List[str],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        search_type: str = "hybrid",
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search across multiple collections and aggregate results (role ACL)."""
        all_results = []

        for collection_name in collections:
            try:
                collection = self.client.collections.get(collection_name)
                props = collection.config.get().properties
                prop_names = [p.name for p in props]

                where_filter = None if is_admin else _roles_filter(user_roles)

                if filters:
                    for key, value in filters.items():
                        base_prop = key.split(".")[0]
                        if base_prop in prop_names:
                            prop_filter = weaviate.classes.query.Filter.by_property(base_prop).equal(value)
                            where_filter = prop_filter if where_filter is None else where_filter & prop_filter

                embedding_vector = None
                if search_type in ["hybrid", "vector"]:
                    try:
                        embedding_vector = await generate_embedding(query)
                    except Exception as e:
                        logger.warning(f"Could not generate embedding for query: {e}")

                if search_type == "hybrid" and embedding_vector:
                    response = collection.query.hybrid(
                        query=query,
                        vector=embedding_vector,
                        filters=where_filter,
                        limit=limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                    )
                elif search_type == "vector" and embedding_vector:
                    response = collection.query.near_vector(
                        near_vector=embedding_vector,
                        filters=where_filter,
                        limit=limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
                    )
                else:
                    response = collection.query.bm25(
                        query=query,
                        filters=where_filter,
                        limit=limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                    )

                for obj in response.objects:
                    props_dict = obj.properties
                    score = getattr(obj.metadata, "score", None) or getattr(obj.metadata, "distance", 0)
                    result = {
                        "id": str(obj.uuid),
                        "title": props_dict.get("title", ""),
                        "content": props_dict.get("content", ""),
                        "metadata": props_dict.get("metadata", {}),
                        "document_type": props_dict.get("document_type", ""),
                        "roles": props_dict.get("roles", []),
                        "score": float(score) if score else 0.0,
                        "_source_collection": collection_name,
                    }
                    all_results.append(result)

            except Exception as e:
                logger.warning(f"Error searching collection {collection_name}: {e}")
                continue

        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_results[:limit * 2]

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection."""
        try:
            self.client.collections.delete(collection_name)
            logger.info(f"✅ Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete collection {collection_name}: {e}")
            raise

    async def batch_add_documents(
        self,
        collection_name: str,
        documents: List[DocumentCreate],
    ) -> Dict[str, Any]:
        """Batch add multiple documents."""
        try:
            results = []
            collection = self.client.collections.get(collection_name)

            batch_objects = []
            for document in documents:
                doc_id = document.id or str(uuid.uuid4())

                doc_data = {
                    "title": document.title,
                    "content": document.content,
                    "document_id": document.id,
                    "roles": getattr(document, 'roles', None) or [EVERYONE_ROLE],
                    "document_type": document.document_type,
                    "tags": document.tags,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "channel_id": getattr(document, 'channel_id', '') or '',
                    "owner_user_id": getattr(document, 'owner_user_id', '') or '',
                    "source_type": getattr(document, 'source_type', 'upload') or 'upload',
                    "external_id": getattr(document, 'external_id', '') or '',
                    "folder_path": getattr(document, 'folder_path', '') or '',
                    "folder_hierarchy": getattr(document, 'folder_hierarchy', []) or [],
                    "connector_id": getattr(document, 'connector_id', '') or '',
                }

                embedding_vector = None
                await self._check_embedding_service()
                try:
                    text_to_embed = f"{document.title} {document.content}"
                    embedding_vector = await generate_embedding(text_to_embed)
                except Exception as e:
                    logger.warning(f"⚠️ Could not generate batch embedding: {e}")

                if embedding_vector:
                    batch_objects.append(weaviate.classes.data.DataObject(
                        properties=doc_data,
                        uuid=doc_id,
                        vector=embedding_vector,
                    ))
                else:
                    batch_objects.append(weaviate.classes.data.DataObject(
                        properties=doc_data,
                        uuid=doc_id,
                    ))
                results.append(doc_id)

            collection.data.insert_many(batch_objects)

            logger.info(f"✅ Batch added {len(documents)} documents to {collection_name}")
            return {"added_documents": len(documents), "document_ids": results}

        except Exception as e:
            logger.error(f"❌ Batch add failed for {collection_name}: {e}")
            raise

    async def vector_query(
        self,
        collection_name: str,
        query: VectorQuery,
    ) -> SearchResponse:
        """Execute raw vector query with role ACL."""
        try:
            start_time = datetime.now()
            collection = self.client.collections.get(collection_name)

            request_roles = getattr(query, 'user_roles', None) or []
            where_filter = _roles_filter(request_roles)

            if query.filters:
                for key, value in query.filters.items():
                    additional_filter = self._build_property_filter(key, value)
                    if additional_filter is not None:
                        where_filter = where_filter & additional_filter

            return_metadata = [weaviate.classes.query.MetadataQuery.certainty()]
            if query.include_vector:
                return_metadata.append(weaviate.classes.query.MetadataQuery.vector())

            response = collection.query.near_vector(
                near_vector=query.vector,
                filters=where_filter,
                limit=query.limit,
                return_metadata=return_metadata,
            )

            documents = []
            for item in response.objects:
                similarity = None
                if hasattr(item, 'metadata') and item.metadata:
                    similarity = getattr(item.metadata, 'certainty', None)

                doc = DocumentResponse(
                    id=str(item.uuid) if item.uuid else "",
                    title=item.properties.get("title", ""),
                    content=item.properties.get("content", ""),
                    metadata=item.properties.get("metadata", {}),
                    document_type=item.properties.get("document_type", ""),
                    tags=item.properties.get("tags", []),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    similarity_score=similarity,
                    folder_path=item.properties.get("folder_path", ""),
                    folder_hierarchy=item.properties.get("folder_hierarchy", []),
                    connector_id=item.properties.get("connector_id", ""),
                    chunk_index=item.properties.get("chunk_index"),
                    page_number=item.properties.get("page_number"),
                    document_id=item.properties.get("document_id", ""),
                )
                documents.append(doc)

            search_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return SearchResponse(
                query="vector_query",
                results=documents,
                total_results=len(documents),
                search_time_ms=search_time,
                search_type="vector",
            )

        except Exception as e:
            logger.error(f"❌ Vector query failed: {e}")
            raise

    async def hybrid_search(
        self,
        query: str,
        collection_name: str,
        user_roles: List[str],
        limit: int = 10,
        alpha: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentResponse]:
        """Convenience method for hybrid search with role ACL."""
        search_request = SearchRequest(
            query=query,
            limit=limit,
            user_roles=user_roles,
            search_type="hybrid",
            alpha=alpha,
            filters=filters,
        )
        response = await self.search_documents(collection_name, search_request)
        return response.results

    async def vector_search(
        self,
        query: str,
        collection_name: str,
        user_roles: List[str],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentResponse]:
        """Convenience method for vector (semantic) search with role ACL."""
        search_request = SearchRequest(
            query=query,
            limit=limit,
            user_roles=user_roles,
            search_type="vector",
            filters=filters,
        )
        response = await self.search_documents(collection_name, search_request)
        return response.results

    async def keyword_search(
        self,
        query: str,
        collection_name: str,
        user_roles: List[str],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentResponse]:
        """Convenience method for keyword (BM25) search with role ACL."""
        search_request = SearchRequest(
            query=query,
            limit=limit,
            user_roles=user_roles,
            search_type="keyword",
            filters=filters,
        )
        response = await self.search_documents(collection_name, search_request)
        return response.results

    async def filter_search(
        self,
        collection_name: str,
        user_roles: List[str],
        filters: Dict[str, Any],
        limit: int = 10,
    ) -> List[DocumentResponse]:
        """Search documents using only filters (no query text)."""
        search_request = SearchRequest(
            query="*",
            limit=limit,
            user_roles=user_roles,
            search_type="keyword",
            filters=filters,
        )
        response = await self.search_documents(collection_name, search_request)
        return response.results

    async def search(
        self,
        search_request: SearchRequest,
        collection_name: str = None,
    ) -> SearchResponse:
        """Generic search wrapper for SearchRequest."""
        if collection_name is None:
            collection_name = DOCUMENTS_COLLECTION

        return await self.search_documents(collection_name, search_request)

    # =========================================================================
    # TrustGraph Entities Collection — entity embeddings for Graph RAG
    # =========================================================================

    TRUSTGRAPH_ENTITIES_COLLECTION = "TrustGraphEntities"

    async def ensure_trustgraph_entities_collection(self) -> bool:
        """Create TrustGraphEntities collection if it does not already exist."""
        collection_name = self.TRUSTGRAPH_ENTITIES_COLLECTION
        try:
            existing = self.client.collections.list_all()
            if collection_name in existing:
                logger.info(f"Collection {collection_name} already exists")
                return True

            dims = getattr(settings, "embedding_dimensions", 1024)

            self.client.collections.create(
                name=collection_name,
                description="Entity embeddings for TrustGraph Graph RAG",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(
                        name="entity_uri",
                        data_type=weaviate.classes.config.DataType.TEXT,
                    ),
                    weaviate.classes.config.Property(
                        name="label",
                        data_type=weaviate.classes.config.DataType.TEXT,
                    ),
                    weaviate.classes.config.Property(
                        name="definition",
                        data_type=weaviate.classes.config.DataType.TEXT,
                    ),
                    weaviate.classes.config.Property(
                        name="entity_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                    ),
                    weaviate.classes.config.Property(
                        name="roles",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Roles allowed to view (plus EVERYONE sentinel)",
                        index_filterable=True,
                    ),
                    weaviate.classes.config.Property(
                        name="collection",
                        data_type=weaviate.classes.config.DataType.TEXT,
                    ),
                    weaviate.classes.config.Property(
                        name="embed_text",
                        data_type=weaviate.classes.config.DataType.TEXT,
                    ),
                ],
            )
            logger.info(f"Created collection {collection_name} ({dims} dims, cosine HNSW)")
            return True

        except Exception as e:
            logger.error(f"Failed to ensure {collection_name} collection: {e}")
            return False

    ONTOLOGY_TERMS_COLLECTION = "OntologyTerms"

    async def ensure_ontology_terms_collection(self) -> bool:
        """Create OntologyTerms collection if it does not already exist."""
        collection_name = self.ONTOLOGY_TERMS_COLLECTION
        try:
            existing = self.client.collections.list_all()
            if collection_name in existing:
                logger.info(f"Collection {collection_name} already exists")
                return True

            dims = getattr(settings, "embedding_dimensions", 1024)

            self.client.collections.create(
                name=collection_name,
                description="Vectorized predicate definitions for Ontology RAG",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(name="predicate_name", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="namespace", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="description", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="domain_type", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="range_type", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="embed_text", data_type=weaviate.classes.config.DataType.TEXT),
                ],
            )
            logger.info(f"Created collection {collection_name} ({dims} dims, cosine HNSW)")
            return True

        except Exception as e:
            logger.error(f"Failed to ensure {collection_name} collection: {e}")
            return False

    async def search_ontology_terms(
        self,
        query_embedding: list[float],
        limit: int = 3,
        namespace: str | None = None,
    ) -> list[dict]:
        """Vector similarity search over OntologyTerms."""
        try:
            await self.ensure_ontology_terms_collection()
            col = self.client.collections.get(self.ONTOLOGY_TERMS_COLLECTION)

            filters = None
            if namespace:
                filters = weaviate.classes.query.Filter.by_property("namespace").equal(namespace)

            response = col.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                filters=filters,
                return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
            )

            results = []
            for obj in response.objects:
                score = 1.0 - (obj.metadata.distance or 0.0)
                results.append({
                    "predicate_name": obj.properties.get("predicate_name", ""),
                    "namespace": obj.properties.get("namespace", ""),
                    "description": obj.properties.get("description", ""),
                    "score": round(score, 4),
                })
            return results

        except Exception as e:
            logger.error(f"OntologyTerms search failed: {e}")
            return []

    async def upsert_ontology_term(
        self,
        predicate_name: str,
        namespace: str,
        description: str,
        domain_type: str,
        range_type: str,
        embed_text: str,
        embedding: list[float],
    ) -> bool:
        """Insert a single OntologyTerm with pre-computed embedding."""
        try:
            await self.ensure_ontology_terms_collection()
            col = self.client.collections.get(self.ONTOLOGY_TERMS_COLLECTION)

            col.data.insert(
                properties={
                    "predicate_name": predicate_name,
                    "namespace": namespace,
                    "description": description,
                    "domain_type": domain_type,
                    "range_type": range_type,
                    "embed_text": embed_text,
                },
                vector=embedding,
            )
            return True

        except Exception as e:
            logger.error(f"OntologyTerm upsert failed for {namespace}/{predicate_name}: {e}")
            return False

    async def search_trustgraph_entities(
        self,
        query_embedding: List[float],
        user_roles: List[str],
        collection: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Vector similarity search over TrustGraphEntities with role ACL.

        TrustGraph entities are seeded with ``roles=[EVERYONE]`` so any
        authenticated caller sees them. Callers may further restrict by
        source collection name.
        """
        try:
            col = self.client.collections.get(self.TRUSTGRAPH_ENTITIES_COLLECTION)

            combined_filter = _roles_filter(user_roles)
            if collection:
                col_filter = weaviate.classes.query.Filter.by_property("collection").equal(collection)
                combined_filter = combined_filter & col_filter

            response = col.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                filters=combined_filter,
                return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
            )

            results = []
            for obj in response.objects:
                distance = obj.metadata.distance if obj.metadata else None
                score = (1.0 - distance) if distance is not None else None
                results.append({
                    "entity_uri": obj.properties.get("entity_uri"),
                    "label": obj.properties.get("label"),
                    "definition": obj.properties.get("definition"),
                    "entity_type": obj.properties.get("entity_type"),
                    "score": score,
                })

            return results

        except Exception as e:
            logger.error(f"Failed to search TrustGraphEntities: {e}")
            return []

    async def upsert_trustgraph_entities_batch(
        self,
        entities: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> int:
        """Batch upsert entity embeddings into TrustGraphEntities.

        Entities are always seeded with ``roles=[EVERYONE]`` because
        TrustGraph semantic layer is shared across the organisation.
        """
        try:
            await self.ensure_trustgraph_entities_collection()
            col = self.client.collections.get(self.TRUSTGRAPH_ENTITIES_COLLECTION)

            batch_objects = []
            for entity, vector in zip(entities, embeddings):
                embed_text = f"{entity.get('label', '')} {entity.get('definition', '')}".strip()
                props = {
                    "entity_uri": entity.get("entity_uri", ""),
                    "label": entity.get("label", ""),
                    "definition": entity.get("definition", ""),
                    "entity_type": entity.get("entity_type", ""),
                    "roles": [EVERYONE_ROLE],
                    "collection": entity.get("collection", ""),
                    "embed_text": embed_text,
                }
                obj_uuid = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"trustgraph:{entity.get('entity_uri', embed_text)}",
                ))
                batch_objects.append(
                    weaviate.classes.data.DataObject(
                        properties=props,
                        uuid=obj_uuid,
                        vector=vector,
                    )
                )

            if not batch_objects:
                return 0

            col.data.insert_many(batch_objects)
            logger.info(f"Upserted {len(batch_objects)} TrustGraphEntities")
            return len(batch_objects)

        except Exception as e:
            logger.error(f"Failed to batch-upsert TrustGraphEntities: {e}")
            raise

    async def delete_trustgraph_entities(self) -> int:
        """Delete all TrustGraphEntities (single-org full wipe)."""
        try:
            col = self.client.collections.get(self.TRUSTGRAPH_ENTITIES_COLLECTION)

            response = col.query.fetch_objects(limit=10_000)

            deleted = 0
            for obj in response.objects:
                col.data.delete_by_id(obj.uuid)
                deleted += 1

            logger.info(f"Deleted {deleted} TrustGraphEntities")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete TrustGraphEntities: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Check Weaviate service health."""
        try:
            if not self.client:
                return {"status": "unhealthy", "error": "Client not initialized"}

            is_ready = self.client.is_ready()
            is_live = self.client.is_live()

            embedding_info = {
                "provider": "intelligence-docs-service",
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
                "confirmed": self._embedding_checked,
            }

            return {
                "status": "healthy" if is_ready and is_live else "unhealthy",
                "ready": is_ready,
                "live": is_live,
                "url": settings.weaviate_url,
                "embeddings": embedding_info,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global service instance
weaviate_service = WeaviateService()
