"""
General Agent Node

Fallback agent for non-specialized queries.
Handles general document search, analysis, and Q&A.

Domain Coverage:
- General document search and retrieval
- Document summarization
- Structural queries (counting, listing, filtering via FalkorDB graph)
- Cross-domain questions
- Fallback when no specialist matches

Tools:
- document_search: Search across all documents
- document_summary: Summarize document content
- structural_query: Query document structure (count, list, filter by date/type)
"""

import logging
import time
from typing import Any, Dict, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...state import RAGState
from .base import create_specialist_node

# Langfuse tracing
try:
    from app.core.langfuse_config import langfuse_context, observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    def observe(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger(__name__)

# General Agent System Prompt
GENERAL_SYSTEM_PROMPT = """Eres Emma, asistente de IA especializada en gestión documental.

Tu rol es ayudar a los usuarios a:
- Buscar y encontrar documentos en su repositorio
- Responder preguntas sobre el contenido de los documentos
- Resumir y analizar documentos
- Navegar la estructura de carpetas y proyectos
- Responder consultas estructurales (contar, listar, filtrar por fecha/tipo)

Capacidades:
1. **Consultas estructurales** (PRIORITARIA): Para preguntas de conteo, listado o filtrado usa `structural_query`
   - "¿Cuántos expedientes tengo del año 2006?" → structural_query
   - "Lista todos los contratos de ACME" → structural_query
   - "¿Tengo facturas de más de 10.000€?" → structural_query
   - "Documentos del último mes" → structural_query
2. **Búsqueda de documentos**: Para buscar por contenido semántico usa `document_search`
3. **Análisis de contenido**: Puedes leer y analizar el contenido de los documentos
4. **Resumen**: Puedes generar resúmenes de documentos específicos con `document_summary`

Directrices:
- **IMPORTANTE**: Para preguntas de CONTEO o LISTADO, usa SIEMPRE `structural_query` primero
- Responde siempre basándote en los documentos del usuario, no en conocimiento general
- Si no encuentras información relevante, indícalo claramente
- Sugiere búsquedas alternativas cuando sea apropiado
- Mantén las respuestas concisas pero informativas
- Cita siempre las fuentes cuando sea posible

Responde SIEMPRE en español."""


# Tool Input Schemas
class DocumentSearchInput(BaseModel):
    """Input for document search tool."""
    query: str = Field(description="Search query - natural language or keywords")
    search_type: str = Field(
        default="hybrid",
        description="Search type: 'semantic' (meaning), 'keyword' (exact), 'hybrid' (both)"
    )
    limit: int = Field(default=10, description="Maximum number of results")


class DocumentSummaryInput(BaseModel):
    """Input for document summary tool."""
    document_id: str = Field(description="ID of the document to summarize")
    summary_type: str = Field(
        default="concise",
        description="Summary type: 'concise' (brief), 'detailed' (comprehensive), 'key_points' (bullet points)"
    )


class StructuralQueryInput(BaseModel):
    """Input for structural queries using FalkorDB graph."""
    query: str = Field(
        description="Natural language query about document structure. Examples: "
                    "'¿Cuántos expedientes tengo del año 2006?', "
                    "'Lista todos los contratos de ACME', "
                    "'Documentos del último mes', "
                    "'¿Tengo facturas de más de 10.000€?'"
    )
    max_results: int = Field(
        default=100,
        description="Maximum number of results for list queries"
    )




# Tool Implementations
async def document_search(
    query: str,
    search_type: str = "hybrid",
    limit: int = 10,
    tenant_id: str = "",
    user_id: str = "",
) -> str:
    """
    Search for documents in the user's repository.

    Uses hybrid search combining semantic (meaning-based)
    and keyword (exact match) approaches.
    """
    try:
        from app.clients.weaviate_client import get_weaviate_client

        weaviate_client = get_weaviate_client()

        # Use HTTP client for microservice communication
        if search_type == "hybrid":
            results = await weaviate_client.hybrid_search(
                tenant_id=tenant_id,
                query=query,
                limit=limit,
            )
        else:
            results = await weaviate_client.search_documents(
                tenant_id=tenant_id,
                query=query,
                limit=limit,
            )

        if not results:
            return f"No se encontraron documentos para: '{query}'"

        formatted = [f"**Resultados de búsqueda para**: '{query}'\n"]

        for i, result in enumerate(results, 1):
            title = result.metadata.get('title', 'Sin título')
            score = result.score
            content = result.content

            # Truncate content preview
            preview = content[:200] + "..." if len(content) > 200 else content

            formatted.append(
                f"{i}. **{title}** (relevancia: {score:.2f})\n"
                f"   {preview}\n"
            )

        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"Document search failed: {e}")
        return f"Error en la búsqueda: {str(e)}"


async def document_summary(
    document_id: str,
    summary_type: str = "concise",
    tenant_id: str = "",
) -> str:
    """
    Generate a summary of a document.

    Retrieves the document content and generates
    a summary based on the requested type.
    """
    try:
        from app.clients.weaviate_client import get_weaviate_client

        weaviate_client = get_weaviate_client()

        # Get document content via HTTP
        doc_content = await weaviate_client.get_document_content(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        if not doc_content or "error" in doc_content:
            return f"No se pudo obtener el contenido del documento: {document_id}"

        # For now, return a truncated version as summary
        # In production, this would use LLM for summarization
        content = doc_content.get("content", "")

        if summary_type == "concise":
            max_len = 500
        elif summary_type == "detailed":
            max_len = 2000
        else:  # key_points
            max_len = 1000

        if len(content) > max_len:
            summary = content[:max_len] + "..."
        else:
            summary = content

        title = doc_content.get("title", "Documento")

        return f"""**Resumen de**: {title}

{summary}

*Tipo de resumen: {summary_type}*"""

    except Exception as e:
        logger.error(f"Document summary failed: {e}")
        return f"Error al generar resumen: {str(e)}"


async def structural_query(
    query: str,
    max_results: int = 100,
    tenant_id: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Execute structural query using FalkorDB graph.

    Use this for:
    - Counting documents/folders by criteria (year, type, client)
    - Listing documents with filters (date range, document type)
    - Checking existence of documents
    - Navigating folder structure

    The query is processed by the SIL engine which routes to:
    - GRAPH_ONLY: Pure structural queries (fast, no content reading)
    - VECTOR_ONLY: Semantic content search
    - HYBRID: Combination when both structure and content needed

    Examples:
    - "¿Cuántos expedientes tengo del año 2006?"
    - "Lista todos los contratos de ACME"
    - "¿Tengo facturas de más de 10.000€?"
    - "Documentos creados en el último mes"

    Returns:
        Dict with 'response' (str) and 'reasoning_steps' (list) for traceability
    """
    from ...reasoning_tracker import ReasoningTracker, StepType

    start_time = time.time()

    # Get or create tracker for dynamic step registration
    tracker = ReasoningTracker.get_current()
    tracker.set_source("structural_query")

    # Step 1: Query analysis
    tracker.add_step(
        StepType.QUERY_ANALYSIS,
        f"Analizando consulta: '{query[:60]}...'"
    )

    # Traceability: Log decision to use structural query
    logger.info(
        f"🔍 STRUCTURAL_QUERY: Starting | "
        f"tenant={tenant_id} | query='{query[:80]}...' | max_results={max_results}"
    )

    try:
        from app.services.tenant_knowledge_service import tenant_knowledge_service

        # Step 2: Routing to graph
        tracker.add_connector_step(
            "FalkorDB",
            "conectando",
            "base de datos de grafos"
        )

        # Initialize FalkorDB connection
        await tenant_knowledge_service.initialize()

        # Step 3: Route determination - always GRAPH_ONLY (direct FalkorDB)
        tracker.add_step(
            StepType.ROUTING,
            "Ruta: GRAPH_ONLY - Consulta directa al grafo FalkorDB (rápido, sin leer contenido)",
            confidence=0.95
        )

        # Gather data from FalkorDB graph
        totals = await tenant_knowledge_service.get_totals(tenant_id)
        type_counts = await tenant_knowledge_service.get_document_type_counts(tenant_id)
        top_folders = await tenant_knowledge_service.get_top_folders(tenant_id)
        toon_context = await tenant_knowledge_service.build_toon_context(tenant_id)

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"📊 STRUCTURAL_QUERY: Completed | "
            f"route=GRAPH_ONLY | totals={totals} | "
            f"latency={latency_ms:.1f}ms"
        )

        # Step 4: Data extraction
        entities_found = []
        if totals.get("documents", 0) > 0:
            entities_found.append(f"{totals['documents']} documentos")
        if totals.get("folders", 0) > 0:
            entities_found.append(f"{totals['folders']} carpetas/expedientes")
        if type_counts:
            entities_found.append(f"{len(type_counts)} tipos de documento")

        tracker.add_step(
            StepType.DATA_EXTRACTION,
            f"Datos extraídos: {', '.join(entities_found) if entities_found else 'sin resultados'}",
            entities=entities_found,
            confidence=0.95
        )

        # Build response with graph data
        response_parts = []
        response_parts.append("📈 **Consulta estructural** (vía GRAPH_ONLY)\n")

        # Add TOON context (formatted summary for LLM)
        context_text = toon_context.get("context_for_llm", "")
        if context_text:
            response_parts.append(context_text)

        # Add totals
        if totals:
            response_parts.append(f"\n**Total documentos**: {totals.get('documents', 0)}")
            response_parts.append(f"**Total carpetas**: {totals.get('folders', 0)}")

        # Add type breakdown
        if type_counts:
            response_parts.append(f"\n**Por tipo de documento** ({len(type_counts)}):")
            for doc_type, count in list(type_counts.items())[:10]:
                response_parts.append(f"- {doc_type}: {count}")

        # Add top folders
        if top_folders:
            response_parts.append(f"\n**Carpetas principales** ({len(top_folders)}):")
            for i, folder in enumerate(top_folders[:10], 1):
                name = folder.get("name", "Sin nombre")
                folder_type = folder.get("folder_type", "")
                doc_count = folder.get("doc_count", "")
                detail = f"{i}. {name}"
                if folder_type:
                    detail += f" [{folder_type}]"
                if doc_count:
                    detail += f" ({doc_count} documentos)"
                response_parts.append(detail)

        response_parts.append(f"\n*Confianza: 95% | Tiempo: {latency_ms:.0f}ms*")

        # Step 5: Response generation
        tracker.add_step(
            StepType.RESPONSE,
            f"Respuesta generada en {latency_ms:.0f}ms"
        )

        return {
            "response": "\n".join(response_parts),
            "reasoning_steps": tracker.get_steps(),
        }

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(
            f"❌ STRUCTURAL_QUERY: Exception | "
            f"error={str(e)} | latency={latency_ms:.1f}ms",
            exc_info=True
        )
        tracker.add_error_step(str(e))
        return {
            "response": f"Error en consulta estructural: {str(e)}",
            "reasoning_steps": tracker.get_steps(),
        }


# Create LangChain tools
# Note: We'll add context (tenant_id, user_id) at execution time
general_tools = [
    StructuredTool.from_function(
        coroutine=structural_query,
        name="structural_query",
        description=(
            "Query document structure using FalkorDB graph. "
            "USE THIS FIRST for counting, listing, or filtering queries. "
            "Examples: '¿Cuántos expedientes tengo del año 2006?', "
            "'Lista todos los contratos de ACME', 'Documentos del último mes'"
        ),
        args_schema=StructuralQueryInput,
    ),
    StructuredTool.from_function(
        coroutine=document_search,
        name="document_search",
        description=(
            "Search for documents by content using semantic, keyword, or hybrid search. "
            "Use for content-based queries, NOT for counting or listing."
        ),
        args_schema=DocumentSearchInput,
    ),
    StructuredTool.from_function(
        coroutine=document_summary,
        name="document_summary",
        description="Generate a summary of a specific document (concise, detailed, or key points)",
        args_schema=DocumentSummaryInput,
    ),
]

# Track tools that require context injection (tenant_id, user_id)
# Using a set of tool names instead of modifying StructuredTool objects
CONTEXT_REQUIRED_TOOLS = {"structural_query", "document_search", "document_summary"}


async def general_node(state: RAGState) -> Dict[str, Any]:
    """
    General fallback agent node.

    Handles non-specialized queries including:
    - Document search and retrieval
    - Summarization
    - Structural navigation
    - Cross-domain questions

    Args:
        state: Current RAG state

    Returns:
        State updates with general agent results
    """
    return await create_specialist_node(
        agent_name="general_agent",
        system_prompt=GENERAL_SYSTEM_PROMPT,
        tools=general_tools,
        state=state,
    )
