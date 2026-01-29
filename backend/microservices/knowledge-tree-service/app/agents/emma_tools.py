"""
Emma Tools - Consolidated Tool Definitions

OpenAI-compatible tool definitions for Emma.
These tools are designed to work with the native async LLM client.

**IMPORTANT**: This version uses HTTP client to call weaviate-service
instead of direct service imports. This enables the separation of
emma-agent-service from weaviate-service.

Tool Count: 5 (consolidated from 15+ in v1)
- search: Unified search (semantic, keyword, hybrid)
- read_document: Get full document content
- analyze: Deep analysis with RAG
- ask_user: Human-in-the-loop clarification
- legal_search: Search public legal knowledge (BOE, etc.)

Each tool is defined as:
1. OpenAI-compatible function schema (for LLM tool calling)
2. Async executor function (for actual execution via HTTP)

Architecture (emma-agent-service):
    ┌─────────────────────────────────────────────────────────────┐
    │                    Emma Tools                               │
    │                                                             │
    │   LLM → Tool Call → Tool Router → Executor → HTTP Result   │
    │                                                             │
    │   Tools:                                                    │
    │   ├── search        → WeaviateClient.search_documents      │
    │   ├── read_document → WeaviateClient.get_document_content  │
    │   ├── analyze       → WeaviateClient.rag_query             │
    │   ├── ask_user      → HITL callback mechanism              │
    │   └── legal_search  → WeaviateClient (public knowledge)    │
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
Returns the complete text content of the document.""",
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
EMMA_TOOLS: List[Dict[str, Any]] = [
    SEARCH_TOOL,
    READ_DOCUMENT_TOOL,
    ANALYZE_TOOL,
    ASK_USER_TOOL,
    LEGAL_SEARCH_TOOL,
]

EMMA_TOOL_NAMES: List[str] = [t["name"] for t in EMMA_TOOLS]


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
# HTTP Client (calls weaviate-service)
# =============================================================================

# Lazy client loading
_weaviate_client = None


def _get_weaviate_client():
    """Get singleton WeaviateClient for HTTP calls to weaviate-service."""
    global _weaviate_client
    if _weaviate_client is None:
        from app.clients import get_weaviate_client
        _weaviate_client = get_weaviate_client()
    return _weaviate_client


# =============================================================================
# Tool Implementations (via HTTP to weaviate-service)
# =============================================================================

@register_executor("search")
async def execute_search(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute document search via weaviate-service HTTP API."""
    query = args.get("query", "")
    search_type = args.get("search_type", "hybrid")
    limit = args.get("limit", 10)
    filters = args.get("filters", {})

    client = _get_weaviate_client()

    try:
        logger.info(f"Emma search: query='{query[:50]}...', type={search_type}")

        # Use hybrid or semantic search based on type
        if search_type == "hybrid":
            results = await client.hybrid_search(
                tenant_id=ctx.tenant_id,
                query=query,
                limit=limit,
                alpha=0.5,  # Balance between vector and keyword
                filters=filters if filters else None
            )
        else:
            results = await client.search_documents(
                tenant_id=ctx.tenant_id,
                query=query,
                limit=limit,
                filters=filters if filters else None,
                include_content=True
            )

        # Format results
        formatted = []
        for doc in results[:limit]:
            formatted.append({
                "id": doc.document_id,
                "title": doc.metadata.get("title", doc.metadata.get("filename", "Untitled")),
                "score": round(doc.score, 4),
                "snippet": _truncate(doc.content, 300),
                "document_type": doc.metadata.get("document_type", "unknown"),
            })

        logger.info(f"Emma search returned {len(formatted)} results")

        return ToolResult(
            success=True,
            data={
                "results": formatted,
                "count": len(formatted),
                "query": query,
                "total_found": len(formatted),
            },
            metadata={"search_type": search_type},
        )

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


@register_executor("read_document")
async def execute_read_document(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute document read via weaviate-service HTTP API."""
    document_id = args.get("document_id", "")
    include_metadata = args.get("include_metadata", True)

    if not document_id:
        return ToolResult(success=False, data=None, error="document_id is required")

    client = _get_weaviate_client()

    try:
        # Get document content via HTTP
        content = await client.get_document_content(
            tenant_id=ctx.tenant_id,
            document_id=document_id,
            include_chunks=False
        )

        if "error" in content:
            return ToolResult(success=False, data=None, error=content["error"])

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
    """Execute document analysis via weaviate-service RAG pipeline."""
    document_id = args.get("document_id", "")
    analysis_type = args.get("analysis_type", "comprehensive")
    specific_question = args.get("specific_question", "")

    if not document_id:
        return ToolResult(success=False, data=None, error="document_id is required")

    client = _get_weaviate_client()

    try:
        # Build analysis query
        if specific_question:
            query = specific_question
        else:
            query = _get_analysis_query(analysis_type)

        # Add document context to query
        full_query = f"Regarding document {document_id}: {query}"

        # Use RAG query via HTTP
        result = await client.rag_query(
            tenant_id=ctx.tenant_id,
            query=full_query,
            user_id=ctx.user_id,
            max_tokens=4096,
            include_sources=True
        )

        return ToolResult(
            success=True,
            data={
                "document_id": document_id,
                "analysis_type": analysis_type,
                "analysis": result.answer,
                "sources": result.sources,
                "confidence": result.confidence,
            },
        )

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        return ToolResult(success=False, data=None, error=str(e))


@register_executor("ask_user")
async def execute_ask_user(args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Execute user clarification request (no HTTP needed - local callback)."""
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
    """Execute public legal knowledge search via weaviate-service."""
    query = args.get("query", "")
    sources = args.get("sources", ["all"])
    limit = args.get("limit", 5)

    if not query:
        return ToolResult(success=False, data=None, error="query is required")

    client = _get_weaviate_client()

    try:
        # Use general search but with public knowledge collection
        # Note: weaviate-service routes this to public knowledge service
        results = await client.search_documents(
            tenant_id="public",  # Special tenant for public knowledge
            query=query,
            limit=limit,
            filters={"sources": sources} if "all" not in sources else None
        )

        formatted = []
        for doc in results[:limit]:
            formatted.append({
                "title": doc.metadata.get("title", ""),
                "source": doc.metadata.get("source", ""),
                "reference": doc.metadata.get("reference", ""),
                "snippet": _truncate(doc.content, 500),
                "url": doc.metadata.get("url", ""),
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

def get_emma_tools() -> List[Dict[str, Any]]:
    """Get all Emma tool schemas."""
    return EMMA_TOOLS


def get_tool_names() -> List[str]:
    """Get all Emma tool names."""
    return EMMA_TOOL_NAMES


