import logging
import httpx
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult

logger = logging.getLogger(__name__)


class DoclingProvider(ExtractionProvider):
    """Extract text via IBM Docling Serve API. Returns Markdown."""

    name = "docling"

    def __init__(self, url: str, timeout: int = 600):
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._url}/v1/convert/file",
                files={"file": (filename, file_bytes)},
            )
            response.raise_for_status()
            data = response.json()

        text = data.get("document", {}).get("md_content", "")
        if not text:
            text = data.get("text", "")

        language = ""
        if text and len(text) > 20:
            try:
                language = detect(text)
            except Exception:
                pass

        page_count = data.get("document", {}).get("num_pages", 0)

        return ExtractionResult(
            text=text,
            language=language,
            metadata={
                "extraction_provider": "docling",
                "extraction_format": "markdown",
                "characters": len(text),
                "pages": page_count,
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
                resp = await client.get(f"{self._url}/health")
                return resp.status_code == 200
        except Exception:
            return False
