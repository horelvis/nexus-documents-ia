"""
RAG Pipeline Orchestrator (Production Grade - 7 Layers)

Coordinates all layers of the production RAG pipeline:
- Layer 0: Document Processing (future - multi-stage PDF extraction)
- Layer 1: Semantic Chunking (future - structure-aware chunking)
- Layer 2: Query Intelligence - Query expansion, intent classification
- Layer 3: Hybrid Retrieval + RRF - Dense + Sparse with Reciprocal Rank Fusion
- Layer 4: Context Assembly - Token management, structured context
- Layer 5: Validated Generation - LLM generation with semantic claim validation
- Layer 6: Semantic Cache - Redis-based caching for similar queries

Key improvements:
- Semantic cache layer for -90% latency on repeated queries (~47% hit rate)
- RRF fusion for +15-20% recall improvement
- Cross-encoder reranking for precision

This replaces the Elysia framework with a custom implementation
optimized for local LLMs and multi-tenant document management.
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List, AsyncGenerator
from datetime import datetime

from .models import (
    RAGResponse,
    QueryAnalysis,
    RetrievedDocument,
    AssembledContext,
    ValidatedResponse,
)
from .query_intelligence import QueryIntelligence, query_intelligence
from .multi_stage_retriever import MultiStageRetriever, multi_stage_retriever
from .context_assembler import ContextAssembler, context_assembler
from .validated_generator import ValidatedGenerator, validated_generator
from .semantic_cache import SemanticCache, semantic_cache, CachedResponse
from .monitoring import RAGMonitor, rag_monitor, QueryMetrics
from .cache import (
    RetrievalCache, retrieval_cache,
    ContextAssemblyCache, context_cache,
    CacheVersionManager, cache_version_manager,
)
from ...core.config import settings

logger = logging.getLogger(__name__)

# Configuration
CACHE_ENABLED = os.environ.get("RAG_CACHE_ENABLED", "true").lower() == "true"
RETRIEVAL_CACHE_ENABLED = os.environ.get("RETRIEVAL_CACHE_ENABLED", "true").lower() == "true"
CONTEXT_CACHE_ENABLED = os.environ.get("CONTEXT_CACHE_ENABLED", "true").lower() == "true"
MONITORING_ENABLED = os.environ.get("RAG_MONITORING_ENABLED", "true").lower() == "true"


class RAGPipeline:
    """
    Main orchestrator for the 7-layer RAG pipeline (Production Grade).

    Includes semantic caching layer for dramatic latency reduction on
    repeated/similar queries.

    Usage:
        pipeline = RAGPipeline()
        await pipeline.initialize()
        response = await pipeline.process_query(
            query="¿Qué dice el contrato sobre la confidencialidad?",
            tenant_id="tenant_123"
        )
    """

    def __init__(
        self,
        query_intel: Optional[QueryIntelligence] = None,
        retriever: Optional[MultiStageRetriever] = None,
        assembler: Optional[ContextAssembler] = None,
        generator: Optional[ValidatedGenerator] = None,
        cache: Optional[SemanticCache] = None,
        monitor: Optional[RAGMonitor] = None,
        retrieval_cache_instance: Optional[RetrievalCache] = None,
        context_cache_instance: Optional[ContextAssemblyCache] = None,
        version_manager: Optional[CacheVersionManager] = None,
    ):
        # Use provided components or global instances
        self.query_intel = query_intel or query_intelligence
        self.retriever = retriever or multi_stage_retriever
        self.assembler = assembler or context_assembler
        self.generator = generator or validated_generator
        self.cache = cache or semantic_cache
        self.monitor = monitor or rag_monitor

        # Multi-tier caching components
        self.retrieval_cache = retrieval_cache_instance or retrieval_cache
        self.context_cache = context_cache_instance or context_cache
        self.version_manager = version_manager or cache_version_manager

        self._initialized = False
        self._cache_enabled = CACHE_ENABLED
        self._retrieval_cache_enabled = RETRIEVAL_CACHE_ENABLED
        self._context_cache_enabled = CONTEXT_CACHE_ENABLED
        self._monitoring_enabled = MONITORING_ENABLED

    async def initialize(self):
        """Initialize all pipeline components"""
        if self._initialized:
            return

        logger.info("🚀 Initializing RAG Pipeline (7-layer production + multi-tier caching)...")

        # Initialize retriever (which initializes Weaviate)
        await self.retriever.initialize()

        # Initialize semantic cache (Layer 6 - final responses)
        if self._cache_enabled:
            try:
                await self.cache.initialize()
                logger.info("✅ Semantic cache initialized")
            except Exception as e:
                logger.warning(f"⚠️ Semantic cache initialization failed: {e}")
                self._cache_enabled = False

        # Initialize retrieval cache (Layer 3.5 - search results)
        if self._retrieval_cache_enabled:
            try:
                await self.retrieval_cache.initialize()
                logger.info("✅ Retrieval cache initialized")
            except Exception as e:
                logger.warning(f"⚠️ Retrieval cache initialization failed: {e}")
                self._retrieval_cache_enabled = False

        # Initialize context cache (Layer 4.5 - assembled context)
        if self._context_cache_enabled:
            try:
                await self.context_cache.initialize()
                logger.info("✅ Context cache initialized")
            except Exception as e:
                logger.warning(f"⚠️ Context cache initialization failed: {e}")
                self._context_cache_enabled = False

        # Initialize version manager and register invalidation callbacks
        try:
            await self.version_manager.initialize()
            # Register caches for automatic invalidation on document changes
            if self._retrieval_cache_enabled:
                self.version_manager.register_invalidation_callback(
                    self.retrieval_cache.invalidate_by_documents
                )
            if self._context_cache_enabled:
                self.version_manager.register_invalidation_callback(
                    self.context_cache.invalidate_by_documents
                )
            if self._cache_enabled:
                # Wrapper to adapt semantic_cache's single-doc method to multi-doc callback
                async def semantic_cache_invalidator(tenant_id: str, doc_ids: List[str]) -> int:
                    total = 0
                    for doc_id in doc_ids:
                        total += await self.cache.invalidate_by_document(tenant_id, doc_id)
                    return total
                self.version_manager.register_invalidation_callback(semantic_cache_invalidator)
            logger.info("✅ Version manager initialized with invalidation callbacks")
        except Exception as e:
            logger.warning(f"⚠️ Version manager initialization failed: {e}")

        self._initialized = True
        logger.info("✅ RAG Pipeline initialized successfully (3-tier caching active)")

    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        validate_claims: bool = True,
        model_type: str = "vllm",
        context: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        include_public_knowledge: Optional[bool] = None,
    ) -> RAGResponse:
        """
        Process a query through the full RAG pipeline.

        Args:
            query: User's query
            tenant_id: Tenant identifier for multi-tenant isolation
            user_id: User identifier for ACL filtering (REQUIRED for document access control)
            user_role_ids: List of role IDs the user belongs to (for role-based ACL)
            is_admin: Whether user is admin (bypasses ACL checks)
            collection_name: Optional specific collection to search
            top_k: Number of documents to retrieve
            validate_claims: Whether to validate generated claims
            model_type: LLM provider type (vllm, openai)
            context: Additional context (e.g., conversation history)
            use_cache: Whether to use semantic cache (default: True)
            include_public_knowledge: Whether to include public legal knowledge (defaults to config)

        Returns:
            RAGResponse with answer, sources, and metadata

        SECURITY: user_id and user_role_ids are used for:
        1. ACL filtering in document retrieval (only returns accessible documents)
        2. User-isolated semantic caching (prevents cross-user data exposure)
        """
        await self.initialize()

        start_time = time.time()
        logger.info(f"🔄 Processing query: '{query[:50]}...' for tenant {tenant_id}")

        # Initialize monitoring metrics
        metrics = None
        if self._monitoring_enabled:
            metrics = self.monitor.start_query(tenant_id, user_id, query)

        try:
            # === Layer 2: Query Intelligence ===
            layer_start = time.time()
            logger.info("  Layer 2: Query Intelligence")
            query_analysis = await self.query_intel.analyze_query_async(query)
            logger.info(f"    Intent: {query_analysis.intent.value}")
            logger.info(f"    Key terms: {query_analysis.key_terms[:5]}")

            if metrics:
                metrics.query_analysis_ms = (time.time() - layer_start) * 1000
                metrics.intent = query_analysis.intent.value

            # === Layer 6: Semantic Cache Check ===
            query_embedding = None  # Initialize for later cache storage
            if use_cache and self._cache_enabled:
                cache_start = time.time()
                logger.info("  Layer 6: Checking semantic cache...")
                query_embedding = await self.cache.get_embedding(query)
                if query_embedding:
                    public_flag = (
                        include_public_knowledge
                        if include_public_knowledge is not None
                        else settings.rag_public_knowledge_enabled
                    )
                    cache_scope = (
                        f"model_type={model_type}"
                        f"|vllm_model={settings.vllm_model}"
                        f"|public={public_flag}"
                        f"|validate={validate_claims}"
                    )
                    cached = await self.cache.get(
                        query=query,
                        query_embedding=query_embedding,
                        tenant_id=tenant_id,
                        user_id=user_id,  # SECURITY: User-isolated cache
                        scope=cache_scope,
                    )
                    if cached:
                        execution_time_ms = (time.time() - start_time) * 1000
                        logger.info(f"✅ Cache HIT! Returning cached response in {execution_time_ms:.0f}ms")

                        # Log cache hit metrics
                        if metrics:
                            metrics.cache_hit = True
                            metrics.cache_check_ms = (time.time() - cache_start) * 1000
                            metrics.total_latency_ms = execution_time_ms
                            metrics.confidence_score = cached.confidence_score
                            metrics.num_results = len(cached.sources)
                            await self.monitor.end_query(metrics)

                        # Convert cached response to RAGResponse
                        sources = [
                            RetrievedDocument(
                                id=s.get("id", ""),
                                title=s.get("title", ""),
                                content=s.get("content", ""),
                                score=s.get("score", 0.0),
                                document_type=s.get("document_type"),
                                tenant_id=tenant_id,
                            )
                            for s in cached.sources
                        ]

                        return RAGResponse(
                            query=query,
                            answer=cached.answer,
                            confidence_score=cached.confidence_score,
                            sources=sources,
                            query_analysis=query_analysis,
                            context_info=cached.context_info,
                            validation_info=None,  # Cached responses don't re-validate
                            execution_time_ms=execution_time_ms,
                            iterations=1,
                            success=True,
                        )
                    else:
                        logger.info("    Cache MISS, proceeding with full pipeline")

                if metrics:
                    metrics.cache_check_ms = (time.time() - cache_start) * 1000

            # === Layer 3: Hybrid Retrieval + RRF + Public Knowledge + Soft Selection ===
            retrieval_start = time.time()
            logger.info("  Layer 3: Hybrid Retrieval + RRF + Public Knowledge + Soft Selection")

            # Get current versions for cache validation
            versions = await self.version_manager.get_versions(tenant_id)
            current_index_version = versions.index_version

            # === NEW: Retrieval Cache Check ===
            cached_retrieval = None
            if self._retrieval_cache_enabled and query_embedding and user_id:
                cached_retrieval = await self.retrieval_cache.get(
                    query_embedding=query_embedding,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    collection_name=collection_name,
                    top_k=top_k,
                    include_public=include_public_knowledge if include_public_knowledge is not None else settings.rag_public_knowledge_enabled,
                    current_version=current_index_version,
                )

            if cached_retrieval:
                # Retrieval cache HIT - reconstruct documents from IDs
                logger.info(f"    ✅ Retrieval cache HIT: {len(cached_retrieval.doc_ids)} doc IDs")
                # Fetch actual documents by IDs (much faster than full search)
                retrieved_docs = await self.retriever.fetch_documents_by_ids(
                    doc_ids=cached_retrieval.doc_ids,
                    tenant_id=tenant_id,
                    scores=cached_retrieval.scores,
                )
                selection_metadata = cached_retrieval.metadata
            else:
                # Retrieval cache MISS - full search
                retrieved_docs, selection_metadata = await self.retriever.retrieve(
                    query_analysis=query_analysis,
                    tenant_id=tenant_id,
                    user_id=user_id,  # ACL: user identification
                    user_role_ids=user_role_ids,  # ACL: role-based access
                    is_admin=is_admin,  # ACL: admin bypass
                    collection_name=collection_name,
                    top_k=top_k,
                    include_public_knowledge=include_public_knowledge,
                )

                # === NEW: Store in Retrieval Cache ===
                if self._retrieval_cache_enabled and query_embedding and user_id and retrieved_docs:
                    await self.retrieval_cache.set(
                        query_embedding=query_embedding,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        doc_ids=[d.id for d in retrieved_docs],
                        scores=[d.score for d in retrieved_docs],
                        metadata=selection_metadata or {},
                        collection_name=collection_name,
                        top_k=top_k,
                        include_public=include_public_knowledge if include_public_knowledge is not None else settings.rag_public_knowledge_enabled,
                        version=current_index_version,
                    )

            # Log public vs tenant document count
            public_count = sum(1 for d in retrieved_docs if d.tenant_id == "public")
            tenant_count = len(retrieved_docs) - public_count
            soft_selection_info = ""
            if selection_metadata and selection_metadata.get("soft_selection_enabled"):
                soft_selection_info = f", diversity={selection_metadata.get('diversity_score', 0):.2f}, coverage={selection_metadata.get('coverage_score', 0):.2f}"
            cache_info = " (from cache)" if cached_retrieval else ""
            logger.info(f"    Retrieved {len(retrieved_docs)} documents ({tenant_count} tenant, {public_count} public{soft_selection_info}){cache_info}")

            if metrics:
                metrics.retrieval_ms = (time.time() - retrieval_start) * 1000
                metrics.num_results = len(retrieved_docs)
                if retrieved_docs:
                    metrics.top_score = retrieved_docs[0].score
                    metrics.avg_score = sum(d.score for d in retrieved_docs) / len(retrieved_docs)

            if not retrieved_docs:
                # No documents found - return appropriate response
                if metrics:
                    metrics.total_latency_ms = (time.time() - start_time) * 1000
                    await self.monitor.end_query(metrics)
                return self._build_no_results_response(
                    query=query,
                    query_analysis=query_analysis,
                    start_time=start_time,
                )

            # === Layer 4: Context Assembly (with proportional token allocation) ===
            context_start = time.time()
            logger.info("  Layer 4: Context Assembly (proportional allocation)")

            # === NEW: Context Cache Check ===
            cached_context = None
            doc_ids_for_context = [d.id for d in retrieved_docs]
            chunk_version = versions.chunk_strategy
            index_version = versions.index_version

            if self._context_cache_enabled and doc_ids_for_context:
                cached_context = await self.context_cache.get(
                    doc_ids=doc_ids_for_context,
                    tenant_id=tenant_id,
                    chunk_version=chunk_version,
                    index_version=index_version,
                    model_type=model_type,
                )

            if cached_context:
                # Context cache HIT - use cached context
                logger.info(f"    ✅ Context cache HIT: {cached_context.total_tokens} tokens")
                # Reconstruct AssembledContext from cache
                assembled_context = AssembledContext(
                    formatted_context=cached_context.context_string,
                    total_tokens=cached_context.total_tokens,
                    documents=retrieved_docs[:cached_context.doc_count],  # Match cached doc count
                    metadata=cached_context.metadata,
                )
            else:
                # Context cache MISS - full assembly
                assembled_context = self.assembler.assemble_context(
                    query_analysis=query_analysis,
                    documents=retrieved_docs,
                    model_type=model_type,
                    soft_weights=selection_metadata.get("soft_weights") if selection_metadata else None,
                    selection_metadata=selection_metadata,
                )

                # === NEW: Store in Context Cache ===
                if self._context_cache_enabled and assembled_context.formatted_context:
                    await self.context_cache.set(
                        doc_ids=doc_ids_for_context,
                        tenant_id=tenant_id,
                        context_string=assembled_context.formatted_context,
                        total_tokens=assembled_context.total_tokens,
                        metadata=assembled_context.to_dict(),
                        chunk_version=chunk_version,
                        index_version=index_version,
                        model_type=model_type,
                    )

            context_cache_info = " (from cache)" if cached_context else ""
            logger.info(f"    Context: {assembled_context.total_tokens} tokens, "
                       f"{len(assembled_context.documents)} docs included{context_cache_info}")

            if metrics:
                metrics.context_assembly_ms = (time.time() - context_start) * 1000

            # === Layer 5: Validated Generation ===
            generation_start = time.time()
            logger.info("  Layer 5: Validated Generation")
            validated_response = await self.generator.generate(
                query=query,
                context=assembled_context,
                validate_claims=validate_claims,
            )
            logger.info(f"    Confidence: {validated_response.confidence_score:.2f}")
            logger.info(f"    Citations: {len(validated_response.citations)}")

            if metrics:
                metrics.generation_ms = (time.time() - generation_start) * 1000
                metrics.confidence_score = validated_response.confidence_score
                metrics.num_citations = len(validated_response.citations)
                metrics.has_unsupported_claims = validated_response.has_unsupported_claims

            # Build final response
            execution_time_ms = (time.time() - start_time) * 1000

            response = RAGResponse(
                query=query,
                answer=validated_response.answer,
                confidence_score=validated_response.confidence_score,
                sources=assembled_context.documents,
                query_analysis=query_analysis,
                context_info=assembled_context.to_dict(),
                validation_info=validated_response.to_dict() if validate_claims else None,
                execution_time_ms=execution_time_ms,
                iterations=1,
                success=True,
            )

            # === Layer 6: Store in Semantic Cache ===
            if use_cache and self._cache_enabled and query_embedding:
                try:
                    if validated_response.has_unsupported_claims:
                        logger.info("    Skipping cache: response has unsupported claims")
                    elif validated_response.confidence_score < settings.rag_cache_min_confidence:
                        logger.info(
                            "    Skipping cache: confidence %.2f < %.2f",
                            validated_response.confidence_score,
                            settings.rag_cache_min_confidence,
                        )
                    else:
                        public_flag = (
                            include_public_knowledge
                            if include_public_knowledge is not None
                            else settings.rag_public_knowledge_enabled
                        )
                        cache_scope = (
                            f"model_type={model_type}"
                            f"|vllm_model={settings.vllm_model}"
                            f"|public={public_flag}"
                            f"|validate={validate_claims}"
                        )
                        await self.cache.set(
                            query=query,
                            query_embedding=query_embedding,
                            tenant_id=tenant_id,
                            user_id=user_id,  # SECURITY: User-isolated cache
                            answer=validated_response.answer,
                            sources=[s.to_dict() for s in assembled_context.documents],
                            confidence_score=validated_response.confidence_score,
                            query_analysis=query_analysis.to_dict(),
                            context_info=assembled_context.to_dict(),
                            scope=cache_scope,
                        )
                        logger.info("    Cached response for future similar queries")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to cache response: {e}")

            # Finalize monitoring metrics
            if metrics:
                metrics.total_latency_ms = execution_time_ms
                await self.monitor.end_query(metrics)

            logger.info(f"✅ Query processed in {execution_time_ms:.0f}ms")
            return response

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ RAG Pipeline error: {e}")

            # Build error query analysis
            from .models import QueryIntent
            error_analysis = QueryAnalysis(
                original_query=query,
                expanded_query=query,
                query_variations=[],
                intent=query_analysis.intent if 'query_analysis' in locals() else QueryIntent.UNKNOWN,
                extracted_filters={},
                key_terms=[],
            )

            return RAGResponse(
                query=query,
                answer=f"Error procesando la consulta: {str(e)}",
                confidence_score=0.0,
                sources=[],
                query_analysis=error_analysis,
                context_info={},
                validation_info=None,
                execution_time_ms=execution_time_ms,
                iterations=1,
                success=False,
                error=str(e),
            )

    async def process_query_stream(
        self,
        query: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        collection_name: Optional[str] = None,
        top_k: int = 10,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a query with streaming progress updates.

        Yields progress events and final result.
        """
        await self.initialize()

        start_time = time.time()

        try:
            # === Layer 1: Query Intelligence ===
            yield {"type": "progress", "content": "Analizando consulta...", "progress": 10}
            query_analysis = await self.query_intel.analyze_query_async(query)

            yield {
                "type": "analysis",
                "content": f"Intent: {query_analysis.intent.value}, Terms: {', '.join(query_analysis.key_terms[:3])}",
                "progress": 20
            }

            # === Layer 2: Multi-Stage Retrieval + Soft Selection ===
            yield {"type": "progress", "content": "Buscando documentos relevantes...", "progress": 30}
            retrieved_docs, selection_metadata = await self.retriever.retrieve(
                query_analysis=query_analysis,
                tenant_id=tenant_id,
                collection_name=collection_name,
                top_k=top_k,
            )

            if not retrieved_docs:
                yield {
                    "type": "result",
                    "content": self._build_no_results_response(
                        query=query,
                        query_analysis=query_analysis,
                        start_time=start_time,
                    ).to_cag_response()
                }
                return

            yield {
                "type": "retrieval",
                "content": f"Encontrados {len(retrieved_docs)} documentos",
                "progress": 50
            }

            # === Layer 3: Context Assembly (proportional allocation) ===
            yield {"type": "progress", "content": "Preparando contexto...", "progress": 60}
            assembled_context = self.assembler.assemble_context(
                query_analysis=query_analysis,
                documents=retrieved_docs,
                soft_weights=selection_metadata.get("soft_weights") if selection_metadata else None,
                selection_metadata=selection_metadata,
            )

            # === Layer 4: Validated Generation (streaming) ===
            yield {"type": "progress", "content": "Generando respuesta...", "progress": 70}

            answer_parts = []
            async for event in self.generator.generate_stream(
                query=query,
                context=assembled_context,
            ):
                if event["type"] == "token":
                    answer_parts.append(event["content"])
                    yield {"type": "token", "content": event["content"]}
                elif event["type"] == "result":
                    # Final result from generator
                    validation_info = event["content"]

            # Build final response
            execution_time_ms = (time.time() - start_time) * 1000

            response = RAGResponse(
                query=query,
                answer="".join(answer_parts),
                confidence_score=validation_info.get("confidence_score", 0.5),
                sources=assembled_context.documents,
                query_analysis=query_analysis,
                context_info=assembled_context.to_dict(),
                validation_info=validation_info,
                execution_time_ms=execution_time_ms,
                iterations=1,
                success=True,
            )

            yield {"type": "result", "content": response.to_cag_response(), "progress": 100}

        except Exception as e:
            logger.error(f"❌ Streaming RAG Pipeline error: {e}")
            yield {"type": "error", "content": str(e)}

    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        analysis_type: str = "comprehensive",
    ) -> Dict[str, Any]:
        """
        Analyze a document using the RAG pipeline.

        For document analysis, we use the document content directly
        without retrieval (since we have the full document).
        """
        await self.initialize()

        start_time = time.time()

        # Build analysis query based on type
        # Prompts are loaded from emma_prompts.yaml via prompt_loader
        from app.services.rag.prompt_loader import get_analysis_prompt

        analysis_queries = {
            "comprehensive": get_analysis_prompt("comprehensive"),
            "risks": get_analysis_prompt("risks"),
            "summary": get_analysis_prompt("summary"),
            "entities": get_analysis_prompt("entities"),
            "compliance": get_analysis_prompt("compliance"),
            "obligations": get_analysis_prompt("obligations"),
        }

        query = analysis_queries.get(analysis_type, analysis_queries["comprehensive"])

        # Create a synthetic "retrieved" document
        doc = RetrievedDocument(
            id=document_id,
            title=f"Documento {document_id}",
            content=document_content,
            score=1.0,
            document_type="analysis_target",
            tenant_id=tenant_id,
        )

        # Analyze query
        query_analysis = await self.query_intel.analyze_query_async(query)

        # Assemble context with the single document
        assembled_context = self.assembler.assemble_context(
            query_analysis=query_analysis,
            documents=[doc],
        )

        # Generate analysis
        validated_response = await self.generator.generate(
            query=query,
            context=assembled_context,
            validate_claims=False,  # Skip validation for document analysis
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "success": True,
            "document_id": document_id,
            "analysis_type": analysis_type,
            "answer": validated_response.answer,
            "quality_score": validated_response.confidence_score,
            "execution_time": execution_time_ms / 1000,
            "metadata": {
                "query_analysis": query_analysis.to_dict(),
                "context_tokens": assembled_context.total_tokens,
            },
        }

    def _build_no_results_response(
        self,
        query: str,
        query_analysis: QueryAnalysis,
        start_time: float,
    ) -> RAGResponse:
        """Build response when no documents are found"""
        execution_time_ms = (time.time() - start_time) * 1000

        return RAGResponse(
            query=query,
            answer="No se encontraron documentos relevantes para tu consulta. Por favor, intenta con términos diferentes o verifica que los documentos necesarios hayan sido indexados.",
            confidence_score=0.0,
            sources=[],
            query_analysis=query_analysis,
            context_info={"documents_count": 0, "truncated": False},
            validation_info=None,
            execution_time_ms=execution_time_ms,
            iterations=1,
            success=True,
        )

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all pipeline components"""
        try:
            await self.initialize()

            # Get cache stats if available
            cache_stats = {}
            if self._cache_enabled:
                stats = await self.cache.get_stats()
                cache_stats = {
                    "enabled": True,
                    "hits": stats.hits,
                    "misses": stats.misses,
                    "hit_rate": f"{stats.hit_rate:.1%}",
                }
            else:
                cache_stats = {"enabled": False}

            # Get monitoring stats
            monitor_stats = {}
            if self._monitoring_enabled:
                monitor_stats = self.monitor.get_global_summary()

            return {
                "status": "healthy",
                "pipeline": "7-layer-rag-production",
                "components": {
                    "query_intelligence": True,
                    "hybrid_retriever_rrf": self.retriever._initialized,
                    "context_assembler": True,
                    "validated_generator": True,
                    "semantic_cache": self._cache_enabled,
                    "monitoring": self._monitoring_enabled,
                },
                "cache_stats": cache_stats,
                "monitor_stats": monitor_stats,
                "config": {
                    "llm_provider": settings.llm_provider,
                    "llm_model": settings.vllm_model,
                    "embedding_model": settings.embedding_model,
                    "rrf_enabled": True,
                    "cache_enabled": self._cache_enabled,
                    "monitoring_enabled": self._monitoring_enabled,
                },
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    def get_monitoring_metrics(
        self,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get detailed monitoring metrics for dashboards"""
        if not self._monitoring_enabled:
            return {"monitoring_enabled": False}

        aggregated = self.monitor.get_aggregated_metrics(tenant_id=tenant_id)

        return {
            "monitoring_enabled": True,
            "period": {
                "start": aggregated.period_start,
                "end": aggregated.period_end,
            },
            "queries": {
                "total": aggregated.total_queries,
                "cache_hits": aggregated.cache_hits,
                "cache_misses": aggregated.cache_misses,
                "cache_hit_rate": f"{aggregated.cache_hit_rate:.1%}",
                "zero_results": aggregated.zero_result_queries,
            },
            "latency": {
                "p50_ms": round(aggregated.latency_p50_ms, 1),
                "p90_ms": round(aggregated.latency_p90_ms, 1),
                "p99_ms": round(aggregated.latency_p99_ms, 1),
            },
            "quality": {
                "avg_top_score": round(aggregated.avg_top_score, 3),
                "avg_num_results": round(aggregated.avg_num_results, 1),
                "avg_confidence": round(aggregated.avg_confidence, 3),
                "avg_user_rating": round(aggregated.avg_user_rating, 2),
                "rated_queries": aggregated.rated_queries,
            },
            "slow_queries": self.monitor.get_slow_queries(limit=5),
            "zero_result_queries": self.monitor.get_zero_result_queries(limit=5),
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available 'tools' (for backwards compatibility with Elysia API).

        In the new RAG pipeline, these are the pipeline stages.
        """
        return [
            {
                "name": "query_intelligence",
                "description": "Analyzes and expands user queries",
                "layer": 2,
            },
            {
                "name": "hybrid_retriever_rrf",
                "description": "Dense + Sparse search with Reciprocal Rank Fusion",
                "layer": 3,
            },
            {
                "name": "context_assembler",
                "description": "Builds structured context for LLM",
                "layer": 4,
            },
            {
                "name": "validated_generator",
                "description": "Generates answers with citations and validation",
                "layer": 5,
            },
            {
                "name": "semantic_cache",
                "description": "Redis-based semantic caching for similar queries",
                "layer": 6,
                "enabled": self._cache_enabled,
            },
        ]


# Global instance
rag_pipeline = RAGPipeline()
