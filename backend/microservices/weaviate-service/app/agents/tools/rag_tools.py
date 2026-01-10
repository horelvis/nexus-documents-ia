"""
RAG Tools for Agent Framework

Main RAG pipeline tool that provides complete question-answering
capabilities with source citation and claim validation.

This is the primary tool for answering user questions using the
document knowledge base.

FRAMEWORK: Microsoft Agent Framework
Uses ChatAgent with @ai_function decorator.
"""

import json
import logging
from typing import Annotated, Optional
from pydantic import Field

from app.core.security import get_tenant_collection_name
from app.core.execution_context import (
    resolve_tenant_id,
    get_user_id,
    get_user_role_ids,
    get_is_admin,
)

# Try to import ai_function from Agent Framework, fall back to identity decorator
try:
    from agent_framework import ai_function
except ImportError:
    def ai_function(func):
        return func

logger = logging.getLogger(__name__)

# Lazy loading
_rag_pipeline = None
_weaviate_service = None


def _get_rag_pipeline():
    """Get or create RAG pipeline (lazy loading)."""
    global _rag_pipeline
    if _rag_pipeline is None:
        from app.services.rag.rag_pipeline import RAGPipeline
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline


def _get_weaviate_service():
    """Get or create Weaviate service (lazy loading)."""
    global _weaviate_service
    if _weaviate_service is None:
        from app.services.weaviate_service import WeaviateService
        _weaviate_service = WeaviateService()
    return _weaviate_service


@ai_function
async def rag_answer(
    query: Annotated[str, Field(description="The user's question or information request")],
    tenant_id: Annotated[str, Field(description="Tenant ID for document access")],
    validate_claims: Annotated[bool, Field(description="Whether to validate claims against sources")] = True,
    include_sources: Annotated[bool, Field(description="Whether to include source citations")] = True,
    max_sources: Annotated[int, Field(description="Maximum number of sources to cite")] = 5,
) -> str:
    """
    Generate a complete answer using the RAG pipeline.

    This is the main tool for answering questions about documents.
    It performs:
    1. Query analysis and expansion
    2. Multi-stage document retrieval
    3. Context assembly from relevant chunks
    4. Answer generation with the LLM
    5. Optional claim validation
    6. Source citation

    Use this tool when the user asks a question that needs to be
    answered using information from their documents.

    Args:
        query: The question or request to answer
        tenant_id: Tenant identifier for accessing the correct documents
        validate_claims: If True, validates generated claims against sources
        include_sources: If True, includes source citations in the response
        max_sources: Maximum number of sources to include

    Returns:
        JSON string with:
        - answer: The generated response
        - sources: List of source documents used (if include_sources)
        - confidence: Confidence score (0-1)
        - validation: Claim validation results (if validate_claims)

    Example:
        >>> result = await rag_answer(
        ...     query="What are the payment terms in the contract?",
        ...     tenant_id="tenant-123"
        ... )
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"RAG answer: query='{query[:50]}...', tenant={actual_tenant_id}")

    try:
        pipeline = _get_rag_pipeline()

        # Process query through full RAG pipeline
        result = await pipeline.process_query(
            query=query,
            tenant_id=actual_tenant_id,
            validate_claims=validate_claims,
            top_k=max_sources * 2,  # Retrieve more, show fewer
        )

        # Format response
        response = {
            "answer": result.answer if hasattr(result, 'answer') else str(result),
            "query": query,
        }

        # Add sources if requested
        if include_sources and hasattr(result, 'sources'):
            sources = []
            for src in result.sources[:max_sources]:
                sources.append({
                    "title": getattr(src, "title", "Unknown"),
                    "id": getattr(src, "id", getattr(src, "document_id", "")),
                    "score": round(getattr(src, "score", 0.0), 4),
                    "excerpt": getattr(src, "excerpt", "")[:200],
                })
            response["sources"] = sources

        # Add confidence if available
        if hasattr(result, 'confidence'):
            response["confidence"] = result.confidence

        # Add validation if performed
        if validate_claims and hasattr(result, 'validation'):
            response["validation"] = result.validation

        return json.dumps(response, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"RAG answer error: {e}")
        return json.dumps({
            "error": str(e),
            "query": query,
            "answer": "I was unable to generate an answer due to an error."
        })


@ai_function
async def get_document_content(
    document_id: Annotated[str, Field(description="The document ID to retrieve")],
    tenant_id: Annotated[str, Field(description="Tenant ID for access control")],
    max_length: Annotated[int, Field(description="Maximum content length to return")] = 10000,
) -> str:
    """
    Retrieve the full content of a specific document.

    Use this tool when you need to read a specific document's content
    for analysis or to answer questions about it.

    SECURITY: This function automatically applies channel access control:
    - Regular uploads are always accessible
    - Tenant-wide channels are accessible to all tenant users
    - Personal channels (Gmail, personal Drive) are only accessible to the owner

    Args:
        document_id: Unique identifier of the document
        tenant_id: Tenant identifier for access control
        max_length: Maximum characters to return (truncates if exceeded)

    Returns:
        JSON string with:
        - id: Document identifier
        - title: Document title
        - content: Full or truncated content
        - metadata: Document metadata (type, date, etc.)
        - truncated: Whether content was truncated
        - is_channel: Whether document is from a channel or regular documents
    """
    # Resolve tenant_id and ACL context from execution context
    actual_tenant_id = resolve_tenant_id(tenant_id)
    actual_user_id = get_user_id()
    actual_user_role_ids = get_user_role_ids()
    actual_is_admin = get_is_admin()
    logger.info(f"Getting document: id={document_id}, tenant={actual_tenant_id}, user={actual_user_id[:8] if actual_user_id else 'None'}...")

    try:
        service = _get_weaviate_service()

        # Always use cross-collection search with ACL verification
        # SECURITY: This ensures:
        # 1. User can only access documents they have ACL permission to see
        # 2. Owner always has access
        # 3. Role-based ACL is checked
        # 4. Documents shared with "everyone" are accessible
        # 5. Admin users bypass ACL checks
        doc = await service.get_document_by_id_across_collections(
            tenant_id=actual_tenant_id,
            document_id=document_id,
            user_id=actual_user_id,
            user_role_ids=actual_user_role_ids,
            is_admin=actual_is_admin,
        )

        if not doc:
            return json.dumps({
                "error": "Document not found in any collection",
                "document_id": document_id,
                "tenant_id": actual_tenant_id
            })

        content = doc.get("content", "")
        truncated = len(content) > max_length

        return json.dumps({
            "id": document_id,
            "title": doc.get("title", "Unknown"),
            "content": content[:max_length] if truncated else content,
            "truncated": truncated,
            "total_length": len(content),
            "metadata": doc.get("metadata", {}),
            "source_collection": doc.get("_source_collection", ""),
            "is_channel": doc.get("_is_channel", False),
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Get document error: {e}")
        return json.dumps({
            "error": str(e),
            "document_id": document_id
        })


@ai_function
async def summarize_documents(
    query: Annotated[str, Field(description="Topic or question to summarize around")],
    tenant_id: Annotated[str, Field(description="Tenant ID for document access")],
    max_documents: Annotated[int, Field(description="Maximum documents to include in summary")] = 5,
) -> str:
    """
    Create a summary across multiple documents on a topic.

    This retrieves relevant documents and creates a consolidated
    summary that synthesizes information from all sources.

    Use this when the user wants an overview of a topic that may
    span multiple documents.

    Args:
        query: Topic or question to summarize
        tenant_id: Tenant identifier
        max_documents: Maximum number of documents to consider

    Returns:
        JSON string with:
        - summary: Consolidated summary
        - documents_used: List of documents that contributed
        - topic: The original query/topic
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Summarizing documents: query='{query[:50]}...', tenant={actual_tenant_id}")

    try:
        pipeline = _get_rag_pipeline()
        service = _get_weaviate_service()
        collection_name = get_tenant_collection_name(actual_tenant_id)

        # First, search for relevant documents
        results = await service.hybrid_search(
            query=query,
            collection_name=collection_name,
            limit=max_documents,
            tenant_id=actual_tenant_id,
        )

        if not results:
            return json.dumps({
                "error": "No relevant documents found",
                "query": query
            })

        # Collect content from documents
        doc_contents = []
        for doc in results:
            title = getattr(doc, "title", "Unknown")
            content = getattr(doc, "content", "")[:2000]
            doc_contents.append(f"Document: {title}\n{content}")

        combined_context = "\n\n---\n\n".join(doc_contents)

        # Generate summary
        prompt = f"""Create a comprehensive summary on the topic: "{query}"

Based on the following documents:

{combined_context}

Provide:
1. Overview of what the documents say about this topic
2. Key points from each document
3. Any contradictions or different perspectives
4. Overall conclusion
"""

        result = await pipeline.generate_response(
            query=prompt,
            context=combined_context,
            system_prompt="You are a research analyst. Create comprehensive summaries that synthesize multiple sources."
        )

        return json.dumps({
            "topic": query,
            "summary": result,
            "documents_used": [
                {
                    "title": getattr(doc, "title", "Unknown"),
                    "id": getattr(doc, "id", ""),
                }
                for doc in results
            ],
            "document_count": len(results),
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Summarize documents error: {e}")
        return json.dumps({
            "error": str(e),
            "query": query
        })


@ai_function
async def answer_with_context(
    query: Annotated[str, Field(description="The question to answer")],
    context: Annotated[str, Field(description="Pre-provided context to use for answering")],
    tenant_id: Annotated[str, Field(description="Tenant ID (for logging/tracking)")],
) -> str:
    """
    Answer a question using provided context (no retrieval).

    Use this when you already have the relevant context and just
    need to generate an answer. This skips the retrieval step.

    Args:
        query: Question to answer
        context: Context text to use for answering
        tenant_id: Tenant ID for logging

    Returns:
        JSON string with the answer
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Answer with context: query='{query[:50]}...', tenant={actual_tenant_id}")

    try:
        pipeline = _get_rag_pipeline()

        result = await pipeline.generate_response(
            query=query,
            context=context,
            system_prompt="Answer the question based only on the provided context. If the context doesn't contain the answer, say so."
        )

        return json.dumps({
            "query": query,
            "answer": result,
            "context_used": True,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Answer with context error: {e}")
        return json.dumps({
            "error": str(e),
            "query": query
        })
