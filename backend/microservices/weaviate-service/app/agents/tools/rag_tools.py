"""
RAG Tools for Qwen-Agent Framework

Main RAG pipeline tools that provide complete question-answering
capabilities with source citation and claim validation.

This is the primary toolset for answering user questions using the
document knowledge base.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework @ai_function pattern
- Uses class-based tools with @register_tool decorator
"""

import asyncio
import json
import logging
from typing import Optional, Union

from qwen_agent.tools.base import BaseTool, register_tool

from app.core.security import get_tenant_collection_name
from app.core.execution_context import (
    resolve_tenant_id,
    get_user_id,
    get_user_role_ids,
    get_is_admin,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Async Helper
# =============================================================================

def _run_async(coro):
    """
    Run an async coroutine from sync context.

    Handles the case where we might already be in an async context (FastAPI)
    or need to create a new event loop.
    """
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=120)  # Longer timeout for RAG
    except RuntimeError:
        return asyncio.run(coro)


# =============================================================================
# Lazy Loading
# =============================================================================

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


# =============================================================================
# Qwen-Agent Tool Classes
# =============================================================================

@register_tool('rag_answer')
class RAGAnswerTool(BaseTool):
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
    """

    description = '''Generate a complete answer using the RAG pipeline.

Use this tool when the user asks a question that needs to be answered using information from their documents.

Returns JSON with:
- answer: The generated response
- sources: List of source documents used
- confidence: Confidence score (0-1)
- validation: Claim validation results (if enabled)'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': "The user's question or information request",
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for document access',
            'required': True
        },
        {
            'name': 'validate_claims',
            'type': 'boolean',
            'description': 'Whether to validate claims against sources (default true)',
            'required': False
        },
        {
            'name': 'include_sources',
            'type': 'boolean',
            'description': 'Whether to include source citations (default true)',
            'required': False
        },
        {
            'name': 'max_sources',
            'type': 'integer',
            'description': 'Maximum number of sources to cite (default 5)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute RAG answer generation."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        tenant_id = params.get('tenant_id')
        validate_claims = params.get('validate_claims', True)
        include_sources = params.get('include_sources', True)
        max_sources = params.get('max_sources', 5)

        return _run_async(self._rag_answer(
            query=query,
            tenant_id=tenant_id,
            validate_claims=validate_claims,
            include_sources=include_sources,
            max_sources=max_sources
        ))

    async def _rag_answer(
        self,
        query: str,
        tenant_id: str,
        validate_claims: bool = True,
        include_sources: bool = True,
        max_sources: int = 5,
    ) -> str:
        """Async implementation of RAG answer."""
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


@register_tool('get_document_content')
class GetDocumentContentTool(BaseTool):
    """
    Retrieve the full content of a specific document.

    Use this tool when you need to read a specific document's content
    for analysis or to answer questions about it.

    SECURITY: This function automatically applies channel access control:
    - Regular uploads are always accessible
    - Tenant-wide channels are accessible to all tenant users
    - Personal channels (Gmail, personal Drive) are only accessible to the owner
    """

    description = '''Retrieve the full content of a specific document.

Use this when you need to read a specific document's content for analysis or to answer questions about it.

Returns JSON with:
- id: Document identifier
- title: Document title
- content: Full or truncated content
- metadata: Document metadata (type, date, etc.)
- truncated: Whether content was truncated
- is_channel: Whether document is from a channel'''

    parameters = [
        {
            'name': 'document_id',
            'type': 'string',
            'description': 'The document ID to retrieve',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for access control',
            'required': True
        },
        {
            'name': 'max_length',
            'type': 'integer',
            'description': 'Maximum content length to return (default 10000)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute document content retrieval."""
        if isinstance(params, str):
            params = json.loads(params)

        document_id = params.get('document_id')
        tenant_id = params.get('tenant_id')
        max_length = params.get('max_length', 10000)

        return _run_async(self._get_document_content(
            document_id=document_id,
            tenant_id=tenant_id,
            max_length=max_length
        ))

    async def _get_document_content(
        self,
        document_id: str,
        tenant_id: str,
        max_length: int = 10000,
    ) -> str:
        """Async implementation of document content retrieval."""
        # Resolve tenant_id and ACL context from execution context
        actual_tenant_id = resolve_tenant_id(tenant_id)
        actual_user_id = get_user_id()
        actual_user_role_ids = get_user_role_ids()
        actual_is_admin = get_is_admin()
        logger.info(f"Getting document: id={document_id}, tenant={actual_tenant_id}, user={actual_user_id[:8] if actual_user_id else 'None'}...")

        try:
            service = _get_weaviate_service()

            # Always use cross-collection search with ACL verification
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


@register_tool('summarize_documents')
class SummarizeDocumentsTool(BaseTool):
    """
    Create a summary across multiple documents on a topic.

    This retrieves relevant documents and creates a consolidated
    summary that synthesizes information from all sources.
    """

    description = '''Create a summary across multiple documents on a topic.

Use this when the user wants an overview of a topic that may span multiple documents.

Returns JSON with:
- summary: Consolidated summary
- documents_used: List of documents that contributed
- topic: The original query/topic'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'Topic or question to summarize around',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID for document access',
            'required': True
        },
        {
            'name': 'max_documents',
            'type': 'integer',
            'description': 'Maximum documents to include in summary (default 5)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute document summarization."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        tenant_id = params.get('tenant_id')
        max_documents = params.get('max_documents', 5)

        return _run_async(self._summarize_documents(
            query=query,
            tenant_id=tenant_id,
            max_documents=max_documents
        ))

    async def _summarize_documents(
        self,
        query: str,
        tenant_id: str,
        max_documents: int = 5,
    ) -> str:
        """Async implementation of document summarization."""
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

            # Generate summary using RAG pipeline
            summary_query = f"""Create a comprehensive summary on the topic: "{query}"

Synthesize information from the available documents and provide:
1. Overview of what the documents say about this topic
2. Key points from each document
3. Any contradictions or different perspectives
4. Overall conclusion"""

            rag_result = await pipeline.process_query(
                query=summary_query,
                tenant_id=actual_tenant_id,
                validate_claims=False,
                top_k=max_documents,
            )

            summary = rag_result.answer if hasattr(rag_result, 'answer') else str(rag_result)

            return json.dumps({
                "topic": query,
                "summary": summary,
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


@register_tool('answer_with_context')
class AnswerWithContextTool(BaseTool):
    """
    Answer a question using provided context (no retrieval).

    Use this when you already have the relevant context and just
    need to generate an answer. This skips the retrieval step.
    """

    description = '''Answer a question using provided context (no retrieval).

Use this when you already have the relevant context and just need to generate an answer.

Returns JSON with the answer.'''

    parameters = [
        {
            'name': 'query',
            'type': 'string',
            'description': 'The question to answer',
            'required': True
        },
        {
            'name': 'context',
            'type': 'string',
            'description': 'Pre-provided context to use for answering',
            'required': True
        },
        {
            'name': 'tenant_id',
            'type': 'string',
            'description': 'Tenant ID (for logging/tracking)',
            'required': True
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute context-based answering."""
        if isinstance(params, str):
            params = json.loads(params)

        query = params.get('query')
        context = params.get('context')
        tenant_id = params.get('tenant_id')

        return _run_async(self._answer_with_context(
            query=query,
            context=context,
            tenant_id=tenant_id
        ))

    async def _answer_with_context(
        self,
        query: str,
        context: str,
        tenant_id: str,
    ) -> str:
        """Async implementation of context-based answering."""
        # Resolve tenant_id from execution context (overrides LLM-provided value)
        actual_tenant_id = resolve_tenant_id(tenant_id)
        logger.info(f"Answer with context: query='{query[:50]}...', tenant={actual_tenant_id}")

        try:
            pipeline = _get_rag_pipeline()

            contextual_query = f"""Based on the following context, answer this question: {query}

CONTEXT:
{context[:6000]}

Answer based only on the provided context. If the context doesn't contain the answer, say so."""

            rag_result = await pipeline.process_query(
                query=contextual_query,
                tenant_id=actual_tenant_id,
                validate_claims=False,
                top_k=3,
            )

            answer = rag_result.answer if hasattr(rag_result, 'answer') else str(rag_result)

            return json.dumps({
                "query": query,
                "answer": answer,
                "context_used": True,
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.exception(f"Answer with context error: {e}")
            return json.dumps({
                "error": str(e),
                "query": query
            })


# =============================================================================
# Tool Registration Exports
# =============================================================================

RAG_TOOLS = [
    RAGAnswerTool,
    GetDocumentContentTool,
    SummarizeDocumentsTool,
    AnswerWithContextTool,
]

RAG_TOOL_NAMES = [
    'rag_answer',
    'get_document_content',
    'summarize_documents',
    'answer_with_context',
]


def get_rag_tools() -> list:
    """
    Get list of RAG tool names for use in Qwen-Agent Assistant's function_list.

    Example:
        from app.agents.tools.rag_tools import get_rag_tools

        agent = Assistant(
            llm=llm_cfg,
            function_list=get_rag_tools(),
            system_message="..."
        )
    """
    return RAG_TOOL_NAMES
