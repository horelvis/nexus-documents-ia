"""
Tenant Knowledge Service

Thin wrapper that queries SIL Graph directly for tenant-specific terminology.
NO data duplication - SIL is the single source of truth.

When Emma needs to know if "expediente" is a folder or document,
she queries SIL directly instead of maintaining a separate cache.
"""
import logging
from typing import Dict, List, Optional, Set

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
                SELECT * FROM cypher('knowledge_graph', $$
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
                SELECT * FROM cypher('knowledge_graph', $$
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
        Note: Apache AGE doesn't support DISTINCT with aggregates in the same query,
        so we get all folder_types and count in Python.
        """
        try:
            graph = await self._get_graph()
            # AGE-compatible: just get folder_types, count in Python
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('knowledge_graph', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    WHERE f.folder_type IS NOT NULL
                    RETURN f.folder_type as folder_type
                $$) as (folder_type agtype)
                """
            )
            # Count occurrences in Python
            type_counts: Dict[str, int] = {}
            for row in result:
                ft = str(row['folder_type']).strip('"') if row['folder_type'] else None
                if ft and ft != 'null':
                    type_counts[ft] = type_counts.get(ft, 0) + 1

            # Sort by count descending and return top types
            sorted_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
            return sorted_types[:limit]
        except Exception as e:
            logger.debug(f"get_container_types query failed: {e}")
        return []

    async def get_document_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        """
        Get distinct document types for this tenant.

        Queries SIL Graph directly.
        Note: Apache AGE doesn't support DISTINCT with aggregates in the same query,
        so we get all doc_types and count in Python.
        """
        try:
            graph = await self._get_graph()
            # AGE-compatible: just get doc_types, count in Python
            result = await graph.execute_cypher(
                f"""
                SELECT * FROM cypher('knowledge_graph', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE d.semantic_type IS NOT NULL
                    RETURN d.semantic_type as doc_type
                $$) as (doc_type agtype)
                """
            )
            # Count occurrences in Python
            type_counts: Dict[str, int] = {}
            for row in result:
                dt = str(row['doc_type']).strip('"') if row['doc_type'] else None
                if dt and dt != 'null':
                    type_counts[dt] = type_counts.get(dt, 0) + 1

            # Sort by count descending and return top types
            sorted_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
            return sorted_types[:limit]
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
                SELECT * FROM cypher('knowledge_graph', $$
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

    async def get_primary_container_terminology(
        self,
        tenant_id: str
    ) -> tuple[str, str]:
        """
        Get the most common container terminology for this tenant.

        Learns from the actual data what the tenant calls their containers:
        - Law firm: "expediente/expedientes"
        - Consulting: "proyecto/proyectos"
        - Commercial: "cliente/clientes"

        Returns:
            Tuple of (singular, plural) terms. Defaults to ("carpeta", "carpetas")
        """
        try:
            container_types = await self.get_container_types(tenant_id, limit=5)

            if container_types:
                # Get the most common type
                primary_type = container_types[0].lower()

                # Map to proper singular/plural
                type_mapping = {
                    # Spanish terms
                    "case": ("expediente", "expedientes"),
                    "expediente": ("expediente", "expedientes"),
                    "expedientes": ("expediente", "expedientes"),
                    "project": ("proyecto", "proyectos"),
                    "proyecto": ("proyecto", "proyectos"),
                    "proyectos": ("proyecto", "proyectos"),
                    "client": ("cliente", "clientes"),
                    "cliente": ("cliente", "clientes"),
                    "clientes": ("cliente", "clientes"),
                    "client_folder": ("cliente", "clientes"),
                    "obra": ("obra", "obras"),
                    "obras": ("obra", "obras"),
                    "paciente": ("paciente", "pacientes"),
                    "pacientes": ("paciente", "pacientes"),
                    "caso": ("caso", "casos"),
                    "casos": ("caso", "casos"),
                    "legajo": ("legajo", "legajos"),
                    "legajos": ("legajo", "legajos"),
                    # English terms
                    "folder": ("carpeta", "carpetas"),
                    "folders": ("carpeta", "carpetas"),
                    "general": ("carpeta", "carpetas"),
                    "year": ("año", "años"),
                }

                if primary_type in type_mapping:
                    return type_mapping[primary_type]

                # If not in mapping, try to infer plural
                if primary_type.endswith("s"):
                    singular = primary_type[:-1]
                    return (singular, primary_type)
                else:
                    plural = primary_type + "s"
                    return (primary_type, plural)

        except Exception as e:
            logger.debug(f"get_primary_container_terminology failed: {e}")

        return ("carpeta", "carpetas")

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
