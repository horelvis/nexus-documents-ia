"""
Memory Bank Service -- MemoRAG-inspired Document Memory Store (FalkorDB)

Stores compact document "memories" (summaries, key entities, topics) as
DocumentMemory nodes in the FalkorDB knowledge graph, linked to their
source Document node via HAS_MEMORY edges.

These memories serve as retrieval clues for the planner model (4B):
instead of searching raw chunks, the planner scans lightweight memory
nodes to decide what documents are relevant, then retrieves full content.

Architecture:
    Document -[:HAS_MEMORY]-> DocumentMemory
                                    |
                                    +-- summary (2-3 sentences)
                                    +-- key_entities (JSON array)
                                    +-- key_topics (JSON array)
                                    +-- domain (legal, fiscal, etc.)
                                    +-- semantic_type (factura, contrato, etc.)
                                    +-- memory_version (for re-generation)
                                    +-- updated_at (ISO timestamp)

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

from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)

MEMORY_VERSION = 1


class MemoryBankService:
    """
    CRUD service for DocumentMemory nodes in the FalkorDB graph.

    Each document gets at most one memory node (MERGE by document_id).
    Memories are lightweight (~200 tokens) and designed for bulk scan
    by the planner model.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await falkordb_client.initialize()
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
        Store or update a document memory in the graph.

        Creates a DocumentMemory node and links it to the source
        Document node via HAS_MEMORY edge.

        Args:
            tenant_id: Tenant identifier
            document_id: Source document ID (matches Document.document_id)
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

        if not falkordb_client._initialized:
            return {"success": False, "error": "FalkorDB client not available"}

        now = datetime.now(timezone.utc).isoformat()
        entities_json = json.dumps(key_entities or [], ensure_ascii=False)
        topics_json = json.dumps(key_topics or [], ensure_ascii=False)

        try:
            query = """
                MERGE (m:DocumentMemory {
                    tenant_id: $tenant_id,
                    document_id: $document_id
                })
                SET m.summary = $summary,
                    m.key_entities = $entities_json,
                    m.key_topics = $topics_json,
                    m.domain = $domain,
                    m.semantic_type = $semantic_type,
                    m.memory_version = $memory_version,
                    m.updated_at = $updated_at
                WITH m
                MATCH (d:Document {
                    tenant_id: $tenant_id,
                    document_id: $document_id
                })
                MERGE (d)-[:HAS_MEMORY]->(m)
                RETURN id(m) AS memory_id
            """
            params = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "summary": summary,
                "entities_json": entities_json,
                "topics_json": topics_json,
                "domain": domain or "",
                "semantic_type": semantic_type or "",
                "memory_version": MEMORY_VERSION,
                "updated_at": now,
            }
            await falkordb_client.execute_cypher(query, params)

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
        if not falkordb_client._initialized:
            return None

        try:
            query = """
                MATCH (m:DocumentMemory {
                    tenant_id: $tenant_id,
                    document_id: $document_id
                })
                RETURN m.document_id AS document_id,
                       m.summary AS summary,
                       m.key_entities AS key_entities,
                       m.key_topics AS key_topics,
                       m.domain AS domain,
                       m.semantic_type AS semantic_type,
                       m.memory_version AS memory_version,
                       m.updated_at AS updated_at
            """
            rows = await falkordb_client.execute_cypher(query, {
                "tenant_id": tenant_id,
                "document_id": document_id,
            })
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
        if not falkordb_client._initialized:
            return []

        # Build WHERE clause with parameters
        where_parts = ["m.tenant_id = $tenant_id"]
        params: Dict[str, Any] = {"tenant_id": tenant_id, "limit": limit}

        if domain:
            where_parts.append("m.domain = $domain")
            params["domain"] = domain
        if semantic_type:
            where_parts.append("m.semantic_type = $semantic_type")
            params["semantic_type"] = semantic_type

        where_clause = " AND ".join(where_parts)

        try:
            query = f"""
                MATCH (m:DocumentMemory)
                WHERE {where_clause}
                RETURN m.document_id AS document_id,
                       m.summary AS summary,
                       m.key_entities AS key_entities,
                       m.key_topics AS key_topics,
                       m.domain AS domain,
                       m.semantic_type AS semantic_type,
                       m.memory_version AS memory_version,
                       m.updated_at AS updated_at
                ORDER BY m.updated_at DESC
                LIMIT $limit
            """
            rows = await falkordb_client.execute_cypher(query, params)

            memories = [self._parse_memory_row(r) for r in rows]

            # Client-side topic filtering (graph DB doesn't support JSON array containment)
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
        if not falkordb_client._initialized:
            return []

        try:
            query = """
                MATCH (m:DocumentMemory {tenant_id: $tenant_id})
                RETURN m.document_id AS document_id
            """
            rows = await falkordb_client.execute_cypher(query, {"tenant_id": tenant_id})
            return [r.get("document_id") for r in rows if r.get("document_id")]
        except Exception as e:
            logger.warning(f"MemoryBank: get_all_document_ids_with_memory failed: {e}")
            return []

    async def delete_memory(
        self,
        tenant_id: str,
        document_id: str,
    ) -> bool:
        """Delete a document's memory node and its HAS_MEMORY edge."""
        if not falkordb_client._initialized:
            return False

        try:
            query = """
                MATCH (m:DocumentMemory {
                    tenant_id: $tenant_id,
                    document_id: $document_id
                })
                DETACH DELETE m
            """
            await falkordb_client.execute_cypher(query, {
                "tenant_id": tenant_id,
                "document_id": document_id,
            })
            logger.info(f"MemoryBank: deleted memory for doc {document_id}")
            return True
        except Exception as e:
            logger.warning(f"MemoryBank: delete_memory failed for {document_id}: {e}")
            return False

    async def get_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get memory bank statistics for a tenant."""
        if not falkordb_client._initialized:
            return {"total_memories": 0, "by_domain": {}, "by_type": {}}

        try:
            query = """
                MATCH (m:DocumentMemory {tenant_id: $tenant_id})
                RETURN m.domain AS domain, m.semantic_type AS semantic_type,
                       count(*) AS cnt
            """
            rows = await falkordb_client.execute_cypher(query, {"tenant_id": tenant_id})

            total = 0
            by_domain: Dict[str, int] = {}
            by_type: Dict[str, int] = {}

            for r in rows:
                count = int(r.get("cnt", 0))
                total += count
                domain_val = r.get("domain") or "unknown"
                stype = r.get("semantic_type") or "unknown"
                by_domain[domain_val] = by_domain.get(domain_val, 0) + count
                by_type[stype] = by_type.get(stype, 0) + count

            return {
                "total_memories": total,
                "by_domain": by_domain,
                "by_type": by_type,
            }
        except Exception as e:
            logger.warning(f"MemoryBank: get_stats failed: {e}")
            return {"total_memories": 0, "by_domain": {}, "by_type": {}}

    # --- Internal ---------------------------------------------------------

    @staticmethod
    def _parse_memory_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a FalkorDB row into a clean memory dict."""
        key_entities_raw = row.get("key_entities") or "[]"
        key_topics_raw = row.get("key_topics") or "[]"

        try:
            key_entities = json.loads(key_entities_raw) if isinstance(key_entities_raw, str) else key_entities_raw
        except (json.JSONDecodeError, TypeError):
            key_entities = []

        try:
            key_topics = json.loads(key_topics_raw) if isinstance(key_topics_raw, str) else key_topics_raw
        except (json.JSONDecodeError, TypeError):
            key_topics = []

        # Ensure lists
        if not isinstance(key_entities, list):
            key_entities = []
        if not isinstance(key_topics, list):
            key_topics = []

        return {
            "document_id": row.get("document_id"),
            "summary": row.get("summary"),
            "key_entities": key_entities,
            "key_topics": key_topics,
            "domain": row.get("domain"),
            "semantic_type": row.get("semantic_type"),
            "memory_version": row.get("memory_version"),
            "updated_at": row.get("updated_at"),
        }


# Singleton
memory_bank = MemoryBankService()
