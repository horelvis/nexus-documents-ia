"""
Emma ReAct Agent — Web Search Tool

Wraps the existing WebSearchClient (Tavily → DuckDuckGo fallback)
for internet queries when internal sources are insufficient.

This tool is conditionally available — only when web_search_enabled=True
in the request features.
"""

import logging
from typing import Any, Dict, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    """Input for web search."""
    query: str = Field(
        description="Consulta de búsqueda en internet. "
        "Sé específico y usa términos clave relevantes."
    )
    max_results: int = Field(
        default=5,
        description="Número máximo de resultados (1-10).",
        ge=1, le=10,
    )


class WebSearchTool(EmmaTool):
    """Search the internet for external information."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Busca información en internet. Usa esto cuando las fuentes internas "
            "(documentos del usuario, legislación) no son suficientes, o para "
            "información actual: noticias, clima, datos públicos, etc."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return WebSearchInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.services.web_search import get_web_search_client

        query = arguments["query"]
        max_results = arguments.get("max_results", 5)

        client = get_web_search_client()

        if not client.enabled:
            return ToolResult.from_error(
                "La búsqueda web no está habilitada en este entorno.",
                suggestion="Usa smart_search para buscar en documentos y legislación.",
            )

        try:
            results = await client.search(query=query, max_results=max_results)
        except Exception as e:
            logger.error(f"web_search failed: {e}")
            return ToolResult.from_error(
                f"Error en búsqueda web: {e}",
                suggestion="Intenta reformular la consulta.",
            )

        if not results:
            return ToolResult(
                output=f"No se encontraron resultados web para: '{query}'",
                sources=[],
            )

        lines = [f"Resultados web para '{query}':\n"]
        sources = []

        for i, r in enumerate(results, 1):
            lines.append(f"**{i}. {r.title}**")
            lines.append(f"   URL: {r.url}")
            snippet = r.snippet or r.content or ""
            if snippet:
                lines.append(f"   {snippet[:400]}")
            lines.append("")

            sources.append({
                "title": r.title,
                "url": r.url,
                "type": "web",
            })

        return ToolResult(
            output="\n".join(lines),
            sources=sources,
            data={"result_count": len(results)},
        )
