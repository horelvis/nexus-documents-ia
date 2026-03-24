"""Weaviate service implementation with Sentence Transformers embeddings"""
import weaviate
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from functools import lru_cache

from app.core.config import settings
from app.core.security import get_tenant_collection_name
from app.schemas.weaviate import (
    DocumentCreate, DocumentResponse, SearchRequest, SearchResponse,
    CollectionInfo, VectorQuery
)
from weaviate.exceptions import UnexpectedStatusCodeException

logger = logging.getLogger(__name__)


# Singleton for embedding model (avoid reloading on each request)
_embedding_model = None
_embedding_model_lock = asyncio.Lock()
_tei_client = None


async def get_tei_embedding(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using TEI (Text Embeddings Inference) server"""
    global _tei_client
    import httpx

    if _tei_client is None:
        _tei_client = httpx.AsyncClient(timeout=30.0)

    try:
        response = await _tei_client.post(
            f"{settings.tei_url}/embed",
            json={"inputs": texts}
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"❌ TEI error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ TEI request failed: {e}")
        return None


async def get_embedding_model():
    """Get or initialize the embedding model based on provider (TEI or Sentence Transformers)"""
    global _embedding_model

    # For TEI, we don't need a local model
    if settings.embedding_provider == "tei":
        return "tei"

    if _embedding_model is not None:
        return _embedding_model

    async with _embedding_model_lock:
        # Double-check after acquiring lock
        if _embedding_model is not None:
            return _embedding_model

        try:
            from sentence_transformers import SentenceTransformer
            import torch

            # Determine device
            device = settings.embedding_device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            elif device == "cuda" and not torch.cuda.is_available():
                logger.warning("⚠️ CUDA requested but not available, falling back to CPU")
                device = "cpu"

            # Load model
            model_name = settings.embedding_model
            logger.info(f"🔄 Loading embedding model: {model_name} on {device}")

            _embedding_model = SentenceTransformer(
                model_name, device=device, trust_remote_code=True,
            )

            # Verify dimensions match config
            test_embedding = _embedding_model.encode("test", convert_to_numpy=True)
            actual_dims = len(test_embedding)

            if actual_dims != settings.embedding_dimensions:
                logger.warning(
                    f"⚠️ Embedding dimensions mismatch: config={settings.embedding_dimensions}, "
                    f"actual={actual_dims}. Using actual dimensions."
                )

            logger.info(f"✅ Loaded embedding model: {model_name} ({actual_dims} dims) on {device}")
            return _embedding_model

        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            return None


async def generate_embedding(text: str, task: str = "") -> list[float] | None:
    """Generate embedding for a single text using configured provider.

    Args:
        text: Text to embed.
        task: Jina v3 LoRA task adapter name (e.g., "retrieval.query", "retrieval.passage").
              Ignored by models that don't support prompt_name (e.g., BGE-M3).
    """
    if settings.embedding_provider == "tei":
        embeddings = await get_tei_embedding([text])
        return embeddings[0] if embeddings else None
    else:
        model = await get_embedding_model()
        if model is None or model == "tei":
            return None
        loop = asyncio.get_event_loop()

        def _encode():
            kwargs = {"convert_to_numpy": True}
            if task:
                try:
                    return model.encode(text, prompt_name=task, **kwargs).tolist()
                except (TypeError, ValueError, KeyError):
                    pass  # Model doesn't support this prompt_name/task adapter
            return model.encode(text, **kwargs).tolist()

        return await loop.run_in_executor(None, _encode)


class WeaviateService:
    """Service for Weaviate operations"""
    
    def __init__(self):
        self.client = None
        self.embedding_model = None
        self._initialized = False

    def _build_property_filter(self, key: str, value: Any):
        """Create filter for property supporting list/dict inputs"""
        if value is None:
            return None

        # Support dict format with operator/value keys
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

        # Lists/tuples/sets become OR filters
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

    def _build_channel_access_filter(self, user_id: str) -> Any:
        """
        Build a filter for channel-based document access control.

        Users can see documents that are:
        1. Regular uploads (no channel) - channel_id is empty
        2. From tenant-wide channels - channel_visibility = "tenant"
        3. From their own personal channels - channel_visibility = "personal" AND owner_user_id = user_id

        This filter is combined with the tenant_id filter for complete isolation.
        """
        Filter = weaviate.classes.query.Filter

        # Regular uploads (channel_id is empty or null)
        regular_upload = Filter.by_property("channel_id").equal("")

        # Tenant-wide channel documents
        tenant_channel = Filter.by_property("channel_visibility").equal("tenant")

        # Personal channel documents owned by the current user
        personal_channel = (
            Filter.by_property("channel_visibility").equal("personal") &
            Filter.by_property("owner_user_id").equal(user_id)
        )

        # Combine: regular uploads OR tenant channels OR personal channels
        return regular_upload | tenant_channel | personal_channel

    def _build_document_access_filter(
        self,
        user_id: str,
        user_role_ids: Optional[List[str]] = None,
        collection_has_acl: bool = False
    ) -> Any:
        """
        Build a filter for document-level ACL access control.

        Users can see documents that match ANY of these conditions:
        1. acl_everyone=True (explicit ACL) - only if collection has ACL props
        2. user_id is in acl_user_ids array (explicit ACL) - only if collection has ACL props
        3. Any of user's roles is in acl_role_ids array (explicit ACL) - only if collection has ACL props
        4. User is the owner (owner_user_id matches)
        5. Legacy documents without owner (owner_user_id is empty)

        This filter is combined with tenant_id and channel filters for complete isolation.

        NOTE: For backwards compatibility with collections that don't have ACL properties,
        we allow access to legacy documents where owner_user_id is empty (uploaded before ACL).

        Args:
            user_id: Current user's UUID as string
            user_role_ids: List of role UUIDs the user belongs to
            collection_has_acl: Whether the collection has ACL properties in schema

        Returns:
            Weaviate filter expression
        """
        Filter = weaviate.classes.query.Filter

        # Condition 1: User is the document owner
        owner_access = Filter.by_property("owner_user_id").equal(user_id)

        # Condition 2: Legacy documents without owner (uploaded before ACL system)
        # These are accessible to all tenant users (backwards compatible)
        legacy_no_owner = Filter.by_property("owner_user_id").equal("")

        # Start with: owner OR legacy_no_owner (always safe, no schema dependency)
        acl_filter = owner_access | legacy_no_owner

        # Add ACL-based filters only if collection has ACL properties
        if collection_has_acl:
            # Condition 3: Accessible to everyone in tenant (explicit ACL)
            everyone_access = Filter.by_property("acl_everyone").equal(True)
            acl_filter = acl_filter | everyone_access

            # Condition 4: User has explicit access
            user_access = Filter.by_property("acl_user_ids").contains_any([user_id])
            acl_filter = acl_filter | user_access

            # Condition 5: User's roles have access (if roles provided)
            if user_role_ids and len(user_role_ids) > 0:
                role_access = Filter.by_property("acl_role_ids").contains_any(user_role_ids)
                acl_filter = acl_filter | role_access

        return acl_filter

    def _build_combined_access_filter(
        self,
        user_id: str,
        user_role_ids: Optional[List[str]] = None
    ) -> Any:
        """
        Build a combined filter for both channel AND document-level ACL.

        Access logic for different document types:

        1. Channel documents (Gmail, Drive, etc.):
           - Use channel_visibility rules (tenant/personal)
           - Personal channels: only owner has access
           - Tenant channels: all tenant users have access

        2. Regular uploads (no channel):
           - Use document-level ACL (acl_everyone, acl_user_ids, acl_role_ids)
           - Owner always has access
           - Legacy docs without ACL properties get access via owner_user_id match

        For backwards compatibility with legacy channel documents that don't have
        ACL properties (acl_everyone=null), we use OR between channel access and
        ACL access. This ensures:
        - Channel docs with proper channel_visibility work (even without ACL props)
        - Regular docs with ACL props work
        - Legacy docs work via owner_user_id match

        Args:
            user_id: Current user's UUID as string
            user_role_ids: List of role UUIDs the user belongs to

        Returns:
            Combined Weaviate filter expression
        """
        Filter = weaviate.classes.query.Filter

        # Get both filters
        channel_filter = self._build_channel_access_filter(user_id)
        acl_filter = self._build_document_access_filter(user_id, user_role_ids)

        # For channel documents: channel access is sufficient
        # (they may not have ACL properties set)
        # Channel doc = channel_id is not empty
        is_channel_doc = Filter.by_property("channel_id").not_equal("")
        channel_doc_access = is_channel_doc & channel_filter

        # For regular uploads: ACL filter is sufficient
        # Regular doc = channel_id is empty
        is_regular_doc = Filter.by_property("channel_id").equal("")
        regular_doc_access = is_regular_doc & acl_filter

        # Combined: (channel doc with channel access) OR (regular doc with ACL access)
        return channel_doc_access | regular_doc_access

    async def initialize(self):
        """Initialize Weaviate client and Sentence Transformers embeddings"""
        if self._initialized and self.client:
            return
        try:
            # Initialize Weaviate client v4 syntax - always use local (not WCD)
            # Parse host and port from URL
            url_without_protocol = settings.weaviate_url.replace("http://", "").replace("https://", "")
            if ":" in url_without_protocol:
                host = url_without_protocol.split(":")[0]
                port = int(url_without_protocol.split(":")[1])
            else:
                host = url_without_protocol
                port = 8080

            # Always connect to local Weaviate (no WCD)
            self.client = weaviate.connect_to_local(
                host=host,
                port=port
            )

            # Test connection
            if self.client.is_ready():
                logger.info(f"✅ Connected to Weaviate at {settings.weaviate_url}")
            else:
                raise Exception("Weaviate not ready")

            # Initialize embedding model based on provider
            if settings.embedding_provider == "tei":
                # Test TEI connection
                try:
                    test_embedding = await generate_embedding("test connection")
                    if test_embedding:
                        self.embedding_model = "tei"
                        logger.info(f"✅ Using TEI embeddings: {settings.embedding_model} ({len(test_embedding)} dims)")
                    else:
                        logger.warning("⚠️ TEI not responding, falling back to BM25 only")
                        self.embedding_model = None
                except Exception as e:
                    logger.warning(f"⚠️ TEI connection failed: {e}, falling back to BM25 only")
                    self.embedding_model = None
            else:
                model = await get_embedding_model()
                if model is not None:
                    self.embedding_model = "sentence-transformers"
                    logger.info(f"✅ Using Sentence Transformers: {settings.embedding_model}")
                else:
                    logger.warning("⚠️ Embedding model not available, falling back to BM25 only")
                    self.embedding_model = None

            self._initialized = True

        except Exception as e:
            logger.error(f"❌ Failed to initialize Weaviate: {e}")
            self._initialized = False
            raise
    
    async def cleanup(self):
        """Cleanup connections"""
        if self.client:
            # Weaviate client doesn't need explicit cleanup
            self.client = None
            logger.info("✅ Weaviate client cleaned up")
        self._initialized = False
    
    async def create_collection(self, collection_name: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new Weaviate collection"""
        try:
            # Default schema for document collections
            if not schema:
                schema = {
                    "class": collection_name,
                    "description": f"Collection for documents: {collection_name}",
                    "properties": [
                        {
                            "name": "title",
                            "dataType": ["text"],
                            "description": "Document title"
                        },
                        {
                            "name": "content", 
                            "dataType": ["text"],
                            "description": "Document content"
                        },
                        {
                            "name": "metadata",
                            "dataType": ["object"],
                            "description": "Document metadata"
                        },
                        {
                            "name": "tenant_id",
                            "dataType": ["text"],
                            "description": "Tenant identifier"
                        },
                        {
                            "name": "document_type",
                            "dataType": ["text"],
                            "description": "Type of document"
                        },
                        {
                            "name": "tags",
                            "dataType": ["text[]"],
                            "description": "Document tags"
                        },
                        {
                            "name": "created_at",
                            "dataType": ["date"],
                            "description": "Creation timestamp"
                        },
                        {
                            "name": "updated_at",
                            "dataType": ["date"],
                            "description": "Last update timestamp"
                        }
                    ],
                    "vectorizer": "text2vec-transformers" if not self.embedding_model else "none"
                }
            
            # Create the collection using v4 API with explicit vector index
            collection = self.client.collections.create(
                name=collection_name,
                description=schema.get("description", f"Collection for documents: {collection_name}"),
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(
                        name="title",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document title"
                    ),
                    weaviate.classes.config.Property(
                        name="content",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document content"
                    ),
                    weaviate.classes.config.Property(
                        name="document_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="PostgreSQL document ID"
                    ),
                    weaviate.classes.config.Property(
                        name="tenant_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Tenant identifier"
                    ),
                    weaviate.classes.config.Property(
                        name="document_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Type of document"
                    ),
                    weaviate.classes.config.Property(
                        name="tags",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Document tags"
                    ),
                    weaviate.classes.config.Property(
                        name="created_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Creation timestamp"
                    ),
                    weaviate.classes.config.Property(
                        name="updated_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Last update timestamp"
                    ),
                    # ========== Position properties for PDF annotation ==========
                    weaviate.classes.config.Property(
                        name="page_start",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Start page number (1-indexed)"
                    ),
                    weaviate.classes.config.Property(
                        name="page_end",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="End page number (1-indexed)"
                    ),
                    weaviate.classes.config.Property(
                        name="char_start",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Character start position in full text"
                    ),
                    weaviate.classes.config.Property(
                        name="char_end",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Character end position in full text"
                    ),
                    weaviate.classes.config.Property(
                        name="chunk_index",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Index of this chunk within the document (0-based)"
                    ),
                    # Bbox start coordinates (x0, y0, x1, y1)
                    weaviate.classes.config.Property(
                        name="bbox_start_x0",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Start bbox x0 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_start_y0",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Start bbox y0 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_start_x1",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Start bbox x1 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_start_y1",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Start bbox y1 coordinate"
                    ),
                    # Bbox end coordinates (x0, y0, x1, y1)
                    weaviate.classes.config.Property(
                        name="bbox_end_x0",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="End bbox x0 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_end_y0",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="End bbox y0 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_end_x1",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="End bbox x1 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_end_y1",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="End bbox y1 coordinate"
                    ),
                    # ========== Channel properties for RAG access control ==========
                    weaviate.classes.config.Property(
                        name="channel_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Information channel ID (empty for regular uploads)"
                    ),
                    weaviate.classes.config.Property(
                        name="channel_visibility",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Channel visibility: personal, tenant, or empty for regular docs"
                    ),
                    weaviate.classes.config.Property(
                        name="owner_user_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="User ID who owns this document (for personal channels)"
                    ),
                    weaviate.classes.config.Property(
                        name="source_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document source: upload, gmail, google_drive, external_db"
                    ),
                    weaviate.classes.config.Property(
                        name="external_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="External system identifier for channel documents"
                    ),
                    # ========== Folder hierarchy properties for path-based filtering ==========
                    weaviate.classes.config.Property(
                        name="folder_path",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Full folder path (e.g., /Contracts/ACME/2024)"
                    ),
                    weaviate.classes.config.Property(
                        name="folder_hierarchy",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Array of folder levels [/, /Contracts, /Contracts/ACME]"
                    ),
                    weaviate.classes.config.Property(
                        name="connector_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Connector that indexed this document"
                    ),
                    # ========== ACL properties for document-level access control ==========
                    weaviate.classes.config.Property(
                        name="acl_user_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="User IDs with view access (from ACL system)"
                    ),
                    weaviate.classes.config.Property(
                        name="acl_role_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Role IDs with view access (from ACL system)"
                    ),
                    weaviate.classes.config.Property(
                        name="acl_everyone",
                        data_type=weaviate.classes.config.DataType.BOOL,
                        description="True if accessible to all tenant users (backwards compatible default)"
                    ),
                    # ========== Enrichment properties for multi-signal retrieval ==========
                    weaviate.classes.config.Property(
                        name="domain",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Business domain (e.g., legal, fiscal, medical)",
                        skip_vectorization=True,
                    ),
                    weaviate.classes.config.Property(
                        name="semantic_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Semantic document type (e.g., factura, contrato, nomina)",
                        skip_vectorization=True,
                    ),
                    weaviate.classes.config.Property(
                        name="quality_score",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Document quality score 0.0-1.0 from DocumentIntelligence",
                    ),
                    weaviate.classes.config.Property(
                        name="associated_person",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Person associated via folder hierarchy or entity extraction",
                        skip_vectorization=True,
                    ),
                ]
            )
            result = {"class": collection_name, "status": "created"}
            logger.info(f"✅ Created collection: {collection_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to create collection {collection_name}: {e}")
            raise
    
    # Names of enrichment properties added post-launch — used by migration
    _ENRICHMENT_PROPERTIES = {
        "domain": (weaviate.classes.config.DataType.TEXT, True),
        "semantic_type": (weaviate.classes.config.DataType.TEXT, True),
        "quality_score": (weaviate.classes.config.DataType.NUMBER, False),
        "associated_person": (weaviate.classes.config.DataType.TEXT, True),
        # Parent-Child Chunk Retrieval (Feature 4)
        "parent_chunk_id": (weaviate.classes.config.DataType.TEXT, True),
        "parent_content": (weaviate.classes.config.DataType.TEXT, True),
        "child_index": (weaviate.classes.config.DataType.INT, False),
        # Contextual Retrieval per-chunk context (Feature 2)
        "chunk_context": (weaviate.classes.config.DataType.TEXT, True),
    }

    async def ensure_enrichment_properties(self, collection_name: str) -> None:
        """
        Idempotent migration: add enrichment properties to an existing collection.

        Weaviate v4 supports `collection.config.add_property()` to add new
        properties without recreating the collection. Existing objects get
        the new property with a zero-value default.
        """
        try:
            collection = self.client.collections.get(collection_name)
            existing_props = {p.name for p in collection.config.get().properties}

            for prop_name, (data_type, skip_vec) in self._ENRICHMENT_PROPERTIES.items():
                if prop_name in existing_props:
                    continue
                logger.info(f"🔧 Adding enrichment property '{prop_name}' to {collection_name}")
                kwargs = {
                    "name": prop_name,
                    "data_type": data_type,
                }
                if skip_vec:
                    kwargs["skip_vectorization"] = True
                collection.config.add_property(
                    weaviate.classes.config.Property(**kwargs)
                )
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure enrichment properties on {collection_name}: {e}")

    async def ensure_collection_exists(self, collection_name: str) -> bool:
        """Ensure that a collection exists, create it if it doesn't"""
        try:
            # Check if collection exists
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                logger.info(f"✅ Collection {collection_name} already exists")
                # Migrate: ensure enrichment properties exist on older collections
                await self.ensure_enrichment_properties(collection_name)
                return True

            # Create the collection if it doesn't exist
            logger.info(f"🔧 Creating collection: {collection_name}")
            await self.create_collection(collection_name)
            return True

        except Exception as e:
            logger.error(f"❌ Failed to ensure collection {collection_name} exists: {e}")
            return False

    # =========================================================================
    # KNOWLEDGE GRAPH COLLECTION METHODS
    # =========================================================================

    def get_knowledge_collection_name(self, tenant_id: str) -> str:
        """Get the knowledge collection name for a tenant"""
        # Sanitize tenant_id for collection name (alphanumeric only)
        safe_tenant = ''.join(c for c in tenant_id if c.isalnum())[:32]
        return f"Nouxcube_{safe_tenant}_knowledge"

    async def create_knowledge_collection(self, tenant_id: str) -> Dict[str, Any]:
        """
        Create a knowledge collection for storing extracted entities.

        This collection stores knowledge entities (persons, organizations, clauses, terms, etc.)
        extracted from documents, enabling semantic search over the knowledge graph.
        """
        collection_name = self.get_knowledge_collection_name(tenant_id)

        try:
            # Check if already exists
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                logger.info(f"✅ Knowledge collection {collection_name} already exists")
                return {"class": collection_name, "status": "exists"}

            # Create knowledge collection with specific schema
            collection = self.client.collections.create(
                name=collection_name,
                description=f"Knowledge entities for tenant {tenant_id}",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    # Entity identification
                    weaviate.classes.config.Property(
                        name="entity_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="PostgreSQL entity UUID"
                    ),
                    weaviate.classes.config.Property(
                        name="entity_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Type: person, organization, clause, term, date, amount, location"
                    ),
                    weaviate.classes.config.Property(
                        name="entity_value",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Normalized entity value"
                    ),
                    weaviate.classes.config.Property(
                        name="entity_label",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Human-readable label"
                    ),
                    # Context for embedding
                    weaviate.classes.config.Property(
                        name="context_text",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Context text for semantic embedding"
                    ),
                    # Domain and source
                    weaviate.classes.config.Property(
                        name="domain",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Domain: legal, fiscal, hr, general"
                    ),
                    weaviate.classes.config.Property(
                        name="source_document_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Source document UUID"
                    ),
                    weaviate.classes.config.Property(
                        name="confidence",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Extraction confidence 0.0-1.0"
                    ),
                    # Related entities (denormalized for fast search)
                    weaviate.classes.config.Property(
                        name="related_entity_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Related entity UUIDs"
                    ),
                    weaviate.classes.config.Property(
                        name="related_document_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Related document UUIDs"
                    ),
                    # Metadata
                    weaviate.classes.config.Property(
                        name="tenant_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Tenant identifier"
                    ),
                    weaviate.classes.config.Property(
                        name="attributes",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="JSON-encoded additional attributes"
                    ),
                    weaviate.classes.config.Property(
                        name="created_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Creation timestamp"
                    ),
                    # ACL (inherited from source document)
                    weaviate.classes.config.Property(
                        name="acl_user_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="User IDs with access"
                    ),
                    weaviate.classes.config.Property(
                        name="acl_role_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Role IDs with access"
                    ),
                    weaviate.classes.config.Property(
                        name="acl_everyone",
                        data_type=weaviate.classes.config.DataType.BOOL,
                        description="Public access flag"
                    ),
                ]
            )

            result = {"class": collection_name, "status": "created"}
            logger.info(f"✅ Created knowledge collection: {collection_name}")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to create knowledge collection {collection_name}: {e}")
            raise

    async def add_knowledge_entity(
        self,
        tenant_id: str,
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
        acl_user_ids: Optional[List[str]] = None,
        acl_role_ids: Optional[List[str]] = None,
        acl_everyone: bool = False
    ) -> str:
        """
        Add a knowledge entity to Weaviate for semantic search.

        Returns the Weaviate object UUID (embedding_id to store in PostgreSQL).
        """
        collection_name = self.get_knowledge_collection_name(tenant_id)

        # Ensure collection exists
        await self.create_knowledge_collection(tenant_id)

        try:
            collection = self.client.collections.get(collection_name)

            # Generate embedding from context text
            embedding = await generate_embedding(context_text)

            # Prepare entity data
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
                "tenant_id": tenant_id,
                "attributes": json.dumps(attributes or {}),
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "acl_user_ids": acl_user_ids or [],
                "acl_role_ids": acl_role_ids or [],
                "acl_everyone": acl_everyone,
            }

            # Add to Weaviate with embedding
            weaviate_uuid = collection.data.insert(
                properties=entity_data,
                vector=embedding
            )

            logger.info(f"✅ Added knowledge entity {entity_id} ({entity_type}) to Weaviate: {weaviate_uuid}")
            return str(weaviate_uuid)

        except Exception as e:
            logger.error(f"❌ Failed to add knowledge entity: {e}")
            raise

    async def search_knowledge_entities(
        self,
        tenant_id: str,
        query: str,
        entity_types: Optional[List[str]] = None,
        domain: Optional[str] = None,
        limit: int = 10,
        min_certainty: float = 0.5,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge entities semantically.

        Supports filtering by entity_type, domain, and ACL.
        """
        collection_name = self.get_knowledge_collection_name(tenant_id)

        try:
            # Check collection exists
            collections = await self.list_collections()
            if collection_name not in collections and collection_name.capitalize() not in collections:
                logger.warning(f"Knowledge collection {collection_name} does not exist")
                return []

            collection = self.client.collections.get(collection_name)

            # Generate query embedding
            query_embedding = await generate_embedding(query)

            # Build filters
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

            # ACL filtering (if not admin)
            if not is_admin and (user_id or user_role_ids):
                acl_filters = [
                    weaviate.classes.query.Filter.by_property("acl_everyone").equal(True)
                ]
                if user_id:
                    acl_filters.append(
                        weaviate.classes.query.Filter.by_property("acl_user_ids").contains_any([user_id])
                    )
                if user_role_ids:
                    acl_filters.append(
                        weaviate.classes.query.Filter.by_property("acl_role_ids").contains_any(user_role_ids)
                    )
                filters.append(weaviate.classes.query.Filter.any_of(acl_filters))

            # Combine filters
            combined_filter = None
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f

            # Execute search
            response = collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                certainty=min_certainty,
                filters=combined_filter,
                return_metadata=weaviate.classes.query.MetadataQuery(certainty=True, distance=True)
            )

            # Format results
            results = []
            for obj in response.objects:
                import json
                result = {
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
                }
                results.append(result)

            logger.info(f"🔍 Knowledge search returned {len(results)} entities for query: {query[:50]}...")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to search knowledge entities: {e}")
            return []

    async def delete_knowledge_entity(self, tenant_id: str, entity_id: str) -> bool:
        """Delete a knowledge entity from Weaviate by its PostgreSQL entity_id"""
        collection_name = self.get_knowledge_collection_name(tenant_id)

        try:
            collection = self.client.collections.get(collection_name)

            # Find and delete by entity_id
            response = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("entity_id").equal(entity_id),
                limit=1
            )

            if response.objects:
                collection.data.delete_by_id(response.objects[0].uuid)
                logger.info(f"✅ Deleted knowledge entity {entity_id} from Weaviate")
                return True

            logger.warning(f"⚠️ Knowledge entity {entity_id} not found in Weaviate")
            return False

        except Exception as e:
            logger.error(f"❌ Failed to delete knowledge entity {entity_id}: {e}")
            return False

    async def delete_knowledge_by_document(self, tenant_id: str, document_id: str) -> int:
        """Delete all knowledge entities from a specific document"""
        collection_name = self.get_knowledge_collection_name(tenant_id)

        try:
            collection = self.client.collections.get(collection_name)

            # Find all entities from this document
            response = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("source_document_id").equal(document_id),
                limit=1000
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

    def get_visual_collection_name(self, tenant_id: str) -> str:
        """Get the visual content collection name for a tenant"""
        safe_tenant = ''.join(c for c in tenant_id if c.isalnum())[:32]
        return f"Nouxcube_{safe_tenant}_visual"

    async def create_visual_collection(self, tenant_id: str) -> Dict[str, Any]:
        """
        Create a visual content collection for storing multimodal embeddings.

        This collection stores visual elements (images, tables, diagrams) extracted
        from documents, enabling cross-modal search (text-to-image, image-to-text).

        Schema includes:
        - Visual content metadata (type, page, bbox)
        - Caption/description for multimodal context
        - ACL properties inherited from source document
        """
        collection_name = self.get_visual_collection_name(tenant_id)

        try:
            # Check if already exists
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                logger.info(f"✅ Visual collection {collection_name} already exists")
                return {"class": collection_name, "status": "exists"}

            # Create visual collection with multimodal-specific schema
            collection = self.client.collections.create(
                name=collection_name,
                description=f"Visual content embeddings for tenant {tenant_id}",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    # Visual content identification
                    weaviate.classes.config.Property(
                        name="visual_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Unique visual content identifier"
                    ),
                    weaviate.classes.config.Property(
                        name="content_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Type: image, table_image, diagram, page_thumbnail"
                    ),
                    weaviate.classes.config.Property(
                        name="caption",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Text caption/description for multimodal context"
                    ),
                    # Source document reference
                    weaviate.classes.config.Property(
                        name="document_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Source document UUID"
                    ),
                    weaviate.classes.config.Property(
                        name="tenant_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Tenant identifier"
                    ),
                    # Position in document
                    weaviate.classes.config.Property(
                        name="page_number",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Page number (0-indexed)"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_x0",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Bounding box x0 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_y0",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Bounding box y0 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_x1",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Bounding box x1 coordinate"
                    ),
                    weaviate.classes.config.Property(
                        name="bbox_y1",
                        data_type=weaviate.classes.config.DataType.NUMBER,
                        description="Bounding box y1 coordinate"
                    ),
                    # Visual dimensions
                    weaviate.classes.config.Property(
                        name="width",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Image width in pixels"
                    ),
                    weaviate.classes.config.Property(
                        name="height",
                        data_type=weaviate.classes.config.DataType.INT,
                        description="Image height in pixels"
                    ),
                    # Embedding metadata
                    weaviate.classes.config.Property(
                        name="embedding_model",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Model used for embedding: bge-m3, Qwen3-VL-2B, etc."
                    ),
                    weaviate.classes.config.Property(
                        name="detection_method",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="How visual was detected: embedded, ruled, shapes, etc."
                    ),
                    # Timestamps
                    weaviate.classes.config.Property(
                        name="created_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Creation timestamp"
                    ),
                    # ACL (inherited from source document)
                    weaviate.classes.config.Property(
                        name="acl_user_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="User IDs with access"
                    ),
                    weaviate.classes.config.Property(
                        name="acl_role_ids",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Role IDs with access"
                    ),
                    weaviate.classes.config.Property(
                        name="acl_everyone",
                        data_type=weaviate.classes.config.DataType.BOOL,
                        description="Public access flag"
                    ),
                    # Channel access (inherited from source document)
                    weaviate.classes.config.Property(
                        name="channel_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Information channel ID"
                    ),
                    weaviate.classes.config.Property(
                        name="channel_visibility",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Channel visibility: personal, tenant"
                    ),
                    weaviate.classes.config.Property(
                        name="owner_user_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Owner user ID"
                    ),
                ]
            )

            result = {"class": collection_name, "status": "created"}
            logger.info(f"✅ Created visual collection: {collection_name}")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to create visual collection {collection_name}: {e}")
            raise

    async def add_visual_content(
        self,
        tenant_id: str,
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
        acl_user_ids: Optional[List[str]] = None,
        acl_role_ids: Optional[List[str]] = None,
        acl_everyone: bool = True,
        channel_id: str = "",
        channel_visibility: str = "",
        owner_user_id: str = "",
    ) -> str:
        """
        Add a visual content embedding to Weaviate.

        Args:
            tenant_id: Tenant identifier
            document_id: Source document UUID
            visual_id: Unique identifier for this visual
            content_type: Type of visual (image, table_image, diagram, page_thumbnail)
            embedding: Pre-computed embedding vector (1024 dims from Qwen3-VL)
            page_number: Page number in source document (0-indexed)
            bbox: Bounding box (x0, y0, x1, y1) in PDF coordinates
            caption: Text caption/description for multimodal context
            width: Image width in pixels
            height: Image height in pixels
            embedding_model: Model used for embedding
            detection_method: How the visual was detected
            acl_*: Access control lists (inherited from source document)
            channel_*: Channel access (inherited from source document)

        Returns:
            Weaviate object UUID
        """
        collection_name = self.get_visual_collection_name(tenant_id)

        # Ensure collection exists
        await self.create_visual_collection(tenant_id)

        try:
            collection = self.client.collections.get(collection_name)

            # Prepare visual data
            visual_data = {
                "visual_id": visual_id,
                "content_type": content_type,
                "caption": caption or "",
                "document_id": document_id,
                "tenant_id": tenant_id,
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
                "acl_user_ids": acl_user_ids or [],
                "acl_role_ids": acl_role_ids or [],
                "acl_everyone": acl_everyone,
                "channel_id": channel_id,
                "channel_visibility": channel_visibility,
                "owner_user_id": owner_user_id,
            }

            # Insert with pre-computed embedding
            result = collection.data.insert(
                properties=visual_data,
                uuid=visual_id,
                vector=embedding
            )

            logger.debug(f"✅ Added visual content {visual_id} ({content_type}) to {collection_name}")
            return visual_id

        except Exception as e:
            logger.error(f"❌ Failed to add visual content {visual_id}: {e}")
            raise

    async def search_visual_content(
        self,
        tenant_id: str,
        query_vector: List[float],
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        limit: int = 10,
        certainty: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search for visual content using vector similarity.

        Supports cross-modal search: query with text embedding to find images,
        or query with image embedding to find related visuals.

        Args:
            tenant_id: Tenant identifier
            query_vector: Query embedding (1024 dims)
            user_id: Current user ID for ACL filtering
            user_role_ids: User's role IDs for ACL filtering
            content_types: Filter by content types (image, table_image, diagram)
            document_ids: Filter by specific documents
            limit: Maximum results
            certainty: Minimum similarity threshold

        Returns:
            List of visual content results with metadata
        """
        collection_name = self.get_visual_collection_name(tenant_id)

        try:
            collection = self.client.collections.get(collection_name)

            # Build filters
            filters = weaviate.classes.query.Filter.by_property("tenant_id").equal(tenant_id)

            # Add ACL filter if user_id provided
            if user_id:
                acl_filter = self._build_document_access_filter(user_id, user_role_ids)
                filters = filters & acl_filter

            # Add content type filter
            if content_types:
                type_filter = None
                for ct in content_types:
                    cf = weaviate.classes.query.Filter.by_property("content_type").equal(ct)
                    type_filter = cf if type_filter is None else type_filter | cf
                filters = filters & type_filter

            # Add document filter
            if document_ids:
                doc_filter = None
                for doc_id in document_ids:
                    df = weaviate.classes.query.Filter.by_property("document_id").equal(doc_id)
                    doc_filter = df if doc_filter is None else doc_filter | df
                filters = filters & doc_filter

            # Execute vector search
            response = collection.query.near_vector(
                near_vector=query_vector,
                filters=filters,
                limit=limit,
                certainty=certainty,
                return_metadata=weaviate.classes.query.MetadataQuery(
                    certainty=True,
                    distance=True
                )
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

            logger.info(f"✅ Found {len(results)} visual results for tenant {tenant_id}")
            return results

        except Exception as e:
            logger.error(f"❌ Visual search failed for tenant {tenant_id}: {e}")
            return []

    async def delete_visual_by_document(self, tenant_id: str, document_id: str) -> int:
        """Delete all visual content from a specific document"""
        collection_name = self.get_visual_collection_name(tenant_id)

        try:
            collection = self.client.collections.get(collection_name)

            # Find all visuals from this document
            response = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("document_id").equal(document_id),
                limit=1000
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
        """
        Fetch specific chunks by document_id and chunk_indices.

        Used for chunk expansion in Long Context RAG to retrieve
        adjacent chunks and preserve context across boundaries.

        Args:
            collection_name: Weaviate collection name
            document_id: Parent document ID
            chunk_indices: List of chunk indices to fetch

        Returns:
            List of chunk dictionaries with content and metadata
        """
        if not chunk_indices:
            return []

        try:
            collection = self.client.collections.get(collection_name)

            # Build filter for document_id
            doc_filter = weaviate.classes.query.Filter.by_property("document_id").equal(document_id)

            # Fetch all chunks for this document (we'll filter by index in Python)
            # This is more efficient than multiple Weaviate queries for small expand_size
            response = collection.query.fetch_objects(
                filters=doc_filter,
                limit=100,  # Max chunks per document we'll scan
                return_properties=["content", "chunk_index", "document_id", "title"],
            )

            # Filter to requested indices
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

            logger.debug(
                f"  Fetched {len(results)} adjacent chunks for document {document_id}"
            )
            return results

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch chunks by indices: {e}")
            return []

    async def fetch_objects_by_ids(
        self,
        collection_name: str,
        object_ids: List[str],
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Fetch multiple objects by their UUIDs (for cache support).

        This is optimized for retrieval cache hits where we already know
        which documents we need. Much faster than re-running vector search.

        Args:
            collection_name: Weaviate collection name
            object_ids: List of object UUIDs to fetch

        Returns:
            List of object dictionaries (None for not-found objects)
        """
        if not object_ids:
            return []

        try:
            collection = self.client.collections.get(collection_name)
            results: List[Optional[Dict[str, Any]]] = []

            # Batch fetch in chunks of 100
            batch_size = 100
            for i in range(0, len(object_ids), batch_size):
                batch_ids = object_ids[i:i + batch_size]

                for obj_id in batch_ids:
                    try:
                        # Fetch single object by UUID
                        obj = collection.query.fetch_object_by_id(
                            uuid=obj_id,
                            return_properties=[
                                "content", "title", "document_type", "tenant_id",
                                "chunk_index", "total_chunks", "document_id",
                                "folder_path", "file_type", "created_at"
                            ],
                        )
                        if obj:
                            results.append({
                                "uuid": str(obj.uuid),
                                "content": obj.properties.get("content", ""),
                                "title": obj.properties.get("title", ""),
                                "document_type": obj.properties.get("document_type"),
                                "tenant_id": obj.properties.get("tenant_id"),
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

    async def add_document(self, collection_name: str, document: DocumentCreate) -> DocumentResponse:
        """
        Add a document to Weaviate.

        If document.chunks is provided, stores each chunk as a separate Weaviate object
        for fine-grained RAG retrieval. Otherwise, stores the document as a single object.

        This enables:
        - Full indexing of long documents (100+ pages)
        - Precise chunk-level retrieval for RAG
        - folder_path filtering at chunk level
        """
        try:
            # Ensure collection exists before adding document
            if not await self.ensure_collection_exists(collection_name):
                raise Exception(f"Could not create or access collection: {collection_name}")

            # Generate ID if not provided
            doc_id = document.id or str(uuid.uuid4())

            # Get collection using v4 API
            collection = self.client.collections.get(collection_name)

            # Common properties for all objects (document or chunks)
            base_properties = {
                "document_id": doc_id,
                "title": document.title,
                "tenant_id": document.tenant_id,
                "document_type": document.document_type or "document",
                "tags": document.tags or [],
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                # Channel properties
                "channel_id": getattr(document, 'channel_id', '') or '',
                "channel_visibility": getattr(document, 'channel_visibility', '') or '',
                "owner_user_id": getattr(document, 'owner_user_id', '') or '',
                "source_type": getattr(document, 'source_type', 'upload') or 'upload',
                "external_id": getattr(document, 'external_id', '') or '',
                # Folder hierarchy for path-based filtering
                "folder_path": getattr(document, 'folder_path', '') or '',
                "folder_hierarchy": getattr(document, 'folder_hierarchy', []) or [],
                "connector_id": getattr(document, 'connector_id', '') or '',
                # ACL properties
                "acl_user_ids": getattr(document, 'acl_user_ids', []) or [],
                "acl_role_ids": getattr(document, 'acl_role_ids', []) or [],
                "acl_everyone": getattr(document, 'acl_everyone', True),
                # Enrichment properties for multi-signal retrieval
                "domain": getattr(document, 'domain', '') or '',
                "semantic_type": getattr(document, 'semantic_type', '') or '',
                "quality_score": float(getattr(document, 'quality_score', 0.0) or 0.0),
                "associated_person": getattr(document, 'associated_person', '') or '',
            }

            # Check if we have chunks to store individually
            chunks = getattr(document, 'chunks', None) or []

            if chunks and len(chunks) > 0:
                # ====== CHUNK-LEVEL STORAGE ======
                # Store each chunk as a separate Weaviate object for fine-grained RAG
                logger.info(f"📦 Storing {len(chunks)} chunks for document {doc_id}")

                # First, delete any existing chunks for this document (in case of re-indexing)
                await self._delete_document_chunks(collection_name, doc_id)

                # Prepare batch objects for all chunks
                batch_objects = []

                for chunk in chunks:
                    chunk_content = chunk.get("content", "")
                    chunk_metadata = chunk.get("metadata", {})
                    chunk_index = chunk.get("chunk_index", 0)

                    # Generate unique UUID for this chunk
                    chunk_uuid = str(uuid.uuid4())

                    # Build chunk properties - inherit from base and add chunk-specific
                    chunk_properties = {
                        **base_properties,
                        "content": chunk_content,
                        # Position properties from chunk metadata
                        "chunk_index": chunk_index,
                        "char_start": chunk_metadata.get("char_start", 0),
                        "char_end": chunk_metadata.get("char_end", 0),
                        "page_start": chunk_metadata.get("page_start", 0),
                        "page_end": chunk_metadata.get("page_end", 0),
                        # Override folder fields if chunk has its own (shouldn't differ, but be safe)
                        "folder_path": chunk_metadata.get("folder_path") or base_properties["folder_path"],
                        "folder_hierarchy": chunk_metadata.get("folder_hierarchy") or base_properties["folder_hierarchy"],
                        "connector_id": chunk_metadata.get("connector_id") or base_properties["connector_id"],
                        # Enrichment: propagate from chunk metadata or fall back to base
                        "domain": chunk_metadata.get("domain", "") or base_properties.get("domain", ""),
                        "semantic_type": chunk_metadata.get("semantic_type", "") or base_properties.get("semantic_type", ""),
                        "quality_score": float(chunk_metadata.get("quality_score", 0.0) or base_properties.get("quality_score", 0.0)),
                        "associated_person": chunk_metadata.get("associated_person", "") or base_properties.get("associated_person", ""),
                        # Parent-Child Chunk Retrieval (Feature 4)
                        "parent_chunk_id": chunk_metadata.get("parent_chunk_id", ""),
                        "parent_content": chunk_metadata.get("parent_content", ""),
                        "child_index": chunk_metadata.get("child_index", 0),
                        # Contextual Retrieval per-chunk context (Feature 2)
                        "chunk_context": chunk_metadata.get("chunk_context", ""),
                    }

                    # Generate embedding for chunk
                    embedding_vector = None
                    if self.embedding_model:
                        try:
                            text_to_embed = f"{document.title} {chunk_content}"
                            embedding_vector = await generate_embedding(text_to_embed)
                        except Exception as e:
                            logger.warning(f"⚠️ Could not generate chunk embedding: {e}")

                    if embedding_vector:
                        batch_objects.append(weaviate.classes.data.DataObject(
                            properties=chunk_properties,
                            uuid=chunk_uuid,
                            vector=embedding_vector
                        ))
                    else:
                        batch_objects.append(weaviate.classes.data.DataObject(
                            properties=chunk_properties,
                            uuid=chunk_uuid
                        ))

                # Batch insert all chunks
                if batch_objects:
                    try:
                        collection.data.insert_many(batch_objects)
                        logger.info(f"✅ Inserted {len(batch_objects)} chunks for document {doc_id}")
                    except Exception as e:
                        logger.error(f"❌ Batch chunk insert failed: {e}")
                        raise

                # Return response with first chunk content preview
                first_chunk_content = chunks[0].get("content", "")[:500] if chunks else ""

                return DocumentResponse(
                    id=doc_id,
                    title=document.title,
                    content=first_chunk_content + f"... [{len(chunks)} chunks total]",
                    metadata={"chunk_count": len(chunks)},
                    tenant_id=document.tenant_id,
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
                # ====== SINGLE DOCUMENT STORAGE ======
                # No chunks - store as single document (legacy/upload flow)
                doc_data = {
                    **base_properties,
                    "content": document.content,
                }

                # Generate embedding for document
                embedding_vector = None
                if self.embedding_model:
                    try:
                        text_to_embed = f"{document.title} {document.content}"
                        embedding_vector = await generate_embedding(text_to_embed)
                        if embedding_vector:
                            logger.info(f"🧮 Generated embedding vector of size {len(embedding_vector)}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate embedding: {e}")

                # Insert document; if it exists already, replace it
                try:
                    if embedding_vector:
                        result = collection.data.insert(
                            properties=doc_data,
                            uuid=doc_id,
                            vector=embedding_vector
                        )
                    else:
                        result = collection.data.insert(
                            properties=doc_data,
                            uuid=doc_id
                        )
                    logger.info(f"✅ Inserted document {doc_id} to {collection_name}")
                except UnexpectedStatusCodeException as exc:
                    if exc.status_code == 422 and "already exists" in str(exc):
                        logger.info(f"♻️ Document {doc_id} already exists, replacing")
                        if embedding_vector:
                            result = collection.data.replace(
                                properties=doc_data,
                                uuid=doc_id,
                                vector=embedding_vector
                            )
                        else:
                            result = collection.data.replace(
                                properties=doc_data,
                                uuid=doc_id
                            )
                        logger.info(f"✅ Replaced document {doc_id}")
                    else:
                        raise

                return DocumentResponse(
                    id=doc_id,
                    title=document.title,
                    content=document.content,
                    metadata={},
                    tenant_id=document.tenant_id,
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
        """
        Delete all chunks belonging to a document before re-indexing.

        Returns the number of chunks deleted.
        """
        try:
            collection = self.client.collections.get(collection_name)

            # Find all objects with this document_id
            Filter = weaviate.classes.query.Filter
            doc_filter = Filter.by_property("document_id").equal(document_id)

            result = collection.query.fetch_objects(
                filters=doc_filter,
                limit=1000,  # Max chunks we expect per document
                return_properties=["document_id"]
            )

            if not result.objects:
                return 0

            # Delete each chunk
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

    async def delete_document(self, collection_name: str, document_id: str) -> bool:
        """
        Delete a document from Weaviate collection by its document_id property.

        Note: document_id is the PostgreSQL UUID stored as a property, not the Weaviate UUID.
        We need to find the Weaviate object by its document_id property and then delete it.

        Args:
            collection_name: Name of the Weaviate collection
            document_id: The PostgreSQL document UUID (stored in document_id property)

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist, nothing to delete")
                return True  # Consider it success if collection doesn't exist

            collection = self.client.collections.get(collection_name)

            # Find the object by document_id property
            Filter = weaviate.classes.query.Filter
            doc_filter = Filter.by_property("document_id").equal(document_id)

            # Query to find the object
            result = collection.query.fetch_objects(
                filters=doc_filter,
                limit=1,
                return_properties=["document_id"]
            )

            if not result.objects:
                logger.warning(f"⚠️ Document {document_id} not found in {collection_name}")
                return True  # Consider it success if document doesn't exist

            # Get the Weaviate UUID and delete
            weaviate_uuid = result.objects[0].uuid
            collection.data.delete_by_id(weaviate_uuid)

            logger.info(f"✅ Deleted document {document_id} (weaviate_uuid: {weaviate_uuid}) from {collection_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete document {document_id} from {collection_name}: {e}")
            return False

    async def search_documents(self, collection_name: str, search_request: SearchRequest) -> SearchResponse:
        """Search documents in Weaviate"""
        try:
            start_time = datetime.now()

            # Ensure client is initialized
            await self.initialize()

            # Return empty results if collection doesn't exist (new tenant, no docs)
            if not self.client.collections.exists(collection_name):
                logger.info(f"📭 Collection {collection_name} does not exist, returning empty results")
                return SearchResponse(
                    query=search_request.query,
                    results=[],
                    total_results=0,
                    search_time_ms=0,
                    search_type=search_request.search_type or "hybrid",
                    tenant_id=search_request.tenant_id,
                )

            # Get collection for search using v4 API
            collection = self.client.collections.get(collection_name)
            
            # Build filters for tenant isolation using v4 API
            tenant_filter = weaviate.classes.query.Filter.by_property("tenant_id").equal(search_request.tenant_id)

            # Apply access control if user_id is provided
            # Three modes depending on include_channels flag:
            # 1. include_channels=True (default): Combined channel + document ACL filter
            #    - Requires channel_id, owner_user_id properties in collection schema
            #    - Full access control for collections with channel support
            # 2. include_channels=False: Skip access filters entirely
            #    - For collections without ACL properties (owner_user_id, channel_id, etc.)
            #    - Relies on tenant_id isolation only
            #    - Safe for legacy collections with basic properties
            include_channels = getattr(search_request, 'include_channels', True)
            is_admin = getattr(search_request, 'is_admin', False)

            if is_admin:
                # Admin users bypass ACL checks - only tenant isolation
                combined_filters = tenant_filter
            elif search_request.user_id and include_channels:
                # Full combined filter (channel + ACL) - requires ACL properties in schema
                access_filter = self._build_combined_access_filter(
                    user_id=search_request.user_id,
                    user_role_ids=search_request.user_role_ids
                )
                combined_filters = tenant_filter & access_filter
            else:
                # Skip access filter - tenant isolation only
                # Used when:
                # - No user_id provided (anonymous/system access)
                # - include_channels=False (collection lacks ACL properties)
                combined_filters = tenant_filter

            # Add additional filters if provided
            if search_request.filters:
                for key, value in search_request.filters.items():
                    additional_filter = self._build_property_filter(key, value)
                    if additional_filter is not None:
                        combined_filters = combined_filters & additional_filter

            # Add folder hierarchy filters for path-based RAG queries
            Filter = weaviate.classes.query.Filter

            # Exact folder path match
            folder_path = getattr(search_request, 'folder_path', None)
            if folder_path:
                folder_filter = Filter.by_property("folder_path").equal(folder_path)
                combined_filters = combined_filters & folder_filter
                logger.debug(f"📁 Filtering by exact folder_path: {folder_path}")

            # Folder hierarchy contains (documents in folder or any subfolder)
            folder_hierarchy_contains = getattr(search_request, 'folder_hierarchy_contains', None)
            if folder_hierarchy_contains:
                # folder_hierarchy is an array like ["/", "/Contracts", "/Contracts/ACME"]
                # We filter for documents where the hierarchy contains this path
                hierarchy_filter = Filter.by_property("folder_hierarchy").contains_any([folder_hierarchy_contains])
                combined_filters = combined_filters & hierarchy_filter
                logger.debug(f"📁 Filtering by folder_hierarchy_contains: {folder_hierarchy_contains}")

            # ========== Enrichment filters for multi-signal retrieval ==========
            # Check which enrichment properties exist in the schema to avoid
            # GRPC errors on collections that haven't been migrated yet.
            try:
                _cfg = collection.config.get()
                _schema_props = {p.name for p in _cfg.properties}
            except Exception:
                _schema_props = set()

            domain_filter = getattr(search_request, 'domain_filter', None)
            if domain_filter and "domain" in _schema_props:
                combined_filters = combined_filters & Filter.by_property("domain").equal(domain_filter)
                logger.debug(f"🏷️ Filtering by domain: {domain_filter}")

            semantic_type_filter = getattr(search_request, 'semantic_type_filter', None)
            if semantic_type_filter:
                if "semantic_type" in _schema_props:
                    combined_filters = combined_filters & Filter.by_property("semantic_type").equal(semantic_type_filter)
                    logger.debug(f"🏷️ Filtering by semantic_type: {semantic_type_filter}")
                else:
                    logger.warning(f"⚠️ semantic_type_filter={semantic_type_filter} requested but 'semantic_type' not in schema props: {sorted(_schema_props)}")

            person_filter = getattr(search_request, 'person_filter', None)
            if person_filter:
                # Match person against BOTH associated_person AND folder_path
                # (associated_person is often empty; folder_path like "/Javier Martinez/" is reliable)
                person_conditions = []
                if "associated_person" in _schema_props:
                    person_conditions.append(
                        Filter.by_property("associated_person").like(f"*{person_filter}*")
                    )
                person_conditions.append(
                    Filter.by_property("folder_path").like(f"*{person_filter}*")
                )
                if len(person_conditions) == 2:
                    combined_filters = combined_filters & (person_conditions[0] | person_conditions[1])
                else:
                    combined_filters = combined_filters & person_conditions[0]
                logger.debug(f"👤 Filtering by person (associated_person OR folder_path): {person_filter}")

            min_quality = getattr(search_request, 'min_quality', None)
            if min_quality is not None and "quality_score" in _schema_props:
                combined_filters = combined_filters & Filter.by_property("quality_score").greater_or_equal(min_quality)
                logger.debug(f"⭐ Filtering by min_quality: {min_quality}")

            # ========== Temporal filters ==========
            date_from = getattr(search_request, 'date_from', None)
            if date_from and "created_at" in _schema_props:
                from datetime import datetime as dt
                try:
                    parsed = dt.fromisoformat(date_from)
                    combined_filters = combined_filters & Filter.by_property("created_at").greater_or_equal(parsed)
                    logger.debug(f"📅 Filtering by date_from: {date_from}")
                except ValueError:
                    logger.warning(f"⚠️ Invalid date_from format: {date_from}")

            date_to = getattr(search_request, 'date_to', None)
            if date_to and "created_at" in _schema_props:
                from datetime import datetime as dt
                try:
                    parsed = dt.fromisoformat(date_to)
                    combined_filters = combined_filters & Filter.by_property("created_at").less_or_equal(parsed)
                    logger.debug(f"📅 Filtering by date_to: {date_to}")
                except ValueError:
                    logger.warning(f"⚠️ Invalid date_to format: {date_to}")

            # Execute search based on type using v4 API
            if search_request.search_type == "vector":
                # Generate embedding for query using configured provider
                query_embedding = None
                if self.embedding_model:
                    try:
                        query_embedding = await generate_embedding(search_request.query)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate query embedding: {e}")
                
                if query_embedding:
                    # Vector search with near_vector using generated embedding
                    response = collection.query.near_vector(
                        near_vector=query_embedding,
                        limit=search_request.limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(certainty=True, score=True),
                        filters=combined_filters
                    )
                else:
                    # Fall back to BM25 keyword search if no embeddings available
                    response = collection.query.bm25(
                        query=search_request.query,
                        limit=search_request.limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                        filters=combined_filters
                    )
            elif search_request.search_type == "keyword":
                # BM25 keyword search
                response = collection.query.bm25(
                    query=search_request.query,
                    limit=search_request.limit,
                    return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                    filters=combined_filters
                )
            else:  # hybrid
                # Detect if collection has a vector index — if not, skip vector
                _has_vectors = _cfg.vector_index_type is not None if _cfg else False
                if not _has_vectors:
                    logger.warning(f"⚠️ Collection {collection_name} has no vector index. Re-sync connectors to enable hybrid search.")

                # Hybrid search requires both vector and keyword
                query_embedding = None
                if _has_vectors and self.embedding_model:
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
                        alpha=effective_alpha,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True, explain_score=True),
                        filters=combined_filters
                    )
                else:
                    # Fall back to BM25 if no embeddings or no vector index
                    response = collection.query.bm25(
                        query=search_request.query,
                        limit=search_request.limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                        filters=combined_filters
                    )

            # ── Filter-only fallback ──────────────────────────────────
            # BM25 uses word tokenization without stemming, so "facturas"
            # won't match "factura". When enrichment filters are active
            # (semantic_type, person, domain) and the keyword search returns
            # 0 results, retry with a filter-only fetch so that metadata
            # filtering still returns relevant documents.
            _has_enrichment = any([
                getattr(search_request, 'semantic_type_filter', None),
                getattr(search_request, 'person_filter', None),
                getattr(search_request, 'domain_filter', None),
            ])
            if len(response.objects) == 0 and _has_enrichment:
                logger.info("🔄 BM25 returned 0 with enrichment filters — retrying with filter-only fetch")
                response = collection.query.fetch_objects(
                    limit=search_request.limit,
                    filters=combined_filters,
                    return_metadata=weaviate.classes.query.MetadataQuery(creation_time=True),
                )
                logger.info(f"🔄 Filter-only fetch: {len(response.objects)} objects returned")

            # Process results using v4 response format
            documents = []
            for item in response.objects:
                # Extract similarity score from metadata
                similarity = None
                if hasattr(item, 'metadata') and item.metadata:
                    similarity = getattr(item.metadata, 'certainty', None) or getattr(item.metadata, 'score', None)
                
                # Handle datetime parsing safely
                created_at = datetime.now()
                updated_at = datetime.now()
                
                if item.properties.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(item.properties["created_at"])
                    except:
                        pass
                        
                if item.properties.get("updated_at"):
                    try:
                        updated_at = datetime.fromisoformat(item.properties["updated_at"])
                    except:
                        pass
                
                doc = DocumentResponse(
                    id=item.properties.get("document_id", str(item.uuid) if item.uuid else ""),  # Use PostgreSQL document_id
                    title=item.properties.get("title", ""),
                    content=item.properties.get("content", ""),
                    metadata=item.properties.get("metadata", {}),
                    tenant_id=item.properties.get("tenant_id", ""),
                    document_type=item.properties.get("document_type", ""),
                    tags=item.properties.get("tags", []),
                    created_at=created_at,
                    updated_at=updated_at,
                    similarity_score=similarity,
                    # Folder hierarchy fields for path-based filtering
                    folder_path=item.properties.get("folder_path", ""),
                    folder_hierarchy=item.properties.get("folder_hierarchy", []),
                    connector_id=item.properties.get("connector_id", ""),
                    # Enrichment properties for multi-signal retrieval
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
                tenant_id=search_request.tenant_id
            )
            
        except Exception as e:
            logger.error(f"❌ Search failed in {collection_name}: {e}")
            raise

    async def get_document_by_id(self, collection_name: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific document by its PostgreSQL document ID"""
        try:
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return None

            collection = self.client.collections.get(collection_name)

            # Search for document by document_id property
            import weaviate.classes.query as wq
            response = collection.query.fetch_objects(
                filters=wq.Filter.by_property("document_id").equal(document_id),
                limit=1
            )

            if response.objects and len(response.objects) > 0:
                item = response.objects[0]
                return {
                    "id": item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                    "title": item.properties.get("title", ""),
                    "content": item.properties.get("content", ""),
                    "metadata": item.properties.get("metadata", {}),
                    "tenant_id": item.properties.get("tenant_id", ""),
                    "document_type": item.properties.get("document_type", ""),
                    "tags": item.properties.get("tags", [])
                }

            logger.warning(f"⚠️ Document {document_id} not found in {collection_name}")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document {document_id}: {e}")
            return None

    async def get_document_by_id_across_collections(
        self,
        tenant_id: str,
        document_id: str,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get a document by ID, searching across all tenant collections in parallel.

        This method searches in:
        - Main document collection (uploaded files)
        - All channel collections (Gmail, Google Drive, etc.)

        SECURITY: When user_id is provided, applies document-level ACL verification:
        - Admin users bypass ACL checks (see all documents)
        - Owner (owner_user_id == user_id) always has access
        - User explicitly in acl_user_ids has access
        - User's role in acl_role_ids has access
        - Document with acl_everyone=true is accessible to all
        - Legacy documents without ACL (empty owner_user_id) are accessible

        Additionally applies channel access control:
        - Regular uploads (no channel) use ACL
        - Tenant-wide channels (visibility="tenant") are accessible to all tenant users
        - Personal channels (visibility="personal") are only accessible to the owner

        OPTIMIZATION: Searches all collections in parallel using asyncio.gather
        instead of iterating sequentially.

        Args:
            tenant_id: Tenant identifier
            document_id: Document ID to find
            user_id: User ID for ACL verification
            user_role_ids: User's role IDs for role-based ACL
            is_admin: Whether user is admin (bypasses ACL)

        Returns:
            Document dict if found and accessible, None otherwise
        """
        try:
            await self.initialize()
            import weaviate.classes.query as wq

            # Get all collections for this tenant
            collections = await self.get_tenant_collections(tenant_id)

            if not collections:
                logger.warning(f"⚠️ No collections found for tenant {tenant_id}")
                return None

            logger.debug(f"Searching for document {document_id} across {len(collections)} collections in parallel (user_id={user_id[:8] if user_id else 'None'}...)")

            # Helper function to search in a single collection
            async def search_in_collection(collection_name: str) -> Optional[Dict[str, Any]]:
                try:
                    if not self.client.collections.exists(collection_name):
                        return None

                    collection = self.client.collections.get(collection_name)

                    # Build filter: document_id only (ACL verified after retrieval)
                    doc_filter = wq.Filter.by_property("document_id").equal(document_id)

                    response = collection.query.fetch_objects(
                        filters=doc_filter,
                        limit=1
                    )

                    if response.objects and len(response.objects) > 0:
                        item = response.objects[0]
                        return {
                            "id": item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                            "title": item.properties.get("title", ""),
                            "content": item.properties.get("content", ""),
                            "metadata": item.properties.get("metadata", {}),
                            "tenant_id": item.properties.get("tenant_id", ""),
                            "document_type": item.properties.get("document_type", ""),
                            "tags": item.properties.get("tags", []),
                            "channel_visibility": item.properties.get("channel_visibility", ""),
                            "owner_user_id": item.properties.get("owner_user_id", ""),
                            # ACL properties
                            "acl_user_ids": item.properties.get("acl_user_ids", []),
                            "acl_role_ids": item.properties.get("acl_role_ids", []),
                            "acl_everyone": item.properties.get("acl_everyone", False),
                            "_source_collection": collection_name,
                            "_is_channel": "_channel_" in collection_name.lower()
                        }
                    return None
                except Exception as e:
                    logger.debug(f"Error searching in {collection_name}: {e}")
                    return None

            # Helper function to verify ACL access
            def has_acl_access(doc: Dict[str, Any]) -> bool:
                """
                Verify if the user has ACL access to the document.

                SECURITY: Returns True if any of these conditions is met:
                1. Admin user (bypasses all ACL)
                2. No user_id provided (legacy behavior / internal calls)
                3. User is the document owner
                4. User is explicitly in acl_user_ids
                5. User has a role in acl_role_ids
                6. Document is shared with everyone (acl_everyone=true)
                7. Legacy document (no owner set)
                """
                # Admin bypass
                if is_admin:
                    return True

                # No user context = legacy/internal call
                if not user_id:
                    return True

                # Check ownership
                owner = doc.get("owner_user_id", "")
                if owner and owner == user_id:
                    return True

                # Legacy document (no owner)
                if not owner:
                    return True

                # Check explicit user ACL
                acl_users = doc.get("acl_user_ids", []) or []
                if user_id in acl_users:
                    return True

                # Check role-based ACL
                acl_roles = doc.get("acl_role_ids", []) or []
                if user_role_ids:
                    for role_id in user_role_ids:
                        if role_id in acl_roles:
                            return True

                # Check everyone flag
                if doc.get("acl_everyone", False):
                    return True

                return False

            # Search all collections in parallel
            results = await asyncio.gather(*[search_in_collection(coll) for coll in collections])

            # Return first non-None result that passes ACL check
            for result in results:
                if result:
                    # Verify ACL access
                    if has_acl_access(result):
                        logger.info(f"✅ Found document {document_id} in collection {result['_source_collection']} (ACL verified)")
                        return result
                    else:
                        logger.warning(f"🔐 Document {document_id} found but user {user_id[:8] if user_id else 'None'}... denied by ACL")
                        return None  # Document exists but user doesn't have access

            logger.warning(f"⚠️ Document {document_id} not found in tenant {tenant_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document {document_id} across collections: {e}")
            return None

    async def get_document_by_title(self, collection_name: str, title: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific document by its title (filename)"""
        try:
            await self.initialize()

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return None

            collection = self.client.collections.get(collection_name)

            # Search for document by title property with tenant isolation
            import weaviate.classes.query as wq
            response = collection.query.fetch_objects(
                filters=(
                    wq.Filter.by_property("title").like(f"*{title}*") &
                    wq.Filter.by_property("tenant_id").equal(tenant_id)
                ),
                limit=1
            )

            if response.objects and len(response.objects) > 0:
                item = response.objects[0]
                logger.info(f"✅ Found document by title: {item.properties.get('title')}")
                return {
                    "id": item.properties.get("document_id", str(item.uuid) if item.uuid else ""),
                    "title": item.properties.get("title", ""),
                    "content": item.properties.get("content", ""),
                    "metadata": item.properties.get("metadata", {}),
                    "tenant_id": item.properties.get("tenant_id", ""),
                    "document_type": item.properties.get("document_type", ""),
                    "tags": item.properties.get("tags", [])
                }

            logger.warning(f"⚠️ Document with title '{title}' not found for tenant {tenant_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document by title '{title}': {e}")
            return None

    async def get_document_full_content(
        self,
        tenant_id: str,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the full content of a document by fetching and concatenating all its chunks.

        Used by NexusLM for podcast generation - retrieves all chunks of a document,
        sorts them by chunk_index, and returns the concatenated content.

        Args:
            tenant_id: Tenant identifier
            document_id: Document ID to retrieve

        Returns:
            Dict with document_id, title, content (concatenated), chunk_count, word_count
        """
        try:
            await self.initialize()
            import weaviate.classes.query as wq

            # Get the main documents collection for this tenant
            from app.core.security import get_tenant_collection_name
            collection_name = get_tenant_collection_name(tenant_id, "documents")

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return None

            collection = self.client.collections.get(collection_name)

            # Fetch all chunks for this document
            doc_filter = wq.Filter.by_property("document_id").equal(document_id)

            response = collection.query.fetch_objects(
                filters=doc_filter,
                limit=500,  # Max chunks to retrieve
                return_properties=["content", "char_start", "document_id", "title", "document_type", "source_type"],
            )

            if not response.objects:
                logger.warning(f"⚠️ No chunks found for document {document_id}")
                return None

            # Sort chunks by char_start (character position) for proper ordering
            chunks = sorted(
                response.objects,
                key=lambda x: x.properties.get("char_start", 0) or 0
            )

            # Get document info from first chunk
            first_chunk = chunks[0]
            title = first_chunk.properties.get("title", "Untitled")
            source_type = first_chunk.properties.get("document_type", "")

            # Concatenate all chunk contents
            full_content = "\n\n".join(
                chunk.properties.get("content", "") for chunk in chunks
            )

            # Count words
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
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool
    ) -> bool:
        """
        Update ACL properties of a document in Weaviate.

        This method is called by the DocumentACLService when ACLs are
        modified in PostgreSQL. It synchronizes the ACL state to Weaviate
        for efficient filtering during vector searches.

        Args:
            collection_name: Weaviate collection name
            document_id: PostgreSQL document ID
            acl_user_ids: List of user UUIDs with view access
            acl_role_ids: List of role UUIDs with view access
            acl_everyone: True if all tenant users can view

        Returns:
            True if update succeeded
        """
        try:
            await self.initialize()
            import weaviate.classes.query as wq

            if not self.client.collections.exists(collection_name):
                logger.warning(f"⚠️ Collection {collection_name} does not exist")
                return False

            collection = self.client.collections.get(collection_name)

            # Find the document by document_id property
            response = collection.query.fetch_objects(
                filters=wq.Filter.by_property("document_id").equal(document_id),
                limit=1,
                include_vector=False
            )

            if not response.objects or len(response.objects) == 0:
                logger.warning(f"⚠️ Document {document_id} not found in {collection_name}")
                return False

            weaviate_uuid = response.objects[0].uuid

            # Update only the ACL properties
            collection.data.update(
                uuid=weaviate_uuid,
                properties={
                    "acl_user_ids": acl_user_ids,
                    "acl_role_ids": acl_role_ids,
                    "acl_everyone": acl_everyone,
                    "updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                }
            )

            logger.info(f"✅ Updated ACL for document {document_id}: users={len(acl_user_ids)}, roles={len(acl_role_ids)}, everyone={acl_everyone}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update document ACL {document_id}: {e}")
            return False

    async def update_document_acl_across_collections(
        self,
        tenant_id: str,
        document_id: str,
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool
    ) -> bool:
        """
        Update ACL properties across all tenant collections.

        Since a document might exist in multiple collections (e.g., main
        collection and channel collection), this method updates all copies.

        Args:
            tenant_id: Tenant identifier
            document_id: PostgreSQL document ID
            acl_user_ids: List of user UUIDs with view access
            acl_role_ids: List of role UUIDs with view access
            acl_everyone: True if all tenant users can view

        Returns:
            True if at least one update succeeded
        """
        try:
            collections = await self.get_tenant_collections(tenant_id)
            if not collections:
                return False

            any_success = False
            for collection_name in collections:
                success = await self.update_document_acl(
                    collection_name=collection_name,
                    document_id=document_id,
                    acl_user_ids=acl_user_ids,
                    acl_role_ids=acl_role_ids,
                    acl_everyone=acl_everyone
                )
                if success:
                    any_success = True

            return any_success

        except Exception as e:
            logger.error(f"❌ Failed to update ACL across collections: {e}")
            return False

    async def get_collection_info(self, collection_name: str) -> CollectionInfo:
        """Get information about a collection"""
        try:
            # Get collection info using v4 API
            collection = self.client.collections.get(collection_name)
            config = collection.config.get()
            schema = {
                "description": config.description or "",
                "properties": [prop.name for prop in config.properties] if config.properties else [],
                "vectorizer": str(config.vectorizer) if config.vectorizer else None
            }
            
            # Get object count using v4 API aggregate
            count_result = collection.aggregate.over_all(total_count=True)
            objects_count = count_result.total_count or 0
            
            return CollectionInfo(
                name=collection_name,
                description=schema.get("description", ""),
                objects_count=objects_count,
                properties=schema.get("properties", []),
                vectorizer=schema.get("vectorizer"),
                created_at=datetime.now()  # Weaviate doesn't store creation time
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to get info for collection {collection_name}: {e}")
            raise
    
    async def list_collections(self) -> List[str]:
        """List all collections"""
        try:
            # List collections using v4 API
            collections_list = self.client.collections.list_all()
            collections = [collection for collection in collections_list.keys() if collection is not None and isinstance(collection, str)]
            return collections
        except Exception as e:
            logger.error(f"❌ Failed to list collections: {e}")
            raise

    async def count_by_semantic_type(
        self, tenant_id: str, semantic_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Count documents by semantic_type using Weaviate aggregate.

        If semantic_type is given, returns the count for that type.
        If None, returns a breakdown of all types.

        Counts unique document_ids (not chunks) across all tenant collections.
        """
        import weaviate.classes.query as wq

        # Find all collections for this tenant
        collections = await self.get_tenant_collections(tenant_id)
        if not collections:
            return {"semantic_type": semantic_type, "count": 0} if semantic_type else {"type_counts": {}}

        try:
            all_doc_ids: Dict[str, set] = {}  # semantic_type → set of document_ids

            for coll_name in collections:
                # Skip non-document collections (summaries, knowledge, visual)
                if any(suffix in coll_name.lower() for suffix in ("_summaries", "_knowledge", "_visual")):
                    continue

                try:
                    collection = self.client.collections.get(coll_name)

                    if semantic_type:
                        response = collection.query.fetch_objects(
                            filters=wq.Filter.by_property("tenant_id").equal(tenant_id)
                            & wq.Filter.by_property("semantic_type").equal(semantic_type),
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
                            filters=wq.Filter.by_property("tenant_id").equal(tenant_id),
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

    async def get_tenant_collections(self, tenant_id: str) -> List[str]:
        """
        Get all collections belonging to a specific tenant.

        This finds ALL collections that match the tenant's UUID pattern,
        handling multiple naming conventions:
        - nexus_{tenant_id}_documents (main document collection)
        - nexus_{tenant_id}_channel_{channel_id} (channel-specific collections)
        - Nouxcube_{tenant_id}__documents (legacy format with double underscore)

        Args:
            tenant_id: The tenant UUID (with or without dashes)

        Returns:
            List of collection names belonging to the tenant
        """
        try:
            all_collections = await self.list_collections()

            # Normalize tenant_id to underscore format for matching
            tenant_normalized = tenant_id.lower().replace("-", "_")

            # Find all collections containing this tenant ID
            tenant_collections = []
            for coll in all_collections:
                coll_lower = coll.lower()
                if tenant_normalized in coll_lower:
                    tenant_collections.append(coll)

            logger.debug(f"Found {len(tenant_collections)} collections for tenant {tenant_id}: {tenant_collections}")
            return tenant_collections
        except Exception as e:
            logger.error(f"❌ Failed to get tenant collections for {tenant_id}: {e}")
            raise

    async def get_channel_collections(self, tenant_id: str, source_type: Optional[str] = None) -> List[str]:
        """
        Get channel-specific collections for a tenant.

        Channel collections use the format: nexus_{tenant_id}_channel_{channel_id}
        This method filters tenant collections to return only channel collections.

        Args:
            tenant_id: The tenant UUID
            source_type: Optional filter by source type (gmail, google_drive, etc.)
                        If provided, will check documents in each collection

        Returns:
            List of channel collection names
        """
        import re

        try:
            all_tenant_collections = await self.get_tenant_collections(tenant_id)

            # Filter to only channel collections (contain "_channel_")
            channel_collections = [
                coll for coll in all_tenant_collections
                if "_channel_" in coll.lower()
            ]

            logger.debug(f"Found {len(channel_collections)} channel collections for tenant {tenant_id}")
            return channel_collections
        except Exception as e:
            logger.error(f"❌ Failed to get channel collections for {tenant_id}: {e}")
            raise

    async def search_across_collections(
        self,
        collections: List[str],
        query: str,
        tenant_id: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        search_type: str = "hybrid",
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search across multiple collections and aggregate results.

        Args:
            collections: List of collection names to search
            query: Search query
            tenant_id: Tenant ID for access control
            limit: Max results per collection
            filters: Optional filters (applied only if collection has the property)
            search_type: Type of search (hybrid, semantic, keyword)
            user_id: User ID for ACL filtering
            user_role_ids: Role IDs for ACL filtering
            is_admin: If True, bypass ACL checks

        Returns:
            Combined list of results from all collections, sorted by score
        """
        all_results = []

        for collection_name in collections:
            try:
                # Get collection
                collection = self.client.collections.get(collection_name)

                # Check which properties exist in this collection
                props = collection.config.get().properties
                prop_names = [p.name for p in props]

                # Build base filter for tenant isolation
                where_filter = weaviate.classes.query.Filter.by_property("tenant_id").equal(tenant_id)

                # Apply ACL filtering if not admin and collection has ACL properties
                if not is_admin and user_id:
                    collection_has_acl = "acl_user_ids" in prop_names
                    acl_filter = self._build_document_access_filter(
                        user_id=user_id,
                        user_role_ids=user_role_ids,
                        collection_has_acl=collection_has_acl
                    )
                    where_filter = where_filter & acl_filter

                # Only apply additional filters if the property exists
                if filters:
                    for key, value in filters.items():
                        base_prop = key.split(".")[0]
                        if base_prop in prop_names:
                            prop_filter = weaviate.classes.query.Filter.by_property(base_prop).equal(value)
                            where_filter = where_filter & prop_filter

                # Generate embedding for vector search
                embedding_vector = None
                if search_type in ["hybrid", "vector"]:
                    try:
                        embedding_vector = await generate_embedding(query)
                    except Exception as e:
                        logger.warning(f"Could not generate embedding for query: {e}")

                # Execute search based on type
                if search_type == "hybrid" and embedding_vector:
                    response = collection.query.hybrid(
                        query=query,
                        vector=embedding_vector,
                        filters=where_filter,
                        limit=limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True)
                    )
                elif search_type == "vector" and embedding_vector:
                    response = collection.query.near_vector(
                        near_vector=embedding_vector,
                        filters=where_filter,
                        limit=limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(distance=True)
                    )
                else:
                    # Keyword search fallback
                    response = collection.query.bm25(
                        query=query,
                        filters=where_filter,
                        limit=limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True)
                    )

                # Process results
                for obj in response.objects:
                    props_dict = obj.properties
                    score = getattr(obj.metadata, "score", None) or getattr(obj.metadata, "distance", 0)
                    result = {
                        "id": str(obj.uuid),
                        "title": props_dict.get("title", ""),
                        "content": props_dict.get("content", ""),
                        "metadata": props_dict.get("metadata", {}),
                        "document_type": props_dict.get("document_type", ""),
                        "tenant_id": props_dict.get("tenant_id", ""),
                        "score": float(score) if score else 0.0,
                        "_source_collection": collection_name
                    }
                    all_results.append(result)

            except Exception as e:
                logger.warning(f"Error searching collection {collection_name}: {e}")
                continue

        # Sort by score (descending) and limit total results
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_results[:limit * 2]

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection"""
        try:
            # Delete collection using v4 API
            self.client.collections.delete(collection_name)
            logger.info(f"✅ Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete collection {collection_name}: {e}")
            raise
    
    async def batch_add_documents(self, collection_name: str, documents: List[DocumentCreate]) -> Dict[str, Any]:
        """Batch add multiple documents"""
        try:
            results = []
            
            # Get collection for batch operations
            collection = self.client.collections.get(collection_name)
            
            # Prepare documents for batch insert
            batch_objects = []
            for document in documents:
                doc_id = document.id or str(uuid.uuid4())
                
                doc_data = {
                    "title": document.title,
                    "content": document.content,
                    "document_id": document.id,  # Store PostgreSQL document ID as property
                    "tenant_id": document.tenant_id,
                    "document_type": document.document_type,
                    "tags": document.tags,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    # Channel properties
                    "channel_id": getattr(document, 'channel_id', '') or '',
                    "channel_visibility": getattr(document, 'channel_visibility', '') or '',
                    "owner_user_id": getattr(document, 'owner_user_id', '') or '',
                    "source_type": getattr(document, 'source_type', 'upload') or 'upload',
                    "external_id": getattr(document, 'external_id', '') or '',
                    # Folder hierarchy for path-based filtering in RAG
                    "folder_path": getattr(document, 'folder_path', '') or '',
                    "folder_hierarchy": getattr(document, 'folder_hierarchy', []) or [],
                    "connector_id": getattr(document, 'connector_id', '') or '',
                    # ACL properties
                    "acl_user_ids": getattr(document, 'acl_user_ids', []) or [],
                    "acl_role_ids": getattr(document, 'acl_role_ids', []) or [],
                    "acl_everyone": getattr(document, 'acl_everyone', True),
                }
                
                # Generate embeddings using configured provider (TEI or Sentence Transformers)
                embedding_vector = None
                if self.embedding_model:
                    try:
                        text_to_embed = f"{document.title} {document.content}"
                        embedding_vector = await generate_embedding(text_to_embed)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate batch embedding: {e}")
                
                if embedding_vector:
                    batch_objects.append(weaviate.classes.data.DataObject(
                        properties=doc_data,
                        uuid=doc_id,
                        vector=embedding_vector
                    ))
                else:
                    batch_objects.append(weaviate.classes.data.DataObject(
                        properties=doc_data,
                        uuid=doc_id
                    ))
                results.append(doc_id)
            
            # Execute batch insert using v4 API
            collection.data.insert_many(batch_objects)
            
            logger.info(f"✅ Batch added {len(documents)} documents to {collection_name}")
            return {"added_documents": len(documents), "document_ids": results}
            
        except Exception as e:
            logger.error(f"❌ Batch add failed for {collection_name}: {e}")
            raise
    
    async def vector_query(self, collection_name: str, query: VectorQuery) -> SearchResponse:
        """Execute raw vector query"""
        try:
            start_time = datetime.now()
            
            # Get collection for vector query using v4 API
            collection = self.client.collections.get(collection_name)
            
            # Build where filter for tenant isolation using v4 API
            where_filter = weaviate.classes.query.Filter.by_property("tenant_id").equal(query.tenant_id)
            
            if query.filters:
                for key, value in query.filters.items():
                    additional_filter = self._build_property_filter(key, value)
                    if additional_filter is not None:
                        where_filter = where_filter & additional_filter
            
            # Execute vector search using v4 API
            return_metadata = [weaviate.classes.query.MetadataQuery.certainty()]
            if query.include_vector:
                return_metadata.append(weaviate.classes.query.MetadataQuery.vector())
            
            response = collection.query.near_vector(
                near_vector=query.vector,
                where=where_filter,
                limit=query.limit,
                return_metadata=return_metadata
            )
            
            # Process results using v4 response format
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
                    tenant_id=item.properties.get("tenant_id", ""),
                    document_type=item.properties.get("document_type", ""),
                    tags=item.properties.get("tags", []),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    similarity_score=similarity,
                    # Folder hierarchy fields
                    folder_path=item.properties.get("folder_path", ""),
                    folder_hierarchy=item.properties.get("folder_hierarchy", []),
                    connector_id=item.properties.get("connector_id", ""),
                    # Chunk-level source attribution
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
                tenant_id=query.tenant_id
            )
            
        except Exception as e:
            logger.error(f"❌ Vector query failed: {e}")
            raise

    async def hybrid_search(
        self,
        query: str,
        collection_name: str,
        tenant_id: str,
        limit: int = 10,
        alpha: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentResponse]:
        """
        Convenience method for hybrid search.

        Combines vector (semantic) and keyword (BM25) search.

        Args:
            query: Search query text
            collection_name: Name of the collection to search
            tenant_id: Tenant ID for isolation
            limit: Maximum results to return
            alpha: Balance between vector (1.0) and keyword (0.0) search
            filters: Optional additional filters

        Returns:
            List of DocumentResponse objects
        """
        search_request = SearchRequest(
            query=query,
            limit=limit,
            tenant_id=tenant_id,
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
        tenant_id: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentResponse]:
        """
        Convenience method for vector (semantic) search.

        Args:
            query: Search query text
            collection_name: Name of the collection to search
            tenant_id: Tenant ID for isolation
            limit: Maximum results to return
            filters: Optional additional filters

        Returns:
            List of DocumentResponse objects
        """
        search_request = SearchRequest(
            query=query,
            limit=limit,
            tenant_id=tenant_id,
            search_type="vector",
            filters=filters,
        )

        response = await self.search_documents(collection_name, search_request)
        return response.results

    async def keyword_search(
        self,
        query: str,
        collection_name: str,
        tenant_id: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentResponse]:
        """
        Convenience method for keyword (BM25) search.

        Args:
            query: Search query text
            collection_name: Name of the collection to search
            tenant_id: Tenant ID for isolation
            limit: Maximum results to return
            filters: Optional additional filters

        Returns:
            List of DocumentResponse objects
        """
        search_request = SearchRequest(
            query=query,
            limit=limit,
            tenant_id=tenant_id,
            search_type="keyword",
            filters=filters,
        )

        response = await self.search_documents(collection_name, search_request)
        return response.results

    async def filter_search(
        self,
        collection_name: str,
        tenant_id: str,
        filters: Dict[str, Any],
        limit: int = 10,
    ) -> List[DocumentResponse]:
        """
        Search documents using only filters (no query text).

        Args:
            collection_name: Name of the collection to search
            tenant_id: Tenant ID for isolation
            filters: Filters to apply (document_type, tags, etc.)
            limit: Maximum results to return

        Returns:
            List of DocumentResponse objects
        """
        # Use empty query with keyword search type when only filtering
        search_request = SearchRequest(
            query="*",  # Match all
            limit=limit,
            tenant_id=tenant_id,
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
        """
        Generic search wrapper for SearchRequest.

        Args:
            search_request: Search request with all parameters
            collection_name: Collection name (can derive from tenant_id if not provided)

        Returns:
            SearchResponse with results
        """
        if collection_name is None:
            collection_name = get_tenant_collection_name(search_request.tenant_id)

        return await self.search_documents(collection_name, search_request)

    async def health_check(self) -> Dict[str, Any]:
        """Check Weaviate service health"""
        try:
            if not self.client:
                return {"status": "unhealthy", "error": "Client not initialized"}

            is_ready = self.client.is_ready()
            is_live = self.client.is_live()

            # Check embedding model status
            embedding_info = None
            if self.embedding_model:
                if settings.embedding_provider == "tei":
                    embedding_info = {
                        "provider": "tei",
                        "model": settings.embedding_model,
                        "dimensions": settings.embedding_dimensions,
                        "url": settings.tei_url
                    }
                else:
                    embedding_info = {
                        "provider": "sentence-transformers",
                        "model": settings.embedding_model,
                        "dimensions": settings.embedding_dimensions,
                        "device": settings.embedding_device
                    }

            return {
                "status": "healthy" if is_ready and is_live else "unhealthy",
                "ready": is_ready,
                "live": is_live,
                "url": settings.weaviate_url,
                "embeddings": embedding_info
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global service instance
weaviate_service = WeaviateService()
