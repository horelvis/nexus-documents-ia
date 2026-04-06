import logging
import mimetypes
import httpx
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult

logger = logging.getLogger(__name__)

MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".html": "text/html",
    ".csv": "text/csv",
    ".md": "text/markdown",
}


class TikaProvider(ExtractionProvider):
    """Extract text via Apache Tika REST API."""

    name = "tika"

    def __init__(self, url: str, timeout: int = 600):
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = MIME_MAP.get(ext) or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(
                f"{self._url}/tika",
                content=file_bytes,
                headers={
                    "Content-Type": content_type,
                    "Accept": "text/plain",
                },
            )
            response.raise_for_status()
            text = response.text.strip()

        language = ""
        if text and len(text) > 20:
            try:
                language = detect(text)
            except Exception:
                pass

        return ExtractionResult(
            text=text,
            language=language,
            metadata={
                "extraction_provider": "tika",
                "content_type": content_type,
                "characters": len(text),
            },
        )

    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return await self.extract(resp.content, filename, **options)

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._url}/version")
                return resp.status_code == 200
        except Exception:
            return False
