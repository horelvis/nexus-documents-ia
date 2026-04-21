"""HTTP client for Main API storage proxy (GCS upload/download)."""

import logging
from typing import Any, List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StorageClient:
    """Communicates with Main API for GCS storage operations."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.main_api_url
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

    async def download_document(
        self,
        file_path: str,
        user_roles: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> bytes | None:
        """Download original document bytes from GCS via storage proxy."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/api/v1/storage/proxy/{file_path}",
                    headers=self._headers(user_roles, user_id),
                )
                if resp.status_code == 200:
                    return resp.content
                logger.warning(
                    "Download failed for %s (status=%d)", file_path, resp.status_code
                )
                return None
        except Exception as e:
            logger.error("Failed to download document: %s", e)
            return None

    async def upload_document(
        self,
        file_bytes: bytes,
        file_name: str,
        folder_path: str,
        user_roles: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any] | None:
        """Upload document bytes to GCS via storage proxy."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/storage/proxy/upload",
                    files={"file": (file_name, file_bytes, content_type)},
                    data={"folder_path": folder_path},
                    headers=self._headers(user_roles, user_id),
                )
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.error("Upload failed (status=%d): %s", resp.status_code, resp.text)
                return None
        except Exception as e:
            logger.error("Failed to upload document: %s", e)
            return None

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


_client = None


def get_storage_client() -> StorageClient:
    global _client
    if _client is None:
        _client = StorageClient()
    return _client
