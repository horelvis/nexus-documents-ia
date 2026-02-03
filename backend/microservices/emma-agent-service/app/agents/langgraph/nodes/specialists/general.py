"""
General Agent Node

Fallback agent for non-specialized queries.
Handles general document search, analysis, and Q&A.

Domain Coverage:
- General document search and retrieval
- Document summarization
- Structural queries (counting, listing, filtering via Apache AGE graph)
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
from app.clients import get_knowledge_tree_client
from app.clients.weaviate_client import get_weaviate_client
from app.clients.weaviate_client import StructuralQueryResult
from app.core.execution_context import get_tenant_id_or_raise, get_user_id, resolve_document_id
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
5. **Búsqueda web**: Para información externa o verificación de hechos usa `web_search`

Directrices:
- **IMPORTANTE**: Para preguntas de CONTEO o LISTADO, usa SIEMPRE `structural_query` primero
- **IMPORTANTE**: Si el usuario pide RESUMIR, ANALIZAR o EXPLICAR un documento y el contexto incluye `document_id`, SIEMPRE llama a `document_summary` con ese document_id. NUNCA pidas el ID al usuario si ya está en el contexto. NUNCA intentes resumir con los fragmentos del contexto — usa el tool que tiene acceso al documento completo.
- Si el contexto incluye `indexed_document_ids`, usa esos IDs directamente para `document_summary` sin pedirlos de nuevo
- Si el contexto incluye texto de documentos subidos (no indexados), responde con ese contenido y NO llames a herramientas
- Responde siempre basándote en los documentos del usuario, no en conocimiento general
- Si no encuentras información relevante, indícalo claramente
- Si los documentos internos no contienen la respuesta, puedes complementar con búsqueda web usando `web_search`
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


class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(description="Search query for the web")
    max_results: int = Field(default=5, description="Maximum number of results to return")


class StructuralQueryInput(BaseModel):
    """Input for structural queries using Apache AGE graph."""
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
) -> str:
    """
    Search for documents in the user's repository.

    Uses hybrid search combining semantic (meaning-based)
    and keyword (exact match) approaches.
    """
    try:
        tenant_id = get_tenant_id_or_raise()
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
) -> str:
    """
    Generate an LLM-powered summary of a document.

    Retrieves the document content and uses the LLM to produce
    a real summary (concise, detailed, or key_points).
    """
    try:
        tenant_id = get_tenant_id_or_raise()
        document_id = resolve_document_id(document_id) or document_id
        weaviate_client = get_weaviate_client()

        # Get document content via HTTP
        doc_content = await weaviate_client.get_document_content(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        if not doc_content or "error" in doc_content:
            return f"No se pudo obtener el contenido del documento: {document_id}"

        content = doc_content.get("content", "")
        title = doc_content.get("title", "Documento")

        if not content.strip():
            return f"El documento '{title}' no tiene contenido de texto extraído."

        # Truncate content to fit in LLM context (keep ~12K chars max)
        max_content = 12000
        if len(content) > max_content:
            content = content[:max_content] + "\n\n[... contenido truncado por longitud ...]"

        # Build summary prompt based on type
        summary_instructions = {
            "concise": (
                "Genera un resumen conciso (200-400 palabras) del documento. "
                "Incluye los puntos más importantes, las partes involucradas, "
                "fechas relevantes y conclusiones clave."
            ),
            "detailed": (
                "Genera un resumen detallado y completo del documento. "
                "Cubre todas las secciones principales, cláusulas relevantes, "
                "obligaciones de las partes, plazos, condiciones y cualquier "
                "aspecto notable. Usa entre 400-800 palabras."
            ),
            "key_points": (
                "Extrae los puntos clave del documento en formato de lista. "
                "Incluye: partes involucradas, objeto del documento, "
                "obligaciones principales, fechas/plazos, condiciones especiales "
                "y cualquier cláusula destacable. Usa viñetas (•)."
            ),
        }

        instruction = summary_instructions.get(summary_type, summary_instructions["concise"])

        system_prompt = (
            "Eres Emma, asistente de IA experta en análisis documental. "
            "Genera resúmenes precisos basándote SOLO en el contenido proporcionado. "
            "No inventes información. Responde siempre en español."
        )
        user_prompt = (
            f"{instruction}\n\n"
            f"Título del documento: {title}\n\n"
            f"Contenido del documento:\n{content}"
        )

        # Generate summary with LLM
        from app.agents.llm_client import get_llm_client

        llm_client = await get_llm_client()
        response = await llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
            enable_thinking=False,
        )

        if response and response.content:
            summary = response.content.strip()
            return f"**Resumen de**: {title}\n\n{summary}"

        # Fallback: return beginning of content if LLM fails
        logger.warning("LLM summary returned empty, falling back to truncation")
        fallback = content[:2000] + ("..." if len(content) > 2000 else "")
        return f"**Resumen de**: {title}\n\n{fallback}"

    except Exception as e:
        logger.error(f"Document summary failed: {e}")
        return f"Error al generar resumen: {str(e)}"


async def structural_query(
    query: str,
    max_results: int = 100,
) -> Dict[str, Any]:
    """
    Execute structural query using Apache AGE graph.

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

    tenant_id = get_tenant_id_or_raise()
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
        from app.clients import get_knowledge_tree_client

        knowledge_tree_client = get_knowledge_tree_client()

        # Step 2: Routing to graph
        tracker.add_connector_step(
            "Apache AGE",
            "conectando",
            "base de datos de grafos"
        )

        # Execute structural query via Apache AGE
        response = await knowledge_tree_client.structural_query(
            tenant_id=tenant_id,
            query=query,
            max_results=max_results,
        )

        result = StructuralQueryResult(
            route=response.get("route", "ERROR"),
            confidence=response.get("confidence", 0.0),
            context=response.get("context", ""),
            data=response.get("data", {}) or {},
        )

        latency_ms = (time.time() - start_time) * 1000

        # Step 3: Route determination
        route_descriptions = {
            "GRAPH_ONLY": "Consulta solo en el grafo estructural (rápido, sin leer contenido)",
            "VECTOR_ONLY": "Búsqueda semántica de contenido",
            "HYBRID": "Combinación de estructura + contenido",
        }
        tracker.add_step(
            StepType.ROUTING,
            f"Ruta seleccionada: {result.route} - {route_descriptions.get(result.route, 'Desconocido')}",
            confidence=result.confidence
        )

        # Traceability: Log the routing decision and result
        logger.info(
            f"📊 STRUCTURAL_QUERY: Completed | "
            f"route={result.route} | confidence={result.confidence:.2f} | "
            f"latency={latency_ms:.1f}ms"
        )

        # Handle error route
        if result.route == "ERROR":
            error_msg = result.data.get("error", "Unknown error")
            logger.error(f"❌ STRUCTURAL_QUERY: Error | {error_msg}")
            tracker.add_error_step(error_msg)
            return {
                "response": f"Error en consulta estructural: {error_msg}",
                "reasoning_steps": tracker.get_steps(),
            }

        # Step 4: Data extraction
        data = result.data
        entities_found = []

        if data:
            entities = data.get("entities", [])
            if entities:
                entities_found.extend(entities)
            else:
                totals = data.get("totals", {})
                if totals.get("documents", 0):
                    entities_found.append(f"{totals['documents']} documentos")
                if totals.get("folders", 0):
                    entities_found.append(f"{totals['folders']} carpetas")
                document_type_counts = data.get("document_type_counts", data.get("type_counts", {}))
                if document_type_counts:
                    entities_found.append(f"{len(document_type_counts)} tipos de documento")
                container_type_counts = data.get("container_type_counts", {})
                if container_type_counts:
                    entities_found.append(f"{len(container_type_counts)} tipos de carpeta")

        tracker.add_step(
            StepType.DATA_EXTRACTION,
            f"Datos extraídos: {', '.join(entities_found) if entities_found else 'sin resultados'}",
            entities=entities_found,
            confidence=result.confidence
        )

        # Format response based on route type
        response_parts = []

        # Add route info for traceability
        route_emoji = {
            "GRAPH_ONLY": "📈",
            "VECTOR_ONLY": "🔎",
            "HYBRID": "🔀"
        }.get(result.route, "❓")

        response_parts.append(
            f"{route_emoji} **Consulta estructural** (vía {result.route})\n"
        )

        # Add context/answer
        if result.context:
            response_parts.append(result.context)

        # Add data details if available
        if data:
            if "count" in data:
                year = data.get("year")
                matched_type = data.get("matched_type")
                count_type = data.get("count_type")
                if year and matched_type:
                    response_parts.append(f"\n**Total {matched_type} en {year}**: {data['count']}")
                elif year and count_type:
                    response_parts.append(f"\n**Total {count_type} en {year}**: {data['count']}")
                else:
                    response_parts.append(f"\n**Total encontrado**: {data['count']}")

            if "documents" in data and isinstance(data["documents"], list):
                docs = data["documents"]
                if docs:
                    response_parts.append(f"\n**Documentos** ({len(docs)}):")
                    for i, doc in enumerate(docs[:10], 1):
                        title = doc.get("title", doc.get("name", "Sin título"))
                        doc_type = doc.get("type", doc.get("document_type", ""))
                        date = doc.get("date", doc.get("created_at", ""))

                        detail = f"{i}. {title}"
                        if doc_type:
                            detail += f" [{doc_type}]"
                        if date:
                            detail += f" ({date})"
                        response_parts.append(detail)

                    if len(docs) > 10:
                        response_parts.append(f"... y {len(docs) - 10} más")

            if "folders" in data and isinstance(data["folders"], list):
                folders = data["folders"]
                if folders:
                    response_parts.append(f"\n**Carpetas/Expedientes** ({len(folders)}):")
                    for i, folder in enumerate(folders[:10], 1):
                        name = folder.get("name", folder.get("title", "Sin nombre"))
                        count = folder.get("document_count", folder.get("count", ""))

                        detail = f"{i}. {name}"
                        if count:
                            detail += f" ({count} documentos)"
                        response_parts.append(detail)

                    if len(folders) > 10:
                        response_parts.append(f"... y {len(folders) - 10} más")

        # Add confidence for transparency
        response_parts.append(f"\n*Confianza: {result.confidence:.0%} | Tiempo: {latency_ms:.0f}ms*")

        # Step 5: Response generation
        tracker.add_step(
            StepType.RESPONSE,
            f"Respuesta generada en {latency_ms:.0f}ms"
        )

        response_text = "\n".join(response_parts)

        # Always pass structural data through LLM for natural response
        # GRAPH_ONLY enriches context; the LLM formulates the final answer
        try:
            from app.agents.llm_client import get_llm_client
            from app.agents.dynamic_prompt_loader import DynamicPromptLoader

            loader = DynamicPromptLoader()
            yaml_config = loader._load_yaml()
            synthesis_config = yaml_config.get("structural_synthesis", {})

            system_prompt = synthesis_config.get("system", "Eres Emma. Responde SOLO con los datos proporcionados.")
            user_template = synthesis_config.get("user_template", "Consulta: {query}\nDatos:\n{structural_data}")
            user_prompt = user_template.format(query=query, structural_data=response_text)

            llm_client = await get_llm_client()
            llm_response = await llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=500,
                enable_thinking=False,
            )
            if llm_response and llm_response.content:
                response_text = llm_response.content.strip()
        except Exception as e:
            logger.warning(f"LLM synthesis for structural data failed, using raw format: {e}")

        return {
            "response": response_text,
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
            "Query document structure using Apache AGE graph. "
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


# Web Search Tool
async def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the internet using DuckDuckGo.

    Use this for external information, current events, or facts
    not found in internal documents.
    """
    try:
        from app.services.web_search import get_web_search_client

        client = get_web_search_client()
        results = await client.search(query, max_results)

        if not results:
            return f"No se encontraron resultados web para: '{query}'"

        formatted = [f"**Resultados web para**: '{query}'\n"]
        for i, r in enumerate(results, 1):
            formatted.append(
                f"{i}. **{r.title}**\n"
                f"   {r.snippet}\n"
                f"   Fuente: {r.url}\n"
            )
        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"Web search tool failed: {e}")
        return f"Error en búsqueda web: {str(e)}"


general_tools.append(
    StructuredTool.from_function(
        coroutine=web_search,
        name="web_search",
        description=(
            "Search the internet for external information, current events, "
            "or facts not found in internal documents. "
            "Use when internal documents don't have the answer."
        ),
        args_schema=WebSearchInput,
    )
)

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
    metadata = state.get("metadata", {})
    doc_id = metadata.get("document_id")
    uploaded_texts = metadata.get("uploaded_texts") or []
    uploaded_file_ids = metadata.get("uploaded_file_ids") or []

    logger.info(
        f"📋 general_node: document_id={doc_id}, "
        f"uploaded_texts={len(uploaded_texts)}, "
        f"uploaded_file_ids={len(uploaded_file_ids)}, "
        f"is_structural={metadata.get('is_structural_query', False)}"
    )

    if metadata.get("is_structural_query"):
        start_time = time.time()
        query = state.get("query", "")
        result = await structural_query(
            query=query,
            max_results=100,
        )
        latency_ms = (time.time() - start_time) * 1000
        agent_results = dict(state.get("agent_results", {}))
        agent_results["general_agent"] = {
            "agent": "general_agent",
            "output": result.get("response", ""),
            "tools_used": ["structural_query"],
            "sources": [],
            "error": None,
            "latency_ms": latency_ms,
            "reasoning_steps": result.get("reasoning_steps", []),
        }
        return {
            "agent_results": agent_results,
            "current_agent": "general_agent",
            "current_agent_index": state.get("current_agent_index", 0) + 1,
            "metadata": {
                **state.get("metadata", {}),
                "general_agent_latency_ms": latency_ms,
                "general_agent_reasoning_steps": result.get("reasoning_steps", []),
                "structural_query_short_circuit": True,
            },
        }

    # =====================================================================
    # Short-circuit: Document analysis when document_id is attached
    # =====================================================================
    # If the user attached a document, they want something done with it.
    # Small LLMs (Qwen3-4B) often skip tool calls and respond with partial
    # chunks or ask the user for the ID. We short-circuit: if there's a
    # document_id, call document_summary directly with the full content.
    if doc_id:
        start_time = time.time()
        logger.info(f"📄 Summary short-circuit: document_id={doc_id}")
        summary_result = await document_summary(
            document_id=doc_id,
            summary_type="detailed",
        )
        latency_ms = (time.time() - start_time) * 1000
        agent_results = dict(state.get("agent_results", {}))
        agent_results["general_agent"] = {
            "agent": "general_agent",
            "output": summary_result,
            "tools_used": ["document_summary"],
            "sources": [],
            "error": None,
            "latency_ms": latency_ms,
            "reasoning_steps": [],
        }
        return {
            "agent_results": agent_results,
            "current_agent": "general_agent",
            "current_agent_index": state.get("current_agent_index", 0) + 1,
            "metadata": {
                **metadata,
                "general_agent_latency_ms": latency_ms,
                "summary_short_circuit": True,
            },
        }

    # =====================================================================
    # Short-circuit: Uploaded local documents (text already extracted)
    # =====================================================================
    if uploaded_texts:
        start_time = time.time()
        # Build content from all uploaded files
        content_parts = []
        for item in uploaded_texts:
            fname = item.get("filename", "documento")
            text = item.get("text", "")
            if text:
                content_parts.append(f"=== {fname} ===\n{text}")

        if content_parts:
            combined = "\n\n".join(content_parts)
            # Truncate to fit LLM context
            if len(combined) > 12000:
                combined = combined[:12000] + "\n\n[... contenido truncado por longitud ...]"

            logger.info(f"📄 Upload short-circuit: {len(uploaded_texts)} file(s), {len(combined)} chars")

            from app.agents.llm_client import get_llm_client

            query = state.get("query", "")
            llm_client = await get_llm_client()
            response = await llm_client.chat(
                messages=[
                    {"role": "system", "content": (
                        "Eres Emma, asistente de IA experta en análisis documental. "
                        "El usuario ha subido documento(s) local(es). El texto ya fue extraído. "
                        "Responde la consulta del usuario basándote SOLO en el contenido proporcionado. "
                        "No inventes información. Responde siempre en español."
                    )},
                    {"role": "user", "content": (
                        f"Consulta: {query}\n\n"
                        f"Contenido de los documentos:\n{combined}"
                    )},
                ],
                temperature=0.3,
                max_tokens=2000,
                enable_thinking=False,
            )

            output = response.content.strip() if response and response.content else "No se pudo generar una respuesta."
            latency_ms = (time.time() - start_time) * 1000

            agent_results = dict(state.get("agent_results", {}))
            agent_results["general_agent"] = {
                "agent": "general_agent",
                "output": output,
                "tools_used": ["uploaded_content_analysis"],
                "sources": [item.get("filename", "") for item in uploaded_texts],
                "error": None,
                "latency_ms": latency_ms,
                "reasoning_steps": [],
            }
            return {
                "agent_results": agent_results,
                "current_agent": "general_agent",
                "current_agent_index": state.get("current_agent_index", 0) + 1,
                "metadata": {
                    **metadata,
                    "general_agent_latency_ms": latency_ms,
                    "upload_short_circuit": True,
                },
            }

    # =====================================================================
    # Knowledge queries: NO tools — the model answers with its parametric
    # knowledge + retrieved docs context. Tools confuse small models (7B)
    # which emit <tool_call> text instead of answering directly.
    #
    # NOTE: Social channel queries now use dedicated social_agent (see plan.py)
    # =====================================================================
    return await create_specialist_node(
        agent_name="general_agent",
        system_prompt=GENERAL_SYSTEM_PROMPT,
        tools=[],
        state=state,
    )
