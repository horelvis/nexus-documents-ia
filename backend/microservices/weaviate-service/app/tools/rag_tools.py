"""
RAG Pipeline Tools for Emma.

These tools provide LLM-callable interfaces to the RAG (Retrieval-Augmented
Generation) pipeline. They wrap the existing WeaviateService search
functionality as tools that Emma can invoke.

Tool Hierarchy:
    1. search_documents - Basic semantic search in tenant documents
    2. hybrid_search - Combines semantic + keyword search
    3. search_with_context - Returns relevant document chunks

These tools form the foundation of Emma's document understanding
capabilities. Channel tools build on top of this by adding source_type
filters for Gmail, Drive, etc.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from app.services.weaviate_service import WeaviateService
from app.services.rag.rag_pipeline import RAGPipeline
from app.schemas.weaviate import SearchRequest
from app.core.security import get_tenant_collection_name

from .base import (
    BaseTool,
    ToolDefinition,
    ToolExecutionContext,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Parameter Models
# =============================================================================

class SearchDocumentsParams(BaseModel):
    """Parameters for document search."""
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum documents to return")
    document_type: Optional[str] = Field(
        default=None,
        description="Filter by document type (contract, invoice, report, etc.)"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Filter by document tags"
    )


class HybridSearchParams(BaseModel):
    """Parameters for hybrid (semantic + keyword) search."""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum results")
    alpha: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Balance: 1.0=pure semantic, 0.0=pure keyword"
    )
    keywords: Optional[List[str]] = Field(
        default=None,
        description="Explicit keywords to boost"
    )


class RAGQueryParams(BaseModel):
    """Parameters for full RAG query with context retrieval."""
    question: str = Field(..., description="Question to answer from documents")
    max_chunks: int = Field(default=5, ge=1, le=10, description="Maximum context chunks")
    include_sources: bool = Field(default=True, description="Include source references")


# =============================================================================
# Document Search Tool
# =============================================================================

class SearchDocumentsTool(BaseTool[SearchDocumentsParams]):
    """
    Search documents in the tenant's knowledge base.

    This is the primary RAG search tool. It performs semantic search
    across all indexed documents and returns relevant matches.

    Use cases:
    - Finding relevant contracts or policies
    - Searching for specific topics across documents
    - Retrieving context for answering questions
    """

    def __init__(self, weaviate_service: Optional[WeaviateService] = None):
        self._weaviate = weaviate_service

    @property
    def name(self) -> str:
        return "search_documents"

    @property
    def category(self) -> str:
        return "rag"

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def get_params_class(self) -> Type[SearchDocumentsParams]:
        return SearchDocumentsParams

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Search the organization's document knowledge base using semantic search. "
                "Finds documents relevant to a natural language query. Use this to find "
                "contracts, policies, reports, or any indexed documents."
            ),
            category=self.category,
            parameters=[
                ToolParameter(
                    name="query",
                    type=ToolParameterType.STRING,
                    description="Natural language search query describing what you're looking for",
                    required=True
                ),
                ToolParameter(
                    name="limit",
                    type=ToolParameterType.INTEGER,
                    description="Maximum number of documents to return (1-20, default 5)",
                    required=False,
                    default=5
                ),
                ToolParameter(
                    name="document_type",
                    type=ToolParameterType.STRING,
                    description="Filter by document type: contract, invoice, report, policy, memo, other",
                    required=False
                ),
                ToolParameter(
                    name="tags",
                    type=ToolParameterType.ARRAY,
                    description="Filter by document tags",
                    required=False,
                    items_type=ToolParameterType.STRING
                ),
            ]
        )

    async def execute(
        self,
        params: SearchDocumentsParams,
        context: ToolExecutionContext
    ) -> ToolResult:
        """
        Execute semantic document search.

        Args:
            params: Search parameters
            context: Execution context with tenant_id

        Returns:
            ToolResult with matching documents
        """
        call_id = context.metadata.get("call_id", "")

        try:
            weaviate = self._weaviate or WeaviateService()
            await weaviate.initialize()

            # Build filters
            filters = {}
            if params.document_type:
                filters["document_type"] = params.document_type
            if params.tags:
                filters["tags"] = params.tags

            # Create SearchRequest for the service
            search_request = SearchRequest(
                query=params.query,
                tenant_id=context.tenant_id,
                limit=params.limit,
                filters=filters if filters else None,
                search_type="hybrid",
                user_id=context.user_id
            )

            # Perform search using SearchRequest
            response = await weaviate.search(search_request)

            # Format results for LLM (response is SearchResponse)
            formatted_docs = []
            for doc in response.results:
                # doc may be DocumentResponse (Pydantic) or dict
                doc_dict = doc if isinstance(doc, dict) else doc.model_dump()
                content = doc_dict.get("content", "")
                formatted_docs.append({
                    "title": doc_dict.get("title", "Untitled"),
                    "type": doc_dict.get("document_type", "document"),
                    "snippet": content[:500] + "..." if len(content) > 500 else content,
                    "relevance_score": doc_dict.get("score", 0),
                    "id": doc_dict.get("id", "")
                })

            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={
                    "documents": formatted_docs,
                    "total_found": len(formatted_docs),
                    "query": params.query
                }
            )

        except Exception as e:
            logger.exception(f"Error in document search: {e}")
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=f"Document search failed: {str(e)}"
            )


# =============================================================================
# Hybrid Search Tool
# =============================================================================

class HybridSearchTool(BaseTool[HybridSearchParams]):
    """
    Hybrid search combining semantic and keyword matching.

    This tool balances semantic understanding with exact keyword matching,
    useful when you need both contextual relevance and specific terms.

    The alpha parameter controls the balance:
    - 1.0 = Pure semantic search (meaning-based)
    - 0.0 = Pure keyword search (exact matches)
    - 0.7 = Default (favors semantic with keyword boost)
    """

    def __init__(self, weaviate_service: Optional[WeaviateService] = None):
        self._weaviate = weaviate_service

    @property
    def name(self) -> str:
        return "hybrid_search"

    @property
    def category(self) -> str:
        return "rag"

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def get_params_class(self) -> Type[HybridSearchParams]:
        return HybridSearchParams

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Hybrid search combining semantic meaning and keyword matching. "
                "Use this when you need both contextual relevance and specific terms. "
                "Adjust alpha to balance semantic vs keyword weighting."
            ),
            category=self.category,
            parameters=[
                ToolParameter(
                    name="query",
                    type=ToolParameterType.STRING,
                    description="Search query",
                    required=True
                ),
                ToolParameter(
                    name="limit",
                    type=ToolParameterType.INTEGER,
                    description="Maximum results (default 5)",
                    required=False,
                    default=5
                ),
                ToolParameter(
                    name="alpha",
                    type=ToolParameterType.NUMBER,
                    description="Semantic vs keyword balance: 1.0=semantic, 0.0=keyword (default 0.7)",
                    required=False,
                    default=0.7
                ),
                ToolParameter(
                    name="keywords",
                    type=ToolParameterType.ARRAY,
                    description="Specific keywords to boost in results",
                    required=False,
                    items_type=ToolParameterType.STRING
                ),
            ]
        )

    async def execute(
        self,
        params: HybridSearchParams,
        context: ToolExecutionContext
    ) -> ToolResult:
        call_id = context.metadata.get("call_id", "")

        try:
            weaviate = self._weaviate or WeaviateService()
            await weaviate.initialize()

            # Get collection name for tenant
            collection_name = get_tenant_collection_name(context.tenant_id)

            results = await weaviate.hybrid_search(
                query=params.query,
                collection_name=collection_name,
                tenant_id=context.tenant_id,
                limit=params.limit,
                alpha=params.alpha
            )

            formatted_docs = []
            for doc in results:
                # doc is DocumentResponse, access as object or dict
                doc_dict = doc if isinstance(doc, dict) else doc.model_dump()
                formatted_docs.append({
                    "title": doc_dict.get("title", "Untitled"),
                    "snippet": doc_dict.get("content", "")[:500] if doc_dict.get("content") else "",
                    "score": doc_dict.get("similarity_score", 0),
                    "id": doc_dict.get("id", "")
                })

            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={
                    "documents": formatted_docs,
                    "total_found": len(formatted_docs),
                    "alpha": params.alpha
                }
            )

        except Exception as e:
            logger.exception(f"Error in hybrid search: {e}")
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=str(e)
            )


# =============================================================================
# RAG Query Tool (with context assembly)
# =============================================================================

class RAGQueryTool(BaseTool[RAGQueryParams]):
    """
    Full RAG query tool for question answering.

    This tool retrieves relevant document chunks and assembles them
    into context suitable for answering questions. It's the most
    complete RAG tool for Q&A scenarios.

    Returns:
    - Relevant context chunks from documents
    - Source references for citations
    - Suggested answer based on context
    """

    def __init__(
        self,
        weaviate_service: Optional[WeaviateService] = None,
        rag_pipeline: Optional[RAGPipeline] = None
    ):
        self._weaviate = weaviate_service
        self._rag_pipeline = rag_pipeline

    @property
    def name(self) -> str:
        return "rag_query"

    @property
    def category(self) -> str:
        return "rag"

    @property
    def timeout_seconds(self) -> float:
        return 30.0  # RAG queries can take longer

    def get_params_class(self) -> Type[RAGQueryParams]:
        return RAGQueryParams

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Ask a question that will be answered using the document knowledge base. "
                "This tool retrieves relevant context from documents and provides source "
                "references. Use for questions that need document-grounded answers."
            ),
            category=self.category,
            parameters=[
                ToolParameter(
                    name="question",
                    type=ToolParameterType.STRING,
                    description="The question to answer from the documents",
                    required=True
                ),
                ToolParameter(
                    name="max_chunks",
                    type=ToolParameterType.INTEGER,
                    description="Maximum context chunks to retrieve (default 5)",
                    required=False,
                    default=5
                ),
                ToolParameter(
                    name="include_sources",
                    type=ToolParameterType.BOOLEAN,
                    description="Include source document references (default true)",
                    required=False,
                    default=True
                ),
            ]
        )

    async def execute(
        self,
        params: RAGQueryParams,
        context: ToolExecutionContext
    ) -> ToolResult:
        call_id = context.metadata.get("call_id", "")

        try:
            weaviate = self._weaviate or WeaviateService()
            await weaviate.initialize()

            # Create SearchRequest
            search_request = SearchRequest(
                query=params.question,
                tenant_id=context.tenant_id,
                limit=params.max_chunks,
                search_type="hybrid",
                user_id=context.user_id
            )

            # Retrieve relevant chunks using SearchRequest
            response = await weaviate.search(search_request)

            # Assemble context
            context_parts = []
            sources = []

            for i, chunk in enumerate(response.results):
                # chunk may be DocumentResponse (Pydantic) or dict
                chunk_dict = chunk if isinstance(chunk, dict) else chunk.model_dump()
                context_parts.append(f"[{i+1}] {chunk_dict.get('content', '')}")

                if params.include_sources:
                    sources.append({
                        "index": i + 1,
                        "title": chunk_dict.get("title", "Unknown"),
                        "id": chunk_dict.get("id", ""),
                        "relevance": chunk_dict.get("similarity_score", 0)
                    })

            assembled_context = "\n\n".join(context_parts)

            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={
                    "context": assembled_context,
                    "sources": sources if params.include_sources else [],
                    "chunk_count": len(response.results),
                    "question": params.question
                }
            )

        except Exception as e:
            logger.exception(f"Error in RAG query: {e}")
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=str(e)
            )


# =============================================================================
# Registration
# =============================================================================

def register_rag_tools(registry) -> None:
    """
    Register all RAG tools with the registry.

    Args:
        registry: ToolRegistry instance
    """
    registry.register(SearchDocumentsTool())
    registry.register(HybridSearchTool())
    registry.register(RAGQueryTool())
    logger.info("Registered RAG tools")
