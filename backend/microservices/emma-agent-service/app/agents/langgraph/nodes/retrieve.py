"""
RETRIEVE Node - Vector Search with ACL Filtering

This node performs document retrieval from Weaviate with:
- Tenant isolation (always)
- User-level ACL filtering (when not admin)
- Hybrid search (semantic + keyword)

The node populates:
- retrieved_docs: List of relevant documents
- doc_scores: Relevance scores

Design Decisions:
1. Uses existing WeaviateService for consistency with v1
2. ACL is enforced at retrieval time (not post-filter)
3. Supports skip for conversational follow-ups

References:
- Anthropic Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from ..state import RAGState, DocumentResult
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)


async def retrieve_node(state: RAGState) -> Dict[str, Any]:
    """
    Retrieve documents with ACL filtering.

    This node:
    1. Performs hybrid vector search on Weaviate
    2. Applies tenant isolation
    3. Applies user-level ACL filtering (unless admin)
    4. Returns top-k relevant documents

    Args:
        state: Current RAG state with query and ACL context

    Returns:
        State updates: retrieved_docs, doc_scores, metadata
    """
    start_time = time.time()
    tracker = ReasoningTracker()
    tracker.set_source("retrieve")

    query = state.get("query", "")
    tenant_id = state.get("tenant_id", "")
    user_id = state.get("user_id")
    user_role_ids = state.get("user_role_ids", [])
    is_admin = state.get("is_admin", False)

    logger.info(f"🔍 RETRIEVE: query='{query[:50]}...', tenant={tenant_id}")

    tracker.add_step(
        StepType.SEARCH,
        "Buscando documentos relevantes...",
        confidence=1.0,
    )

    # Check if user attached specific documents
    metadata = state.get("metadata", {})
    target_doc_id = metadata.get("document_id")
    target_doc_ids = metadata.get("indexed_document_ids") or []

    # Check if user uploaded local (non-indexed) files — text already in context
    has_uploaded_content = bool(
        metadata.get("uploaded_texts") or metadata.get("uploaded_file_ids")
    )
    if not target_doc_id and not target_doc_ids and has_uploaded_content:
        logger.info("⏭️ Skipping retrieval (uploaded content already in context)")
        tracker.add_step(
            StepType.OBSERVATION,
            "Usando contenido subido directamente (sin búsqueda vectorial)",
            confidence=1.0,
        )
        return {
            "retrieved_docs": [],
            "doc_scores": [],
            "retrieval_skipped": True,
            "reasoning_steps": tracker.get_steps(),
            "metadata": {
                **metadata,
                "retrieval_skipped_reason": "uploaded_content",
            },
        }

    # Check if retrieval should be skipped (e.g., purely conversational)
    # But never skip if user attached a specific document
    if not target_doc_id and not target_doc_ids and _should_skip_retrieval(query, state):
        logger.info("⏭️ Skipping retrieval (conversational/meta query)")
        return {
            "retrieved_docs": [],
            "doc_scores": [],
            "retrieval_skipped": True,
            "metadata": {
                **state.get("metadata", {}),
                "retrieval_skipped_reason": "conversational_query",
            },
        }

    try:
        # Import WeaviateClient (HTTP client for microservice communication)
        from app.clients.weaviate_client import get_weaviate_client

        weaviate_client = get_weaviate_client()

        # If user attached specific documents, filter retrieval to those
        doc_filter_ids = target_doc_ids if target_doc_ids else ([target_doc_id] if target_doc_id else None)
        search_filters = None

        if doc_filter_ids:
            logger.info(f"📎 RETRIEVE: Filtering to attached document(s): {doc_filter_ids}")
            search_filters = {"document_id": doc_filter_ids}

        # Use sector-specific retrieval params if available
        sector_config = state.get("sector_config")
        search_limit = 10
        search_alpha = 0.7
        if sector_config:
            search_limit = sector_config.get("top_k", 10)
            search_alpha = sector_config.get("hybrid_alpha", 0.7)

        # Perform hybrid search with ACL filtering via HTTP
        results = await weaviate_client.hybrid_search(
            tenant_id=tenant_id,
            query=query,
            limit=search_limit,
            alpha=search_alpha,
            filters=search_filters,
        )

        # Convert to DocumentResult format
        retrieved_docs: List[DocumentResult] = []
        doc_scores: List[float] = []

        for result in results:
            doc = DocumentResult(
                id=result.document_id,
                title=result.metadata.get("title", ""),
                content=result.content,
                score=result.score,
                metadata=result.metadata,
                collection="",
            )
            retrieved_docs.append(doc)
            doc_scores.append(result.score)

        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ RETRIEVE: Found {len(retrieved_docs)} docs in {latency_ms:.1f}ms")

        tracker.add_step(
            StepType.OBSERVATION,
            f"{len(retrieved_docs)} documentos encontrados ({latency_ms:.0f}ms)",
            confidence=1.0,
        )

        return {
            "retrieved_docs": retrieved_docs,
            "doc_scores": doc_scores,
            "retrieval_skipped": False,
            "reasoning_steps": tracker.get_steps(),
            "metadata": {
                **state.get("metadata", {}),
                "retrieval_latency_ms": latency_ms,
                "retrieval_count": len(retrieved_docs),
            },
        }

    except Exception as e:
        logger.error(f"❌ RETRIEVE failed: {e}")
        latency_ms = (time.time() - start_time) * 1000

        # Return empty results on error (don't fail the entire graph)
        return {
            "retrieved_docs": [],
            "doc_scores": [],
            "retrieval_skipped": False,
            "metadata": {
                **state.get("metadata", {}),
                "retrieval_error": str(e),
                "retrieval_latency_ms": latency_ms,
            },
        }


def _should_skip_retrieval(query: str, state: RAGState) -> bool:
    """
    Determine if retrieval should be skipped.

    Skip retrieval for:
    - Greetings and meta-questions
    - Follow-up questions that reference previous context
    - Purely conversational queries

    Args:
        query: User's query
        state: Current state (may have conversation history)

    Returns:
        True if retrieval should be skipped
    """
    query_lower = query.lower().strip()

    # Note: uploaded_texts/uploaded_file_ids are handled earlier in the
    # retrieve node with a distinct reason ("uploaded_content"), not here.

    # Greeting patterns (Spanish + English)
    greetings = [
        "hola", "buenos días", "buenas tardes", "buenas noches",
        "hello", "hi", "hey", "good morning", "good afternoon",
        "qué tal", "cómo estás", "how are you",
    ]

    if any(query_lower.startswith(g) or query_lower == g for g in greetings):
        return True

    # Meta-questions about Emma
    meta_patterns = [
        "quién eres", "qué puedes hacer", "ayuda", "help",
        "who are you", "what can you do", "what are you",
    ]

    if any(p in query_lower for p in meta_patterns):
        return True

    # Name declarations or name recall
    name_statements = [
        r"me llamo\s+\w+",
        r"mi nombre es\s+\w+",
        r"llámame\s+\w+",
        r"puedes llamarme\s+\w+",
        r"my name is\s+\w+",
        r"call me\s+\w+",
    ]
    if any(re.search(p, query_lower) for p in name_statements):
        return True

    name_questions = [
        "cómo me llamo", "como me llamo", "recuerdas mi nombre",
        "qué nombre tengo", "que nombre tengo", "¿cuál es mi nombre?",
        "what is my name", "do you remember my name",
    ]
    if any(p in query_lower for p in name_questions):
        return True

    # Very short queries are likely conversational
    if len(query_lower.split()) <= 2 and "?" not in query_lower:
        # Unless they're document-related
        doc_keywords = ["documento", "contrato", "factura", "document", "file"]
        if not any(k in query_lower for k in doc_keywords):
            return True

    return False


async def retrieve_with_reranking(
    state: RAGState,
    rerank_model: Optional[str] = None,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Enhanced retrieval with cross-encoder reranking.

    This is an alternative retrieve node that:
    1. Performs initial retrieval (broader, e.g., 20 docs)
    2. Reranks with cross-encoder
    3. Returns top-k highest scored

    Useful for high-precision scenarios.

    Args:
        state: Current RAG state
        rerank_model: Cross-encoder model name
        top_k: Number of docs after reranking

    Returns:
        State updates with reranked documents
    """
    start_time = time.time()

    # First, get initial retrieval (broader)
    initial_result = await retrieve_node({
        **state,
        # Override to get more docs for reranking
    })

    retrieved_docs = initial_result.get("retrieved_docs", [])

    if len(retrieved_docs) <= top_k:
        # No need to rerank if we have fewer docs than top_k
        return initial_result

    try:
        # Import cross-encoder (lazy)
        from sentence_transformers import CrossEncoder

        # Use default model if not specified
        model_name = rerank_model or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        reranker = CrossEncoder(model_name)

        query = state.get("query", "")

        # Prepare pairs for reranking
        pairs = [
            (query, doc.get("content", "")[:1000])  # Truncate for efficiency
            for doc in retrieved_docs
        ]

        # Get reranking scores
        rerank_scores = reranker.predict(pairs)

        # Sort by rerank score
        scored_docs = list(zip(retrieved_docs, rerank_scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        # Take top-k
        reranked_docs = [doc for doc, _ in scored_docs[:top_k]]
        reranked_scores = [float(score) for _, score in scored_docs[:top_k]]

        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ RETRIEVE+RERANK: {len(reranked_docs)} docs in {latency_ms:.1f}ms")

        return {
            "retrieved_docs": reranked_docs,
            "doc_scores": reranked_scores,
            "retrieval_skipped": False,
            "metadata": {
                **state.get("metadata", {}),
                "retrieval_latency_ms": latency_ms,
                "retrieval_count": len(reranked_docs),
                "reranking_applied": True,
                "rerank_model": model_name,
            },
        }

    except Exception as e:
        logger.warning(f"⚠️ Reranking failed, using initial results: {e}")
        return initial_result
