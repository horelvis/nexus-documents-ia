"""
HTTP client for knowledge-tree-service.
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseHTTPClient, HTTPClientConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeTreeClient(BaseHTTPClient):
    def __init__(self):
        config = HTTPClientConfig(
            base_url=settings.knowledge_tree_service_url,
            timeout=settings.knowledge_tree_service_timeout,
            max_connections=50,
            max_keepalive_connections=10,
            retry_attempts=2,
            retry_delay=0.5,
        )
        super().__init__(config)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key": settings.MICROSERVICES_API_KEY,
        }

    async def get_tree_context(self, tenant_id: str, limit: int = 15) -> Dict[str, Any]:
        payload = {"tenant_id": tenant_id, "limit": limit}
        try:
            return await self.post_json("/tree/context", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Knowledge tree context failed: {e}")
            return {"success": False, "context_for_llm": "", "metadata": {"error": str(e)}}

    async def get_structural_summary(self, tenant_id: str) -> Dict[str, Any]:
        payload = {"tenant_id": tenant_id}
        try:
            return await self.post_json("/tree/summary", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Knowledge tree summary failed: {e}")
            return {"summary": ""}

    async def structural_query(self, tenant_id: str, query: str, max_results: int = 100) -> Dict[str, Any]:
        payload = {
            "tenant_id": tenant_id,
            "query": query,
            "max_results": max_results,
        }
        try:
            return await self.post_json("/tree/structural/query", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Knowledge tree structural query failed: {e}")
            return {
                "route": "ERROR",
                "confidence": 0.0,
                "context": "",
                "data": {"error": str(e)},
            }


    async def graph_query(self, cypher: str, graph_name: str, tenant_id: str) -> Dict[str, Any]:
        payload = {
            "cypher": cypher,
            "graph_name": graph_name,
            "tenant_id": tenant_id,
        }
        try:
            return await self.post_json("/tree/graph/query", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Knowledge tree graph query failed: {e}")
            return {"results": [], "paths": []}

    # ─── Memory Bank ──────────────────────────────────────────

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
        """Store a document memory in the knowledge graph."""
        payload = {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "summary": summary,
            "key_entities": key_entities or [],
            "key_topics": key_topics or [],
            "domain": domain,
            "semantic_type": semantic_type,
        }
        try:
            return await self.post_json("/tree/memory/store", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Memory bank store failed: {e}")
            return {"success": False, "error": str(e)}

    async def recall_memories(
        self,
        tenant_id: str,
        query_topics: Optional[List[str]] = None,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Recall document memories matching criteria. Used by planner for clue generation."""
        payload = {
            "tenant_id": tenant_id,
            "query_topics": query_topics,
            "domain": domain,
            "semantic_type": semantic_type,
            "limit": limit,
        }
        try:
            result = await self.post_json("/tree/memory/recall", json=payload, headers=self._headers())
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning(f"Memory bank recall failed: {e}")
            return []

    async def get_memorized_document_ids(self, tenant_id: str) -> List[str]:
        """Get document IDs that already have memories. Used to skip re-generation."""
        try:
            result = await self.get_json(
                f"/tree/memory/?tenant_id={tenant_id}", headers=self._headers()
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning(f"Memory bank list failed: {e}")
            return []

    async def get_documents_by_person(
        self, tenant_id: str, person_name: str, entity_type: str = "person"
    ) -> List[str]:
        """Get document IDs linked to a person via the FalkorDB knowledge graph."""
        payload = {
            "tenant_id": tenant_id,
            "entity_name": person_name,
            "entity_type": entity_type,
        }
        try:
            result = await self.post_json(
                "/tree/graph/documents-by-entity", json=payload, headers=self._headers()
            )
            return result.get("document_ids", [])
        except Exception as e:
            logger.warning(f"Documents-by-person query failed: {e}")
            return []


    async def extract_subgraph(
        self,
        tenant_id: str,
        entities: List[Dict[str, Any]],
        max_hops: int = 2,
        max_nodes: int = 30,
        include_legal: bool = True,
    ) -> Dict[str, Any]:
        """Extract a multi-hop subgraph rooted at entities from FalkorDB (GraphRAG).

        Returns structured nodes/edges for LLM context, not flat document IDs.
        """
        payload = {
            "tenant_id": tenant_id,
            "entities": entities,
            "max_hops": max_hops,
            "max_nodes": max_nodes,
            "include_legal": include_legal,
        }
        try:
            return await self.post_json("/tree/graph/subgraph", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Subgraph extraction failed: {e}")
            return {"nodes": [], "edges": [], "root_entities": [], "pruned_count": 0}


    async def query_triples(
        self,
        tenant_id: str,
        subject_uri: Optional[str] = None,
        predicate_uri: Optional[str] = None,
        object_value: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Query triples from TrustGraph."""
        payload = {
            "tenant_id": tenant_id,
            "limit": limit,
        }
        if subject_uri is not None:
            payload["subject_uri"] = subject_uri
        if predicate_uri is not None:
            payload["predicate_uri"] = predicate_uri
        if object_value is not None:
            payload["object_value"] = object_value
        try:
            return await self.post_json("/triples/query", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Triple query failed: {e}")
            return {"success": False, "triples": [], "error": str(e)}

    async def get_triple_context(self, tenant_id: str, limit: int = 20) -> Dict[str, Any]:
        """Get LLM context from triple store."""
        payload = {"tenant_id": tenant_id, "limit": limit}
        try:
            return await self.post_json("/triples/context", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Triple context failed: {e}")
            return {"success": False, "context_for_llm": "", "error": str(e)}

    async def get_triple_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get graph statistics."""
        try:
            return await self.get_json(
                f"/triples/stats?tenant_id={tenant_id}", headers=self._headers()
            )
        except Exception as e:
            logger.warning(f"Triple stats failed: {e}")
            return {"success": False, "error": str(e)}

    async def batch_neighbors(
        self,
        tenant_id: str,
        seed_uris: List[str],
        max_hops: int = 2,
        max_edges: int = 150,
        triples_per_entity: int = 30,
        exclude_predicates: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """BFS subgraph traversal via /triples/neighbors."""
        payload = {
            "tenant_id": tenant_id,
            "seed_uris": seed_uris,
            "max_hops": max_hops,
            "max_edges": max_edges,
            "exclude_predicates": exclude_predicates or ["prov/.*"],
        }
        try:
            return await self.post_json("/triples/neighbors", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Batch neighbors failed: {e}")
            return {"edges": [], "entities_visited": 0, "hops_used": 0}


    async def trace_sources(
        self,
        tenant_id: str,
        edges: List[Dict[str, str]],
        collection: str = "default",
    ) -> List[Dict[str, Any]]:
        """Trace graph edges back to source document chunks."""
        payload = {
            "edges": edges,
            "tenant_id": tenant_id,
            "collection": collection,
        }
        try:
            result = await self.post_json("/triples/trace-sources", json=payload, headers=self._headers())
            return result.get("sources", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.warning(f"trace_sources failed: {e}")
            return []


_knowledge_tree_client: Optional[KnowledgeTreeClient] = None


def get_knowledge_tree_client() -> KnowledgeTreeClient:
    global _knowledge_tree_client
    if _knowledge_tree_client is None:
        _knowledge_tree_client = KnowledgeTreeClient()
    return _knowledge_tree_client
