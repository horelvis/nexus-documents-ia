"""
Tenant Knowledge Service

Thin wrapper that queries SIL Graph directly for tenant-specific terminology.
NO data duplication - SIL is the single source of truth.

When Emma needs to know if "expediente" is a folder or document,
she queries SIL directly instead of maintaining a separate cache.
"""
import logging
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class TenantKnowledgeService:
    """
    Queries SIL Graph directly for tenant terminology.
    No caching, no duplication - SIL is the source of truth.
    """

    def __init__(self):
        self._graph = None

    async def _get_graph(self):
        """Lazy load graph service."""
        if self._graph is None:
            from app.services.knowledge.age_graph_service import age_knowledge_graph
            self._graph = age_knowledge_graph
            await self._graph.initialize()
        return self._graph

    async def is_container_term(self, term: str, tenant_id: str) -> bool:
        """
        Check if a term refers to a container/folder in this tenant's data.

        Queries SIL Graph directly.
        """
        try:
            graph = await self._get_graph()
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('sil_graph', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    WHERE toLower(f.name) CONTAINS toLower('{term}')
                       OR toLower(f.folder_type) CONTAINS toLower('{term}')
                    RETURN count(f) as cnt
                $$) as (cnt agtype)
                """
            )
            for row in result:
                cnt = int(str(row['cnt'])) if row['cnt'] else 0
                return cnt > 0
        except Exception as e:
            logger.debug(f"is_container_term query failed: {e}")
        return False

    async def is_document_term(self, term: str, tenant_id: str) -> bool:
        """
        Check if a term refers to a document type in this tenant's data.

        Queries SIL Graph directly.
        """
        try:
            graph = await self._get_graph()
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('sil_graph', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE toLower(d.semantic_type) CONTAINS toLower('{term}')
                       OR toLower(d.document_type) CONTAINS toLower('{term}')
                    RETURN count(d) as cnt
                $$) as (cnt agtype)
                """
            )
            for row in result:
                cnt = int(str(row['cnt'])) if row['cnt'] else 0
                return cnt > 0
        except Exception as e:
            logger.debug(f"is_document_term query failed: {e}")
        return False

    async def get_container_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        """
        Get distinct container/folder types for this tenant.

        Queries SIL Graph directly.
        """
        try:
            graph = await self._get_graph()
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('sil_graph', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    RETURN DISTINCT f.folder_type as folder_type, count(f) as cnt
                    ORDER BY cnt DESC
                    LIMIT {limit}
                $$) as (folder_type agtype, cnt agtype)
                """
            )
            types = []
            for row in result:
                ft = str(row['folder_type']).strip('"') if row['folder_type'] else None
                if ft and ft != 'null':
                    types.append(ft)
            return types
        except Exception as e:
            logger.debug(f"get_container_types query failed: {e}")
        return []

    async def get_document_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        """
        Get distinct document types for this tenant.

        Queries SIL Graph directly.
        """
        try:
            graph = await self._get_graph()
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('sil_graph', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    RETURN DISTINCT d.semantic_type as doc_type, count(d) as cnt
                    ORDER BY cnt DESC
                    LIMIT {limit}
                $$) as (doc_type agtype, cnt agtype)
                """
            )
            types = []
            for row in result:
                dt = str(row['doc_type']).strip('"') if row['doc_type'] else None
                if dt and dt != 'null':
                    types.append(dt)
            return types
        except Exception as e:
            logger.debug(f"get_document_types query failed: {e}")
        return []

    async def get_clients(self, tenant_id: str, limit: int = 50) -> List[str]:
        """
        Get known clients for this tenant.

        Queries SIL Graph directly.
        """
        try:
            graph = await self._get_graph()
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('sil_graph', $$
                    MATCH (c:client {{tenant_id: '{tenant_id}'}})
                    RETURN c.name as name
                    LIMIT {limit}
                $$) as (name agtype)
                """
            )
            clients = []
            for row in result:
                name = str(row['name']).strip('"') if row['name'] else None
                if name and name != 'null':
                    clients.append(name)
            return clients
        except Exception as e:
            logger.debug(f"get_clients query failed: {e}")
        return []

    async def classify_query_target(
        self,
        query: str,
        tenant_id: str
    ) -> str:
        """
        Classify if a query is about folders, documents, or both.

        Returns: "folder", "document", or "both"
        """
        query_lower = query.lower()

        # Get tenant's actual terminology from SIL
        container_types = await self.get_container_types(tenant_id, limit=10)
        document_types = await self.get_document_types(tenant_id, limit=10)

        is_folder = any(ct.lower() in query_lower for ct in container_types)
        is_doc = any(dt.lower() in query_lower for dt in document_types)

        # Also check common patterns
        folder_patterns = ["expediente", "carpeta", "folder", "caso", "case"]
        doc_patterns = ["documento", "document", "archivo", "file", "contrato", "factura"]

        is_folder = is_folder or any(p in query_lower for p in folder_patterns)
        is_doc = is_doc or any(p in query_lower for p in doc_patterns)

        if is_folder and is_doc:
            return "both"
        elif is_folder:
            return "folder"
        else:
            return "document"

    async def get_structural_summary(self, tenant_id: str) -> str:
        """
        Get a brief structural summary for Emma's context.

        This is the ONLY place where we "format" data for prompts,
        but it's a live query, not cached/duplicated data.
        """
        try:
            container_types = await self.get_container_types(tenant_id, limit=5)
            document_types = await self.get_document_types(tenant_id, limit=5)
            clients = await self.get_clients(tenant_id, limit=5)

            if not container_types and not document_types:
                return ""

            lines = ["## Estructura del Tenant (desde SIL)"]

            if container_types:
                lines.append(f"- Tipos de carpeta: {', '.join(container_types)}")
            if document_types:
                lines.append(f"- Tipos de documento: {', '.join(document_types)}")
            if clients:
                lines.append(f"- Clientes: {', '.join(clients)}")

            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"get_structural_summary failed: {e}")
            return ""


# Global singleton
tenant_knowledge_service = TenantKnowledgeService()
