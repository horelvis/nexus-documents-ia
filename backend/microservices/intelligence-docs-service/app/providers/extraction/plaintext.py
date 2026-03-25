import logging
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult

logger = logging.getLogger(__name__)

PLAINTEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm", ".rst", ".yaml", ".yml"}


def is_plaintext(filename: str) -> bool:
    """Check if file is a plaintext format that doesn't need extraction."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in PLAINTEXT_EXTENSIONS


class PlaintextProvider(ExtractionProvider):
    """Read plaintext files directly — no extraction needed."""

    name = "plaintext"

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        # Try UTF-8 first, fallback to latin-1
        try:
            text = file_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1").strip()

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
                "extraction_provider": "plaintext",
                "characters": len(text),
            },
        )

    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return await self.extract(resp.content, filename, **options)

    async def is_available(self) -> bool:
        return True
