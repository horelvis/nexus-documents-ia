"""HTTP client for intelligence-docs-service (text extraction)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from .base import BaseHTTPClient, HTTPClientConfig

logger = logging.getLogger(__name__)


class TextExtractionClient(BaseHTTPClient):
    """Client for intelligence-docs-service (POST /extract)."""

    async def extract_text(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY or "",
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if user_id:
            headers["X-User-ID"] = user_id

        files = {
            "file": (filename, file_bytes),
        }

        response = await self.post(
            "/extract",
            headers=headers,
            files=files,
        )
        return response.json()


_text_extraction_client: Optional[TextExtractionClient] = None


def get_text_extraction_client() -> TextExtractionClient:
    """Get singleton text extraction client."""
    global _text_extraction_client
    if _text_extraction_client is None:
        _text_extraction_client = TextExtractionClient(
            HTTPClientConfig(
                base_url=settings.text_extraction_service_url,
                timeout=settings.text_extraction_service_timeout,
            )
        )
    return _text_extraction_client


async def close_text_extraction_client() -> None:
    """Close the text extraction client."""
    global _text_extraction_client
    if _text_extraction_client:
        await _text_extraction_client.close()
        _text_extraction_client = None
