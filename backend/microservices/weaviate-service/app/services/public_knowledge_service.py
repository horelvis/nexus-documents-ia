"""
Public Knowledge Base Service
Manages a shared vector database for specialized documents (legislation, regulations, etc.)
accessible by all tenants.
"""
import weaviate
import weaviate.classes.config as wc
import weaviate.classes.query as wq
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import httpx

from app.core.config import settings
from app.schemas.public_knowledge import (
    PublicDocumentCreate,
    PublicDocumentResponse,
    PublicSearchRequest,
    PublicSearchResponse,
    CombinedSearchRequest,
    CombinedSearchResponse,
    PublicKnowledgeStats,
    PublicDocumentCategory,
    Jurisdiction
)

logger = logging.getLogger(__name__)

# Collection name for public knowledge base
PUBLIC_KNOWLEDGE_COLLECTION = "PublicKnowledge"


class PublicKnowledgeService:
    """Service for managing public knowledge base in Weaviate"""

    def __init__(self):
        self.client = None
        self._initialized = False

    async def initialize(self):
        """Initialize connection and ensure collection exists"""
        if self._initialized:
            return

        try:
            # Get Weaviate client from main service
            from app.services.weaviate_service import weaviate_service
            await weaviate_service.initialize()
            self.client = weaviate_service.client

            if not self.client:
                raise Exception("Weaviate client not available")

            # Ensure public knowledge collection exists
            await self._ensure_collection_exists()

            self._initialized = True
            logger.info("Public Knowledge Service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Public Knowledge Service: {e}")
            raise

    async def _ensure_collection_exists(self):
        """Create the public knowledge collection if it doesn't exist, or update schema if needed"""
        try:
            existing = self.client.collections.list_all()
            if PUBLIC_KNOWLEDGE_COLLECTION in existing:
                logger.info(f"Collection {PUBLIC_KNOWLEDGE_COLLECTION} already exists")
                # Ensure all required properties exist
                await self._ensure_schema_properties()
                return

            logger.info(f"Creating collection {PUBLIC_KNOWLEDGE_COLLECTION}")

            # Create collection with specialized schema for legal documents
            self.client.collections.create(
                name=PUBLIC_KNOWLEDGE_COLLECTION,
                description="Public knowledge base for specialized documents (legislation, regulations, jurisprudence)",
                properties=[
                    # Basic content
                    wc.Property(
                        name="title",
                        data_type=wc.DataType.TEXT,
                        description="Document title"
                    ),
                    wc.Property(
                        name="content",
                        data_type=wc.DataType.TEXT,
                        description="Full document content"
                    ),
                    wc.Property(
                        name="summary",
                        data_type=wc.DataType.TEXT,
                        description="Document summary"
                    ),
                    # Classification
                    wc.Property(
                        name="category",
                        data_type=wc.DataType.TEXT,
                        description="Document category (legislation, regulation, etc.)"
                    ),
                    wc.Property(
                        name="subcategory",
                        data_type=wc.DataType.TEXT,
                        description="Specific subcategory"
                    ),
                    wc.Property(
                        name="jurisdiction",
                        data_type=wc.DataType.TEXT,
                        description="Legal jurisdiction (es, eu, int)"
                    ),
                    # Legal metadata
                    wc.Property(
                        name="legal_reference",
                        data_type=wc.DataType.TEXT,
                        description="Official legal reference"
                    ),
                    wc.Property(
                        name="publication_date",
                        data_type=wc.DataType.DATE,
                        description="Official publication date"
                    ),
                    wc.Property(
                        name="effective_date",
                        data_type=wc.DataType.DATE,
                        description="Effective date"
                    ),
                    wc.Property(
                        name="expiration_date",
                        data_type=wc.DataType.DATE,
                        description="Expiration date"
                    ),
                    # Search optimization
                    wc.Property(
                        name="keywords",
                        data_type=wc.DataType.TEXT_ARRAY,
                        description="Search keywords"
                    ),
                    wc.Property(
                        name="topics",
                        data_type=wc.DataType.TEXT_ARRAY,
                        description="Related topics"
                    ),
                    wc.Property(
                        name="related_documents",
                        data_type=wc.DataType.TEXT_ARRAY,
                        description="IDs of related documents"
                    ),
                    # Source
                    wc.Property(
                        name="source_url",
                        data_type=wc.DataType.TEXT,
                        description="Original source URL"
                    ),
                    wc.Property(
                        name="source_name",
                        data_type=wc.DataType.TEXT,
                        description="Source name"
                    ),
                    # Quality
                    wc.Property(
                        name="verified",
                        data_type=wc.DataType.BOOL,
                        description="Verification status"
                    ),
                    wc.Property(
                        name="version",
                        data_type=wc.DataType.TEXT,
                        description="Document version"
                    ),
                    # Timestamps
                    wc.Property(
                        name="created_at",
                        data_type=wc.DataType.DATE,
                        description="Creation timestamp"
                    ),
                    wc.Property(
                        name="updated_at",
                        data_type=wc.DataType.DATE,
                        description="Update timestamp"
                    )
                ]
            )

            logger.info(f"Created collection {PUBLIC_KNOWLEDGE_COLLECTION}")

        except Exception as e:
            logger.error(f"Failed to create public knowledge collection: {e}")
            raise

    async def _ensure_schema_properties(self):
        """Add missing properties to existing PublicKnowledge collection"""
        required_properties = {
            "title": (wc.DataType.TEXT, "Document title"),
            "content": (wc.DataType.TEXT, "Full document content"),
            "summary": (wc.DataType.TEXT, "Document summary"),
            "category": (wc.DataType.TEXT, "Document category"),
            "subcategory": (wc.DataType.TEXT, "Specific subcategory"),
            "jurisdiction": (wc.DataType.TEXT, "Legal jurisdiction"),
            "legal_reference": (wc.DataType.TEXT, "Official legal reference"),
            "publication_date": (wc.DataType.DATE, "Official publication date"),
            "effective_date": (wc.DataType.DATE, "Effective date"),
            "expiration_date": (wc.DataType.DATE, "Expiration date"),
            "keywords": (wc.DataType.TEXT_ARRAY, "Search keywords"),
            "topics": (wc.DataType.TEXT_ARRAY, "Related topics"),
            "related_documents": (wc.DataType.TEXT_ARRAY, "IDs of related documents"),
            "source_url": (wc.DataType.TEXT, "Original source URL"),
            "source_name": (wc.DataType.TEXT, "Source name"),
            "source": (wc.DataType.TEXT, "Source identifier"),
            "url": (wc.DataType.TEXT, "Document URL"),
            "document_type": (wc.DataType.TEXT, "Document type"),
            "language": (wc.DataType.TEXT, "Document language"),
            "relevance_score": (wc.DataType.NUMBER, "Relevance score"),
            "verified": (wc.DataType.BOOL, "Verification status"),
            "is_current_version": (wc.DataType.BOOL, "Whether this is the current version"),
            "version": (wc.DataType.TEXT, "Document version"),
            "created_at": (wc.DataType.DATE, "Creation timestamp"),
            "updated_at": (wc.DataType.DATE, "Update timestamp"),
        }

        try:
            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)
            config = collection.config.get()
            existing_props = {p.name for p in config.properties}

            for prop_name, (data_type, description) in required_properties.items():
                if prop_name not in existing_props:
                    logger.info(f"Adding missing property '{prop_name}' to {PUBLIC_KNOWLEDGE_COLLECTION}")
                    collection.config.add_property(
                        wc.Property(
                            name=prop_name,
                            data_type=data_type,
                            description=description
                        )
                    )

        except Exception as e:
            logger.warning(f"Failed to ensure schema properties: {e}")

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using TEI (Text Embeddings Inference)"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.tei_url}/embed",
                    json={
                        "inputs": text,
                        "truncate": True
                    },
                    timeout=30.0
                )
                if response.status_code == 200:
                    embeddings = response.json()
                    # TEI returns array of embeddings, get first one
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
        return None

    async def add_document(self, document: PublicDocumentCreate) -> PublicDocumentResponse:
        """Add a document to the public knowledge base"""
        await self.initialize()

        try:
            doc_id = document.id or str(uuid.uuid4())
            now = datetime.now()

            # Prepare properties
            properties = {
                "title": document.title,
                "content": document.content,
                "summary": document.summary or "",
                "category": document.category.value if isinstance(document.category, PublicDocumentCategory) else document.category,
                "subcategory": document.subcategory or "",
                "jurisdiction": document.jurisdiction.value if isinstance(document.jurisdiction, Jurisdiction) else document.jurisdiction,
                "legal_reference": document.legal_reference or "",
                "keywords": document.keywords,
                "topics": document.topics,
                "related_documents": document.related_documents,
                "source_url": document.source_url or "",
                "source_name": document.source_name or "",
                "verified": document.verified,
                "version": document.version,
                # Versioning metadata
                "version_number": document.version_number,
                "is_current_version": document.is_current_version,
                "modification_type": document.modification_type,
                "legal_status": document.legal_status,
                # Identifiers
                "boe_id": document.boe_id or "",
                "eli_uri": document.eli_uri or "",
                # Timestamps
                "created_at": now.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "updated_at": now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }

            # Add dates if provided
            if document.publication_date:
                properties["publication_date"] = document.publication_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            if document.effective_date:
                properties["effective_date"] = document.effective_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            if document.expiration_date:
                properties["expiration_date"] = document.expiration_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

            # Generate embedding for semantic search
            embedding_text = f"{document.title} {document.summary or ''} {' '.join(document.keywords)}"
            embedding = await self._generate_embedding(embedding_text)

            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)

            if embedding:
                collection.data.insert(
                    properties=properties,
                    uuid=doc_id,
                    vector=embedding
                )
            else:
                collection.data.insert(
                    properties=properties,
                    uuid=doc_id
                )

            logger.info(f"Added public document {doc_id}: {document.title}")

            return PublicDocumentResponse(
                id=doc_id,
                title=document.title,
                content=document.content,
                summary=document.summary,
                category=properties["category"],
                subcategory=document.subcategory,
                jurisdiction=properties["jurisdiction"],
                legal_reference=document.legal_reference,
                publication_date=document.publication_date,
                effective_date=document.effective_date,
                expiration_date=document.expiration_date,
                keywords=document.keywords,
                topics=document.topics,
                related_documents=document.related_documents,
                source_url=document.source_url,
                source_name=document.source_name,
                verified=document.verified,
                version=document.version,
                created_at=now,
                updated_at=now
            )

        except Exception as e:
            logger.error(f"Failed to add public document: {e}")
            raise

    async def search(self, request: PublicSearchRequest) -> PublicSearchResponse:
        """Search the public knowledge base"""
        await self.initialize()

        start_time = datetime.now()

        try:
            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)

            # Build filters
            filters = None

            if request.categories:
                category_values = [
                    c.value if isinstance(c, PublicDocumentCategory) else c
                    for c in request.categories
                ]
                category_filter = None
                for cat in category_values:
                    f = wq.Filter.by_property("category").equal(cat)
                    category_filter = f if category_filter is None else category_filter | f
                filters = category_filter

            if request.jurisdictions:
                jurisdiction_values = [
                    j.value if isinstance(j, Jurisdiction) else j
                    for j in request.jurisdictions
                ]
                jurisdiction_filter = None
                for jur in jurisdiction_values:
                    f = wq.Filter.by_property("jurisdiction").equal(jur)
                    jurisdiction_filter = f if jurisdiction_filter is None else jurisdiction_filter | f

                if filters:
                    filters = filters & jurisdiction_filter
                else:
                    filters = jurisdiction_filter

            if request.verified_only:
                verified_filter = wq.Filter.by_property("verified").equal(True)
                filters = filters & verified_filter if filters else verified_filter

            # Filter by current version only (default behavior)
            if request.current_version_only:
                current_version_filter = wq.Filter.by_property("is_current_version").equal(True)
                filters = filters & current_version_filter if filters else current_version_filter

            # Filter by legal status
            if request.legal_status:
                status_filter = None
                for status in request.legal_status:
                    f = wq.Filter.by_property("legal_status").equal(status)
                    status_filter = f if status_filter is None else status_filter | f
                filters = filters & status_filter if filters else status_filter

            # Execute search
            if request.search_type == "vector":
                embedding = await self._generate_embedding(request.query)
                if embedding:
                    response = collection.query.near_vector(
                        near_vector=embedding,
                        limit=request.limit,
                        return_metadata=wq.MetadataQuery(certainty=True, score=True),
                        filters=filters
                    )
                else:
                    # Fall back to keyword search
                    response = collection.query.bm25(
                        query=request.query,
                        limit=request.limit,
                        return_metadata=wq.MetadataQuery(score=True),
                        filters=filters
                    )
            elif request.search_type == "keyword":
                response = collection.query.bm25(
                    query=request.query,
                    limit=request.limit,
                    return_metadata=wq.MetadataQuery(score=True),
                    filters=filters
                )
            else:  # hybrid
                embedding = await self._generate_embedding(request.query)
                if embedding:
                    response = collection.query.hybrid(
                        query=request.query,
                        vector=embedding,
                        limit=request.limit,
                        alpha=0.7,
                        return_metadata=wq.MetadataQuery(score=True),
                        filters=filters
                    )
                else:
                    response = collection.query.bm25(
                        query=request.query,
                        limit=request.limit,
                        return_metadata=wq.MetadataQuery(score=True),
                        filters=filters
                    )

            # Process results
            results = []
            for item in response.objects:
                props = item.properties
                similarity = None
                if hasattr(item, 'metadata') and item.metadata:
                    similarity = getattr(item.metadata, 'certainty', None) or getattr(item.metadata, 'score', None)

                # Parse dates safely
                pub_date = None
                eff_date = None
                exp_date = None
                created = datetime.now()
                updated = datetime.now()

                if props.get("publication_date"):
                    try:
                        pub_date = datetime.fromisoformat(str(props["publication_date"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("effective_date"):
                    try:
                        eff_date = datetime.fromisoformat(str(props["effective_date"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("expiration_date"):
                    try:
                        exp_date = datetime.fromisoformat(str(props["expiration_date"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("created_at"):
                    try:
                        created = datetime.fromisoformat(str(props["created_at"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("updated_at"):
                    try:
                        updated = datetime.fromisoformat(str(props["updated_at"]).replace('Z', '+00:00'))
                    except:
                        pass

                # Parse consolidation date
                consolidation_date = None
                if props.get("consolidation_date"):
                    try:
                        consolidation_date = datetime.fromisoformat(str(props["consolidation_date"]).replace('Z', '+00:00'))
                    except:
                        pass

                # Handle None values from Weaviate that should have defaults
                verified_val = props.get("verified")
                is_current_val = props.get("is_current_version")
                version_num_val = props.get("version_number")

                results.append(PublicDocumentResponse(
                    id=str(item.uuid) if item.uuid else "",
                    title=props.get("title", ""),
                    content=props.get("content", ""),
                    summary=props.get("summary"),
                    category=props.get("category", ""),
                    subcategory=props.get("subcategory"),
                    jurisdiction=props.get("jurisdiction", ""),
                    legal_reference=props.get("legal_reference"),
                    publication_date=pub_date,
                    effective_date=eff_date,
                    expiration_date=exp_date,
                    keywords=props.get("keywords") or [],
                    topics=props.get("topics") or [],
                    related_documents=props.get("related_documents") or [],
                    source_url=props.get("source_url"),
                    source_name=props.get("source_name"),
                    verified=verified_val if verified_val is not None else False,
                    version=props.get("version") or "1.0",
                    # Versioning metadata
                    version_number=version_num_val if version_num_val is not None else 1,
                    is_current_version=is_current_val if is_current_val is not None else True,
                    consolidation_date=consolidation_date,
                    superseded_by=props.get("superseded_by"),
                    supersedes=props.get("supersedes"),
                    # Modification tracking
                    modification_type=props.get("modification_type") or "original",
                    modifying_laws=props.get("modifying_laws") or [],
                    modified_articles=props.get("modified_articles") or [],
                    # Legal status
                    legal_status=props.get("legal_status") or "vigente",
                    derogated_by=props.get("derogated_by"),
                    partial_derogations=props.get("partial_derogations") or [],
                    # Identifiers
                    boe_id=props.get("boe_id"),
                    eli_uri=props.get("eli_uri"),
                    # Timestamps
                    created_at=created,
                    updated_at=updated,
                    similarity_score=similarity
                ))

            search_time = int((datetime.now() - start_time).total_seconds() * 1000)

            filters_applied = {}
            if request.categories:
                filters_applied["categories"] = [c.value if hasattr(c, 'value') else c for c in request.categories]
            if request.jurisdictions:
                filters_applied["jurisdictions"] = [j.value if hasattr(j, 'value') else j for j in request.jurisdictions]
            if request.verified_only:
                filters_applied["verified_only"] = True

            return PublicSearchResponse(
                query=request.query,
                results=results,
                total_results=len(results),
                search_time_ms=search_time,
                search_type=request.search_type,
                filters_applied=filters_applied
            )

        except Exception as e:
            logger.error(f"Public knowledge search failed: {e}")
            raise

    async def combined_search(
        self,
        request: CombinedSearchRequest,
        tenant_collection: str
    ) -> CombinedSearchResponse:
        """Search both tenant and public knowledge bases"""
        await self.initialize()

        start_time = datetime.now()
        tenant_results = []
        public_results = []

        try:
            # Search tenant documents
            if request.include_tenant_docs:
                from app.services.weaviate_service import weaviate_service
                from app.schemas.weaviate import SearchRequest

                tenant_search = SearchRequest(
                    query=request.query,
                    limit=request.limit,
                    tenant_id=request.tenant_id,
                    search_type=request.search_type
                )

                tenant_response = await weaviate_service.search_documents(
                    tenant_collection,
                    tenant_search
                )
                tenant_results = [r.model_dump() for r in tenant_response.results]

            # Search public knowledge
            if request.include_public_docs:
                public_search = PublicSearchRequest(
                    query=request.query,
                    limit=request.limit,
                    categories=request.public_categories,
                    jurisdictions=request.public_jurisdictions,
                    search_type=request.search_type
                )

                public_response = await self.search(public_search)
                public_results = public_response.results

            search_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return CombinedSearchResponse(
                query=request.query,
                tenant_results=tenant_results,
                public_results=public_results,
                total_tenant_results=len(tenant_results),
                total_public_results=len(public_results),
                search_time_ms=search_time,
                merge_strategy=request.merge_strategy
            )

        except Exception as e:
            logger.error(f"Combined search failed: {e}")
            raise

    async def get_stats(self) -> PublicKnowledgeStats:
        """Get statistics about the public knowledge base"""
        await self.initialize()

        try:
            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)

            # Get total count
            total_result = collection.aggregate.over_all(total_count=True)
            total_documents = total_result.total_count or 0

            # Count by category
            documents_by_category = {}
            for category in PublicDocumentCategory:
                filter_cat = wq.Filter.by_property("category").equal(category.value)
                cat_result = collection.aggregate.over_all(
                    total_count=True,
                    filters=filter_cat
                )
                if cat_result.total_count:
                    documents_by_category[category.value] = cat_result.total_count

            # Count by jurisdiction
            documents_by_jurisdiction = {}
            for jurisdiction in Jurisdiction:
                filter_jur = wq.Filter.by_property("jurisdiction").equal(jurisdiction.value)
                jur_result = collection.aggregate.over_all(
                    total_count=True,
                    filters=filter_jur
                )
                if jur_result.total_count:
                    documents_by_jurisdiction[jurisdiction.value] = jur_result.total_count

            # Count verified
            verified_filter = wq.Filter.by_property("verified").equal(True)
            verified_result = collection.aggregate.over_all(
                total_count=True,
                filters=verified_filter
            )
            verified_count = verified_result.total_count or 0

            # Get unique topics (simplified - just return empty for now as aggregation is complex)
            topics_index = []

            return PublicKnowledgeStats(
                total_documents=total_documents,
                documents_by_category=documents_by_category,
                documents_by_jurisdiction=documents_by_jurisdiction,
                verified_count=verified_count,
                last_updated=datetime.now(),
                topics_index=topics_index
            )

        except Exception as e:
            logger.error(f"Failed to get public knowledge stats: {e}")
            raise

    async def get_document(self, document_id: str) -> Optional[PublicDocumentResponse]:
        """Get a specific document by ID"""
        await self.initialize()

        try:
            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)
            item = collection.query.fetch_object_by_id(document_id)

            if not item:
                return None

            props = item.properties

            # Parse dates
            pub_date = None
            eff_date = None
            exp_date = None
            created = datetime.now()
            updated = datetime.now()

            if props.get("publication_date"):
                try:
                    pub_date = datetime.fromisoformat(str(props["publication_date"]).replace('Z', '+00:00'))
                except:
                    pass
            if props.get("effective_date"):
                try:
                    eff_date = datetime.fromisoformat(str(props["effective_date"]).replace('Z', '+00:00'))
                except:
                    pass
            if props.get("expiration_date"):
                try:
                    exp_date = datetime.fromisoformat(str(props["expiration_date"]).replace('Z', '+00:00'))
                except:
                    pass
            if props.get("created_at"):
                try:
                    created = datetime.fromisoformat(str(props["created_at"]).replace('Z', '+00:00'))
                except:
                    pass
            if props.get("updated_at"):
                try:
                    updated = datetime.fromisoformat(str(props["updated_at"]).replace('Z', '+00:00'))
                except:
                    pass

            return PublicDocumentResponse(
                id=str(item.uuid) if item.uuid else document_id,
                title=props.get("title", ""),
                content=props.get("content", ""),
                summary=props.get("summary"),
                category=props.get("category", ""),
                subcategory=props.get("subcategory"),
                jurisdiction=props.get("jurisdiction", ""),
                legal_reference=props.get("legal_reference"),
                publication_date=pub_date,
                effective_date=eff_date,
                expiration_date=exp_date,
                keywords=props.get("keywords", []),
                topics=props.get("topics", []),
                related_documents=props.get("related_documents", []),
                source_url=props.get("source_url"),
                source_name=props.get("source_name"),
                verified=props.get("verified", False),
                version=props.get("version", "1.0"),
                created_at=created,
                updated_at=updated
            )

        except Exception as e:
            logger.error(f"Failed to get document {document_id}: {e}")
            return None

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document from the public knowledge base"""
        await self.initialize()

        try:
            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)
            collection.data.delete_by_id(document_id)
            logger.info(f"Deleted public document {document_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False

    async def batch_add_documents(
        self,
        documents: List[PublicDocumentCreate]
    ) -> Dict[str, Any]:
        """Add multiple documents in batch"""
        await self.initialize()

        success_count = 0
        failed_ids = []

        for doc in documents:
            try:
                await self.add_document(doc)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to add document {doc.title}: {e}")
                failed_ids.append(doc.id or doc.title)

        return {
            "success_count": success_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids
        }


    async def get_version_history(self, legal_reference: str) -> List[PublicDocumentResponse]:
        """Get all versions of a law by its legal reference (e.g., BOE-A-2018-16673)"""
        await self.initialize()

        try:
            collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)

            # Filter by legal_reference or boe_id
            filter_ref = (
                wq.Filter.by_property("legal_reference").equal(legal_reference) |
                wq.Filter.by_property("boe_id").equal(legal_reference)
            )

            response = collection.query.fetch_objects(
                filters=filter_ref,
                limit=50  # Unlikely to have more than 50 versions
            )

            results = []
            for item in response.objects:
                props = item.properties

                # Parse dates
                pub_date = None
                consolidation_date = None
                created = datetime.now()
                updated = datetime.now()

                if props.get("publication_date"):
                    try:
                        pub_date = datetime.fromisoformat(str(props["publication_date"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("consolidation_date"):
                    try:
                        consolidation_date = datetime.fromisoformat(str(props["consolidation_date"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("created_at"):
                    try:
                        created = datetime.fromisoformat(str(props["created_at"]).replace('Z', '+00:00'))
                    except:
                        pass
                if props.get("updated_at"):
                    try:
                        updated = datetime.fromisoformat(str(props["updated_at"]).replace('Z', '+00:00'))
                    except:
                        pass

                results.append(PublicDocumentResponse(
                    id=str(item.uuid) if item.uuid else "",
                    title=props.get("title", ""),
                    content=props.get("content", ""),
                    summary=props.get("summary"),
                    category=props.get("category", ""),
                    subcategory=props.get("subcategory"),
                    jurisdiction=props.get("jurisdiction", ""),
                    legal_reference=props.get("legal_reference"),
                    publication_date=pub_date,
                    effective_date=None,
                    expiration_date=None,
                    keywords=props.get("keywords", []),
                    topics=props.get("topics", []),
                    related_documents=props.get("related_documents", []),
                    source_url=props.get("source_url"),
                    source_name=props.get("source_name"),
                    verified=props.get("verified", False),
                    version=props.get("version", "1.0"),
                    version_number=props.get("version_number", 1),
                    is_current_version=props.get("is_current_version", True),
                    consolidation_date=consolidation_date,
                    superseded_by=props.get("superseded_by"),
                    supersedes=props.get("supersedes"),
                    modification_type=props.get("modification_type") or "original",
                    modifying_laws=props.get("modifying_laws") or [],
                    modified_articles=props.get("modified_articles") or [],
                    legal_status=props.get("legal_status") or "vigente",
                    derogated_by=props.get("derogated_by"),
                    partial_derogations=props.get("partial_derogations") or [],
                    boe_id=props.get("boe_id"),
                    eli_uri=props.get("eli_uri"),
                    created_at=created,
                    updated_at=updated
                ))

            # Sort by version_number descending (most recent first)
            results.sort(key=lambda x: x.version_number, reverse=True)

            return results

        except Exception as e:
            logger.error(f"Failed to get version history for {legal_reference}: {e}")
            return []

    async def add_new_version(
        self,
        legal_reference: str,
        document: PublicDocumentCreate,
        modified_articles: List[str] = None,
        modification_type: str = "modificacion"
    ) -> PublicDocumentResponse:
        """
        Add a new version of an existing law.
        Marks the previous version as superseded.
        """
        await self.initialize()

        try:
            # Get current version
            history = await self.get_version_history(legal_reference)
            current_version = next((v for v in history if v.is_current_version), None)

            new_version_number = 1
            if current_version:
                new_version_number = current_version.version_number + 1

                # Mark old version as superseded
                collection = self.client.collections.get(PUBLIC_KNOWLEDGE_COLLECTION)
                collection.data.update(
                    uuid=current_version.id,
                    properties={
                        "is_current_version": False,
                        "superseded_by": document.id or str(uuid.uuid4())
                    }
                )
                logger.info(f"Marked version {current_version.version_number} as superseded")

            # Create new version
            document.version_number = new_version_number
            document.is_current_version = True
            document.modification_type = modification_type
            if modified_articles:
                document.modified_articles = modified_articles
            if current_version:
                document.supersedes = current_version.id

            result = await self.add_document(document)

            logger.info(f"Added version {new_version_number} of {legal_reference}")
            return result

        except Exception as e:
            logger.error(f"Failed to add new version for {legal_reference}: {e}")
            raise


# Global service instance
public_knowledge_service = PublicKnowledgeService()
