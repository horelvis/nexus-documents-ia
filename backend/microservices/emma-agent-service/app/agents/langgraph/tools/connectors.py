"""
Emma ReAct Agent — Query Connector Tool

Allows live queries to external connectors (SharePoint, Alfresco,
Google Drive, etc.) when indexed documents don't have the answer.

The agent's reasoning flow:
1. smart_search → no results
2. list_sources → discovers active connectors
3. query_connector → live query to external system

This tool is conditionally available based on tenant configuration.
"""

import logging
from typing import Any, Dict, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class QueryConnectorInput(BaseModel):
    """Input for live connector query."""
    connector_id: str = Field(
        description="ID del conector a consultar. Obtén el ID desde list_sources."
    )
    query: str = Field(
        description="Consulta en lenguaje natural para el conector externo."
    )


class QueryConnectorTool(EmmaTool):
    """Query an external connector in real-time (fallback for unindexed data)."""

    @property
    def name(self) -> str:
        return "query_connector"

    @property
    def description(self) -> str:
        return (
            "Consulta un conector externo en tiempo real (SharePoint, Alfresco, "
            "Google Drive). Usa esto como fallback cuando smart_search no "
            "encuentra resultados y sabes que hay conectores activos."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return QueryConnectorInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        tenant_id = context.get("tenant_id", "")
        if not tenant_id:
            return ToolResult.from_error("No tenant_id in context")

        connector_id = arguments["connector_id"]
        query = arguments["query"]

        # Try to use the existing connector infrastructure
        try:
            from app.agents.langgraph.connectors.connector_manager import get_connector_manager
            manager = get_connector_manager()
            result = await manager.query_connector(
                tenant_id=tenant_id,
                connector_id=connector_id,
                query=query,
            )
        except ImportError:
            logger.debug("Connector manager not available")
            return ToolResult.from_error(
                "El sistema de conectores no está disponible en este entorno.",
                suggestion="Usa smart_search para buscar en documentos indexados.",
            )
        except Exception as e:
            logger.error(f"query_connector failed: {e}")
            return ToolResult.from_error(
                f"Error consultando conector {connector_id}: {e}",
                suggestion="Verifica el ID del conector o intenta con smart_search.",
            )

        if not result:
            return ToolResult(
                output=f"El conector {connector_id} no devolvió resultados para: '{query}'",
                sources=[],
            )

        # Format results
        if isinstance(result, dict):
            items = result.get("items", result.get("results", []))
            if items and isinstance(items, list):
                lines = [f"Resultados del conector ({len(items)}):\n"]
                sources = []
                for i, item in enumerate(items[:10], 1):
                    if isinstance(item, dict):
                        title = item.get("title", item.get("name", f"Resultado {i}"))
                        content = item.get("content", item.get("snippet", ""))[:400]
                        lines.append(f"**{i}. {title}**")
                        if content:
                            lines.append(f"   {content}")
                        lines.append("")
                        sources.append({
                            "title": title,
                            "type": "connector",
                            "connector_id": connector_id,
                        })
                return ToolResult(
                    output="\n".join(lines),
                    sources=sources,
                    data={"connector_id": connector_id, "result_count": len(items)},
                )

            # Single result or unstructured
            return ToolResult(
                output=str(result)[:4000],
                data={"connector_id": connector_id},
            )

        return ToolResult(output=str(result)[:4000])
