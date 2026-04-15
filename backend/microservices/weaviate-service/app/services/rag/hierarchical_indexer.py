"""
Hierarchical Indexer for Long Context RAG

Implements 2-level retrieval strategy:
1. Document-level summaries for coarse filtering (fast, high recall)
2. Chunk-level search for precise retrieval (detailed context)

This improves coverage for long documents (>50 pages) by:
- First finding relevant documents via summary search
- Then drilling down to specific chunks within those documents

Reference: "I Rebuilt My RAG Pipeline 11 Times" - Hierarchical Retrieval section
Paper: RLM (Recursive Language Models) - arXiv:2512.24601

Single-tenant deployment (on-premise) — legacy `tenant_id` kwargs are
accepted-and-ignored for backwards compat with Wave-3 upstream callers.
ACL enforcement on summary search is deferred (roles-based filter TODO).
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from ...core.config import settings

logger = logging.getLogger(__name__)

# Fixed summary collection name (single-tenant deployment).
SUMMARY_COLLECTION_NAME = "Nouxcube_documents_summaries"


@dataclass
class DocumentSummary:
    """Summary of a document for hierarchical retrieval"""

    document_id: str
    title: str
    summary: str
    key_topics: List[str]
    key_entities: List[str]
    document_type: str
    total_chunks: int
    total_tokens: int
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Embedding will be generated from summary text
    embedding: Optional[List[float]] = None


@dataclass
class HierarchicalRetrievalResult:
    """Result from hierarchical retrieval (summary + chunks)"""

    document_id: str
    summary: DocumentSummary
    relevant_chunks: List[Dict[str, Any]]
    summary_score: float
    combined_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class HierarchicalIndexer:
    """
    Hierarchical Indexer for Long Context RAG

    Generates document-level summaries during indexing and stores them
    in a separate collection for fast coarse-grained retrieval.

    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    HIERARCHICAL RETRIEVAL                    │
    ├─────────────────────────────────────────────────────────────┤
    │  Query → Summary Search (fast, high recall)                  │
    │           ↓                                                  │
    │  Top-K Document Summaries                                    │
    │           ↓                                                  │
    │  Chunk Search (within selected documents)                    │
    │           ↓                                                  │
    │  Final Results with full context                             │
    └─────────────────────────────────────────────────────────────┘
    """

    def __init__(self):
        self._llm_client = None
        self._weaviate_service = None
        self._initialized = False
        # Summary generation config
        self._max_summary_tokens = 500
        self._max_topics = 10
        self._max_entities = 15

    async def initialize(self):
        """Initialize the hierarchical indexer"""
        if self._initialized:
            return

        try:
            # Import LLM client for summary generation (Emma v2)
            from ...agents.llm_client import get_llm_client

            self._llm_client = await get_llm_client()

            # Import Weaviate service
            from ..weaviate_service import weaviate_service

            self._weaviate_service = weaviate_service
            await self._weaviate_service.initialize()

            self._initialized = True
            logger.info("✅ HierarchicalIndexer initialized")

        except Exception as e:
            logger.warning(f"⚠️ HierarchicalIndexer initialization failed: {e}")
            # Allow partial operation without LLM
            self._initialized = True

    def get_summary_collection_name(
        self,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> str:
        """Get the summary collection name (single-tenant)."""
        return SUMMARY_COLLECTION_NAME

    async def generate_document_summary(
        self,
        document_id: str,
        title: str,
        full_text: str,
        document_type: str,
        total_chunks: int,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> Optional[DocumentSummary]:
        """
        Generate a document-level summary for hierarchical retrieval.

        Args:
            document_id: Document identifier
            title: Document title
            full_text: Complete document text
            document_type: Type of document
            total_chunks: Number of chunks the document was split into
            metadata: Additional metadata
            tenant_id: DEPRECATED, ignored (single-tenant deployment)

        Returns:
            DocumentSummary or None if generation fails
        """
        if not settings.rag_hierarchical_enabled:
            return None

        await self.initialize()

        if not self._llm_client:
            logger.warning("⚠️ LLM client not available for summary generation")
            return None

        try:
            # Truncate text for summary generation (use first ~8K tokens)
            text_for_summary = full_text[:32000]  # ~8K tokens

            # Generate summary using LLM
            prompt = self._build_summary_prompt(title, text_for_summary, document_type)

            response = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._max_summary_tokens + 200,  # Buffer for JSON structure
                temperature=0.3,  # Low temperature for consistent summaries
            )

            # Parse response
            summary_text, topics, entities = self._parse_summary_response(
                response.content if hasattr(response, "content") else str(response)
            )

            # Estimate total tokens
            total_tokens = len(full_text) // 4  # Rough estimate

            summary = DocumentSummary(
                document_id=document_id,
                title=title,
                summary=summary_text,
                key_topics=topics[:self._max_topics],
                key_entities=entities[:self._max_entities],
                document_type=document_type,
                total_chunks=total_chunks,
                total_tokens=total_tokens,
                metadata=metadata or {},
            )

            logger.info(
                f"📝 Generated summary for {document_id}: {len(summary_text)} chars, "
                f"{len(topics)} topics, {len(entities)} entities"
            )

            return summary

        except Exception as e:
            logger.warning(f"⚠️ Summary generation failed for {document_id}: {e}")
            return None

    def _build_summary_prompt(
        self,
        title: str,
        text: str,
        document_type: str,
    ) -> str:
        """Build the prompt for summary generation"""
        return f"""Analiza el siguiente documento y genera:
1. Un resumen ejecutivo de 200-300 palabras
2. Lista de 5-10 temas principales (topics)
3. Lista de 5-15 entidades clave (personas, organizaciones, fechas, montos)

Título: {title}
Tipo de documento: {document_type}

---
{text}
---

Responde EXACTAMENTE en este formato JSON:
{{
    "summary": "Resumen ejecutivo aquí...",
    "topics": ["tema1", "tema2", "tema3"],
    "entities": ["entidad1", "entidad2", "entidad3"]
}}

IMPORTANTE: Solo responde con el JSON, sin texto adicional."""

    def _parse_summary_response(
        self,
        response: str,
    ) -> Tuple[str, List[str], List[str]]:
        """Parse the LLM response for summary components"""
        import json
        import re

        # Default values
        summary = ""
        topics = []
        entities = []

        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group())
                summary = data.get("summary", "")
                topics = data.get("topics", [])
                entities = data.get("entities", [])
            else:
                # Fallback: use entire response as summary
                summary = response.strip()[:1000]

        except json.JSONDecodeError:
            # Fallback: use response as summary
            summary = response.strip()[:1000]

        return summary, topics, entities

    async def index_summary(
        self,
        summary: DocumentSummary,
    ) -> bool:
        """
        Index a document summary in Weaviate.

        Args:
            summary: DocumentSummary to index

        Returns:
            True if successful, False otherwise
        """
        if not settings.rag_hierarchical_enabled:
            return False

        await self.initialize()

        try:
            collection_name = SUMMARY_COLLECTION_NAME

            # Ensure collection exists
            await self._ensure_summary_collection(collection_name)

            # Generate embedding for summary
            embedding = await self._generate_summary_embedding(summary)
            summary.embedding = embedding

            # Build document data
            doc_data = {
                "document_id": summary.document_id,
                "title": summary.title,
                "summary": summary.summary,
                "key_topics": summary.key_topics,
                "key_entities": summary.key_entities,
                "document_type": summary.document_type,
                "total_chunks": summary.total_chunks,
                "total_tokens": summary.total_tokens,
                "created_at": summary.created_at.isoformat(),
            }

            # Add to Weaviate
            collection = self._weaviate_service.client.collections.get(collection_name)

            if embedding:
                collection.data.insert(
                    properties=doc_data,
                    vector=embedding,
                )
            else:
                collection.data.insert(properties=doc_data)

            logger.info(f"✅ Indexed summary for document {summary.document_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to index summary for {summary.document_id}: {e}")
            return False

    async def _ensure_summary_collection(self, collection_name: str):
        """Ensure the summary collection exists with proper schema"""
        try:
            import weaviate.classes as wvc

            # Check if collection exists
            if self._weaviate_service.client.collections.exists(collection_name):
                return

            # Create collection with summary schema
            self._weaviate_service.client.collections.create(
                name=collection_name,
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=[
                    wvc.config.Property(
                        name="document_id",
                        data_type=wvc.config.DataType.TEXT,
                    ),
                    wvc.config.Property(
                        name="title",
                        data_type=wvc.config.DataType.TEXT,
                    ),
                    wvc.config.Property(
                        name="summary",
                        data_type=wvc.config.DataType.TEXT,
                    ),
                    wvc.config.Property(
                        name="key_topics",
                        data_type=wvc.config.DataType.TEXT_ARRAY,
                    ),
                    wvc.config.Property(
                        name="key_entities",
                        data_type=wvc.config.DataType.TEXT_ARRAY,
                    ),
                    wvc.config.Property(
                        name="document_type",
                        data_type=wvc.config.DataType.TEXT,
                    ),
                    wvc.config.Property(
                        name="total_chunks",
                        data_type=wvc.config.DataType.INT,
                    ),
                    wvc.config.Property(
                        name="total_tokens",
                        data_type=wvc.config.DataType.INT,
                    ),
                    wvc.config.Property(
                        name="created_at",
                        data_type=wvc.config.DataType.TEXT,
                    ),
                ],
            )

            logger.info(f"✅ Created summary collection: {collection_name}")

        except Exception as e:
            logger.warning(f"⚠️ Could not create summary collection: {e}")

    async def _generate_summary_embedding(
        self,
        summary: DocumentSummary,
    ) -> Optional[List[float]]:
        """Generate embedding for document summary"""
        try:
            # Combine summary components for embedding
            text_to_embed = f"{summary.title}\n\n{summary.summary}\n\nTopics: {', '.join(summary.key_topics)}"

            # Use the multimodal embedding service if available
            from ..multimodal_embedding_service import multimodal_embedding_service

            result = await multimodal_embedding_service.embed_texts(
                texts=[text_to_embed],
                use_multimodal=False,  # Text-only for summaries
            )

            if result.success and result.vectors:
                return result.vectors[0]

        except Exception as e:
            logger.debug(f"Could not generate summary embedding: {e}")

        return None

    async def search_summaries(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> List[DocumentSummary]:
        """
        Search document summaries for hierarchical retrieval.

        Args:
            query: Search query
            limit: Maximum results
            filters: Optional filters (document_type, etc.)
            tenant_id: DEPRECATED, ignored (single-tenant deployment)

        Returns:
            List of matching DocumentSummary objects

        Note: ACL enforcement (roles-based filter) is deferred. In single-tenant
        mode, all summaries are currently visible — summaries inherit document
        ACL via the parent document lookup. See Wave-8 follow-up.
        """
        if not settings.rag_hierarchical_enabled:
            return []

        await self.initialize()

        try:
            collection_name = SUMMARY_COLLECTION_NAME

            # Check if collection exists
            if not self._weaviate_service.client.collections.exists(collection_name):
                return []

            collection = self._weaviate_service.client.collections.get(collection_name)

            # Generate query embedding
            from ..multimodal_embedding_service import multimodal_embedding_service

            result = await multimodal_embedding_service.embed_texts(
                texts=[query],
                use_multimodal=False,
            )

            if not result.success or not result.vectors:
                logger.warning("Could not generate query embedding for summary search")
                return []

            query_vector = result.vectors[0]

            # Build filters (tenant_id filter removed — single-tenant deployment)
            import weaviate.classes.query as wq

            weaviate_filter = None
            if filters and "document_type" in filters:
                weaviate_filter = wq.Filter.by_property(
                    "document_type"
                ).equal(filters["document_type"])

            # Execute vector search
            query_kwargs = {
                "near_vector": query_vector,
                "limit": limit,
                "return_metadata": wq.MetadataQuery(certainty=True, distance=True),
            }
            if weaviate_filter is not None:
                query_kwargs["filters"] = weaviate_filter

            response = collection.query.near_vector(**query_kwargs)

            # Convert to DocumentSummary objects
            results = []
            for obj in response.objects:
                props = obj.properties

                summary = DocumentSummary(
                    document_id=props.get("document_id", ""),
                    title=props.get("title", ""),
                    summary=props.get("summary", ""),
                    key_topics=props.get("key_topics", []),
                    key_entities=props.get("key_entities", []),
                    document_type=props.get("document_type", ""),
                    total_chunks=props.get("total_chunks", 0),
                    total_tokens=props.get("total_tokens", 0),
                    metadata={
                        "certainty": obj.metadata.certainty if obj.metadata else None,
                        "distance": obj.metadata.distance if obj.metadata else None,
                    },
                )
                results.append(summary)

            logger.info(f"📝 Found {len(results)} document summaries for query")
            return results

        except Exception as e:
            logger.warning(f"⚠️ Summary search failed: {e}")
            return []

    async def delete_summary(
        self,
        document_id: str,
        tenant_id: Optional[str] = None,  # deprecated, accepted-and-ignored
    ) -> bool:
        """Delete a document summary when document is deleted"""
        if not settings.rag_hierarchical_enabled:
            return True

        await self.initialize()

        try:
            collection_name = SUMMARY_COLLECTION_NAME

            if not self._weaviate_service.client.collections.exists(collection_name):
                return True

            collection = self._weaviate_service.client.collections.get(collection_name)

            # Find and delete summary
            import weaviate.classes.query as wq

            response = collection.query.fetch_objects(
                filters=wq.Filter.by_property("document_id").equal(document_id),
                limit=1,
            )

            if response.objects:
                collection.data.delete_by_id(response.objects[0].uuid)
                logger.info(f"✅ Deleted summary for document {document_id}")

            return True

        except Exception as e:
            logger.warning(f"⚠️ Failed to delete summary for {document_id}: {e}")
            return False


# Global instance
hierarchical_indexer = HierarchicalIndexer()
