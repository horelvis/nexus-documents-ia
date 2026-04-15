"""HTTP client for weaviate-service (document metadata + indexing)."""

import logging
from typing import Any, List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ForgeWeaviateClient:
    """Communicates with weaviate-service for document metadata and indexing."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.weaviate_service_url
        self.api_key = settings.MICROSERVICES_API_KEY

    def _headers(
        self,
        user_roles: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> dict:
        h = {"X-API-Key": self.api_key}
        if user_roles is not None:
            h["X-User-Roles"] = ",".join(user_roles)
        if user_id:
            h["X-User-Id"] = user_id
        return h

    async def get_document_metadata(
        self,
        document_id: str,
        user_roles: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Get document metadata including file_path from weaviate-service."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.base_url}/weaviate/documents/{document_id}",
                    headers=self._headers(user_roles, user_id),
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(
                    "Document %s not found (status=%d)", document_id, resp.status_code
                )
                return None
        except Exception as e:
            logger.error("Failed to get document metadata: %s", e)
            return None

    async def index_document(
        self,
        document_data: dict[str, Any],
        user_roles: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Index a document in Weaviate via the indexing pipeline."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/weaviate/index-from-connector",
                    json=document_data,
                    headers=self._headers(user_roles, user_id),
                )
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.error("Index failed (status=%d): %s", resp.status_code, resp.text)
                return None
        except Exception as e:
            logger.error("Failed to index document: %s", e)
            return None

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


_client = None


def get_weaviate_client() -> ForgeWeaviateClient:
    global _client
    if _client is None:
        _client = ForgeWeaviateClient()
    return _client
