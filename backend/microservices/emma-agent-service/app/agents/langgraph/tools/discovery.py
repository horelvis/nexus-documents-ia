"""
Emma ReAct Agent — List Sources Tool (Discovery)

Enables the agent to discover what data sources are available before
deciding which tools to use. This is especially useful when the agent
doesn't know if the tenant has connectors, legislation, or web search.

Returns:
- Active connectors (type, name, last sync)
- Weaviate collection stats (document count)
- BOE legislation availability
- Web search status
"""

import logging
from typing import Any, Dict, Type

from pydantic import BaseModel

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class ListSourcesInput(BaseModel):
    """No parameters needed — discovers all available sources."""
    pass


class ListSourcesTool(EmmaTool):
    """Discover available data sources for the current tenant."""

    @property
    def name(self) -> str:
        return "list_sources"

    @property
    def description(self) -> str:
        return (
            "Descubre las fuentes de datos disponibles: documentos indexados, "
            "conectores activos (SharePoint, Alfresco, Google Drive), "
            "legislación BOE, y búsqueda web. Usa esto cuando no sepas "
            "qué fuentes tiene el usuario."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return ListSourcesInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.weaviate_client import get_weaviate_client
        from app.services.web_search import get_web_search_client

        tenant_id = context.get("tenant_id", "")
        if not tenant_id:
            return ToolResult.from_error("No tenant_id in context")

        lines = ["**Fuentes de datos disponibles:**\n"]
        data: Dict[str, Any] = {}

        # 1. Tenant document stats
        try:
            client = get_weaviate_client()
            stats = await client.get_tenant_stats(tenant_id=tenant_id)
            doc_count = stats.get("total_documents", stats.get("document_count", 0))
            lines.append(f"📄 **Documentos indexados**: {doc_count}")
            if stats.get("collections"):
                for col in stats["collections"]:
                    col_name = col.get("name", "")
                    col_count = col.get("count", 0)
                    lines.append(f"   - {col_name}: {col_count} documentos")
            data["documents"] = {"count": doc_count, "available": doc_count > 0}
        except Exception as e:
            logger.warning(f"Could not get tenant stats: {e}")
            lines.append("📄 **Documentos**: No se pudo obtener información")
            data["documents"] = {"available": True, "error": str(e)}

        # 2. Legislation (always available if PublicKnowledge exists)
        try:
            pk_results = await client.search_public_knowledge(
                query="legislación",
                limit=1,
            )
            legislation_available = len(pk_results) > 0
            if legislation_available:
                lines.append("⚖️ **Legislación BOE**: Disponible (leyes españolas vigentes)")
            else:
                lines.append("⚖️ **Legislación BOE**: No indexada")
            data["legislation"] = {"available": legislation_available}
        except Exception as e:
            logger.debug(f"PublicKnowledge check failed: {e}")
            lines.append("⚖️ **Legislación BOE**: No disponible")
            data["legislation"] = {"available": False}

        # 3. Web search
        try:
            web_client = get_web_search_client()
            web_enabled = web_client.enabled
            provider = web_client.active_provider if web_enabled else "none"
            if web_enabled:
                lines.append(f"🌐 **Búsqueda web**: Habilitada ({provider})")
            else:
                lines.append("🌐 **Búsqueda web**: No habilitada")
            data["web_search"] = {"available": web_enabled, "provider": provider}
        except Exception:
            lines.append("🌐 **Búsqueda web**: No disponible")
            data["web_search"] = {"available": False}

        # 4. Knowledge Graph
        try:
            from app.clients.knowledge_tree_client import get_knowledge_tree_client
            kt_client = get_knowledge_tree_client()
            summary = await kt_client.get_structural_summary(tenant_id=tenant_id)
            if summary and not summary.get("error"):
                node_count = summary.get("total_nodes", summary.get("node_count", 0))
                lines.append(f"🔗 **Grafo de conocimiento**: {node_count} entidades")
                data["knowledge_graph"] = {"available": True, "node_count": node_count}
            else:
                lines.append("🔗 **Grafo de conocimiento**: Vacío")
                data["knowledge_graph"] = {"available": False}
        except Exception:
            lines.append("🔗 **Grafo de conocimiento**: No disponible")
            data["knowledge_graph"] = {"available": False}

        # 5. Connectors (check via context features)
        features = context.get("features", {})
        if features.get("connectors_enabled"):
            lines.append("🔌 **Conectores externos**: Habilitados (usa query_connector)")
        data["connectors"] = {"available": features.get("connectors_enabled", False)}

        return ToolResult(
            output="\n".join(lines),
            data=data,
        )
