"""
IBM Docling extraction backend.

Uses Docling Serve's REST API for AI-powered document understanding:
  POST /v1/convert/file  → structured Markdown with headers, tables, lists

Key advantages over Tika:
- 97.9% table accuracy (vs Tika's ~0% for complex tables)
- Preserves document structure as Markdown headers
- AI-based layout analysis preserves reading order

Output format is Markdown, which the SemanticChunker can leverage
for better section detection (## headers instead of regex heuristics).
"""
from __future__ import annotations

import httpx
from loguru import logger

from .base import BackendResult


class DoclingBackend:
    """IBM Docling document understanding backend."""

    def __init__(self, docling_url: str, timeout: int = 300) -> None:
        self._docling_url = docling_url
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "docling"

    def extract(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str,
    ) -> BackendResult:
        """
        Convert document to Markdown via Docling Serve.

        Docling Serve API (v1):
          POST /v1/convert/file
          - multipart: files=@doc.pdf
          - form fields: to_formats, ocr_engine, ocr_lang
          - returns JSON with document.md_content
        """
        # Docling Serve defaults are already optimal:
        #   to_formats=["md"], do_ocr=true, ocr_engine=easyocr
        # We send just the file — defaults handle the rest.
        # Note: httpx can't mix `files=` and `data=` as list-of-tuples,
        # so we rely on Docling's defaults which are already correct.
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._docling_url}/v1/convert/file",
                files={"files": (filename, file_bytes, content_type)},
            )
            response.raise_for_status()
            result = response.json()

        # Extract markdown content from response
        document = result.get("document", {})
        md_content = document.get("md_content", "")

        if not md_content:
            raise ValueError(
                f"Docling returned empty markdown for {filename}. "
                f"Response keys: {list(result.keys())}"
            )

        # Build metadata — keep tika_* keys for downstream compatibility
        doc_meta = document.get("metadata", {}) if isinstance(document.get("metadata"), dict) else {}
        page_count = document.get("page_count") or doc_meta.get("page_count")

        logger.info(
            "Docling extracted {} chars (markdown) from {}, pages={}",
            len(md_content),
            filename,
            page_count or "unknown",
        )

        return BackendResult(
            text=md_content,
            metadata={
                # Compatibility keys (mapped from Docling metadata when available)
                "tika_content_type": content_type,
                "tika_creator": doc_meta.get("author"),
                "tika_title": doc_meta.get("title"),
                "tika_created": doc_meta.get("created"),
                # Docling-specific keys
                "extraction_backend": "docling",
                "extraction_format": "markdown",
                "docling_page_count": str(page_count) if page_count else None,
            },
        )

    def health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self._docling_url}/health", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False
