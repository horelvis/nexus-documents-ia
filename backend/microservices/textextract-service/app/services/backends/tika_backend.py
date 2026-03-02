"""
Apache Tika extraction backend.

Extracts plain text via Tika's REST API:
  PUT /tika  → text
  PUT /meta  → metadata (author, title, created)
"""
from __future__ import annotations

import httpx
from loguru import logger

from .base import BackendResult


class TikaBackend:
    """Apache Tika text extraction backend."""

    def __init__(self, tika_url: str, timeout: int = 120) -> None:
        self._tika_url = tika_url
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "tika"

    def extract(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str,
    ) -> BackendResult:
        with httpx.Client(timeout=self._timeout) as client:
            # Extract text
            text_response = client.put(
                f"{self._tika_url}/tika",
                content=file_bytes,
                headers={
                    "Content-Type": content_type,
                    "Accept": "text/plain",
                },
            )
            text_response.raise_for_status()
            extracted_text = text_response.text.strip()

            # Extract metadata
            metadata_response = client.put(
                f"{self._tika_url}/meta",
                content=file_bytes,
                headers={
                    "Content-Type": content_type,
                    "Accept": "application/json",
                },
            )
            raw_meta = {}
            if metadata_response.status_code == 200:
                try:
                    raw_meta = metadata_response.json()
                except Exception:
                    pass

        logger.info(
            "Tika extracted {} chars from {}",
            len(extracted_text),
            filename,
        )

        return BackendResult(
            text=extracted_text,
            metadata={
                "tika_content_type": raw_meta.get("Content-Type", content_type),
                "tika_creator": raw_meta.get("dc:creator") or raw_meta.get("Author"),
                "tika_title": raw_meta.get("dc:title") or raw_meta.get("title"),
                "tika_created": (
                    raw_meta.get("dcterms:created") or raw_meta.get("Creation-Date")
                ),
                "extraction_backend": "tika",
            },
        )

    def health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self._tika_url}/tika", timeout=5)
            return resp.status_code < 500
        except Exception:
            return False
