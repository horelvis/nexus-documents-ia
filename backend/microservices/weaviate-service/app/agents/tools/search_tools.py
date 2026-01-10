"""
Search Tools for Agent Framework

These functions wrap the RAG pipeline's search capabilities and are passed
directly to ChatAgent's `tools` parameter. Agent Framework uses the
@ai_function decorator for automatic schema generation.

Parameters use Annotated[type, Field(description="...")] format for
proper schema generation.

FRAMEWORK: Microsoft Agent Framework
Reference: https://learn.microsoft.com/en-us/agent-framework/
"""

import json
import logging
from typing import Annotated, List, Dict, Any, Optional
from pydantic import Field

from app.core.security import get_tenant_collection_name, get_channel_collection_name
from app.core.execution_context import (
    resolve_tenant_id,
    get_user_id,
    get_user_role_ids,
    get_is_admin,
)

# Import ai_function from Agent Framework
try:
    from agent_framework import ai_function
except ImportError:
    # Fallback identity decorator if Agent Framework not installed
    def ai_function(func):
        return func

logger = logging.getLogger(__name__)

# Lazy loading to avoid import errors at startup
_weaviate_service = None
_rag_pipeline = None
_public_knowledge_service = None


def _get_weaviate_service():
    """Get or create the Weaviate service instance (lazy loading)."""
    global _weaviate_service
    if _weaviate_service is None:
        from app.services.weaviate_service import WeaviateService
        _weaviate_service = WeaviateService()
    return _weaviate_service


def _get_rag_pipeline():
    """Get or create the RAG pipeline instance (lazy loading)."""
    global _rag_pipeline
    if _rag_pipeline is None:
        from app.services.rag.rag_pipeline import RAGPipeline
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline


def _get_public_knowledge_service():
    """Get or create the Public Knowledge service instance (lazy loading)."""
    global _public_knowledge_service
    if _public_knowledge_service is None:
        from app.services.public_knowledge_service import public_knowledge_service
        _public_knowledge_service = public_knowledge_service
    return _public_knowledge_service


def _format_search_results(results: List[Any], max_results: int = 10) -> str:
    """Format search results as JSON string for agent consumption."""
    formatted = []
    for doc in results[:max_results]:
        formatted.append({
            "id": getattr(doc, "id", getattr(doc, "document_id", "unknown")),
            "title": getattr(doc, "title", getattr(doc, "filename", "Untitled")),
            "score": round(getattr(doc, "score", 0.0), 4),
            "snippet": _truncate_text(
                getattr(doc, "content", getattr(doc, "text", "")),
                max_length=300
            ),
            "metadata": getattr(doc, "metadata", {}),
        })
    return json.dumps(formatted, ensure_ascii=False, indent=2)


def _truncate_text(text: str, max_length: int = 300) -> str:
    """Truncate text with ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


async def _get_all_tenant_collections(tenant_id: str) -> List[str]:
    """
    Get all collections for a tenant, including documents and channel collections.

    This enables searching across:
    - Main document collection (uploaded files)
    - Channel collections (Gmail, Google Drive, etc.)
    """
    service = _get_weaviate_service()
    await service.initialize()

    try:
        return await service.get_tenant_collections(tenant_id)
    except Exception as e:
        logger.warning(f"Could not get all tenant collections: {e}")
        # Fallback to just the main collection
        return [get_tenant_collection_name(tenant_id)]


def _format_cross_collection_results(results: List[Dict[str, Any]], max_results: int = 10) -> str:
    """Format results from cross-collection search."""
    formatted = []
    for doc in results[:max_results]:
        source_collection = doc.get("_source_collection", "")
        source_type = "channel" if "_channel_" in source_collection else "document"

        formatted.append({
            "id": doc.get("id", "unknown"),
            "title": doc.get("title", "Untitled"),
            "score": round(doc.get("score", 0.0), 4),
            "snippet": _truncate_text(doc.get("content", ""), max_length=300),
            "source_type": source_type,  # "channel" or "document"
            "metadata": doc.get("metadata", {}),
        })
    return json.dumps(formatted, ensure_ascii=False, indent=2)


@ai_function
async def semantic_search(
    query: Annotated[str, Field(description="The search query in natural language")],
    tenant_id: Annotated[str, Field(description="Tenant ID to isolate search results")],
    top_k: Annotated[int, Field(description="Maximum number of results to return")] = 10,
    collection_name: Annotated[Optional[str], Field(description="Specific collection to search (optional)")] = None,
) -> str:
    """
    Perform semantic search on tenant documents using vector embeddings.

    This tool finds documents that are semantically similar to the query,
    even if they don't share exact keywords. It uses dense vector embeddings
    to capture meaning and context.

    Searches across ALL tenant collections including:
    - Uploaded documents
    - Information channels (Gmail, Google Drive, etc.)

    SECURITY: Results are filtered by document-level ACL based on the user's
    permissions from the execution context.

    Use this when:
    - Searching for concepts or ideas
    - Looking for related content
    - The user's query is conversational

    Args:
        query: Natural language search query
        tenant_id: Tenant identifier for data isolation
        top_k: Number of results (default 10, max 50)
        collection_name: Optional specific collection to search

    Returns:
        JSON string with list of relevant documents including:
        - id: Document identifier
        - title: Document title
        - score: Relevance score (0-1)
        - snippet: Text excerpt
        - source_type: "document" or "channel"
        - metadata: Additional document metadata
    """
    # Resolve tenant_id and ACL context from execution context
    actual_tenant_id = resolve_tenant_id(tenant_id)
    user_id = get_user_id()
    user_role_ids = get_user_role_ids()
    is_admin = get_is_admin()
    logger.info(f"Semantic search: query='{query[:50]}...', tenant={actual_tenant_id}, user={user_id}, roles={len(user_role_ids or [])}, top_k={top_k}")

    try:
        service = _get_weaviate_service()
        await service.initialize()

        # If specific collection provided, search only that
        if collection_name:
            results = await service.vector_search(
                query=query,
                collection_name=collection_name,
                limit=min(top_k, 50),
                tenant_id=actual_tenant_id,
            )
            if not results:
                return json.dumps({
                    "results": [],
                    "message": "No documents found matching the query"
                })
            return _format_search_results(results, max_results=top_k)

        # Search across ALL tenant collections (documents + channels) with ACL filtering
        all_collections = await _get_all_tenant_collections(actual_tenant_id)
        logger.info(f"Searching across {len(all_collections)} collections for tenant {actual_tenant_id}")

        results = await service.search_across_collections(
            collections=all_collections,
            query=query,
            tenant_id=actual_tenant_id,
            user_id=user_id,  # ACL: user identification
            user_role_ids=user_role_ids,  # ACL: role-based access
            is_admin=is_admin,  # ACL: admin bypass
            limit=min(top_k, 50),
            search_type="vector"
        )

        if not results:
            return json.dumps({
                "results": [],
                "message": "No documents found matching the query"
            })

        return _format_cross_collection_results(results, max_results=top_k)

    except Exception as e:
        logger.exception(f"Semantic search error: {e}")
        return json.dumps({
            "error": str(e),
            "results": []
        })


@ai_function
async def hybrid_search(
    query: Annotated[str, Field(description="The search query")],
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    top_k: Annotated[int, Field(description="Number of results to return")] = 10,
    alpha: Annotated[float, Field(description="Balance between vector (1.0) and keyword (0.0) search")] = 0.7,
) -> str:
    """
    Perform hybrid search combining semantic vectors and keyword matching.

    This combines dense vector search (semantic meaning) with sparse BM25
    search (exact keywords) using Reciprocal Rank Fusion (RRF) for optimal
    results across both modalities.

    Searches across ALL tenant collections including:
    - Uploaded documents
    - Information channels (Gmail, Google Drive, etc.)

    SECURITY: Results are filtered by document-level ACL based on the user's
    permissions from the execution context.

    Use this for:
    - General document search (recommended default)
    - Queries mixing concepts and specific terms
    - When unsure which search type is best
    - Finding emails, drive files, or any indexed content

    Args:
        query: Search query (natural language or keywords)
        tenant_id: Tenant identifier for data isolation
        top_k: Number of results (default 10)
        alpha: Weight for vector vs keyword (0.7 = 70% semantic, 30% keyword)

    Returns:
        JSON string with ranked documents combining both search methods
    """
    # Resolve tenant_id and ACL context from execution context
    actual_tenant_id = resolve_tenant_id(tenant_id)
    user_id = get_user_id()
    user_role_ids = get_user_role_ids()
    is_admin = get_is_admin()
    logger.info(f"Hybrid search: query='{query[:50]}...', tenant={actual_tenant_id}, user={user_id}, alpha={alpha}")

    try:
        service = _get_weaviate_service()
        await service.initialize()

        # Search across ALL tenant collections (documents + channels) with ACL filtering
        all_collections = await _get_all_tenant_collections(actual_tenant_id)
        logger.info(f"Hybrid searching across {len(all_collections)} collections for tenant {actual_tenant_id}")

        results = await service.search_across_collections(
            collections=all_collections,
            query=query,
            tenant_id=actual_tenant_id,
            user_id=user_id,  # ACL: user identification
            user_role_ids=user_role_ids,  # ACL: role-based access
            is_admin=is_admin,  # ACL: admin bypass
            limit=min(top_k, 50),
            search_type="hybrid"
        )

        if not results:
            return json.dumps({
                "results": [],
                "message": "No documents found"
            })

        return _format_cross_collection_results(results, max_results=top_k)

    except Exception as e:
        logger.exception(f"Hybrid search error: {e}")
        return json.dumps({
            "error": str(e),
            "results": []
        })


@ai_function
async def keyword_search(
    query: Annotated[str, Field(description="Keywords or exact terms to search for")],
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    top_k: Annotated[int, Field(description="Number of results to return")] = 10,
) -> str:
    """
    Perform keyword-based search using BM25 algorithm.

    This finds documents containing the exact keywords or terms specified.
    It uses the BM25 algorithm which considers term frequency and document
    length for ranking.

    Searches across ALL tenant collections including:
    - Uploaded documents
    - Information channels (Gmail, Google Drive, etc.)

    SECURITY: Results are filtered by document-level ACL based on the user's
    permissions from the execution context.

    Use this when:
    - Searching for specific terms, names, or codes
    - Looking for exact phrases
    - The query contains proper nouns or technical terms
    - Finding emails from/to specific people

    Args:
        query: Keywords or terms to search (can include quotes for phrases)
        tenant_id: Tenant identifier for data isolation
        top_k: Number of results (default 10)

    Returns:
        JSON string with documents containing the specified keywords
    """
    # Resolve tenant_id and ACL context from execution context
    actual_tenant_id = resolve_tenant_id(tenant_id)
    user_id = get_user_id()
    user_role_ids = get_user_role_ids()
    is_admin = get_is_admin()
    logger.info(f"Keyword search: query='{query[:50]}...', tenant={actual_tenant_id}, user={user_id}")

    try:
        service = _get_weaviate_service()
        await service.initialize()

        # Search across ALL tenant collections (documents + channels) with ACL filtering
        all_collections = await _get_all_tenant_collections(actual_tenant_id)
        logger.info(f"Keyword searching across {len(all_collections)} collections for tenant {actual_tenant_id}")

        results = await service.search_across_collections(
            collections=all_collections,
            query=query,
            tenant_id=actual_tenant_id,
            user_id=user_id,  # ACL: user identification
            user_role_ids=user_role_ids,  # ACL: role-based access
            is_admin=is_admin,  # ACL: admin bypass
            limit=min(top_k, 50),
            search_type="keyword"
        )

        if not results:
            return json.dumps({
                "results": [],
                "message": "No documents found with those keywords"
            })

        return _format_cross_collection_results(results, max_results=top_k)

    except Exception as e:
        logger.exception(f"Keyword search error: {e}")
        return json.dumps({
            "error": str(e),
            "results": []
        })


@ai_function
async def search_by_metadata(
    tenant_id: Annotated[str, Field(description="Tenant ID for data isolation")],
    document_type: Annotated[Optional[str], Field(description="Filter by document type (pdf, docx, etc.)")] = None,
    date_from: Annotated[Optional[str], Field(description="Filter documents from this date (YYYY-MM-DD)")] = None,
    date_to: Annotated[Optional[str], Field(description="Filter documents until this date (YYYY-MM-DD)")] = None,
    tags: Annotated[Optional[str], Field(description="Comma-separated tags to filter by")] = None,
    top_k: Annotated[int, Field(description="Maximum number of results")] = 20,
) -> str:
    """
    Search documents by metadata filters without text query.

    This allows filtering the document collection by metadata attributes
    like document type, date range, or tags.

    Use this when:
    - Browsing documents by category
    - Finding documents from a specific time period
    - Filtering by document attributes

    Args:
        tenant_id: Tenant identifier
        document_type: File type filter (pdf, docx, xlsx, etc.)
        date_from: Start date for filtering
        date_to: End date for filtering
        tags: Comma-separated list of tags
        top_k: Maximum results to return

    Returns:
        JSON string with filtered documents
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Metadata search: tenant={actual_tenant_id}, type={document_type}")

    try:
        service = _get_weaviate_service()
        collection_name = get_tenant_collection_name(actual_tenant_id)

        # Build filters
        filters = {}
        if document_type:
            filters["document_type"] = document_type
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to
        if tags:
            filters["tags"] = [t.strip() for t in tags.split(",")]

        results = await service.filter_search(
            collection_name=collection_name,
            filters=filters,
            limit=top_k,
            tenant_id=actual_tenant_id,
        )

        if not results:
            return json.dumps({
                "results": [],
                "message": "No documents match the specified filters"
            })

        return _format_search_results(results, max_results=top_k)

    except Exception as e:
        logger.exception(f"Metadata search error: {e}")
        return json.dumps({
            "error": str(e),
            "results": []
        })


@ai_function
async def search_public_knowledge(
    query: Annotated[str, Field(description="Search query for legal/regulatory content")],
    category: Annotated[Optional[str], Field(description="Category filter: legislation, regulation, jurisprudence, or all")] = "all",
    jurisdiction: Annotated[Optional[str], Field(description="Jurisdiction filter: es (Spain), eu (EU), int (International)")] = None,
    top_k: Annotated[int, Field(description="Maximum number of results to return")] = 10,
) -> str:
    """
    Search the public legal knowledge base for legislation, regulations, and jurisprudence.

    This tool searches a curated database of Spanish and EU legal documents including:
    - Legislation: Laws, Royal Decrees, organic laws
    - Regulations: Ministerial orders, directives, technical regulations
    - Jurisprudence: Court rulings, Supreme Court decisions, Constitutional Court rulings

    Use this when:
    - Analyzing documents for legal compliance
    - Finding applicable legislation for a contract clause
    - Checking GDPR/RGPD or LOPD requirements
    - Looking for legal precedents or court decisions
    - Verifying regulatory requirements

    Args:
        query: Natural language query describing the legal topic
        category: Filter by type - legislation, regulation, jurisprudence, or all
        jurisdiction: Filter by jurisdiction - es (Spain), eu (EU), int (International)
        top_k: Number of results (default 10)

    Returns:
        JSON string with relevant legal documents including:
        - id: Document identifier
        - title: Official document title
        - legal_reference: Official legal reference (e.g., "Ley 34/2002")
        - category: Document type (legislation, regulation, etc.)
        - jurisdiction: Applicable jurisdiction
        - snippet: Relevant text excerpt
        - publication_date: When the document was published
        - verified: Whether the content has been verified
    """
    logger.info(f"Public knowledge search: query='{query[:50]}...', category={category}, jurisdiction={jurisdiction}")

    try:
        service = _get_public_knowledge_service()
        await service.initialize()

        # Import schema types
        from app.schemas.public_knowledge import PublicSearchRequest, PublicDocumentCategory, Jurisdiction

        # Build category filter
        categories = None
        if category and category != "all":
            try:
                categories = [PublicDocumentCategory(category)]
            except ValueError:
                pass

        # Build jurisdiction filter
        jurisdictions = None
        if jurisdiction:
            try:
                jurisdictions = [Jurisdiction(jurisdiction)]
            except ValueError:
                pass

        # Create search request
        search_request = PublicSearchRequest(
            query=query,
            limit=min(top_k, 50),
            categories=categories,
            jurisdictions=jurisdictions,
            search_type="hybrid",
            verified_only=True,  # Only return verified legal documents
        )

        # Execute search
        response = await service.search(search_request)

        if not response.results:
            return json.dumps({
                "results": [],
                "message": "No legal documents found matching the query",
                "search_time_ms": response.search_time_ms
            })

        # Format results with legal-specific fields
        formatted = []
        for doc in response.results[:top_k]:
            formatted.append({
                "id": doc.id,
                "title": doc.title,
                "legal_reference": doc.legal_reference,
                "category": doc.category,
                "jurisdiction": doc.jurisdiction,
                "snippet": _truncate_text(doc.content, max_length=400),
                "summary": doc.summary,
                "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
                "verified": doc.verified,
                "source_name": doc.source_name,
                "similarity_score": round(doc.similarity_score, 4) if doc.similarity_score else None,
            })

        return json.dumps({
            "results": formatted,
            "total_results": response.total_results,
            "search_time_ms": response.search_time_ms,
            "filters_applied": response.filters_applied
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Public knowledge search error: {e}")
        return json.dumps({
            "error": str(e),
            "results": []
        })


@ai_function
async def search_with_legal_context(
    query: Annotated[str, Field(description="User's query about document analysis")],
    tenant_id: Annotated[str, Field(description="Tenant ID for document isolation")],
    top_k_tenant: Annotated[int, Field(description="Number of tenant documents to retrieve")] = 10,
    top_k_legal: Annotated[int, Field(description="Number of legal documents to retrieve")] = 5,
) -> str:
    """
    Combined search across tenant documents AND public legal knowledge.

    This tool performs a unified search that returns:
    1. Relevant documents from the tenant's collection
    2. Applicable legal references from the public knowledge base

    Use this for:
    - Analyzing contracts against applicable legislation
    - Compliance verification (GDPR, LOPD, etc.)
    - Legal document review with regulatory context
    - Finding legal basis for document content

    Args:
        query: The analysis query or question
        tenant_id: Tenant identifier for document isolation
        top_k_tenant: Number of tenant documents (default 10)
        top_k_legal: Number of legal references (default 5)

    Returns:
        JSON string with combined results from both sources
    """
    # Resolve tenant_id from execution context (overrides LLM-provided value)
    actual_tenant_id = resolve_tenant_id(tenant_id)
    logger.info(f"Combined search: query='{query[:50]}...', tenant={actual_tenant_id}")

    try:
        # Search tenant documents
        tenant_results = []
        try:
            service = _get_weaviate_service()
            collection_name = get_tenant_collection_name(actual_tenant_id)
            tenant_docs = await service.hybrid_search(
                query=query,
                collection_name=collection_name,
                limit=top_k_tenant,
                alpha=0.7,
                tenant_id=actual_tenant_id,
            )
            for doc in (tenant_docs or []):
                tenant_results.append({
                    "source": "tenant",
                    "id": getattr(doc, "id", "unknown"),
                    "title": getattr(doc, "title", "Untitled"),
                    "score": round(getattr(doc, "score", 0.0), 4),
                    "snippet": _truncate_text(getattr(doc, "content", ""), max_length=300),
                })
        except Exception as e:
            logger.warning(f"Tenant search failed: {e}")

        # Search public legal knowledge
        legal_results = []
        try:
            from app.schemas.public_knowledge import PublicSearchRequest
            pk_service = _get_public_knowledge_service()
            await pk_service.initialize()

            search_request = PublicSearchRequest(
                query=query,
                limit=top_k_legal,
                search_type="hybrid",
                verified_only=True,
            )
            response = await pk_service.search(search_request)

            for doc in (response.results or []):
                legal_results.append({
                    "source": "legal",
                    "id": doc.id,
                    "title": doc.title,
                    "legal_reference": doc.legal_reference,
                    "category": doc.category,
                    "jurisdiction": doc.jurisdiction,
                    "score": round(doc.similarity_score, 4) if doc.similarity_score else None,
                    "snippet": _truncate_text(doc.content, max_length=300),
                })
        except Exception as e:
            logger.warning(f"Legal search failed: {e}")

        return json.dumps({
            "tenant_documents": tenant_results,
            "legal_references": legal_results,
            "summary": {
                "tenant_count": len(tenant_results),
                "legal_count": len(legal_results),
            }
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception(f"Combined search error: {e}")
        return json.dumps({
            "error": str(e),
            "tenant_documents": [],
            "legal_references": []
        })
