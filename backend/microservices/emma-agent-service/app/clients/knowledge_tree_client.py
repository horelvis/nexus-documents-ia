"""
HTTP client for knowledge-tree-service.

History note (2026-04-25): KTS was modernised to expose `/triples/*`,
`/extract/*` and `/graph/*` route prefixes. This client previously held
nine `/tree/*` methods (get_tree_context, get_structural_summary,
structural_query, graph_query, store_memory, recall_memories,
get_memorized_document_ids, get_documents_by_person, extract_subgraph)
that all 404'd silently against the modern service.

This file ports / deletes / marks-TODO each one explicitly so future
sessions don't re-introduce the same drift. See MEMORY entry #15.
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

    # ─── Modern endpoints (work) ──────────────────────────────────────

    async def query_triples(
        self,
        subject_uri: Optional[str] = None,
        predicate_uri: Optional[str] = None,
        object_value: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Query triples from TrustGraph by SPO filter."""
        payload: Dict[str, Any] = {"limit": limit}
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

    async def get_triple_context(self, limit: int = 20) -> Dict[str, Any]:
        """Get LLM context from triple store."""
        payload = {"limit": limit}
        try:
            return await self.post_json("/triples/context", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Triple context failed: {e}")
            return {"success": False, "context_for_llm": "", "error": str(e)}

    async def get_triple_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        try:
            return await self.get_json("/triples/stats", headers=self._headers())
        except Exception as e:
            logger.warning(f"Triple stats failed: {e}")
            return {"success": False, "error": str(e)}

    async def batch_neighbors(
        self,
        seed_uris: List[str],
        max_hops: int = 2,
        max_edges: int = 150,
        triples_per_entity: int = 30,
        exclude_predicates: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """BFS subgraph traversal via /triples/neighbors."""
        payload = {
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
        edges: List[Dict[str, str]],
        collection: str = "default",
    ) -> List[Dict[str, Any]]:
        """Trace graph edges back to source document chunks."""
        payload = {"edges": edges, "collection": collection}
        try:
            result = await self.post_json("/triples/trace-sources", json=payload, headers=self._headers())
            return result.get("sources", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.warning(f"trace_sources failed: {e}")
            return []

    # ─── Ported from legacy /tree/* (now use modern endpoints) ────────

    async def get_structural_summary(self) -> Dict[str, Any]:
        """High-level graph summary. Ported from legacy POST /tree/summary
        to GET /triples/stats — returns counts (nodes, literals, rels,
        contradictions) plus an entity_types breakdown.
        """
        try:
            stats = await self.get_json("/triples/stats", headers=self._headers())
            entity_types = stats.get("entity_types") or {}
            summary_parts = [
                f"{stats.get('nodes', 0)} nodes",
                f"{stats.get('literals', 0)} literals",
                f"{stats.get('rels', 0)} relations",
            ]
            if entity_types:
                top = sorted(entity_types.items(), key=lambda kv: kv[1], reverse=True)[:5]
                summary_parts.append(
                    "top entity types: " + ", ".join(f"{n} {t}" for t, n in top)
                )
            return {
                "summary": "; ".join(summary_parts),
                "stats": stats,
            }
        except Exception as e:
            logger.warning(f"Structural summary failed: {e}")
            return {"summary": "", "stats": {}}

    async def extract_subgraph(
        self,
        entities: List[Dict[str, Any]],
        max_hops: int = 2,
        max_nodes: int = 30,
        include_legal: bool = True,
    ) -> Dict[str, Any]:
        """Extract a multi-hop subgraph around entities (GraphRAG).

        Ported from legacy POST /tree/graph/subgraph to /triples/neighbors.
        The modern endpoint returns edges only, so node URIs are derived
        from edge endpoints. Callers that read .nodes[].properties (e.g.
        smart_search re-ranker filtering by document_id / boe_id) will get
        empty property dicts — those filters become best-effort no-ops
        until a backend extension hydrates per-node properties.

        TODO: extend KTS /triples/neighbors (or add a new endpoint) to
        return per-node properties so smart_search graph expansion can
        filter by document_id / boe_id again.
        """
        # Build seed URIs from entities. Entities arrive as
        # [{"value": "movistar", "type": "organization"}, ...] — the URI
        # convention in TrustGraph is nouxcube://entity/{collection}/{slug}.
        seed_uris: List[str] = []
        for ent in entities:
            value = (ent.get("value") or ent.get("uri") or "").strip()
            if not value:
                continue
            if value.startswith("nouxcube://"):
                seed_uris.append(value)
            else:
                slug = value.lower().replace(" ", "-").replace("/", "-")
                seed_uris.append(f"nouxcube://entity/default/{slug}")

        if not seed_uris:
            return {"nodes": [], "edges": [], "root_entities": [], "pruned_count": 0}

        exclude = ["prov/.*"]
        if not include_legal:
            exclude.append("legal/.*")

        try:
            result = await self.batch_neighbors(
                seed_uris=seed_uris,
                max_hops=max_hops,
                max_edges=max_nodes * 5,  # rough heuristic — N nodes ~ 5N edges
                exclude_predicates=exclude,
            )
        except Exception as e:
            logger.warning(f"extract_subgraph: neighbors call failed: {e}")
            return {"nodes": [], "edges": [], "root_entities": seed_uris, "pruned_count": 0}

        edges = result.get("edges", []) if isinstance(result, dict) else []

        # Derive node list from unique edge endpoints (URIs only — see TODO)
        node_uris: Dict[str, Dict[str, Any]] = {}
        for e in edges:
            for key in ("subject_uri", "object_uri"):
                uri = e.get(key)
                if uri and uri not in node_uris:
                    node_uris[uri] = {"uri": uri, "properties": {}}

        return {
            "nodes": list(node_uris.values()),
            "edges": edges,
            "root_entities": seed_uris,
            "pruned_count": 0,
            "entities_visited": result.get("entities_visited", 0) if isinstance(result, dict) else 0,
        }

    # ─── Legacy methods with no modern equivalent (TODO #15b) ────────

    # The following kept as stubs that fail gracefully so callers do not
    # crash. They need backend work in knowledge-tree-service before they
    # can do anything useful again. Tracked under MEMORY #15b.

    async def structural_query(self, query: str, max_results: int = 100) -> Dict[str, Any]:
        """LEGACY: high-level aggregation queries (counts, type breakdowns).

        TODO #15b: KTS does not yet expose the rich structural router that
        the legacy `/tree/structural/query` provided. Until a replacement
        lands, return the ERROR shape so the structural_query tool falls
        back to suggesting smart_search.
        """
        return {
            "route": "ERROR",
            "confidence": 0.0,
            "context": "structural_query no disponible — usa smart_search",
            "data": {"error": "endpoint not implemented post-modernisation"},
        }

    async def get_documents_by_person(
        self, person_name: str, entity_type: str = "person"
    ) -> List[str]:
        """LEGACY: list documents associated with a person via the graph.

        TODO #15b: needs a dedicated KTS endpoint that walks the predicates
        linking persons to documents. The previous /tree/graph/documents-
        by-entity is gone; replicating it via /triples/query would require
        knowing the linking predicate URIs per ontology.
        """
        return []

    # ─── Memory bank methods — no modern equivalent (TODO #15c) ──────

    async def store_memory(
        self,
        document_id: str,
        summary: str,
        key_entities: Optional[List[str]] = None,
        key_topics: Optional[List[str]] = None,
        semantic_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """LEGACY memory bank store. TODO #15c: KTS does not implement a
        memory bank module any more — the feature was scaffolded but
        never wired into the modern service. Returning a non-success
        shape so memory_generator skips quietly.
        """
        return {"success": False, "error": "memory bank not implemented"}

    async def recall_memories(
        self,
        query_topics: Optional[List[str]] = None,
        semantic_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """LEGACY memory bank recall. See store_memory note."""
        return []

    async def get_memorized_document_ids(self) -> List[str]:
        """LEGACY memory bank list. See store_memory note."""
        return []

    # ─── Trace persistence (Pieza C of the Provenance DAG) ───────────

    async def persist_trace(
        self,
        trace_data: Dict[str, Any],
        collection: str = "default",
    ) -> Dict[str, Any]:
        """POST a reasoning trace to KTS for permanent FalkorDB storage.

        Designed to be called fire-and-forget alongside the existing
        Redis 24h-TTL write at the SSE `complete` event. Returns the
        endpoint response on success, or a shape with `success=False`
        on failure — caller is responsible for ignoring the failure
        case so it never affects the user-facing Emma response.
        """
        payload = {"trace_data": trace_data, "collection": collection}
        try:
            return await self.post_json(
                "/traces/persist",
                json=payload,
                headers=self._headers(),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"persist_trace failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_trace(
        self,
        thread_id: str,
        message_index: int,
        collection: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """GET the persisted trace from KTS — fallback when Redis missed.

        Returns the FalkorDB-reconstructed trace payload (same shape as
        the Redis blob, with a `source: "falkordb"` marker) or None if
        no trace exists for the (thread_id, message_index) tuple.
        """
        path = f"/traces/{thread_id}/{message_index}"
        params = {"collection": collection}
        try:
            return await self.get_json(
                path,
                headers=self._headers(),
                params=params,
            )
        except Exception as e:  # noqa: BLE001
            # 404 → None (no trace persisted); any other → log + None.
            msg = str(e)
            if "404" in msg or "Not Found" in msg:
                return None
            logger.warning(f"get_trace failed: {e}")
            return None


_knowledge_tree_client: Optional[KnowledgeTreeClient] = None


def get_knowledge_tree_client() -> KnowledgeTreeClient:
    global _knowledge_tree_client
    if _knowledge_tree_client is None:
        _knowledge_tree_client = KnowledgeTreeClient()
    return _knowledge_tree_client
