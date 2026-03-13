"""Document conversion orchestration (DOCX → PDF via gotenberg)."""

import logging

from app.clients.gotenberg_client import get_gotenberg_client

logger = logging.getLogger(__name__)


class ForgeConverter:
    """Converts documents between formats using dependent services."""

    async def docx_to_pdf(self, docx_bytes: bytes, filename: str = "document.docx") -> bytes:
        """Convert DOCX to PDF via gotenberg-service."""
        client = get_gotenberg_client()
        return await client.docx_to_pdf(docx_bytes, filename)


_converter = None


def get_converter() -> ForgeConverter:
    global _converter
    if _converter is None:
        _converter = ForgeConverter()
    return _converter
