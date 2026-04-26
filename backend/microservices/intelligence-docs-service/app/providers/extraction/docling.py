import logging
import httpx
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult, ExtractedChunk

logger = logging.getLogger(__name__)


class DoclingProvider(ExtractionProvider):
    """Extract text via IBM Docling Serve API. Returns Markdown.

    Uses /v1/chunk/hybrid/file when available so each chunk arrives with
    page_numbers populated (Docling HybridChunker is page-aware). Falls
    back to /v1/convert/file for the markdown if hybrid chunking fails.
    """

    name = "docling"

    def __init__(self, url: str, timeout: int = 600):
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Step 1: hybrid chunk request — gives us per-chunk page numbers.
            chunks: list[ExtractedChunk] = []
            try:
                chunk_resp = await client.post(
                    f"{self._url}/v1/chunk/hybrid/file",
                    files={"files": (filename, file_bytes)},
                )
                chunk_resp.raise_for_status()
                chunk_data = chunk_resp.json()
                raw_chunks = chunk_data.get("chunks", [])
                for raw in raw_chunks:
                    pages = raw.get("page_numbers") or []
                    chunks.append(ExtractedChunk(
                        text=raw.get("text", ""),
                        chunk_index=raw.get("chunk_index", len(chunks)),
                        page_start=min(pages) if pages else 0,
                        page_end=max(pages) if pages else 0,
                        headings=list(raw.get("headings") or []),
                    ))
            except Exception as e:
                # Hybrid endpoint can 5xx on malformed PDFs or large docs;
                # we still want extraction to succeed via the markdown path.
                logger.warning(
                    f"Docling hybrid chunk failed for {filename}: {e}. "
                    f"Falling back to markdown-only extraction."
                )
                chunks = []

            # Step 2: convert request — full markdown for downstream NER /
            # backwards compatibility with code that consumes the flat text.
            response = await client.post(
                f"{self._url}/v1/convert/file",
                files={"files": (filename, file_bytes)},
            )
            response.raise_for_status()
            data = response.json()

        text = data.get("document", {}).get("md_content", "")
        if not text:
            text = data.get("text", "")
        # If markdown failed but we have chunks, synthesise the text from them
        # so downstream extractors still receive content.
        if not text and chunks:
            text = "\n\n".join(c.text for c in chunks if c.text)

        language = ""
        if text and len(text) > 20:
            try:
                language = detect(text)
            except Exception:
                pass

        page_count = data.get("document", {}).get("num_pages", 0)
        if not page_count and chunks:
            page_count = max((c.page_end for c in chunks), default=0)

        return ExtractionResult(
            text=text,
            language=language,
            metadata={
                "extraction_provider": "docling",
                "extraction_format": "markdown",
                "characters": len(text),
                "pages": page_count,
                "hybrid_chunks_count": len(chunks),
            },
            chunks=chunks or None,
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
