"""
HTTP client for Knowledge Tree Service (legal graph operations).

Replaces direct imports of legal_graph singleton. All legal graph
operations now go through knowledge-tree-service via HTTP.
"""

import logging
from typing import List, Optional, Dict, Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeTreeLegalClient:
    """HTTP client for legal graph operations on knowledge-tree-service."""

    def __init__(self):
        self._base_url = settings.knowledge_tree_service_url.rstrip("/")
        self._timeout = 30.0
        self._headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to knowledge-tree-service."""
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method, url,
                    json=json, params=params,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Knowledge Tree API error {e.response.status_code}: {path}")
            raise
        except Exception as e:
            logger.error(f"Knowledge Tree API request failed: {path} - {e}")
            raise

    # ── Law CRUD ──────────────────────────────────────────────────────

    async def add_law(self, law_data: Dict[str, Any]) -> bool:
        """Add or update a law node."""
        try:
            await self._request("POST", "/legal/laws", json=law_data)
            return True
        except Exception:
            return False

    async def get_law(self, boe_id: str) -> Optional[Dict[str, Any]]:
        """Get a single law by BOE ID."""
        try:
            return await self._request("GET", f"/legal/laws/{boe_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_all_laws(self) -> List[Dict[str, Any]]:
        """Get all laws."""
        try:
            return await self._request("GET", "/legal/laws")
        except Exception:
            return []

    async def get_laws_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """Get laws filtered by domain."""
        try:
            return await self._request("GET", f"/legal/laws/domain/{domain}")
        except Exception:
            return []

    # ── References ────────────────────────────────────────────────────

    async def add_reference(
        self,
        source_boe_id: str,
        target_boe_id: str,
        relationship_type: str = "REFERENCES",
        context_snippet: str = "",
        articles_affected: Optional[List[str]] = None,
    ) -> bool:
        """Add a reference edge between two laws."""
        try:
            result = await self._request("POST", "/legal/references/add", json={
                "source_boe_id": source_boe_id,
                "target_boe_id": target_boe_id,
                "relationship_type": relationship_type,
                "context_snippet": context_snippet,
                "articles_affected": articles_affected or [],
            })
            return result.get("success", False)
        except Exception:
            return False

    async def extract_and_store_references(
        self, boe_id: str, text: str
    ) -> Dict[str, Any]:
        """Extract references from text AND store as graph edges."""
        try:
            return await self._request(
                "POST", "/legal/references/extract-and-store",
                json={"boe_id": boe_id, "text": text},
            )
        except Exception as e:
            logger.error(f"Failed to extract+store refs for {boe_id}: {e}")
            return {"extracted": {}, "stored": {}}

    async def enrich_from_boe_api(self, boe_id: str) -> Dict[str, Any]:
        """Fetch BOE /analisis API enrichment."""
        try:
            return await self._request(
                "POST", "/legal/references/enrich-boe",
                params={"boe_id": boe_id},
            )
        except Exception as e:
            logger.error(f"Failed to enrich from BOE API for {boe_id}: {e}")
            return {"posterior_references": [], "anterior_references": [], "materias": []}

    # ── Traversal ─────────────────────────────────────────────────────

    async def get_law_neighbors(
        self,
        boe_id: str,
        max_depth: int = 2,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Get neighboring laws via graph traversal."""
        try:
            result = await self._request("POST", "/legal/neighbors", json={
                "boe_id": boe_id,
                "max_depth": max_depth,
                "relationship_types": relationship_types,
            })
            return result.get("neighbors", [])
        except Exception:
            return []

    # ── Stats & Structure ─────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """Get legal graph statistics."""
        try:
            return await self._request("GET", "/legal/stats")
        except Exception:
            return {"initialized": False}

    async def get_graph_structure(self) -> Dict[str, Any]:
        """Get full graph structure for D3 visualization."""
        try:
            return await self._request("GET", "/legal/graph/structure")
        except Exception:
            return {"nodes": [], "edges": []}

    async def get_enriched_graph_structure(self) -> Dict[str, Any]:
        """Get enriched graph with domain clusters."""
        try:
            return await self._request("GET", "/legal/graph/enriched")
        except Exception:
            return {"nodes": [], "edges": [], "stats": {}}

    # ── Document-Law Linking ──────────────────────────────────────────

    async def link_document_to_law(
        self, document_id: str, law_boe_id: str, tenant_id: str,
        relationship_type: str = "GOVERNED_BY",
    ) -> bool:
        """Link a document to a law."""
        try:
            await self._request(
                "POST", f"/legal/documents/{document_id}/link-law",
                json={
                    "law_boe_id": law_boe_id,
                    "tenant_id": tenant_id,
                    "relationship_type": relationship_type,
                },
            )
            return True
        except Exception:
            return False

    async def get_applicable_laws(
        self, document_id: str, tenant_id: str
    ) -> List[Dict[str, Any]]:
        """Get laws linked to a document."""
        try:
            return await self._request(
                "GET", f"/legal/documents/{document_id}/applicable-laws",
                params={"tenant_id": tenant_id},
            )
        except Exception:
            return []

    # ── Entity Graph Bridge ──────────────────────────────────────────

    async def store_entities(
        self,
        tenant_id: str,
        document_id: str,
        entities: List[Dict[str, Any]],
        relationships: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Store extracted entities in the sector graph via EntityGraphBridge.

        Called by KnowledgeExtractionService during indexing to persist
        entities as typed nodes with INSTANCE_OF and EXTRACTED_FROM edges.
        """
        try:
            return await self._request("POST", "/tree/entities/store", json={
                "tenant_id": tenant_id,
                "document_id": document_id,
                "entities": entities,
                "relationships": relationships or [],
            })
        except Exception as e:
            logger.warning(f"Failed to store entities in knowledge-tree: {e}")
            return {"success": False, "entities_stored": 0}

    async def get_document_entities(
        self, document_id: str, tenant_id: str
    ) -> List[Dict[str, Any]]:
        """Get entities extracted from a document."""
        try:
            result = await self._request(
                "GET", f"/tree/entities/by-document/{document_id}",
                params={"tenant_id": tenant_id},
            )
            return result.get("entities", [])
        except Exception:
            return []

    async def search_entity(
        self, tenant_id: str, value: str, entity_type: Optional[str] = None,
        max_depth: int = 2, limit: int = 20,
    ) -> Dict[str, Any]:
        """Search entity and its neighborhood for graph-based query expansion."""
        try:
            params = {"tenant_id": tenant_id, "value": value, "max_depth": max_depth, "limit": limit}
            if entity_type:
                params["type"] = entity_type
            return await self._request("GET", "/tree/entities/search", params=params)
        except Exception:
            return {"entity": None, "neighbors": [], "documents": []}

    # ── Structural Queries (proxy to /tree endpoints) ────────────────

    async def get_structural_summary(self, tenant_id: str) -> str:
        """Get tenant structural summary from knowledge-tree-service."""
        try:
            result = await self._request(
                "POST", "/tree/summary",
                json={"tenant_id": tenant_id},
            )
            return result.get("summary", "")
        except Exception as e:
            logger.warning(f"Failed to get structural summary: {e}")
            return ""

    async def get_container_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        """Get distinct container/folder types for a tenant."""
        try:
            result = await self._request(
                "POST", "/tree/structural/query",
                json={"tenant_id": tenant_id, "query": ""},
            )
            type_counts = result.get("data", {}).get("container_type_counts", {})
            return list(type_counts.keys())[:limit]
        except Exception:
            return []

    async def get_document_types(self, tenant_id: str, limit: int = 20) -> List[str]:
        """Get distinct document types for a tenant."""
        try:
            result = await self._request(
                "POST", "/tree/structural/query",
                json={"tenant_id": tenant_id, "query": ""},
            )
            type_counts = result.get("data", {}).get("document_type_counts", {})
            return list(type_counts.keys())[:limit]
        except Exception:
            return []

    # ── Compatibility: initialize() no-op ─────────────────────────────

    async def initialize(self):
        """No-op for API compatibility with old legal_graph singleton."""
        pass

    async def extract_and_link_legal(
        self,
        tenant_id: str,
        document_id: str,
        text_sample: str,
        semantic_type: str = "",
        domain: str = "",
    ) -> Dict[str, Any]:
        """Extract legal references from document and create APLICA edges."""
        return await self._request(
            "POST",
            "/tree/legal-links/extract-and-store",
            json={
                "tenant_id": tenant_id,
                "document_id": document_id,
                "text_sample": text_sample[:2000],
                "semantic_type": semantic_type,
                "domain": domain,
            },
        )


# Global singleton
knowledge_tree_legal_client = KnowledgeTreeLegalClient()
