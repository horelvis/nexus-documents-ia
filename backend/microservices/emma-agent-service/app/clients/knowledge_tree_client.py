"""
HTTP client for knowledge-tree-service.
"""

import logging
from typing import Any, Dict, Optional

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


_knowledge_tree_client: Optional[KnowledgeTreeClient] = None


def get_knowledge_tree_client() -> KnowledgeTreeClient:
    global _knowledge_tree_client
    if _knowledge_tree_client is None:
        _knowledge_tree_client = KnowledgeTreeClient()
    return _knowledge_tree_client
