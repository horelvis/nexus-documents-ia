"""
Emma v2 Tools - Consolidated Tool Definitions

OpenAI-compatible tool definitions for Emma v2.
These tools are designed to work with the native async LLM client.

Tool Count: 6 (consolidated from 15+ in v1)
- search: Unified search (semantic, keyword, hybrid)
- read_document: Get full document content
- analyze: Deep analysis with RAG
- sil_query: Structural queries via SIL/Cypher
- ask_user: Human-in-the-loop clarification
- legal_search: Search public legal knowledge (BOE, etc.)

Each tool is defined as:
1. OpenAI-compatible function schema (for LLM tool calling)
2. Async executor function (for actual execution)

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    Emma v2 Tools                            │
    │                                                             │
    │   LLM → Tool Call → Tool Router → Executor → Result        │
    │                                                             │
    │   Tools:                                                    │
    │   ├── search        → WeaviateService.search               │
    │   ├── read_document → RAGPipeline.get_document_content     │
    │   ├── analyze       → RAGPipeline.analyze_document          │
    │   ├── sil_query     → SIL.pre_llm_reasoning.process_query  │
    │   ├── ask_user      → HITL callback mechanism               │
    │   └── legal_search  → PublicKnowledgeService.search        │
    └─────────────────────────────────────────────────────────────┘
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from app.core.langfuse_config import langfuse_context, observe

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Schemas (OpenAI Function Calling Format)
# =============================================================================

SEARCH_TOOL = {
    "name": "search",
    "description": """Search for documents in the user's document repository.
Supports semantic (meaning-based) and keyword (exact match) search.
Use this when the user asks to find, locate, or search for documents.
Returns document list with titles, snippets, and relevance scores.""",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - can be natural language or keywords"
            },
            "search_type": {
                "type": "string",
                "enum": ["semantic", "keyword", "hybrid"],
                "description": "Search type: semantic (meaning), keyword (exact), hybrid (both)",
                "default": "hybrid"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 10
            },
            "filters": {
                "type": "object",
                "description": "Optional filters: {document_type, client_name, date_from, date_to}",
                "properties": {
                    "document_type": {"type": "string"},
                    "client_name": {"type": "string"},
                    "date_from": {"type": "string", "format": "date"},
                    "date_to": {"type": "string", "format": "date"}
                }
            }
        },
        "required": ["query"]
    }
}

READ_DOCUMENT_TOOL = {
    "name": "read_document",
    "description": """Read the full content of a specific DOCUMENT (file) by its ID.
Use this AFTER search when you need to examine document contents in detail.
Returns the complete text content of the document.

IMPORTANT: This tool is for DOCUMENTS (files like PDFs, Word docs), NOT for folders/containers.
For folders, projects, clients, or other container structures, use 'sil_query' instead.""",
    "parameters": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "The unique identifier of the document (file) to read"
            },
            "include_metadata": {
                "type": "boolean",
                "description": "Whether to include document metadata",
                "default": True
            }
        },
        "required": ["document_id"]
    }
}

ANALYZE_TOOL = {
    "name": "analyze",
    "description": """Perform deep analysis on a document using RAG (Retrieval-Augmented Generation).
Use this for complex questions that require understanding document content in context.
Can analyze contracts, identify risks, extract obligations, etc.""",
    "parameters": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "Document ID to analyze (use search first to find it)"
            },
            "analysis_type": {
                "type": "string",
                "enum": ["comprehensive", "risks", "summary", "obligations", "compliance", "entities"],
                "description": "Type of analysis to perform",
                "default": "comprehensive"
            },
            "specific_question": {
                "type": "string",
                "description": "Optional specific question to answer about the document"
            }
        },
        "required": ["document_id"]
    }
}

SIL_QUERY_TOOL = {
    "name": "sil_query",
    "description": """Query the Structural Intelligence Layer for documents, folders, and their relationships.
Use this for:
- Structural questions: counts, locations, relationships
- Folders/containers: "Show folder X", "What's in project Y?", "List all clients"
- Document listings: "Documents from 2024", "Contracts for client ACME"

IMPORTANT: Use this tool for CONTAINERS (folders, projects, clients, cases, etc.), NOT read_document.
Containers are organizational structures that hold documents, not documents themselves.
The specific terminology varies by organization (expedientes, proyectos, clientes, obras, etc.)

Examples:
- "How many [folders/projects/clients] in 2006?" → sil_query
- "Show [folder/project/client] ABC-123" → sil_query
- "What documents are in [folder/project] X?" → sil_query
- "Where is contract Y?" → sil_query

This tool can answer WITHOUT reading document content, making it very fast.""",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query about documents, folders/containers, or structure"
            },
            "include_content_preview": {
                "type": "boolean",
                "description": "Whether to include content previews in results",
                "default": False
            }
        },
        "required": ["query"]
    }
}

ASK_USER_TOOL = {
    "name": "ask_user",
    "description": """Ask the user for clarification or confirmation.
Use this when:
- Search returns multiple documents and user should choose
- Query is ambiguous and needs clarification
- Action needs user confirmation before proceeding""",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of choices to present to user"
            },
            "context": {
                "type": "string",
                "description": "Additional context for the question"
            }
        },
        "required": ["question"]
    }
}

LEGAL_SEARCH_TOOL = {
    "name": "legal_search",
    "description": """Search public legal knowledge base (Spanish legislation, BOE, jurisprudence).
Use this when the user asks about laws, regulations, or legal requirements.
Does NOT search user documents - only public legal sources.""",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Legal topic or question to search"
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["boe", "jurisprudence", "eu_law", "all"]
                },
                "description": "Legal sources to search",
                "default": ["all"]
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results",
                "default": 5
            }
        },
        "required": ["query"]
    }
}

# All tools in OpenAI format
EMMA_V2_TOOLS: List[Dict[str, Any]] = [
    SEARCH_TOOL,
    READ_DOCUMENT_TOOL,
    ANALYZE_TOOL,
    SIL_QUERY_TOOL,
    ASK_USER_TOOL,
    LEGAL_SEARCH_TOOL,
]

EMMA_V2_TOOL_NAMES: List[str] = [t["name"] for t in EMMA_V2_TOOLS]


# =============================================================================
# Tool Execution Context
# =============================================================================

@dataclass
class ToolContext:
    """Context passed to tool executors."""
    tenant_id: str
    user_id: Optional[str] = None
    role_ids: List[str] = field(default_factory=list)
    is_admin: bool = False
    conversation_id: Optional[str] = None
    # Callbacks
    ask_user_callback: Optional[Callable] = None


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Convert to JSON string for LLM consumption."""
        if self.error:
            return json.dumps({
                "success": False,
                "error": self.error,
            }, ensure_ascii=False)

        return json.dumps({
            "success": True,
            "data": self.data,
            "metadata": self.metadata,
        }, ensure_ascii=False, indent=2)


# =============================================================================
# Tool Executor Registry
# =============================================================================

_tool_executors: Dict[str, Callable] = {}


def register_executor(tool_name: str):
    """Decorator to register a tool executor function."""
    def decorator(func: Callable):
        _tool_executors[tool_name] = func
        return func
    return decorator


async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    context: ToolContext,
) -> ToolResult:
    """
    Execute a tool by name.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments from LLM
        context: Execution context

    Returns:
        ToolResult with data or error
    """
    if tool_name not in _tool_executors:
        return ToolResult(
            success=False,
            data=None,
            error=f"Unknown tool: {tool_name}",
        )

    # Create a span for this tool execution
    parent = langfuse_context.get_current_observation()
    span = None
    if parent:
        try:
            span = parent.span(
                name=f"tool.{tool_name}",
                input=arguments,
                metadata={
                    "tenant_id": context.tenant_id,
                    "user_id": context.user_id,
                },
            )
            langfuse_context.push_observation(span)
        except Exception as e:
            logger.debug(f"Failed to create tool span: {e}")

    start_time = time.time()

    try:
        executor = _tool_executors[tool_name]
        result = await executor(arguments, context)

        # Update span with result
        if span:
            latency_ms = (time.time() - start_time) * 1000
            try:
                span.update(
                    output=result.data if result.success else {"error": result.error},
                    metadata={
                        "success": result.success,
                        "latency_ms": latency_ms,
                    },
                    level="ERROR" if not result.success else "DEFAULT",
                )
                span.end()
            except Exception:
                pass
            langfuse_context.pop_observation()

        return result
    except Exception as e:
        logger.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)

        # Update span with error
        if span:
            try:
                span.update(
                    level="ERROR",
                    status_message=str(e),
                )
                span.end()
            except Exception:
                pass
            langfuse_context.pop_observation()

        return ToolResult(
            success=False,
            data=None,
            error=str(e),
        )


# =============================================================================
# Tool Implementations
# =============================================================================

# Lazy service loading
_weaviate_service = None
_rag_pipeline = None
_sil_engine = None
_public_knowledge = None


def _get_weaviate_service():
    global _weaviate_service
    if _weaviate_service is None:
        from app.services.weaviate_service import WeaviateService
        _weaviate_service = WeaviateService()
    return _weaviate_service


def _get_rag_pipeline():
    global _rag_pipeline
    if _rag_pipeline is None:
        from app.services.rag.rag_pipeline import RAGPipeline
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline


def _get_sil_engine():
    global _sil_engine
    if _sil_engine is None:
        from app.services.sil import pre_llm_engine
        _sil_engine = pre_llm_engine
    return _sil_engine


def _get_public_knowledge():
    global _public_knowledge
    if _public_knowledge is None:
        from app.services.public_knowledge_service import public_knowledge_service
        _public_knowledge = public_knowledge_service
    return _public_knowledge


@register_executor("search")
async def execute_search(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute document search using Weaviate vector/hybrid search."""
    query = args.get("query", "")
    search_type = args.get("search_type", "hybrid")
    limit = args.get("limit", 10)
    filters = args.get("filters", {})

    service = _get_weaviate_service()
    await service.initialize()

    try:
        from app.core.security import get_tenant_collection_name
        from app.schemas.weaviate import SearchRequest

        collection = get_tenant_collection_name(ctx.tenant_id)

        logger.info(f"🔍 Emma search: query='{query[:50]}...', type={search_type}, collection={collection}")

        # Build SearchRequest with proper parameters
        search_request = SearchRequest(
            query=query,
            limit=limit,
            tenant_id=ctx.tenant_id,
            search_type=search_type,  # "hybrid", "semantic", "keyword"
            filters=filters if filters else None,
            user_id=ctx.user_id,
            user_role_ids=ctx.role_ids,
            is_admin=ctx.is_admin,
        )

        # Execute search using the main search method
        response = await service.search_documents(collection, search_request)

        # Format results from SearchResponse
        formatted = []
        for doc in response.results[:limit]:
            formatted.append({
                "id": doc.id or doc.document_id or "unknown",
                "title": doc.title or doc.filename or "Untitled",
                "score": round(doc.score or 0.0, 4),
                "snippet": _truncate(doc.content or "", 300),
                "document_type": doc.document_type or "unknown",
            })

        logger.info(f"✅ Emma search returned {len(formatted)} results")

        return ToolResult(
            success=True,
            data={
                "results": formatted,
                "count": len(formatted),
                "query": query,
                "total_found": response.total,
            },
            metadata={"search_type": search_type, "collection": collection},
        )

    except Exception as e:
        logger.error(f"❌ Search error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


@register_executor("read_document")
async def execute_read_document(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute document read."""
    document_id = args.get("document_id", "")
    include_metadata = args.get("include_metadata", True)

    if not document_id:
        return ToolResult(success=False, data=None, error="document_id is required")

    pipeline = _get_rag_pipeline()
    await pipeline.initialize()

    try:
        from app.core.security import get_tenant_collection_name
        collection = get_tenant_collection_name(ctx.tenant_id)

        # Get document content
        content = await pipeline.get_document_content(
            collection_name=collection,
            document_id=document_id,
        )

        result_data = {
            "document_id": document_id,
            "content": content.get("content", ""),
        }

        if include_metadata:
            result_data["metadata"] = content.get("metadata", {})

        return ToolResult(
            success=True,
            data=result_data,
        )

    except Exception as e:
        logger.error(f"Read document error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


@register_executor("analyze")
async def execute_analyze(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute document analysis."""
    document_id = args.get("document_id", "")
    analysis_type = args.get("analysis_type", "comprehensive")
    specific_question = args.get("specific_question", "")

    if not document_id:
        return ToolResult(success=False, data=None, error="document_id is required")

    pipeline = _get_rag_pipeline()
    await pipeline.initialize()

    try:
        from app.core.security import get_tenant_collection_name
        collection = get_tenant_collection_name(ctx.tenant_id)

        # Build analysis query
        if specific_question:
            query = specific_question
        else:
            query = _get_analysis_query(analysis_type)

        # Use RAG pipeline for analysis
        result = await pipeline.answer_with_context(
            collection_name=collection,
            query=query,
            document_ids=[document_id],
            max_chunks=10,
        )

        return ToolResult(
            success=True,
            data={
                "document_id": document_id,
                "analysis_type": analysis_type,
                "analysis": result.get("answer", ""),
                "sources": result.get("sources", []),
            },
        )

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


@register_executor("sil_query")
async def execute_sil_query(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute SIL structural query."""
    query = args.get("query", "")
    include_preview = args.get("include_content_preview", False)

    if not query:
        return ToolResult(success=False, data=None, error="query is required")

    sil = _get_sil_engine()
    await sil.initialize()

    try:
        result = await sil.process_query(
            query=query,
            tenant_id=ctx.tenant_id,
        )

        # If process_query returns without exception, it was successful
        # Errors are now propagated via CypherQueryError and other exceptions

        response_data = {
            "reasoning_type": result.type.value if hasattr(result.type, 'value') else str(result.type),
            "requires_rag": result.requires_rag,
            "explanation": result.reasoning_explanation,
        }

        # Include structural context
        if result.structural_context:
            ctx_data = result.structural_context
            # Get entity type (folder, document, or both)
            entity_type = getattr(ctx_data, 'entity_type', 'document')
            if ctx_data.details and ctx_data.details.get('entity_type'):
                entity_type = ctx_data.details['entity_type']

            response_data["structural_context"] = {
                "query_type": ctx_data.query_type,
                "entity_type": entity_type,  # folder, document, or both
                "document_count": ctx_data.document_count,
                "document_titles": ctx_data.document_titles[:10],
                "folder_hierarchy": ctx_data.folder_hierarchy,
                "result": ctx_data.query_result,
            }

        # Include target documents if focused RAG needed
        if result.target_document_ids:
            response_data["target_documents"] = result.target_document_ids[:20]

        return ToolResult(
            success=True,
            data=response_data,
            metadata={"processing_time_ms": result.processing_time_ms},
        )

    except Exception as e:
        logger.error(f"SIL query error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


@register_executor("ask_user")
async def execute_ask_user(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute user clarification request."""
    question = args.get("question", "")
    options = args.get("options", [])
    context = args.get("context", "")

    if not question:
        return ToolResult(success=False, data=None, error="question is required")

    # If we have a callback, use it
    if ctx.ask_user_callback:
        try:
            response = await ctx.ask_user_callback(
                question=question,
                options=options,
                context=context,
            )
            return ToolResult(
                success=True,
                data={"user_response": response},
            )
        except Exception as e:
            logger.error(f"Ask user callback error: {e}")

    # Otherwise, return a signal for the conversation handler
    return ToolResult(
        success=True,
        data={
            "_action": "clarification_needed",
            "question": question,
            "options": options,
            "context": context,
        },
    )


@register_executor("legal_search")
async def execute_legal_search(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute public legal knowledge search."""
    query = args.get("query", "")
    sources = args.get("sources", ["all"])
    limit = args.get("limit", 5)

    if not query:
        return ToolResult(success=False, data=None, error="query is required")

    public_knowledge = _get_public_knowledge()

    try:
        await public_knowledge.initialize()

        results = await public_knowledge.search(
            query=query,
            categories=sources if "all" not in sources else None,
            limit=limit,
        )

        formatted = []
        for doc in results[:limit]:
            formatted.append({
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
                "reference": doc.get("reference", ""),
                "snippet": _truncate(doc.get("content", ""), 500),
                "url": doc.get("url", ""),
            })

        return ToolResult(
            success=True,
            data={
                "results": formatted,
                "count": len(formatted),
                "query": query,
            },
        )

    except Exception as e:
        logger.error(f"Legal search error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


# =============================================================================
# Helper Functions
# =============================================================================

def _truncate(text: str, max_length: int = 300) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def _get_analysis_query(analysis_type: str) -> str:
    """Get analysis query for type."""
    queries = {
        "comprehensive": "Realiza un análisis completo de este documento. Identifica el tipo, partes involucradas, puntos clave y cualquier aspecto relevante.",
        "risks": "Identifica los riesgos legales o comerciales en este documento. Señala cláusulas problemáticas o ausencias importantes.",
        "summary": "Resume los puntos principales de este documento de forma concisa.",
        "obligations": "Extrae todas las obligaciones y compromisos de las partes mencionadas en este documento.",
        "compliance": "Evalúa el cumplimiento normativo de este documento respecto a la legislación aplicable.",
        "entities": "Extrae las entidades importantes: personas, organizaciones, fechas, cantidades, direcciones.",
    }
    return queries.get(analysis_type, queries["comprehensive"])


# =============================================================================
# Exports
# =============================================================================

def get_emma_v2_tools() -> List[Dict[str, Any]]:
    """Get all Emma v2 tool schemas."""
    return EMMA_V2_TOOLS


def get_tool_names() -> List[str]:
    """Get all Emma v2 tool names."""
    return EMMA_V2_TOOL_NAMES
