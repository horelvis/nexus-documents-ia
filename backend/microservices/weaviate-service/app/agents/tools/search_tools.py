"""
Search Tools for Qwen-Agent Framework

These tools wrap the RAG pipeline's search capabilities using Qwen-Agent's
BaseTool class pattern with @register_tool decorator.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework @ai_function pattern
- Qwen-Agent handles tool parsing internally (no vLLM --tool-call-parser needed)
- Uses class-based tools with parameters list instead of function annotations
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Union

from qwen_agent.tools.base import BaseTool, register_tool

from app.core.security import get_tenant_collection_name, get_channel_collection_name
from app.core.execution_context import (
    resolve_tenant_id,
    get_user_id,
    get_user_role_ids,
    get_is_admin,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Async Helper - Run async code from sync Qwen-Agent tool context
# =============================================================================

def _run_async(coro):
    """
    Run an async coroutine from sync context.

    Handles the case where we might already be in an async context (FastAPI)
    or need to create a new event loop.
    """
    try:
        loop = asyncio.get_running_loop()
        # Already in async context - create a new task
        # This happens when called from FastAPI async endpoints
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)
    except RuntimeError:
        # No running event loop - create one
        return asyncio.run(coro)


# =============================================================================
# Lazy Loading Service Instances
# =============================================================================

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


# =============================================================================
# Helper Functions
# =============================================================================

def _format_search_results(results: List[Any], max_results: int = 10, query: str = "") -> str:
    """
    Format search results as JSON string for agent consumption.

    OpenCode-style: When multiple results are found, includes a clarification
    flag that signals the system to ask the user for selection.
    """
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

    # OpenCode-style interception: If multiple results, signal clarification needed
    if len(formatted) > 1:
        return json.dumps({
            "results": formatted,
            "count": len(formatted),
            "_clarification_needed": True,
            "_clarification": {
                "_type": "clarification_request",
                "question": f"Encontré {len(formatted)} documentos para '{query[:50]}...'. ¿Cuál deseas analizar?",
                "header": "Selecciona documento",
                "options": [
                    {
                        "label": doc["title"][:40] + ("..." if len(doc["title"]) > 40 else ""),
                        "value": doc["id"],
                        "description": doc["snippet"][:80] + "..." if len(doc["snippet"]) > 80 else doc["snippet"]
                    }
                    for doc in formatted[:8]  # Max 8 options for UI
                ],
                "multi_select": False,
            }
        }, ensure_ascii=False, indent=2)

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


def _format_cross_collection_results(results: List[Dict[str, Any]], max_results: int = 10, query: str = "") -> str:
    """
    Format results from cross-collection search.

    OpenCode-style: When multiple results are found, includes a clarification
    flag that signals the system to ask the user for selection.
    """
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

    # OpenCode-style interception: If multiple results, signal clarification needed
    if len(formatted) > 1:
        return json.dumps({
            "results": formatted,
            "count": len(formatted),
            "_clarification_needed": True,
            "_clarification": {
                "_type": "clarification_request",
                "question": f"Encontré {len(formatted)} documentos para '{query[:50]}...'. ¿Cuál deseas analizar?",
                "header": "Selecciona documento",
                "options": [
                    {
                        "label": doc["title"][:40] + ("..." if len(doc["title"]) > 40 else ""),
                        "value": doc["id"],
                        "description": f"[{doc['source_type']}] " + (doc["snippet"][:60] + "..." if len(doc["snippet"]) > 60 else doc["snippet"])
                    }
                    for doc in formatted[:8]  # Max 8 options for UI
                ],
                "multi_select": False,
            }
        }, ensure_ascii=False, indent=2)

    return json.dumps(formatted, ensure_ascii=False, indent=2)


# =============================================================================
# Qwen-Agent Tool Classes
# =============================================================================

@register_tool('nexus_semantic_search')
class SemanticSearchTool(BaseTool):
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
    """

    description = '''Perform semantic search on tenant documents using vector embeddings.

Use this when:
- Searching for concepts or ideas
- Looking for related content
- The user's query is conversational

Returns JSON with list of relevant documents including id, title, score, snippet, source_type, and metadata.'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'The search query in natural language',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID to isolate search results',
            'required': True
        },
        {
            'name': 'top_k',
            'type': 'integer',
            'description': 'Maximum number of results to return (default 10, max 50)',
            'required': False
        },
        {
            'name': 'collection_name',
            'type': 'string',
            'description': 'Specific collection to search (optional, searches all if not provided)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute semantic search."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        tenant_id = params.get('tenant_id')
        top_k = params.get('top_k', 10)
        collection_name = params.get('collection_name')

        return _run_async(self._semantic_search(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k,
            collection_name=collection_name
        ))

    async def _semantic_search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        collection_name: Optional[str] = None,
    ) -> str:
        """Async implementation of semantic search."""
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
                return _format_search_results(results, max_results=top_k, query=query)

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

            return _format_cross_collection_results(results, max_results=top_k, query=query)

        except Exception as e:
            logger.exception(f"Semantic search error: {e}")
            return json.dumps({
                "error": str(e),
                "results": []
            })


@register_tool('nexus_hybrid_search')
class HybridSearchTool(BaseTool):
    """
    Perform hybrid search combining semantic vectors and keyword matching.

    This combines dense vector search (semantic meaning) with sparse BM25
    search (exact keywords) using Reciprocal Rank Fusion (RRF) for optimal
    results across both modalities.
    """

    description = '''Perform hybrid search combining semantic vectors and keyword matching.

Use this for:
- General document search (recommended default)
- Queries mixing concepts and specific terms
- When unsure which search type is best
- Finding emails, drive files, or any indexed content

Returns JSON with ranked documents combining both search methods.'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'The search query (natural language or keywords)',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'top_k',
            'type': 'integer',
            'description': 'Number of results to return (default 10)',
            'required': False
        },
        {
            'name': 'alpha',
            'type': 'number',
            'description': 'Balance between vector (1.0) and keyword (0.0) search (default 0.7)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute hybrid search."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        tenant_id = params.get('tenant_id')
        top_k = params.get('top_k', 10)
        alpha = params.get('alpha', 0.7)

        return _run_async(self._hybrid_search(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k,
            alpha=alpha
        ))

    async def _hybrid_search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        alpha: float = 0.7,
    ) -> str:
        """Async implementation of hybrid search."""
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

            return _format_cross_collection_results(results, max_results=top_k, query=query)

        except Exception as e:
            logger.exception(f"Hybrid search error: {e}")
            return json.dumps({
                "error": str(e),
                "results": []
            })


@register_tool('nexus_keyword_search')
class KeywordSearchTool(BaseTool):
    """
    Perform keyword-based search using BM25 algorithm.

    This finds documents containing the exact keywords or terms specified.
    It uses the BM25 algorithm which considers term frequency and document
    length for ranking.
    """

    description = '''Perform keyword-based search using BM25 algorithm.

Use this when:
- Searching for specific terms, names, or codes
- Looking for exact phrases
- The query contains proper nouns or technical terms
- Finding emails from/to specific people

Returns JSON with documents containing the specified keywords.'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'Keywords or exact terms to search for (can include quotes for phrases)',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'top_k',
            'type': 'integer',
            'description': 'Number of results to return (default 10)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute keyword search."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        tenant_id = params.get('tenant_id')
        top_k = params.get('top_k', 10)

        return _run_async(self._keyword_search(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k
        ))

    async def _keyword_search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
    ) -> str:
        """Async implementation of keyword search."""
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

            return _format_cross_collection_results(results, max_results=top_k, query=query)

        except Exception as e:
            logger.exception(f"Keyword search error: {e}")
            return json.dumps({
                "error": str(e),
                "results": []
            })


@register_tool('nexus_search_by_metadata')
class SearchByMetadataTool(BaseTool):
    """
    Search documents by metadata filters without text query.

    This allows filtering the document collection by metadata attributes
    like document type, date range, or tags.
    """

    description = '''Search documents by metadata filters without text query.

Use this when:
- Browsing documents by category
- Finding documents from a specific time period
- Filtering by document attributes

Returns JSON with filtered documents.'''

    parameters = [
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for data isolation',
            'required': True
        },
        {
            'name': 'document_type',
            'type': 'string',
            'description': 'Filter by document type (pdf, docx, xlsx, etc.)',
            'required': False
        },
        {
            'name': 'date_from',
            'type': 'string',
            'description': 'Filter documents from this date (YYYY-MM-DD)',
            'required': False
        },
        {
            'name': 'date_to',
            'type': 'string',
            'description': 'Filter documents until this date (YYYY-MM-DD)',
            'required': False
        },
        {
            'name': 'tags',
            'type': 'string',
            'description': 'Comma-separated tags to filter by',
            'required': False
        },
        {
            'name': 'top_k',
            'type': 'integer',
            'description': 'Maximum number of results (default 20)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute metadata search."""
        if isinstance(params, str):
            params = json.loads(params)

        tenant_id = params.get('tenant_id')
        document_type = params.get('document_type')
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        tags = params.get('tags')
        top_k = params.get('top_k', 20)

        return _run_async(self._search_by_metadata(
            tenant_id=tenant_id,
            document_type=document_type,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            top_k=top_k
        ))

    async def _search_by_metadata(
        self,
        tenant_id: str,
        document_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        tags: Optional[str] = None,
        top_k: int = 20,
    ) -> str:
        """Async implementation of metadata search."""
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


@register_tool('nexus_search_public_knowledge')
class SearchPublicKnowledgeTool(BaseTool):
    """
    Search the public legal knowledge base for legislation, regulations, and jurisprudence.

    This tool searches a curated database of Spanish and EU legal documents including:
    - Legislation: Laws, Royal Decrees, organic laws
    - Regulations: Ministerial orders, directives, technical regulations
    - Jurisprudence: Court rulings, Supreme Court decisions, Constitutional Court rulings
    """

    description = '''Search the public legal knowledge base for legislation, regulations, and jurisprudence.

Use this when:
- Analyzing documents for legal compliance
- Finding applicable legislation for a contract clause
- Checking GDPR/RGPD or LOPD requirements
- Looking for legal precedents or court decisions
- Verifying regulatory requirements

Returns JSON with relevant legal documents including id, title, legal_reference, category, jurisdiction, snippet, and more.'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'Search query for legal/regulatory content',
            'required': True
        },
        {
            'name': 'category',
            'type': 'string',
            'description': 'Category filter: legislation, regulation, jurisprudence, or all (default)',
            'required': False
        },
        {
            'name': 'jurisdiction',
            'type': 'string',
            'description': 'Jurisdiction filter: es (Spain), eu (EU), int (International)',
            'required': False
        },
        {
            'name': 'top_k',
            'type': 'integer',
            'description': 'Maximum number of results to return (default 10)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute public knowledge search."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        category = params.get('category', 'all')
        jurisdiction = params.get('jurisdiction')
        top_k = params.get('top_k', 10)

        return _run_async(self._search_public_knowledge(
            query=query,
            category=category,
            jurisdiction=jurisdiction,
            top_k=top_k
        ))

    async def _search_public_knowledge(
        self,
        query: str,
        category: Optional[str] = "all",
        jurisdiction: Optional[str] = None,
        top_k: int = 10,
    ) -> str:
        """Async implementation of public knowledge search."""
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


@register_tool('nexus_search_with_legal_context')
class SearchWithLegalContextTool(BaseTool):
    """
    Combined search across tenant documents AND public legal knowledge.

    This tool performs a unified search that returns:
    1. Relevant documents from the tenant's collection
    2. Applicable legal references from the public knowledge base
    """

    description = '''Combined search across tenant documents AND public legal knowledge.

Use this for:
- Analyzing contracts against applicable legislation
- Compliance verification (GDPR, LOPD, etc.)
- Legal document review with regulatory context
- Finding legal basis for document content

Returns JSON with combined results from both tenant documents and legal references.'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'The analysis query or question',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant identifier for document isolation',
            'required': True
        },
        {
            'name': 'top_k_tenant',
            'type': 'integer',
            'description': 'Number of tenant documents to retrieve (default 10)',
            'required': False
        },
        {
            'name': 'top_k_legal',
            'type': 'integer',
            'description': 'Number of legal documents to retrieve (default 5)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute combined search."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        tenant_id = params.get('tenant_id')
        top_k_tenant = params.get('top_k_tenant', 10)
        top_k_legal = params.get('top_k_legal', 5)

        return _run_async(self._search_with_legal_context(
            query=query,
            tenant_id=tenant_id,
            top_k_tenant=top_k_tenant,
            top_k_legal=top_k_legal
        ))

    async def _search_with_legal_context(
        self,
        query: str,
        tenant_id: str,
        top_k_tenant: int = 10,
        top_k_legal: int = 5,
    ) -> str:
        """Async implementation of combined search."""
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


# =============================================================================
# Tool Registration Exports
# =============================================================================

# List of all tool classes for easy import
SEARCH_TOOLS = [
    SemanticSearchTool,
    HybridSearchTool,
    KeywordSearchTool,
    SearchByMetadataTool,
    SearchPublicKnowledgeTool,
    SearchWithLegalContextTool,
]

# Tool names for function_list in Assistant (must match @register_tool names)
SEARCH_TOOL_NAMES = [
    'nexus_semantic_search',
    'nexus_hybrid_search',
    'nexus_keyword_search',
    'nexus_search_by_metadata',
    'nexus_search_public_knowledge',
    'nexus_search_with_legal_context',
]


def get_search_tools() -> list:
    """
    Get list of search tool names for use in Qwen-Agent Assistant's function_list.

    Example:
        from app.agents.tools.search_tools import get_search_tools

        agent = Assistant(
            llm=llm_cfg,
            function_list=get_search_tools(),
            system_message="..."
        )
    """
    return SEARCH_TOOL_NAMES
