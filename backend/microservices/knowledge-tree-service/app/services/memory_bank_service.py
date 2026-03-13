"""
Memory Bank Service — MemoRAG-inspired Document Memory Store

Stores compact document "memories" (summaries, key entities, topics) as
DocumentMemory nodes in the Apache AGE sector graph, linked to their
source structural_document via HAS_MEMORY edges.

These memories serve as retrieval clues for the planner model (4B):
instead of searching raw chunks, the planner scans lightweight memory
nodes to decide what documents are relevant, then retrieves full content.

Architecture:
    structural_document -[:HAS_MEMORY]-> DocumentMemory
                                            |
                                            +-- summary (2-3 sentences)
                                            +-- key_entities (JSON array)
                                            +-- key_topics (JSON array)
                                            +-- domain (legal, fiscal, etc.)
                                            +-- semantic_type (factura, contrato, etc.)
                                            +-- memory_version (for re-generation)
                                            +-- created_at (ISO timestamp)

Usage:
    from app.services.memory_bank_service import memory_bank

    await memory_bank.store_memory(
        tenant_id="t1",
        document_id="doc-123",
        summary="Contrato de arrendamiento entre ACME y tenant...",
        key_entities=["ACME Corp", "Juan Garcia"],
        key_topics=["arrendamiento", "local comercial", "fianza"],
        domain="legal",
        semantic_type="contrato",
    )

    memories = await memory_bank.recall(tenant_id="t1", query_topics=["contrato", "arrendamiento"])
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.age_client import age_client

logger = logging.getLogger(__name__)

MEMORY_VERSION = 1


def _escape(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.replace("'", "''")


def _json_escape(items: List[str]) -> str:
    """Escape a list as a JSON string safe for Cypher property."""
    return _escape(json.dumps(items, ensure_ascii=False))


class MemoryBankService:
    """
    CRUD service for DocumentMemory nodes in the sector graph.

    Each document gets at most one memory node (MERGE by document_id).
    Memories are lightweight (~200 tokens) and designed for bulk scan
    by the planner model.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await age_client.initialize()
        self._initialized = True

    async def store_memory(
        self,
        tenant_id: str,
        document_id: str,
        summary: str,
        key_entities: Optional[List[str]] = None,
        key_topics: Optional[List[str]] = None,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store or update a document memory in the sector graph.

        Creates a DocumentMemory node and links it to the source
        structural_document via HAS_MEMORY edge.

        Args:
            tenant_id: Tenant identifier
            document_id: Source document ID (matches structural_document.document_id)
            summary: Compact summary (2-3 sentences, ~100 tokens)
            key_entities: List of important entity names
            key_topics: List of key topics/themes
            domain: Business domain (legal, fiscal, medical, etc.)
            semantic_type: Document type (factura, contrato, nomina, etc.)

        Returns:
            Dict with success status and memory node info
        """
        if not self._initialized:
            await self.initialize()

        if not age_client._pool:
            return {"success": False, "error": "AGE client not available"}

        graph = settings.age_graph_name
        if not graph:
            return {"success": False, "error": "No sector graph configured"}

        now = datetime.now(timezone.utc).isoformat()
        entities_json = _json_escape(key_entities or [])
        topics_json = _json_escape(key_topics or [])

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MERGE (m:DocumentMemory {{
                    tenant_id: '{_escape(tenant_id)}',
                    document_id: '{_escape(document_id)}'
                }})
                SET m.summary = '{_escape(summary)}',
                    m.key_entities = '{entities_json}',
                    m.key_topics = '{topics_json}',
                    m.domain = '{_escape(domain or "")}',
                    m.semantic_type = '{_escape(semantic_type or "")}',
                    m.memory_version = {MEMORY_VERSION},
                    m.updated_at = '{now}'
                WITH m
                MATCH (d:structural_document {{
                    tenant_id: '{_escape(tenant_id)}',
                    document_id: '{_escape(document_id)}'
                }})
                MERGE (d)-[:HAS_MEMORY]->(m)
                RETURN id(m)
            $$) as (memory_id agtype)
            """
            await age_client.execute_cypher(cypher)

            logger.info(
                f"MemoryBank: stored memory for doc {document_id} "
                f"({len(summary)} chars, {len(key_entities or [])} entities, "
                f"{len(key_topics or [])} topics)"
            )
            return {"success": True, "document_id": document_id}

        except Exception as e:
            logger.error(f"MemoryBank: failed to store memory for {document_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_memory(
        self,
        tenant_id: str,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the memory for a specific document."""
        if not age_client._pool:
            return None

        graph = settings.age_graph_name
        if not graph:
            return None

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (m:DocumentMemory {{
                    tenant_id: '{_escape(tenant_id)}',
                    document_id: '{_escape(document_id)}'
                }})
                RETURN m.document_id as document_id,
                       m.summary as summary,
                       m.key_entities as key_entities,
                       m.key_topics as key_topics,
                       m.domain as domain,
                       m.semantic_type as semantic_type,
                       m.memory_version as memory_version,
                       m.updated_at as updated_at
            $$) as (document_id agtype, summary agtype, key_entities agtype,
                    key_topics agtype, domain agtype, semantic_type agtype,
                    memory_version agtype, updated_at agtype)
            """
            rows = await age_client.execute_cypher(cypher)
            if not rows:
                return None

            return self._parse_memory_row(rows[0])
        except Exception as e:
            logger.warning(f"MemoryBank: get_memory failed for {document_id}: {e}")
            return None

    async def recall(
        self,
        tenant_id: str,
        query_topics: Optional[List[str]] = None,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Recall document memories matching given criteria.

        This is the main query interface for the planner model.
        Returns lightweight memory summaries that help the planner
        decide which documents to retrieve in full.

        Args:
            tenant_id: Tenant identifier
            query_topics: Topics to match against key_topics
            domain: Filter by business domain
            semantic_type: Filter by document type
            limit: Max memories to return

        Returns:
            List of memory dicts sorted by relevance
        """
        if not age_client._pool:
            return []

        graph = settings.age_graph_name
        if not graph:
            return []

        # Build WHERE clause
        where_parts = [f"m.tenant_id = '{_escape(tenant_id)}'"]
        if domain:
            where_parts.append(f"m.domain = '{_escape(domain)}'")
        if semantic_type:
            where_parts.append(f"m.semantic_type = '{_escape(semantic_type)}'")

        where_clause = " AND ".join(where_parts)

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (m:DocumentMemory)
                WHERE {where_clause}
                RETURN m.document_id as document_id,
                       m.summary as summary,
                       m.key_entities as key_entities,
                       m.key_topics as key_topics,
                       m.domain as domain,
                       m.semantic_type as semantic_type,
                       m.memory_version as memory_version,
                       m.updated_at as updated_at
                ORDER BY m.updated_at DESC
                LIMIT {limit}
            $$) as (document_id agtype, summary agtype, key_entities agtype,
                    key_topics agtype, domain agtype, semantic_type agtype,
                    memory_version agtype, updated_at agtype)
            """
            rows = await age_client.execute_cypher(cypher)

            memories = [self._parse_memory_row(r) for r in rows]

            # Client-side topic filtering (AGE doesn't support JSON array containment)
            if query_topics:
                query_set = {t.lower() for t in query_topics}
                scored = []
                for mem in memories:
                    mem_topics = {t.lower() for t in mem.get("key_topics", [])}
                    mem_entities = {e.lower() for e in mem.get("key_entities", [])}
                    overlap = len(query_set & (mem_topics | mem_entities))
                    if overlap > 0:
                        scored.append((overlap, mem))
                scored.sort(key=lambda x: x[0], reverse=True)
                return [m for _, m in scored[:limit]]

            return memories

        except Exception as e:
            logger.warning(f"MemoryBank: recall failed: {e}")
            return []

    async def get_all_document_ids_with_memory(
        self,
        tenant_id: str,
    ) -> List[str]:
        """
        Get all document IDs that already have a memory node.

        Used by the indexing pipeline to skip re-generation.
        """
        if not age_client._pool:
            return []

        graph = settings.age_graph_name
        if not graph:
            return []

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (m:DocumentMemory {{tenant_id: '{_escape(tenant_id)}'}})
                RETURN m.document_id as document_id
            $$) as (document_id agtype)
            """
            rows = await age_client.execute_cypher(cypher)
            from app.services.ontology_service import _clean_agtype
            return [_clean_agtype(r.get("document_id")) for r in rows if r.get("document_id")]
        except Exception as e:
            logger.warning(f"MemoryBank: get_all_document_ids_with_memory failed: {e}")
            return []

    async def delete_memory(
        self,
        tenant_id: str,
        document_id: str,
    ) -> bool:
        """Delete a document's memory node and its HAS_MEMORY edge."""
        if not age_client._pool:
            return False

        graph = settings.age_graph_name
        if not graph:
            return False

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (m:DocumentMemory {{
                    tenant_id: '{_escape(tenant_id)}',
                    document_id: '{_escape(document_id)}'
                }})
                DETACH DELETE m
                RETURN true
            $$) as (deleted agtype)
            """
            await age_client.execute_cypher(cypher)
            logger.info(f"MemoryBank: deleted memory for doc {document_id}")
            return True
        except Exception as e:
            logger.warning(f"MemoryBank: delete_memory failed for {document_id}: {e}")
            return False

    async def get_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get memory bank statistics for a tenant."""
        if not age_client._pool:
            return {"total_memories": 0, "by_domain": {}, "by_type": {}}

        graph = settings.age_graph_name
        if not graph:
            return {"total_memories": 0, "by_domain": {}, "by_type": {}}

        try:
            cypher = f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (m:DocumentMemory {{tenant_id: '{_escape(tenant_id)}'}})
                RETURN m.domain as domain, m.semantic_type as semantic_type, count(*) as cnt
            $$) as (domain agtype, semantic_type agtype, cnt agtype)
            """
            rows = await age_client.execute_cypher(cypher)

            from app.services.ontology_service import _clean_agtype
            total = 0
            by_domain: Dict[str, int] = {}
            by_type: Dict[str, int] = {}

            for r in rows:
                count = int(_clean_agtype(r.get("cnt")) or 0)
                total += count
                domain = _clean_agtype(r.get("domain")) or "unknown"
                stype = _clean_agtype(r.get("semantic_type")) or "unknown"
                by_domain[domain] = by_domain.get(domain, 0) + count
                by_type[stype] = by_type.get(stype, 0) + count

            return {
                "total_memories": total,
                "by_domain": by_domain,
                "by_type": by_type,
            }
        except Exception as e:
            logger.warning(f"MemoryBank: get_stats failed: {e}")
            return {"total_memories": 0, "by_domain": {}, "by_type": {}}

    # ─── Internal ─────────────────────────────────────────────

    @staticmethod
    def _parse_memory_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse an AGE row into a clean memory dict."""
        from app.services.ontology_service import _clean_agtype

        key_entities_raw = _clean_agtype(row.get("key_entities")) or "[]"
        key_topics_raw = _clean_agtype(row.get("key_topics")) or "[]"

        try:
            key_entities = json.loads(key_entities_raw) if isinstance(key_entities_raw, str) else []
        except (json.JSONDecodeError, TypeError):
            key_entities = []

        try:
            key_topics = json.loads(key_topics_raw) if isinstance(key_topics_raw, str) else []
        except (json.JSONDecodeError, TypeError):
            key_topics = []

        return {
            "document_id": _clean_agtype(row.get("document_id")),
            "summary": _clean_agtype(row.get("summary")),
            "key_entities": key_entities,
            "key_topics": key_topics,
            "domain": _clean_agtype(row.get("domain")),
            "semantic_type": _clean_agtype(row.get("semantic_type")),
            "memory_version": _clean_agtype(row.get("memory_version")),
            "updated_at": _clean_agtype(row.get("updated_at")),
        }


# Singleton
memory_bank = MemoryBankService()
