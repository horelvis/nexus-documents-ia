"""
OntologySearch — vector-based predicate resolution via Weaviate OntologyTerms.

Resolution order:
1. Exact match in OntologyRegistry (fast, no network)
2. Vector search in OntologyTerms (semantic matching)
3. None — predicate is unknown
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from app.services.ontology_registry import get_namespace

logger = logging.getLogger(__name__)

_SEMANTIC_THRESHOLD = 0.80

_WEAVIATE_URL = os.environ.get("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
_INTELLIGENCE_URL = os.environ.get("INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8000")
_API_KEY = os.environ.get("MICROSERVICES_API_KEY", "")


class OntologySearch:
    """Resolve predicates using exact match + vector semantic search."""

    async def resolve_predicate(self, predicate: str) -> Optional[Dict[str, Any]]:
        """Resolve a predicate name to its canonical ontology entry.

        Returns dict with keys: predicate_name, namespace, method, score
        or None if no match found.
        """
        # Step 1: exact match (free, no network)
        namespace = get_namespace(predicate)
        if namespace:
            return {
                "predicate_name": predicate,
                "namespace": namespace,
                "method": "exact",
                "score": 1.0,
            }

        # Step 2: vector search
        try:
            results = await self._vector_search(predicate)
        except Exception as exc:
            logger.warning("OntologySearch vector search failed: %s", exc)
            return None

        if not results:
            return None

        best = results[0]
        if best["score"] >= _SEMANTIC_THRESHOLD:
            return {
                "predicate_name": best["predicate_name"],
                "namespace": best["namespace"],
                "method": "semantic_match",
                "score": best["score"],
            }

        return None

    async def _vector_search(self, predicate: str, limit: int = 3) -> List[Dict]:
        """Embed the predicate text and search OntologyTerms."""
        headers = {"X-API-Key": _API_KEY} if _API_KEY else {}

        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            # Generate embedding
            embed_resp = await client.post(
                f"{_INTELLIGENCE_URL}/embed",
                json={"text": predicate, "task": "retrieval.query"},
            )
            if embed_resp.status_code != 200:
                logger.warning("Embedding failed for predicate %r: %s", predicate, embed_resp.status_code)
                return []
            embed_data = embed_resp.json()
            embedding = embed_data.get("embedding") or embed_data.get("embeddings", [None])[0]
            if not embedding:
                return []

            # Search OntologyTerms
            search_resp = await client.post(
                f"{_WEAVIATE_URL}/weaviate/trustgraph/ontology-terms/search",
                json={"embedding": embedding, "limit": limit},
            )
            if search_resp.status_code != 200:
                return []
            return search_resp.json().get("results", [])
