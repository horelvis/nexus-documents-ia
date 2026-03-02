"""
Service responsible for extracting text from documents.

Supports pluggable backends (Tika, Docling) with automatic fallback.
Validation, MIME detection, and language detection remain in this service —
only the HTTP extraction calls are delegated to backend implementations.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from langdetect import detect, LangDetectException
from loguru import logger

from app.core.config import settings
from app.services.backends.base import ExtractionBackend
from app.services.backends.tika_backend import TikaBackend
from app.services.backends.docling_backend import DoclingBackend


@dataclass
class ExtractionResult:
    """Result of a text extraction operation."""

    text: str
    language: Optional[str]
    metadata: Dict[str, Optional[str]]
    num_characters: int
    content_type: Optional[str]


class TextExtractionError(Exception):
    """Raised when extraction fails."""


def _build_backend(name: str) -> ExtractionBackend:
    """Instantiate a backend by name."""
    if name == "tika":
        return TikaBackend(tika_url=settings.tika_url, timeout=settings.tika_timeout)
    if name == "docling":
        return DoclingBackend(docling_url=settings.docling_url, timeout=settings.docling_timeout)
    raise ValueError(f"Unknown extraction backend: {name!r}")


class TextExtractionService:
    """
    Text extraction service with pluggable backends.

    Backend selection logic:
    - Primary backend is determined by EXTRACTION_BACKEND env var (default: tika)
    - If EXTRACTION_FALLBACK_ENABLED=true and primary is not tika,
      Tika is used as the fallback backend
    - On primary failure, automatically retries with fallback
    """

    def __init__(self) -> None:
        self.allowed_extensions = {ext.lower() for ext in settings.allowed_extensions}

        # Build primary backend
        self._primary = _build_backend(settings.extraction_backend)

        # Build fallback (Tika) only when primary is NOT Tika and fallback is enabled
        self._fallback: Optional[ExtractionBackend] = None
        if (
            settings.extraction_fallback_enabled
            and settings.extraction_backend != "tika"
        ):
            self._fallback = _build_backend("tika")

        logger.info(
            "Extraction backends: primary={}, fallback={}",
            self._primary.name,
            self._fallback.name if self._fallback else "none",
        )

    @property
    def primary_backend_name(self) -> str:
        return self._primary.name

    def _detect_language(self, text: str) -> Optional[str]:
        if not settings.enable_language_detection:
            return None
        sample = text.strip()
        if len(sample) < 20:
            return None
        try:
            return detect(sample)
        except LangDetectException:
            return None

    def _get_content_type(self, filename: str) -> str:
        """Get MIME type based on file extension."""
        ext = os.path.splitext(filename or "")[1].lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".html": "text/html",
            ".odt": "application/vnd.oasis.opendocument.text",
            ".rtf": "application/rtf",
            ".epub": "application/epub+zip",
            ".xml": "application/xml",
            ".json": "application/json",
            # Images - Tika can attempt OCR
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
        }
        return mime_types.get(ext, "application/octet-stream")

    def _detect_mime_from_content(self, file_bytes: bytes) -> Optional[str]:
        """
        Detect MIME type from file content using magic bytes.
        This is more reliable than filename extension.

        Handles cases like "GESTOR.docx.pdf" where the extension is misleading
        but the actual content is a different format.
        """
        if len(file_bytes) < 8:
            return None

        # === Document formats ===

        # PDF
        if file_bytes[:4] == b'%PDF':
            return "application/pdf"

        # ZIP-based formats (DOCX, XLSX, PPTX, ODT, EPUB, etc.)
        if file_bytes[:4] == b'PK\x03\x04':
            sample = file_bytes[:4000]
            if b'word/' in sample or b'[Content_Types].xml' in sample and b'word' in sample:
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if b'xl/' in sample:
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if b'ppt/' in sample:
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if b'mimetype' in file_bytes[:100]:
                if b'opendocument.text' in sample:
                    return "application/vnd.oasis.opendocument.text"
                if b'opendocument.spreadsheet' in sample:
                    return "application/vnd.oasis.opendocument.spreadsheet"
                if b'opendocument.presentation' in sample:
                    return "application/vnd.oasis.opendocument.presentation"
            if b'epub' in sample.lower():
                return "application/epub+zip"
            return None

        # OLE2 Compound Document (DOC, XLS, PPT, MSG)
        if file_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return "application/msword"

        # RTF
        if file_bytes[:5] == b'{\\rtf':
            return "application/rtf"

        # HTML
        if file_bytes[:14] == b'<!DOCTYPE html' or file_bytes[:5].lower() == b'<html':
            return "text/html"

        # XML
        if file_bytes[:5] == b'<?xml':
            return "application/xml"

        # === Image formats (Tika can attempt OCR) ===

        # JPEG
        if file_bytes[:2] == b'\xff\xd8':
            return "image/jpeg"

        # PNG
        if file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"

        # GIF
        if file_bytes[:6] in (b'GIF87a', b'GIF89a'):
            return "image/gif"

        # TIFF (little-endian and big-endian)
        if file_bytes[:4] in (b'II*\x00', b'MM\x00*'):
            return "image/tiff"

        # BMP
        if file_bytes[:2] == b'BM':
            return "image/bmp"

        # Plain text heuristic - if mostly printable ASCII
        if all(32 <= b < 127 or b in (9, 10, 13) for b in file_bytes[:1000]):
            return "text/plain"

        return None

    def _mime_to_ext(self, mime_type: str) -> str:
        """Map MIME type to expected extension (for logging)."""
        mapping = {
            "application/pdf": ".pdf",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/vnd.oasis.opendocument.text": ".odt",
            "application/rtf": ".rtf",
            "text/html": ".html",
            "application/xml": ".xml",
            "text/plain": ".txt",
        }
        return mapping.get(mime_type, "")

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        strategy: str = "auto",  # ignored, kept for API compatibility
    ) -> ExtractionResult:
        """
        Extract text from the provided document bytes.

        IMPORTANT: MIME type is detected from file content (magic bytes), NOT from
        filename extension. This handles misleading filenames like "GESTOR.docx.pdf".

        Args:
            file_bytes: The raw bytes of the document
            filename: Original filename (used for logging, NOT for type detection)
            strategy: Ignored, kept for API compatibility
        """
        if not file_bytes:
            raise TextExtractionError("The provided file is empty.")

        _, ext = os.path.splitext(filename or "")
        ext = ext.lower()

        # PRIORITY 1: Detect MIME type from file content (magic bytes)
        detected_mime = self._detect_mime_from_content(file_bytes)

        if detected_mime:
            expected_ext = self._mime_to_ext(detected_mime)
            if ext and expected_ext and ext != expected_ext:
                logger.info(
                    f"Detected MIME type from content: {detected_mime} "
                    f"(filename extension '{ext}' differs from expected '{expected_ext}' for {filename})"
                )
            content_type = detected_mime
        else:
            if ext and ext not in self.allowed_extensions:
                raise TextExtractionError(f"Unsupported extension '{ext}'.")
            content_type = self._get_content_type(filename)

        if len(file_bytes) > settings.max_file_size_mb * 1024 * 1024:
            raise TextExtractionError("File size exceeds the configured limit.")

        # Try primary backend, then fallback
        backend_result = None
        used_backend = self._primary.name

        try:
            backend_result = self._primary.extract(file_bytes, content_type, filename)
        except Exception as primary_exc:
            logger.warning(
                "Primary backend ({}) failed for {}: {}",
                self._primary.name,
                filename,
                primary_exc,
            )
            if self._fallback:
                logger.info(
                    "Falling back to {} for {}",
                    self._fallback.name,
                    filename,
                )
                try:
                    backend_result = self._fallback.extract(
                        file_bytes, content_type, filename,
                    )
                    used_backend = self._fallback.name
                except Exception as fallback_exc:
                    logger.error(
                        "Fallback backend ({}) also failed for {}: {}",
                        self._fallback.name,
                        filename,
                        fallback_exc,
                    )
                    raise TextExtractionError(
                        f"All backends failed. Primary ({self._primary.name}): {primary_exc}; "
                        f"Fallback ({self._fallback.name}): {fallback_exc}"
                    ) from fallback_exc
            else:
                raise TextExtractionError(
                    f"{self._primary.name} extraction failed: {primary_exc}"
                ) from primary_exc

        extracted_text = backend_result.text
        language = self._detect_language(extracted_text) if extracted_text else None

        logger.info(
            "Extracted {} chars from {} using {}",
            len(extracted_text),
            filename,
            used_backend,
        )

        return ExtractionResult(
            text=extracted_text,
            language=language,
            metadata={
                "file_extension": ext or "",
                **backend_result.metadata,
            },
            num_characters=len(extracted_text),
            content_type=content_type,
        )


# Shared service instance
extraction_service = TextExtractionService()
