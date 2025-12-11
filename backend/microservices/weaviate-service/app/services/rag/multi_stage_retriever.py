"""
Layer 3: Hybrid Retrieval + RRF (Production Grade)

Implements a 4-stage retrieval pipeline with Reciprocal Rank Fusion:
1. Dense vector search (50 candidates)
2. Sparse BM25 search (50 candidates)
3. RRF fusion (combine results)
4. Cross-encoder reranking (precise, 20 results)
5. Context fusion (intelligent grouping, top-K)

Key improvements:
- Separate dense/sparse searches instead of Weaviate's built-in hybrid
- RRF fusion for +15-20% recall improvement over weighted average
- Multi-query expansion with RRF aggregation
- Public Knowledge integration for legal/regulatory context

Reference: "I Rebuilt My RAG Pipeline 11 Times" - Hybrid Search + RRF section
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import httpx

from .models import QueryAnalysis, RetrievedDocument, QueryIntent
from .rrf_fusion import reciprocal_rank_fusion, multi_list_rrf
from ...core.config import settings
from ..weaviate_service import weaviate_service
from ...schemas.weaviate import SearchRequest
from ...schemas.public_knowledge import PublicSearchRequest, PublicDocumentCategory


def _get_tenant_collection_name(tenant_id: str) -> str:
    """
    Generate tenant-specific collection name for Weaviate.

    Format: Nexus_{tenant_id_with_underscores}_documents
    Example: Nexus_1a94d369_8426_4d2b_afec_8971073fce1e_documents

    Note: Weaviate collection names are case-sensitive and use underscores
    """
    # Normalize tenant_id: replace dashes with underscores
    normalized_id = tenant_id.replace("-", "_")
    return f"Nexus_{normalized_id}_documents"

logger = logging.getLogger(__name__)


class MultiStageRetriever:
    """
    Layer 3: Hybrid Retrieval with RRF Fusion

    Stage 1a: Dense vector search (50 candidates)
    Stage 1b: Sparse BM25 search (50 candidates)
    Stage 2: RRF fusion - combine dense and sparse results
    Stage 3: Semantic reranking - precision filtering (20 results)
    Stage 4: Context fusion - group by document, diversify (top-K)

    RRF (Reciprocal Rank Fusion) combines results using:
        score(d) = Σ 1/(k + rank_i(d))
    where k=60 prevents high-ranked items from dominating.

    This typically achieves +15-20% recall improvement over simple weighted average.
    """

    def __init__(self):
        self._reranker = None
        self._reranker_model = settings.embedding_model  # Use same for now
        self._tei_url = settings.tei_url
        self._initialized = False
        # RRF configuration
        self._rrf_k = 60  # Standard RRF constant
        self._dense_weight = 1.0
        self._sparse_weight = 1.0
        # Public Knowledge configuration
        self._public_knowledge_enabled = settings.rag_public_knowledge_enabled
        self._public_knowledge_weight = settings.rag_public_knowledge_weight
        self._public_knowledge_limit = settings.rag_public_knowledge_limit
        self._public_knowledge_categories = [
            cat.strip() for cat in settings.rag_public_knowledge_categories.split(",")
        ]
        self._public_knowledge_service = None

    async def initialize(self):
        """Initialize the retriever and load reranker model"""
        if self._initialized:
            return

        try:
            # Ensure Weaviate is initialized
            await weaviate_service.initialize()

            # Try to load cross-encoder reranker
            await self._load_reranker()

            # Initialize Public Knowledge service if enabled
            if self._public_knowledge_enabled:
                await self._initialize_public_knowledge()

            self._initialized = True
            logger.info("✅ MultiStageRetriever initialized")
        except Exception as e:
            logger.warning(f"⚠️ Reranker not loaded, using score-based fallback: {e}")
            self._initialized = True

    async def _initialize_public_knowledge(self):
        """Initialize the public knowledge service for legal context"""
        try:
            from ..public_knowledge_service import public_knowledge_service
            await public_knowledge_service.initialize()
            self._public_knowledge_service = public_knowledge_service
            logger.info("✅ Public Knowledge service initialized for legal context")
        except Exception as e:
            logger.warning(f"⚠️ Public Knowledge service not available: {e}")
            self._public_knowledge_service = None

    async def _load_reranker(self):
        """
        Try to load cross-encoder reranker.
        Falls back to embedding similarity if not available.
        """
        try:
            # Check if sentence-transformers is available
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                max_length=512
            )
            logger.info("✅ Loaded CrossEncoder reranker: ms-marco-MiniLM-L-6-v2")
        except ImportError:
            logger.info("ℹ️ sentence-transformers not installed, using embedding fallback for reranking")
            self._reranker = None
        except Exception as e:
            logger.warning(f"⚠️ Could not load reranker: {e}")
            self._reranker = None

    async def retrieve(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        user_id: Optional[str] = None,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        stage1_limit: int = 50,
        stage2_limit: int = 20,
        include_public_knowledge: Optional[bool] = None,
    ) -> List[RetrievedDocument]:
        """
        Execute 3-stage retrieval pipeline with optional Public Knowledge integration.

        Args:
            query_analysis: Analyzed query from Layer 1
            tenant_id: Tenant identifier
            collection_name: Optional specific collection (defaults to tenant collection)
            top_k: Final number of documents to return
            stage1_limit: Number of candidates from initial search
            stage2_limit: Number after reranking
            include_public_knowledge: Whether to include public legal knowledge (defaults to config setting)

        Returns:
            List of RetrievedDocument sorted by final score
        """
        await self.initialize()

        # Determine collection name
        if not collection_name:
            collection_name = _get_tenant_collection_name(tenant_id)

        # Determine if public knowledge should be included
        use_public_knowledge = include_public_knowledge if include_public_knowledge is not None else self._public_knowledge_enabled

        logger.info(f"🔍 Starting 3-stage retrieval for: '{query_analysis.original_query}' (public_knowledge={use_public_knowledge})")

        # Stage 1: Filtered vector/hybrid search (tenant documents)
        tenant_candidates = await self._stage1_filtered_search(
            query_analysis=query_analysis,
            tenant_id=tenant_id,
            user_id=user_id,
            collection_name=collection_name,
            limit=stage1_limit,
        )
        logger.info(f"  Stage 1a: {len(tenant_candidates)} candidates from tenant documents")

        # Stage 1b: Public Knowledge search (if enabled)
        public_candidates = []
        if use_public_knowledge and self._public_knowledge_service:
            public_candidates = await self._search_public_knowledge(
                query_analysis=query_analysis,
                limit=self._public_knowledge_limit,
            )
            logger.info(f"  Stage 1b: {len(public_candidates)} candidates from public knowledge")

        # Combine tenant and public candidates with RRF
        if tenant_candidates and public_candidates:
            candidates = self._merge_tenant_and_public(
                tenant_docs=tenant_candidates,
                public_docs=public_candidates,
            )
            logger.info(f"  Stage 1 merged: {len(candidates)} total candidates")
        elif tenant_candidates:
            candidates = tenant_candidates
        elif public_candidates:
            candidates = public_candidates
        else:
            candidates = []

        if not candidates:
            logger.warning("⚠️ No candidates found in Stage 1")
            return []

        # Stage 2: Semantic reranking
        reranked = await self._stage2_semantic_rerank(
            query=query_analysis.expanded_query,
            candidates=candidates,
            limit=stage2_limit,
        )
        logger.info(f"  Stage 2: {len(reranked)} results after reranking")

        # Stage 3: Context fusion (group by document, diversify)
        final = self._stage3_context_fusion(
            query_analysis=query_analysis,
            documents=reranked,
            limit=top_k,
        )
        logger.info(f"  Stage 3: {len(final)} final results after fusion")

        return final

    async def _search_public_knowledge(
        self,
        query_analysis: QueryAnalysis,
        limit: int,
    ) -> List[RetrievedDocument]:
        """
        Search the public knowledge base for legal/regulatory context.

        Returns documents from legislation, regulations, and jurisprudence
        that are relevant to the query.
        """
        if not self._public_knowledge_service:
            return []

        try:
            # Convert category strings to enum values
            categories = []
            for cat in self._public_knowledge_categories:
                try:
                    categories.append(PublicDocumentCategory(cat))
                except ValueError:
                    pass  # Skip invalid categories

            # Build search request
            search_request = PublicSearchRequest(
                query=query_analysis.expanded_query,
                limit=limit,
                categories=categories if categories else None,
                search_type="hybrid",  # Use hybrid for best results
                verified_only=True,  # Only use verified legal documents
            )

            # Execute search
            response = await self._public_knowledge_service.search(search_request)

            # Convert to RetrievedDocument format
            results = []
            for doc in response.results:
                # Build context-rich metadata
                metadata = {
                    "source": "public_knowledge",
                    "category": doc.category,
                    "jurisdiction": doc.jurisdiction,
                    "legal_reference": doc.legal_reference,
                    "verified": doc.verified,
                    "source_name": doc.source_name,
                    "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
                }

                results.append(RetrievedDocument(
                    id=doc.id,
                    title=f"[LEGAL] {doc.title}",  # Prefix to distinguish
                    content=doc.content,
                    score=doc.similarity_score or 0.5,
                    document_type=f"public_{doc.category}",
                    tenant_id="public",  # Mark as public document
                    metadata=metadata,
                ))

            return results

        except Exception as e:
            logger.warning(f"⚠️ Public knowledge search failed: {e}")
            return []

    def _merge_tenant_and_public(
        self,
        tenant_docs: List[RetrievedDocument],
        public_docs: List[RetrievedDocument],
    ) -> List[RetrievedDocument]:
        """
        Merge tenant and public documents using weighted interleaving.

        Public documents are weighted by the configured weight factor.
        This ensures legal context is included but tenant-specific docs
        are prioritized for direct answers.
        """
        # Apply weight adjustment to public docs
        for doc in public_docs:
            doc.score = doc.score * self._public_knowledge_weight

        # Use RRF to merge both lists
        merged = reciprocal_rank_fusion(
            dense_results=tenant_docs,  # Treat tenant as "dense"
            sparse_results=public_docs,  # Treat public as "sparse"
            k=self._rrf_k,
            dense_weight=1.0,  # Tenant weight
            sparse_weight=self._public_knowledge_weight,  # Public weight
        )

        return merged

    async def _stage1_filtered_search(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        user_id: Optional[str],
        collection_name: str,
        limit: int,
    ) -> List[RetrievedDocument]:
        """
        Stage 1: Hybrid search with RRF fusion

        Performs separate dense (vector) and sparse (BM25) searches,
        then combines them using Reciprocal Rank Fusion for better recall.

        Also searches multiple query variations and fuses all results.
        """
        # Collect results from multiple query variations
        all_dense_results: List[List[RetrievedDocument]] = []
        all_sparse_results: List[List[RetrievedDocument]] = []

        # Search with expanded query and variations
        queries_to_search = [query_analysis.expanded_query] + query_analysis.query_variations[:2]

        for query_text in queries_to_search:
            try:
                # Stage 1a: Dense vector search
                dense_results = await self._vector_search(
                    query=query_text,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    collection_name=collection_name,
                    limit=limit,
                )
                if dense_results:
                    all_dense_results.append(dense_results)
                    logger.debug(f"  Dense search returned {len(dense_results)} results")

                # Stage 1b: Sparse BM25 search
                sparse_results = await self._bm25_search(
                    query=query_text,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    collection_name=collection_name,
                    limit=limit,
                )
                if sparse_results:
                    all_sparse_results.append(sparse_results)
                    logger.debug(f"  Sparse search returned {len(sparse_results)} results")

            except Exception as e:
                logger.warning(f"⚠️ Search failed for variation '{query_text[:50]}...': {e}")
                continue

        # Stage 2: RRF Fusion
        # First, fuse all dense results across query variations
        fused_dense = multi_list_rrf(all_dense_results, k=self._rrf_k) if all_dense_results else []

        # Fuse all sparse results across query variations
        fused_sparse = multi_list_rrf(all_sparse_results, k=self._rrf_k) if all_sparse_results else []

        # Finally, fuse dense and sparse together using RRF
        if fused_dense and fused_sparse:
            candidates = reciprocal_rank_fusion(
                dense_results=fused_dense,
                sparse_results=fused_sparse,
                k=self._rrf_k,
                dense_weight=self._dense_weight,
                sparse_weight=self._sparse_weight,
            )
            logger.info(f"  RRF fusion: {len(fused_dense)} dense + {len(fused_sparse)} sparse → {len(candidates)} fused")
        elif fused_dense:
            candidates = fused_dense
            logger.info(f"  Using dense results only: {len(candidates)}")
        elif fused_sparse:
            candidates = fused_sparse
            logger.info(f"  Using sparse results only: {len(candidates)}")
        else:
            candidates = []
            logger.warning("  No results from either dense or sparse search")

        return candidates[:limit]

    async def _vector_search(
        self,
        query: str,
        tenant_id: str,
        user_id: Optional[str],
        collection_name: str,
        limit: int,
    ) -> List[RetrievedDocument]:
        """Execute dense vector search with channel access filtering"""
        try:
            search_request = SearchRequest(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,  # For channel access control
                limit=limit,
                search_type="vector",
                filters=None,
            )

            response = await weaviate_service.search_documents(
                collection_name=collection_name,
                search_request=search_request,
            )

            results = []
            for result in response.results:
                results.append(RetrievedDocument(
                    id=result.id,
                    title=result.title,
                    content=result.content,
                    score=result.similarity_score or 0.0,
                    vector_score=result.similarity_score,
                    document_type=result.document_type,
                    tenant_id=result.tenant_id,
                    metadata=result.metadata or {},
                ))
            return results

        except Exception as e:
            logger.warning(f"⚠️ Vector search failed: {e}")
            return []

    async def _bm25_search(
        self,
        query: str,
        tenant_id: str,
        user_id: Optional[str],
        collection_name: str,
        limit: int,
    ) -> List[RetrievedDocument]:
        """Execute sparse BM25 keyword search with channel access filtering"""
        try:
            search_request = SearchRequest(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,  # For channel access control
                limit=limit,
                search_type="keyword",
                filters=None,
            )

            response = await weaviate_service.search_documents(
                collection_name=collection_name,
                search_request=search_request,
            )

            results = []
            for result in response.results:
                results.append(RetrievedDocument(
                    id=result.id,
                    title=result.title,
                    content=result.content,
                    score=result.similarity_score or 0.0,
                    bm25_score=result.similarity_score,
                    document_type=result.document_type,
                    tenant_id=result.tenant_id,
                    metadata=result.metadata or {},
                ))
            return results

        except Exception as e:
            logger.warning(f"⚠️ BM25 search failed: {e}")
            return []

    async def _stage2_semantic_rerank(
        self,
        query: str,
        candidates: List[RetrievedDocument],
        limit: int,
    ) -> List[RetrievedDocument]:
        """
        Stage 2: Semantic reranking using cross-encoder

        Uses a cross-encoder model to compute query-document relevance
        more accurately than bi-encoder similarity.
        """
        if not candidates:
            return []

        # If cross-encoder is available, use it
        if self._reranker is not None:
            try:
                # Prepare pairs for cross-encoder
                pairs = [
                    (query, doc.content[:1000])  # Limit content length
                    for doc in candidates
                ]

                # Get scores from cross-encoder (synchronous call)
                scores = self._reranker.predict(pairs)

                # Update documents with rerank scores
                for doc, score in zip(candidates, scores):
                    doc.rerank_score = float(score)
                    # Combine with original score (weighted average)
                    doc.score = 0.3 * doc.score + 0.7 * float(score)

                # Sort by new combined score
                reranked = sorted(candidates, key=lambda d: d.score, reverse=True)
                return reranked[:limit]

            except Exception as e:
                logger.warning(f"⚠️ Cross-encoder reranking failed: {e}")
                # Fall through to embedding fallback

        # Fallback: Use embedding similarity for reranking
        return await self._rerank_by_embedding(query, candidates, limit)

    async def _rerank_by_embedding(
        self,
        query: str,
        candidates: List[RetrievedDocument],
        limit: int,
    ) -> List[RetrievedDocument]:
        """
        Fallback reranking using embedding cosine similarity.
        Less accurate than cross-encoder but always available.
        """
        try:
            # Get query embedding
            query_embedding = await self._get_embedding(query)
            if not query_embedding:
                # No embedding available, return original order
                return candidates[:limit]

            # Get content embeddings and compute similarity
            for doc in candidates:
                content_embedding = await self._get_embedding(doc.content[:1000])
                if content_embedding:
                    similarity = self._cosine_similarity(query_embedding, content_embedding)
                    doc.rerank_score = similarity
                    doc.score = 0.4 * doc.score + 0.6 * similarity
                else:
                    doc.rerank_score = doc.score

            # Sort and return
            reranked = sorted(candidates, key=lambda d: d.score, reverse=True)
            return reranked[:limit]

        except Exception as e:
            logger.warning(f"⚠️ Embedding reranking failed: {e}")
            return candidates[:limit]

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from TEI (Text Embeddings Inference)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._tei_url}/embed",
                    json={
                        "inputs": text,
                        "truncate": True
                    }
                )
                if response.status_code == 200:
                    embeddings = response.json()
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]
        except Exception:
            pass
        return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors"""
        if not a or not b or len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def _stage3_context_fusion(
        self,
        query_analysis: QueryAnalysis,
        documents: List[RetrievedDocument],
        limit: int,
    ) -> List[RetrievedDocument]:
        """
        Stage 3: Context fusion and diversity

        Groups chunks by document and ensures diversity in results.
        Prioritizes based on query intent.
        """
        if not documents:
            return []

        # Group by document title (chunks from same document)
        doc_groups: Dict[str, List[RetrievedDocument]] = defaultdict(list)
        for doc in documents:
            # Use title or ID as grouping key
            group_key = doc.title or doc.id
            doc_groups[group_key].append(doc)

        # Select best chunk per document group
        best_per_doc: List[RetrievedDocument] = []
        for group_key, chunks in doc_groups.items():
            # Sort chunks by score
            sorted_chunks = sorted(chunks, key=lambda d: d.score, reverse=True)
            best_chunk = sorted_chunks[0]

            # Add metadata about chunks
            best_chunk.total_chunks = len(chunks)
            best_chunk.chunk_index = 0

            best_per_doc.append(best_chunk)

        # Apply intent-based prioritization
        if query_analysis.intent == QueryIntent.ANALYZE:
            # For analysis, prefer longer documents
            best_per_doc.sort(key=lambda d: (len(d.content), d.score), reverse=True)
        elif query_analysis.intent == QueryIntent.COMPARE:
            # For comparison, ensure diversity in document types
            best_per_doc.sort(
                key=lambda d: (d.document_type or "", d.score),
                reverse=True
            )
        else:
            # Default: sort by score
            best_per_doc.sort(key=lambda d: d.score, reverse=True)

        # Ensure diversity in final results (MMR-like)
        final_results: List[RetrievedDocument] = []
        seen_types: Dict[str, int] = defaultdict(int)

        for doc in best_per_doc:
            if len(final_results) >= limit:
                break

            doc_type = doc.document_type or "unknown"

            # Penalize if too many of same type already selected
            if seen_types[doc_type] >= limit // 2:
                continue

            final_results.append(doc)
            seen_types[doc_type] += 1

        # Fill remaining slots if needed
        for doc in best_per_doc:
            if len(final_results) >= limit:
                break
            if doc not in final_results:
                final_results.append(doc)

        return final_results[:limit]


# Global instance
multi_stage_retriever = MultiStageRetriever()
