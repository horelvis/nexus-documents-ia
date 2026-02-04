"""
Tenant Knowledge Service

Queries Apache AGE for tenant-specific structure and terminology.
"""

import logging
from typing import Dict, List, Optional

from app.core.config import settings
from app.services.age_client import age_client

logger = logging.getLogger(__name__)


class TenantKnowledgeService:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await age_client.initialize()
        self._initialized = True

    async def get_container_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    WHERE f.folder_type IS NOT NULL
                    RETURN f.folder_type as folder_type
                $$) as (folder_type agtype)
                """
            )
            type_counts: Dict[str, int] = {}
            for row in result:
                ft = str(row["folder_type"]).strip('"') if row.get("folder_type") else None
                if ft and ft != "null":
                    type_counts[ft] = type_counts.get(ft, 0) + 1
            sorted_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
            return sorted_types[:limit]
        except Exception as e:
            logger.debug(f"get_container_types failed: {e}")
        return []

    async def get_document_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE d.semantic_type IS NOT NULL
                    RETURN d.semantic_type as doc_type
                $$) as (doc_type agtype)
                """
            )
            type_counts: Dict[str, int] = {}
            for row in result:
                dt = str(row["doc_type"]).strip('"') if row.get("doc_type") else None
                if dt and dt != "null":
                    type_counts[dt] = type_counts.get(dt, 0) + 1
            sorted_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
            return sorted_types[:limit]
        except Exception as e:
            logger.debug(f"get_document_types failed: {e}")
        return []

    async def get_container_type_counts(self, tenant_id: str, limit: int = 20) -> Dict[str, int]:
        """Return counts per folder_type."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    WHERE f.folder_type IS NOT NULL
                    RETURN f.folder_type as folder_type
                $$) as (folder_type agtype)
                """
            )
            type_counts: Dict[str, int] = {}
            for row in result:
                ft = str(row["folder_type"]).strip('"') if row.get("folder_type") else None
                if ft and ft != "null":
                    type_counts[ft] = type_counts.get(ft, 0) + 1
            sorted_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
            return {k: type_counts[k] for k in sorted_types[:limit]}
        except Exception as e:
            logger.debug(f"get_container_type_counts failed: {e}")
        return {}

    async def get_document_type_counts(self, tenant_id: str, limit: int = 20) -> Dict[str, int]:
        """Return counts per document semantic_type."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE d.semantic_type IS NOT NULL
                    RETURN d.semantic_type as doc_type
                $$) as (doc_type agtype)
                """
            )
            type_counts: Dict[str, int] = {}
            for row in result:
                dt = str(row["doc_type"]).strip('"') if row.get("doc_type") else None
                if dt and dt != "null":
                    type_counts[dt] = type_counts.get(dt, 0) + 1
            sorted_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
            return {k: type_counts[k] for k in sorted_types[:limit]}
        except Exception as e:
            logger.debug(f"get_document_type_counts failed: {e}")
        return {}

    async def get_totals(self, tenant_id: str) -> Dict[str, int]:
        """Return total counts for folders and documents (separate queries to avoid cartesian product)."""
        folders = 0
        documents = 0
        try:
            await self.initialize()
            f_result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    RETURN count(f) as cnt
                $$) as (cnt agtype)
                """
            )
            if f_result:
                folders = int(str(f_result[0].get("cnt", "0")).strip('"') or 0)

            d_result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    RETURN count(d) as cnt
                $$) as (cnt agtype)
                """
            )
            if d_result:
                documents = int(str(d_result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_totals failed: {e}")
        return {"folders": folders, "documents": documents}

    async def get_document_count_by_year(self, tenant_id: str, year: str) -> int:
        """Count documents where title/path includes the given year."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE (d.title IS NOT NULL AND toString(d.title) CONTAINS '{year}')
                       OR (d.file_path IS NOT NULL AND toString(d.file_path) CONTAINS '{year}')
                       OR (d.folder_path IS NOT NULL AND toString(d.folder_path) CONTAINS '{year}')
                    RETURN count(d) as cnt
                $$) as (cnt agtype)
                """
            )
            if result:
                return int(str(result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_document_count_by_year failed: {e}")
        return 0

    async def get_folder_count_by_year(self, tenant_id: str, year: str) -> int:
        """Count folders where name/path includes the given year."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    WHERE (f.name IS NOT NULL AND toString(f.name) CONTAINS '{year}')
                       OR (f.path IS NOT NULL AND toString(f.path) CONTAINS '{year}')
                    RETURN count(f) as cnt
                $$) as (cnt agtype)
                """
            )
            if result:
                return int(str(result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_folder_count_by_year failed: {e}")
        return 0

    async def get_folder_count_by_year_and_type(self, tenant_id: str, year: str, folder_type: str) -> int:
        """Count folders of a specific type where name/path includes the given year."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}', folder_type: '{folder_type}'}})
                    WHERE (f.name IS NOT NULL AND toString(f.name) CONTAINS '{year}')
                       OR (f.path IS NOT NULL AND toString(f.path) CONTAINS '{year}')
                    RETURN count(f) as cnt
                $$) as (cnt agtype)
                """
            )
            if result:
                return int(str(result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_folder_count_by_year_and_type failed: {e}")
        return 0

    async def get_folder_count_by_year_and_path_segment(self, tenant_id: str, year: str, segment: str) -> int:
        """Count folders where path includes the given year and segment (case-insensitive)."""
        try:
            await self.initialize()
            seg = segment.lower()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    WHERE (
                        f.path IS NOT NULL
                        AND toLower(toString(f.path)) CONTAINS '{seg}'
                        AND toString(f.path) CONTAINS '{year}'
                    )
                    RETURN count(f) as cnt
                $$) as (cnt agtype)
                """
            )
            if result:
                return int(str(result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_folder_count_by_year_and_path_segment failed: {e}")
        return 0

    async def get_document_count_by_year_and_type(self, tenant_id: str, year: str, doc_type: str) -> int:
        """Count documents of a specific type where title/path includes the given year."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE (d.semantic_type = '{doc_type}' OR d.document_type = '{doc_type}')
                      AND (
                        (d.title IS NOT NULL AND toString(d.title) CONTAINS '{year}')
                        OR (d.file_path IS NOT NULL AND toString(d.file_path) CONTAINS '{year}')
                        OR (d.folder_path IS NOT NULL AND toString(d.folder_path) CONTAINS '{year}')
                      )
                    RETURN count(d) as cnt
                $$) as (cnt agtype)
                """
            )
            if result:
                return int(str(result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_document_count_by_year_and_type failed: {e}")
        return 0

    async def get_document_count_by_year_and_path_segment(self, tenant_id: str, year: str, segment: str) -> int:
        """Count documents where folder_path includes the given year and segment (case-insensitive)."""
        try:
            await self.initialize()
            seg = segment.lower()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    WHERE (
                        d.folder_path IS NOT NULL
                        AND toLower(toString(d.folder_path)) CONTAINS '{seg}'
                        AND toString(d.folder_path) CONTAINS '{year}'
                    )
                    RETURN count(d) as cnt
                $$) as (cnt agtype)
                """
            )
            if result:
                return int(str(result[0].get("cnt", "0")).strip('"') or 0)
        except Exception as e:
            logger.debug(f"get_document_count_by_year_and_path_segment failed: {e}")
        return 0

    async def get_clients(self, tenant_id: str, limit: int = 50) -> List[str]:
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (c:client {{tenant_id: '{tenant_id}'}})
                    RETURN c.name as name
                    LIMIT {limit}
                $$) as (name agtype)
                """
            )
            clients = []
            for row in result:
                name = str(row["name"]).strip('"') if row.get("name") else None
                if name and name != "null":
                    clients.append(name)
            return clients
        except Exception as e:
            logger.debug(f"get_clients failed: {e}")
        return []

    async def get_document_ids(self, tenant_id: str, limit: int = 10000) -> List[str]:
        """Return document IDs from the structural graph."""
        try:
            await self.initialize()
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    RETURN d.document_id as document_id
                    LIMIT {limit}
                $$) as (document_id agtype)
                """
            )
            doc_ids = []
            for row in result:
                doc_id = str(row["document_id"]).strip('"') if row.get("document_id") else None
                if doc_id and doc_id != "null":
                    doc_ids.append(doc_id)
            return doc_ids
        except Exception as e:
            logger.debug(f"get_document_ids failed: {e}")
        return []

    async def clear_tenant_graph(self, tenant_id: str) -> bool:
        """Clear structural nodes for a tenant."""
        try:
            await self.initialize()
            await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                    DETACH DELETE d
                $$) as (d agtype)
                """
            )
            await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    DETACH DELETE f
                $$) as (f agtype)
                """
            )
            return True
        except Exception as e:
            logger.debug(f"clear_tenant_graph failed: {e}")
            return False

    async def get_top_folders(self, tenant_id: str, limit: int = 15) -> List[Dict[str, str]]:
        """
        Return top folders with counts when HAS_DOCUMENT edges exist.
        """
        try:
            await self.initialize()
            # Note: Apache AGE doesn't support using aliases in ORDER BY for aggregations
            # Use WITH to project the aggregation result, then ORDER BY the alias
            result = await age_client.execute_cypher(
                f"""
                SELECT * FROM cypher('{settings.age_graph_name}', $$
                    MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                    OPTIONAL MATCH (f)-[:HAS_DOCUMENT]->(d:structural_document {{tenant_id: '{tenant_id}'}})
                    WITH f.name as name, f.folder_type as folder_type, count(d) as doc_count
                    RETURN name, folder_type, doc_count
                    ORDER BY doc_count DESC
                    LIMIT {limit}
                $$) as (name agtype, folder_type agtype, doc_count agtype)
                """
            )
            folders = []
            for row in result:
                name = str(row["name"]).strip('"') if row.get("name") else None
                folder_type = str(row["folder_type"]).strip('"') if row.get("folder_type") else None
                doc_count = str(row["doc_count"]).strip('"') if row.get("doc_count") else "0"
                if name and name != "null":
                    folders.append(
                        {
                            "name": name,
                            "folder_type": folder_type or "",
                            "doc_count": doc_count,
                        }
                    )
            return folders
        except Exception as e:
            logger.debug(f"get_top_folders failed: {e}")
        return []

    async def build_toon_context(self, tenant_id: str, limit: int = 15) -> Dict[str, str]:
        """
        Build a TOON-like context block for LLMs.
        """
        container_types = await self.get_container_types(tenant_id, limit=10)
        document_types = await self.get_document_types(tenant_id, limit=10)
        container_type_counts = await self.get_container_type_counts(tenant_id, limit=10)
        document_type_counts = await self.get_document_type_counts(tenant_id, limit=10)
        totals = await self.get_totals(tenant_id)
        clients = await self.get_clients(tenant_id, limit=10)
        top_folders = await self.get_top_folders(tenant_id, limit=limit)

        parts: List[str] = []
        parts.append("## Knowledge Graph Results\n")

        if totals.get("folders") or totals.get("documents"):
            parts.append(
                f"**Totales:** carpetas={totals.get('folders', 0)}, documentos={totals.get('documents', 0)}"
            )
        if container_types:
            if container_type_counts:
                counts_str = ", ".join(
                    f"{k} ({v})" for k, v in list(container_type_counts.items())
                )
                parts.append(f"**Tipos de carpeta:** {counts_str}")
            else:
                parts.append(f"**Tipos de carpeta:** {', '.join(container_types)}")
        if document_types:
            if document_type_counts:
                counts_str = ", ".join(
                    f"{k} ({v})" for k, v in list(document_type_counts.items())
                )
                parts.append(f"**Tipos de documento:** {counts_str}")
            else:
                parts.append(f"**Tipos de documento:** {', '.join(document_types)}")
        if clients:
            parts.append(f"**Clientes:** {', '.join(clients)}")

        if top_folders:
            parts.append("\n**Carpetas principales:**")
            for i, f in enumerate(top_folders[:10], 1):
                label = f.get("name", "")
                ftype = f.get("folder_type", "")
                count = f.get("doc_count", "0")
                suffix = f" [{ftype}]" if ftype else ""
                parts.append(f"  {i}. {label}{suffix} (docs: {count})")

        return {
            "context_for_llm": "\n".join(parts).strip(),
        }


tenant_knowledge_service = TenantKnowledgeService()
