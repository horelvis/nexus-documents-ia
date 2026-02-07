"""
Emma ReAct Agent — Graph Tool (structural_query)

Wraps KnowledgeTreeClient for structural queries against Apache AGE:
- Counting documents/entities ("¿cuántos contratos tengo?")
- Listing items ("lista de facturas de 2024")
- Filtering by metadata ("documentos del proyecto ACME")

The Knowledge Tree Service routes queries to GRAPH_ONLY, VECTOR_ONLY,
or HYBRID mode depending on the query type.
"""

import json
import logging
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class StructuralQueryInput(BaseModel):
    """Input for structural/graph queries."""
    query: str = Field(
        description="Consulta estructural en lenguaje natural. "
        "Ejemplos: 'cuántos contratos hay', 'lista de facturas del 2024', "
        "'documentos del proyecto ACME', 'últimos 5 documentos modificados'."
    )
    max_results: int = Field(
        default=20,
        description="Número máximo de resultados (1-100).",
        ge=1, le=100,
    )


class StructuralQueryTool(EmmaTool):
    """Execute structural queries against the knowledge graph (Apache AGE).

    Handles quantitative queries that semantic search can't answer well:
    counts, lists, filters, aggregations, and entity relationships.
    """

    @property
    def name(self) -> str:
        return "structural_query"

    @property
    def description(self) -> str:
        return (
            "Consulta estructural para contar, listar o filtrar documentos y entidades. "
            "Usa esto para preguntas cuantitativas: '¿cuántos contratos?', "
            "'lista de facturas de 2024', 'documentos del proyecto X'. "
            "NO uses para búsqueda de contenido (usa search_documents para eso)."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return StructuralQueryInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.knowledge_tree_client import get_knowledge_tree_client

        tenant_id = context.get("tenant_id", "")
        if not tenant_id:
            return ToolResult.from_error("No tenant_id in context")

        query = arguments["query"]
        max_results = arguments.get("max_results", 20)

        client = get_knowledge_tree_client()

        try:
            result = await client.structural_query(
                tenant_id=tenant_id,
                query=query,
                max_results=max_results,
            )
        except Exception as e:
            logger.error(f"structural_query failed: {e}")
            return ToolResult.from_error(
                f"Error en consulta estructural: {e}",
                suggestion="Intenta reformular la consulta o usa search_documents.",
            )

        if not result or result.get("route") == "ERROR":
            error_msg = result.get("context", "Unknown error") if result else "Empty response"
            return ToolResult.from_error(
                f"No se pudo procesar la consulta estructural: {error_msg}",
                suggestion="Intenta con search_documents para una búsqueda por contenido.",
            )

        # Format result based on route type
        route = result.get("route", "UNKNOWN")
        data = result.get("data", {})
        context_text = result.get("context", "")

        lines = []

        if route == "GRAPH_ONLY":
            # Pure graph query — counts, lists, relationships
            if isinstance(data, dict):
                count = data.get("count") or data.get("total")
                if count is not None:
                    lines.append(f"**Resultado**: {count}")
                items = data.get("items") or data.get("results") or data.get("nodes", [])
                if items and isinstance(items, list):
                    lines.append(f"\n**Elementos encontrados** ({len(items)}):")
                    for i, item in enumerate(items[:max_results], 1):
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("title") or item.get("label", str(item))
                            item_type = item.get("type", "")
                            line = f"  {i}. {name}"
                            if item_type:
                                line += f" ({item_type})"
                            lines.append(line)
                        else:
                            lines.append(f"  {i}. {item}")
            if context_text:
                lines.append(f"\n{context_text}")

        elif route == "HYBRID":
            # Mixed graph + vector results
            if context_text:
                lines.append(context_text)
            if isinstance(data, dict) and data.get("items"):
                lines.append(f"\n**Resultados** ({len(data['items'])}):")
                for i, item in enumerate(data["items"][:max_results], 1):
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("title", str(item))
                        lines.append(f"  {i}. {name}")
                    else:
                        lines.append(f"  {i}. {item}")

        elif route == "VECTOR_ONLY":
            # Fell back to vector search
            if context_text:
                lines.append(context_text)

        # Fallback: just dump what we got
        if not lines:
            if context_text:
                lines.append(context_text)
            elif data:
                lines.append(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
            else:
                lines.append("La consulta no produjo resultados.")

        return ToolResult(
            output="\n".join(lines),
            data={"route": route, "raw_data": data},
        )
