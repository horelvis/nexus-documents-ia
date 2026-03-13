"""HTTP client for gotenberg-service (DOCX → PDF conversion)."""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class GotenbergClient:
    """Converts DOCX to PDF via gotenberg-service."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.gotenberg_service_url
        self.api_key = settings.MICROSERVICES_API_KEY

    async def docx_to_pdf(self, docx_bytes: bytes, filename: str = "document.docx") -> bytes:
        """Convert DOCX bytes to PDF bytes."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/convert/office-to-pdf",
                files={"file": (filename, docx_bytes, DOCX_MIME_TYPE)},
                headers={"X-API-Key": self.api_key},
            )
            response.raise_for_status()
            return response.content

    async def health(self) -> bool:
        """Check gotenberg-service availability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


_client = None


def get_gotenberg_client() -> GotenbergClient:
    global _client
    if _client is None:
        _client = GotenbergClient()
    return _client
