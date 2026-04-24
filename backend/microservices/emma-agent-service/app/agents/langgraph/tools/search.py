"""
Emma ReAct Agent — Search Tools

Wraps existing WeaviateClient for:
- search_documents: Hybrid search in indexed documents
- get_document_content: Read a specific document's full content

These are the most-used tools in the ReAct loop — most queries start
with search_documents before analyzing results.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult, ToolError

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────
# search_documents
# ──────────────────────────────────────────────

class SearchDocumentsInput(BaseModel):
    """Input for document search."""
    query: str = Field(
        description="Consulta de búsqueda en lenguaje natural. "
        "Sé específico: incluye nombres de documentos, fechas o temas clave. "
        "Incluye el tipo de documento en la query (ej: 'factura Movistar', "
        "'contrato laboral', 'nómina enero') — NO uses filtros para tipos semánticos."
    )
    limit: int = Field(
        default=8,
        description="Número máximo de resultados (1-20).",
        ge=1, le=20,
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Filtros exactos opcionales: {tags, folder_path, connector_id}. "
        "IMPORTANTE: NO filtrar por document_type — es el formato de archivo (pdf, docx), "
        "NO el tipo semántico (factura, contrato). Usa la query para buscar por tipo semántico.",
    )


class SearchDocumentsTool(EmmaTool):
    """Hybrid search (semantic + keyword) in indexed documents."""

    @property
    def name(self) -> str:
        return "search_documents"

    @property
    def description(self) -> str:
        return (
            "Busca documentos del usuario por contenido semántico y palabras clave. "
            "Devuelve fragmentos relevantes con puntuación de relevancia. "
            "Usa esto para encontrar contratos, informes, facturas, expedientes, etc."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return SearchDocumentsInput

    # File-format values that are valid for document_type exact filtering
    _VALID_DOC_TYPE_FORMATS = {
        "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
        "txt", "html", "markdown", "csv", "json", "xml", "image",
    }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.weaviate_client import get_weaviate_client

        user_roles = context.get("user_roles", [])
        user_id = context.get("user_id")

        query = arguments["query"]
        limit = arguments.get("limit", 8)
        filters = arguments.get("filters")

        # Guard: drop document_type filter if it's a semantic concept (not a file format)
        # LLMs often confuse "factura" (semantic) with "pdf" (format)
        if filters and "document_type" in filters:
            dt_val = filters["document_type"]
            if isinstance(dt_val, str) and dt_val.lower() not in self._VALID_DOC_TYPE_FORMATS:
                # Fold the semantic type into the query instead of filtering
                query = f"{dt_val} {query}"
                del filters["document_type"]
                logger.info(f"Moved semantic document_type '{dt_val}' from filter to query")
            if not filters:
                filters = None

        client = get_weaviate_client()

        # Use hybrid search for best recall (semantic + BM25)
        alpha = 0.5
        sector_config = context.get("sector_config")
        if sector_config and isinstance(sector_config, dict):
            alpha = sector_config.get("hybrid_alpha", 0.5)

        try:
            results = await client.hybrid_search(
                query=query,
                user_roles=user_roles,
                user_id=user_id,
                limit=limit,
                alpha=alpha,
                filters=filters,
            )
        except Exception as e:
            logger.error(f"search_documents failed: {e}")
            return ToolResult.from_error(
                f"Error buscando documentos: {e}",
                suggestion="Intenta reformular la consulta o reducir los filtros.",
            )

        if not results:
            return ToolResult(
                output=f"No se encontraron documentos para: '{query}'",
                sources=[],
                data={"result_count": 0},
            )

        # Deduplicate: keep only the highest-scoring chunk per document
        seen_doc_ids: Dict[str, Any] = {}
        for r in results:
            doc_id = r.document_id or r.metadata.get("document_id", "")
            if doc_id and doc_id in seen_doc_ids:
                # Keep the one with higher score
                if r.score > seen_doc_ids[doc_id].score:
                    seen_doc_ids[doc_id] = r
            else:
                seen_doc_ids[doc_id or id(r)] = r
        results = sorted(seen_doc_ids.values(), key=lambda r: r.score, reverse=True)

        # Format results for the LLM
        lines = [f"Se encontraron {len(results)} documentos para '{query}':\n"]
        sources = []

        for i, r in enumerate(results, 1):
            title = r.metadata.get("title", r.metadata.get("document_title", "Sin título"))
            doc_id = r.document_id or r.metadata.get("document_id", "")
            score = r.score
            content_preview = r.content[:500] if r.content else ""

            lines.append(f"**{i}. {title}** (relevancia: {score:.2f})")
            if doc_id:
                lines.append(f"   ID: {doc_id}")
            if content_preview:
                lines.append(f"   Contenido: {content_preview}")
            lines.append("")

            sources.append({
                "title": title,
                "document_id": doc_id,
                "score": score,
                "type": "tenant_document",
                "metadata": {
                    k: v for k, v in r.metadata.items()
                    if k in ("document_type", "created_at", "tags", "collection")
                },
            })

        return ToolResult(
            output="\n".join(lines),
            sources=sources,
            data={"result_count": len(results)},
        )


# ──────────────────────────────────────────────
# get_document_content
# ──────────────────────────────────────────────

class GetDocumentContentInput(BaseModel):
    """Input for fetching a specific document's content."""
    document_id: str = Field(
        description=(
            "UUID del documento (formato 8-4-4-4-12, ej. "
            "'48df41b3-2aa7-417a-b08c-81b45d719483'). Nunca pases un nombre "
            "de archivo — obtén el UUID con smart_search primero."
        )
    )
    include_chunks: bool = Field(
        default=False,
        description="Si es True, devuelve todos los chunks individuales del documento.",
    )


class GetDocumentContentTool(EmmaTool):
    """Read a specific document's full content by ID."""

    @property
    def name(self) -> str:
        return "get_document_content"

    @property
    def description(self) -> str:
        return (
            "Lee el contenido completo de un documento específico por su UUID "
            "(formato 8-4-4-4-12). Requiere el UUID exacto, no un nombre de "
            "archivo — úsalo después de smart_search. Útil para análisis "
            "detallado, revisión de contratos, o extracción de datos."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return GetDocumentContentInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.weaviate_client import get_weaviate_client

        user_roles = context.get("user_roles", [])
        user_id = context.get("user_id")

        document_id = arguments["document_id"]
        include_chunks = arguments.get("include_chunks", False)

        # Fast-fail when the LLM passes a filename or other non-UUID token.
        # Without this the request hits Weaviate, gets a 404, and the LLM
        # often re-tries variations before recovering via smart_search —
        # burning seconds of silent SSE on long-running synthesize calls.
        if not _UUID_RE.match(document_id):
            return ToolResult.from_error(
                f"document_id debe ser un UUID (formato 8-4-4-4-12), no '{document_id}'.",
                suggestion=(
                    "Usa smart_search primero con el nombre o descripción del "
                    "documento y obtén el UUID desde el campo 'document_id' "
                    "del resultado."
                ),
            )

        client = get_weaviate_client()

        try:
            doc = await client.get_document_content(
                document_id=document_id,
                user_roles=user_roles,
                user_id=user_id,
                include_chunks=include_chunks,
            )
        except Exception as e:
            logger.error(f"get_document_content failed: {e}")
            return ToolResult.from_error(
                f"Error leyendo documento {document_id}: {e}",
                suggestion="Verifica que el ID del documento es correcto.",
            )

        if not doc or (isinstance(doc, dict) and doc.get("error")):
            return ToolResult.from_error(
                f"Documento no encontrado: {document_id}",
                suggestion="Usa smart_search para buscar el documento correcto.",
            )

        title = doc.get("title", "Sin título")
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})

        # Truncate very long documents to avoid overwhelming the LLM context
        max_content_length = 12000
        truncated = False
        if len(content) > max_content_length:
            content = content[:max_content_length]
            truncated = True

        lines = [f"**Documento: {title}**"]
        if metadata.get("document_type"):
            lines.append(f"Tipo: {metadata['document_type']}")
        if metadata.get("created_at"):
            lines.append(f"Fecha: {metadata['created_at']}")
        lines.append(f"\n{content}")
        if truncated:
            lines.append(
                f"\n[Documento truncado — se muestran {max_content_length} de {doc.get('total_chars', '?')} caracteres. "
                "Usa include_chunks=true para obtener el contenido completo por partes.]"
            )

        # Include chunks if requested
        if include_chunks and doc.get("chunks"):
            lines.append(f"\n--- Chunks ({len(doc['chunks'])}) ---")
            for i, chunk in enumerate(doc["chunks"][:20], 1):  # Max 20 chunks
                chunk_content = chunk.get("content", "")[:2000]
                lines.append(f"\n[Chunk {i}] {chunk_content}")

        return ToolResult(
            output="\n".join(lines),
            sources=[{
                "title": title,
                "document_id": document_id,
                "type": "tenant_document",
                "metadata": metadata,
            }],
            data={"document_id": document_id, "truncated": truncated},
        )
