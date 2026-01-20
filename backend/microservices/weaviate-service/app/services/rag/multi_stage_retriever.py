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
import time
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import httpx

from .models import QueryAnalysis, RetrievedDocument, QueryIntent
from .rrf_fusion import reciprocal_rank_fusion, multi_list_rrf
from .soft_selection import (
    SoftSelector,
    SoftSelectionConfig,
    SoftSelectionResult,
    allocate_token_budget,
)
from .graph_retriever import graph_retriever
from ...core.config import settings
from ...core.security import get_tenant_collection_name
from ..weaviate_service import weaviate_service
from ...schemas.weaviate import SearchRequest
from ...schemas.public_knowledge import PublicSearchRequest, PublicDocumentCategory

logger = logging.getLogger(__name__)


# =============================================================================
# Chunk Expansion for Long Context RAG
# =============================================================================
# Adjacent chunk retrieval preserves context across chunk boundaries.
# When a relevant chunk is found, we also fetch chunks immediately before/after
# from the same document to provide fuller context to the LLM.


# Use centralized function from security module
def _get_tenant_collection_name(tenant_id: str) -> str:
    """Wrapper for centralized collection name generation."""
    return get_tenant_collection_name(tenant_id, "documents")


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

    def __init__(
        self,
        *,
        soft_selection_enabled: Optional[bool] = None,
        soft_selection_config: Optional[SoftSelectionConfig] = None,
        public_knowledge_enabled: Optional[bool] = None,
    ):
        self._reranker = None
        self._reranker_model = settings.embedding_model  # Use same for now
        self._tei_url = settings.tei_url
        self._initialized = False
        # RRF configuration
        self._rrf_k = 60  # Standard RRF constant
        self._dense_weight = 1.0
        self._sparse_weight = 1.0
        # Public Knowledge configuration
        self._public_knowledge_enabled = (
            settings.rag_public_knowledge_enabled
            if public_knowledge_enabled is None
            else public_knowledge_enabled
        )
        self._public_knowledge_weight = settings.rag_public_knowledge_weight
        self._public_knowledge_limit = settings.rag_public_knowledge_limit
        self._public_knowledge_categories = [
            cat.strip() for cat in settings.rag_public_knowledge_categories.split(",")
        ]
        self._public_knowledge_service = None

        # Soft Selection configuration (heuristic diversity-aware selection)
        self._soft_selection_enabled = (
            settings.rag_soft_selection_enabled
            if soft_selection_enabled is None
            else soft_selection_enabled
        )
        if self._soft_selection_enabled:
            config = soft_selection_config or SoftSelectionConfig(
                temperature=settings.rag_soft_selection_temperature,
                mmr_lambda=settings.rag_mmr_lambda,
                num_clusters=settings.rag_num_clusters,
                max_docs=settings.rag_max_docs,
                min_weight=settings.rag_min_weight,
                min_tokens_per_doc=settings.rag_min_tokens_per_doc,
            )
            self._soft_selector = SoftSelector(config)
        else:
            self._soft_selector = None

        # Storage for document embeddings (populated during retrieval)
        self._document_embeddings: Dict[str, List[float]] = {}

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

            # Initialize Graph-Enhanced Retriever if enabled
            if settings.rag_knowledge_graph_enabled:
                try:
                    await graph_retriever.initialize()
                    logger.info("✅ Graph-Enhanced Retriever initialized (Apache AGE)")
                except Exception as e:
                    logger.warning(f"⚠️ Graph-Enhanced Retriever not available: {e}")

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
            import torch

            # Use GPU if available
            device = "cuda" if torch.cuda.is_available() else "cpu"

            self._reranker = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                max_length=512,
                device=device
            )
            logger.info(f"✅ Loaded CrossEncoder reranker: ms-marco-MiniLM-L-6-v2 (device: {device})")
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
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        stage1_limit: int = 50,
        stage2_limit: int = 20,
        include_public_knowledge: Optional[bool] = None,
    ) -> Tuple[List[RetrievedDocument], Dict[str, Any]]:
        """
        Execute 3-stage retrieval pipeline with optional Public Knowledge integration.

        Args:
            query_analysis: Analyzed query from Layer 1
            tenant_id: Tenant identifier
            user_id: User identifier for ACL filtering
            user_role_ids: List of role IDs the user belongs to (for role-based ACL)
            is_admin: Whether user is admin (bypasses ACL checks)
            collection_name: Optional specific collection (defaults to tenant collection)
            top_k: Final number of documents to return
            stage1_limit: Number of candidates from initial search
            stage2_limit: Number after reranking
            include_public_knowledge: Whether to include public legal knowledge (defaults to config setting)

        Returns:
            Tuple of (List[RetrievedDocument], Dict[str, Any]) where dict contains selection_metadata

        SECURITY: user_id and user_role_ids are passed to all search operations
        for document-level ACL filtering. Only documents the user has permission
        to view will be returned.
        """
        await self.initialize()

        # Clear embedding storage for this retrieval
        self._document_embeddings.clear()

        # Determine collection name
        if not collection_name:
            collection_name = _get_tenant_collection_name(tenant_id)

        # Determine if public knowledge should be included
        use_public_knowledge = include_public_knowledge if include_public_knowledge is not None else self._public_knowledge_enabled

        logger.info(f"🔍 Starting 4-stage retrieval for: '{query_analysis.original_query}' (public_knowledge={use_public_knowledge}, soft_selection={self._soft_selection_enabled})")

        # =====================================================================
        # Stage 0: Graph-Enhanced Query Expansion (Knowledge Graph)
        # =====================================================================
        if settings.rag_knowledge_graph_enabled:
            try:
                graph_start = time.time()
                query_analysis = await graph_retriever.expand_query_with_graph(
                    query_analysis=query_analysis,
                    tenant_id=tenant_id,
                )
                graph_time_ms = (time.time() - graph_start) * 1000

                if query_analysis.graph_expansion and query_analysis.graph_expansion.get("applied"):
                    detected = query_analysis.graph_expansion.get("detected_entities", [])
                    expanded = query_analysis.graph_expansion.get("expanded_terms", [])
                    logger.info(
                        f"  Stage 0: Graph expansion - "
                        f"{len(detected)} entities, {len(expanded)} terms added "
                        f"({graph_time_ms:.0f}ms)"
                    )
                else:
                    logger.debug(f"  Stage 0: No graph expansion ({graph_time_ms:.0f}ms)")
            except Exception as e:
                logger.warning(f"  Stage 0: Graph expansion failed: {e}")

        # Stage 1: Filtered vector/hybrid search (tenant documents) with ACL
        tenant_candidates = await self._stage1_filtered_search(
            query_analysis=query_analysis,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
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
            return [], {}

        # Stage 2: Semantic reranking
        reranked = await self._stage2_semantic_rerank(
            query=query_analysis.expanded_query,
            candidates=candidates,
            limit=stage2_limit,
        )
        logger.info(f"  Stage 2: {len(reranked)} results after reranking")

        # Stage 2.5: Chunk Expansion (Long Context RAG)
        # Fetch adjacent chunks to preserve context across boundaries
        if settings.rag_chunk_expansion_enabled:
            expanded = await self.expand_chunks(
                documents=reranked,
                collection_name=collection_name,
                expand_size=settings.rag_chunk_expansion_size,
            )
            logger.info(f"  Stage 2.5: Expanded {len(reranked)} → {len(expanded)} documents with adjacent chunks")
            reranked = expanded

        # Stage 3: Context fusion with soft selection (group by document, diversify)
        final, selection_metadata = self._stage3_context_fusion(
            query_analysis=query_analysis,
            documents=reranked,
            limit=top_k,
        )
        logger.info(f"  Stage 3: {len(final)} final results after fusion")

        # Add chunk expansion metadata
        selection_metadata["chunk_expansion_enabled"] = settings.rag_chunk_expansion_enabled
        selection_metadata["chunk_expansion_size"] = settings.rag_chunk_expansion_size

        # Add graph expansion metadata
        selection_metadata["graph_expansion_enabled"] = settings.rag_knowledge_graph_enabled
        if query_analysis.graph_expansion:
            selection_metadata["graph_expansion"] = query_analysis.graph_expansion

        return final, selection_metadata

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

    # =========================================================================
    # CHUNK EXPANSION METHODS (Long Context RAG)
    # =========================================================================

    async def expand_chunks(
        self,
        documents: List[RetrievedDocument],
        collection_name: str,
        expand_size: int = 1,
    ) -> List[RetrievedDocument]:
        """
        Expand retrieved chunks with adjacent chunks from the same document.

        This preserves context across chunk boundaries, which is critical for:
        - Legal documents where clauses reference previous sections
        - Technical documentation with cross-references
        - Narratives that span multiple chunks

        Args:
            documents: Retrieved documents to expand
            collection_name: Weaviate collection name
            expand_size: Number of chunks to fetch before/after each result

        Returns:
            List of documents with expanded content from adjacent chunks
        """
        if not settings.rag_chunk_expansion_enabled or expand_size <= 0:
            return documents

        expanded_docs = []
        processed_chunks = set()  # Avoid duplicate expansions

        for doc in documents:
            # Extract chunk metadata
            chunk_index = doc.metadata.get("chunk_index", 0)
            total_chunks = doc.metadata.get("total_chunks", 1)
            document_id = doc.metadata.get("document_id") or doc.document_id

            # Skip if no document_id or already processed
            chunk_key = f"{document_id}:{chunk_index}"
            if not document_id or chunk_key in processed_chunks:
                expanded_docs.append(doc)
                continue

            processed_chunks.add(chunk_key)

            # Fetch adjacent chunks
            try:
                adjacent_chunks = await self._fetch_adjacent_chunks(
                    document_id=document_id,
                    current_chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    expand_size=expand_size,
                    collection_name=collection_name,
                )

                if adjacent_chunks:
                    # Merge adjacent chunks into expanded document
                    expanded_doc = self._merge_adjacent_chunks(doc, adjacent_chunks)
                    expanded_docs.append(expanded_doc)
                    # Mark adjacent chunks as processed
                    for adj in adjacent_chunks:
                        adj_idx = adj.get("chunk_index", 0)
                        processed_chunks.add(f"{document_id}:{adj_idx}")
                else:
                    expanded_docs.append(doc)

            except Exception as e:
                logger.warning(f"⚠️ Chunk expansion failed for {document_id}: {e}")
                expanded_docs.append(doc)

        return expanded_docs

    async def _fetch_adjacent_chunks(
        self,
        document_id: str,
        current_chunk_index: int,
        total_chunks: int,
        expand_size: int,
        collection_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetch adjacent chunks from Weaviate by document_id and chunk_index.

        Args:
            document_id: Parent document ID
            current_chunk_index: Index of the current chunk
            total_chunks: Total number of chunks in the document
            expand_size: Number of chunks to fetch before/after
            collection_name: Weaviate collection name

        Returns:
            List of adjacent chunk data dictionaries
        """
        # Calculate indices to fetch
        indices_to_fetch = []
        for offset in range(-expand_size, expand_size + 1):
            if offset == 0:
                continue  # Skip current chunk
            target_idx = current_chunk_index + offset
            if 0 <= target_idx < total_chunks:
                indices_to_fetch.append(target_idx)

        if not indices_to_fetch:
            return []

        try:
            # Query Weaviate for adjacent chunks by document_id + chunk_index
            adjacent_chunks = await weaviate_service.fetch_chunks_by_indices(
                collection_name=collection_name,
                document_id=document_id,
                chunk_indices=indices_to_fetch,
            )
            return adjacent_chunks

        except Exception as e:
            logger.debug(f"Could not fetch adjacent chunks: {e}")
            return []

    def _merge_adjacent_chunks(
        self,
        primary_doc: RetrievedDocument,
        adjacent_chunks: List[Dict[str, Any]],
    ) -> RetrievedDocument:
        """
        Merge primary document with adjacent chunks into expanded content.

        Chunks are ordered by chunk_index and merged with clear delimiters.

        Args:
            primary_doc: The originally retrieved document
            adjacent_chunks: Adjacent chunk data from Weaviate

        Returns:
            New RetrievedDocument with expanded content
        """
        primary_idx = primary_doc.metadata.get("chunk_index", 0)

        # Create list of all chunks including primary
        all_chunks = [
            {
                "chunk_index": primary_idx,
                "content": primary_doc.content,
                "is_primary": True,
            }
        ]

        for chunk in adjacent_chunks:
            all_chunks.append({
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk.get("content", ""),
                "is_primary": False,
            })

        # Sort by chunk_index
        all_chunks.sort(key=lambda c: c["chunk_index"])

        # Merge content with markers
        merged_parts = []
        for chunk in all_chunks:
            if chunk["is_primary"]:
                merged_parts.append(f"[FRAGMENTO PRINCIPAL (chunk {chunk['chunk_index']})]\n{chunk['content']}")
            else:
                merged_parts.append(f"[CONTEXTO ADYACENTE (chunk {chunk['chunk_index']})]\n{chunk['content']}")

        merged_content = "\n\n---\n\n".join(merged_parts)

        # Create new document with expanded content
        expanded_doc = RetrievedDocument(
            id=primary_doc.id,
            title=primary_doc.title,
            content=merged_content,
            score=primary_doc.score,
            document_type=primary_doc.document_type,
            tenant_id=primary_doc.tenant_id,
            metadata={
                **primary_doc.metadata,
                "expanded": True,
                "expansion_size": len(all_chunks),
                "chunk_range": f"{all_chunks[0]['chunk_index']}-{all_chunks[-1]['chunk_index']}",
            },
            vector_score=primary_doc.vector_score,
            bm25_score=primary_doc.bm25_score,
            rerank_score=primary_doc.rerank_score,
            chunk_index=primary_doc.chunk_index,
            total_chunks=primary_doc.total_chunks,
        )

        return expanded_doc

    async def _stage1_filtered_search(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        user_id: Optional[str],
        user_role_ids: Optional[List[str]],
        is_admin: bool,
        collection_name: str,
        limit: int,
    ) -> List[RetrievedDocument]:
        """
        Stage 1: Hybrid search with RRF fusion and ACL filtering

        Performs separate dense (vector) and sparse (BM25) searches,
        then combines them using Reciprocal Rank Fusion for better recall.

        Also searches multiple query variations and fuses all results.

        SECURITY: All searches are filtered by user ACL permissions.
        """
        # Collect results from multiple query variations
        all_dense_results: List[List[RetrievedDocument]] = []
        all_sparse_results: List[List[RetrievedDocument]] = []

        # Search with expanded query and variations
        queries_to_search = [query_analysis.expanded_query] + query_analysis.query_variations[:2]

        for query_text in queries_to_search:
            try:
                # Stage 1a: Dense vector search with ACL
                dense_results = await self._vector_search(
                    query=query_text,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role_ids=user_role_ids,
                    is_admin=is_admin,
                    collection_name=collection_name,
                    limit=limit,
                )
                if dense_results:
                    all_dense_results.append(dense_results)
                    logger.debug(f"  Dense search returned {len(dense_results)} results")

                # Stage 1b: Sparse BM25 search with ACL
                sparse_results = await self._bm25_search(
                    query=query_text,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role_ids=user_role_ids,
                    is_admin=is_admin,
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
        user_role_ids: Optional[List[str]],
        is_admin: bool,
        collection_name: str,
        limit: int,
    ) -> List[RetrievedDocument]:
        """Execute dense vector search with ACL filtering"""
        try:
            search_request = SearchRequest(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,  # ACL: user identification
                user_role_ids=user_role_ids,  # ACL: role-based access
                is_admin=is_admin,  # ACL: admin bypass
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
        user_role_ids: Optional[List[str]],
        is_admin: bool,
        collection_name: str,
        limit: int,
    ) -> List[RetrievedDocument]:
        """Execute sparse BM25 keyword search with ACL filtering"""
        try:
            search_request = SearchRequest(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,  # ACL: user identification
                user_role_ids=user_role_ids,  # ACL: role-based access
                is_admin=is_admin,  # ACL: admin bypass
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
    ) -> Tuple[List[RetrievedDocument], Dict[str, Any]]:
        """
        Stage 3: Context fusion with soft selection (heuristic diversity)

        Groups chunks by document, applies soft selection with:
        - Softmax re-weighting
        - MMR-based diversity (if embeddings available)
        - Stratified cluster selection (if clustering enabled)

        Returns:
            Tuple of (selected_documents, selection_metadata)
        """
        if not documents:
            return [], {}

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

        # Apply intent-based pre-sorting (before soft selection)
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

        # Use soft selection if enabled
        if self._soft_selection_enabled and self._soft_selector:
            selection_result = self._soft_selector.select(
                documents=best_per_doc,
                embeddings=self._document_embeddings if self._document_embeddings else None,
                top_k=limit,
                query_embedding=query_analysis.embeddings,
            )

            # Populate soft selection fields on documents
            for doc in selection_result.documents:
                doc.soft_weight = selection_result.soft_weights.get(doc.id)
                doc.cluster_id = selection_result.cluster_assignments.get(doc.id)

            selection_metadata = {
                "soft_weights": selection_result.soft_weights,
                "cluster_assignments": selection_result.cluster_assignments,
                "diversity_score": selection_result.diversity_score,
                "coverage_score": selection_result.coverage_score,
                "dropped_by_weight": selection_result.dropped_by_weight,
                "dropped_by_cap": selection_result.dropped_by_cap,
                "soft_selection_enabled": True,
            }

            return selection_result.documents, selection_metadata

        # Fallback: Legacy hard cutoff with type diversity
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

        return final_results[:limit], {"soft_selection_enabled": False}

    # =========================================================================
    # MULTIMODAL RETRIEVAL METHODS (Cross-modal search support)
    # =========================================================================

    async def retrieve_multimodal(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        stage1_limit: int = 50,
        stage2_limit: int = 20,
        include_public_knowledge: Optional[bool] = None,
        include_visual: bool = True,
        visual_limit: int = 5,
        visual_content_types: Optional[List[str]] = None,
    ) -> Tuple[List[RetrievedDocument], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute multimodal retrieval: text + visual content search with RRF fusion.

        This method extends the standard retrieve() to also search for relevant
        visual content (tables, diagrams, images) that match the query.

        Args:
            query_analysis: Analyzed query from Layer 1
            tenant_id: Tenant identifier
            user_id: User identifier for ACL filtering
            user_role_ids: Role IDs for role-based ACL
            is_admin: Whether user is admin (bypasses ACL)
            collection_name: Optional specific collection
            top_k: Final number of text documents to return
            stage1_limit: Number of candidates from initial search
            stage2_limit: Number after reranking
            include_public_knowledge: Include public legal knowledge
            include_visual: Whether to search visual content
            visual_limit: Maximum visual results to return
            visual_content_types: Filter visual content types (image, table_image, diagram)

        Returns:
            Tuple of (text_documents, visual_results, metadata)
            - text_documents: List[RetrievedDocument] from text search
            - visual_results: List[Dict] with visual content metadata
            - metadata: Dict with selection and retrieval metadata
        """
        await self.initialize()

        # Execute standard text retrieval
        text_docs, selection_metadata = await self.retrieve(
            query_analysis=query_analysis,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            collection_name=collection_name,
            top_k=top_k,
            stage1_limit=stage1_limit,
            stage2_limit=stage2_limit,
            include_public_knowledge=include_public_knowledge,
        )

        # Execute visual content search if enabled
        visual_results = []
        if include_visual and settings.multimodal_embedding_enabled:
            visual_results = await self._search_visual_content(
                query_analysis=query_analysis,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role_ids=user_role_ids,
                limit=visual_limit,
                content_types=visual_content_types,
            )
            logger.info(f"  Visual search: {len(visual_results)} visual results")

        # Update metadata
        metadata = {
            **selection_metadata,
            "multimodal_enabled": include_visual and settings.multimodal_embedding_enabled,
            "visual_results_count": len(visual_results),
            "text_results_count": len(text_docs),
        }

        return text_docs, visual_results, metadata

    async def _search_visual_content(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        limit: int = 5,
        content_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for visual content using the query embedding.

        Uses the multimodal embedding service to generate a query embedding
        compatible with visual content, then searches the visual collection.

        Args:
            query_analysis: Analyzed query with embedding
            tenant_id: Tenant identifier
            user_id: User ID for ACL filtering
            user_role_ids: Role IDs for ACL
            limit: Maximum results
            content_types: Filter by content types

        Returns:
            List of visual content results with metadata
        """
        try:
            # Import multimodal embedding service
            from ..multimodal_embedding_service import multimodal_embedding_service

            if not multimodal_embedding_service.is_multimodal_enabled:
                return []

            # Generate query embedding using Qwen3-VL for cross-modal compatibility
            # This ensures text queries can find relevant images
            query_embedding_result = await multimodal_embedding_service.embed_texts(
                texts=[query_analysis.expanded_query],
                use_multimodal=True,  # Use Qwen3-VL for cross-modal search
            )

            if not query_embedding_result.success or not query_embedding_result.vectors:
                logger.warning("⚠️ Failed to generate query embedding for visual search")
                return []

            query_vector = query_embedding_result.vectors[0]

            # Search visual content collection
            visual_results = await weaviate_service.search_visual_content(
                tenant_id=tenant_id,
                query_vector=query_vector,
                user_id=user_id,
                user_role_ids=user_role_ids,
                content_types=content_types,
                limit=limit,
                certainty=0.65,  # Lower threshold for cross-modal search
            )

            return visual_results

        except Exception as e:
            logger.warning(f"⚠️ Visual content search failed: {e}")
            return []

    async def retrieve_with_cross_modal_rrf(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        visual_top_k: int = 3,
        text_weight: float = 1.0,
        visual_weight: float = 0.5,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute cross-modal retrieval with RRF fusion of text and visual results.

        This method combines text documents and visual content into a single
        ranked list using Reciprocal Rank Fusion, useful for queries like
        "show me the organization chart" or "find tables about revenue".

        Args:
            query_analysis: Analyzed query
            tenant_id: Tenant identifier
            user_id: User ID for ACL
            user_role_ids: Role IDs for ACL
            is_admin: Admin bypass flag
            collection_name: Optional collection name
            top_k: Total results to return (text + visual combined)
            visual_top_k: Maximum visual results before RRF
            text_weight: Weight for text results in RRF
            visual_weight: Weight for visual results in RRF

        Returns:
            Tuple of (combined_results, metadata)
            - combined_results: List of dicts with 'type' field (text/visual)
            - metadata: Retrieval metadata
        """
        await self.initialize()

        # Get text results
        text_docs, selection_metadata = await self.retrieve(
            query_analysis=query_analysis,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            collection_name=collection_name,
            top_k=top_k * 2,  # Get more candidates for RRF
        )

        # Get visual results
        visual_results = []
        if settings.multimodal_embedding_enabled:
            visual_results = await self._search_visual_content(
                query_analysis=query_analysis,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role_ids=user_role_ids,
                limit=visual_top_k * 2,
            )

        # Convert to unified format for RRF
        text_ranked = [
            {
                "id": doc.chunk_id or doc.document_id,
                "type": "text",
                "score": doc.score,
                "document_id": doc.document_id,
                "content": doc.content,
                "title": doc.title,
                "metadata": doc.metadata,
            }
            for doc in text_docs
        ]

        visual_ranked = [
            {
                "id": v["visual_id"],
                "type": "visual",
                "score": v.get("certainty", 0.5),
                "document_id": v["document_id"],
                "content_type": v["content_type"],
                "caption": v.get("caption"),
                "page_number": v["page_number"],
                "bbox": v["bbox"],
                "metadata": {
                    "width": v.get("width"),
                    "height": v.get("height"),
                    "embedding_model": v.get("embedding_model"),
                },
            }
            for v in visual_results
        ]

        # Apply RRF fusion with weights
        if text_ranked and visual_ranked:
            # Apply weights by adjusting ranks
            combined = self._cross_modal_rrf_fusion(
                text_ranked=text_ranked,
                visual_ranked=visual_ranked,
                text_weight=text_weight,
                visual_weight=visual_weight,
                k=self._rrf_k,
            )
        elif text_ranked:
            combined = text_ranked
        elif visual_ranked:
            combined = visual_ranked
        else:
            combined = []

        # Apply top_k limit
        combined = combined[:top_k]

        metadata = {
            **selection_metadata,
            "cross_modal_rrf": True,
            "text_candidates": len(text_ranked),
            "visual_candidates": len(visual_ranked),
            "combined_results": len(combined),
            "text_weight": text_weight,
            "visual_weight": visual_weight,
        }

        return combined, metadata

    def _cross_modal_rrf_fusion(
        self,
        text_ranked: List[Dict[str, Any]],
        visual_ranked: List[Dict[str, Any]],
        text_weight: float = 1.0,
        visual_weight: float = 0.5,
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Apply RRF fusion to combine text and visual results.

        Uses the formula: score(d) = Σ weight_i / (k + rank_i(d))

        Args:
            text_ranked: Text results sorted by relevance
            visual_ranked: Visual results sorted by relevance
            text_weight: Weight for text results
            visual_weight: Weight for visual results
            k: RRF constant (default 60)

        Returns:
            Combined and re-ranked results
        """
        # Calculate RRF scores
        rrf_scores: Dict[str, float] = {}
        id_to_item: Dict[str, Dict[str, Any]] = {}

        # Process text results
        for rank, item in enumerate(text_ranked):
            item_id = item["id"]
            rrf_score = text_weight / (k + rank + 1)
            rrf_scores[item_id] = rrf_scores.get(item_id, 0) + rrf_score
            id_to_item[item_id] = item

        # Process visual results
        for rank, item in enumerate(visual_ranked):
            item_id = item["id"]
            rrf_score = visual_weight / (k + rank + 1)
            rrf_scores[item_id] = rrf_scores.get(item_id, 0) + rrf_score
            id_to_item[item_id] = item

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # Build combined results
        combined = []
        for item_id in sorted_ids:
            item = id_to_item[item_id].copy()
            item["rrf_score"] = rrf_scores[item_id]
            combined.append(item)

        return combined


# Global instance
multi_stage_retriever = MultiStageRetriever()
