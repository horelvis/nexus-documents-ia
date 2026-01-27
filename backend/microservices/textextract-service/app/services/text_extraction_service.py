"""
Service responsible for extracting text using Apache Tika.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

import httpx
from langdetect import detect, LangDetectException
from loguru import logger

from app.core.config import settings


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


class TextExtractionService:
    """Text extraction service using Apache Tika."""

    def __init__(self) -> None:
        self.allowed_extensions = {ext.lower() for ext in settings.allowed_extensions}
        self.tika_url = settings.tika_url
        self.timeout = settings.tika_timeout

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
        Extract text from the provided document bytes using Apache Tika.

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
        # This is the authoritative source - ignores misleading filename extensions
        detected_mime = self._detect_mime_from_content(file_bytes)

        if detected_mime:
            # We detected the actual content type - use it regardless of extension
            expected_ext = self._mime_to_ext(detected_mime)
            if ext and expected_ext and ext != expected_ext:
                logger.info(
                    f"Detected MIME type from content: {detected_mime} "
                    f"(filename extension '{ext}' differs from expected '{expected_ext}' for {filename})"
                )
            content_type = detected_mime
        else:
            # Could not detect from content - fall back to extension validation
            if ext and ext not in self.allowed_extensions:
                raise TextExtractionError(f"Unsupported extension '{ext}'.")
            content_type = self._get_content_type(filename)

        if len(file_bytes) > settings.max_file_size_mb * 1024 * 1024:
            raise TextExtractionError("File size exceeds the configured limit.")

        try:
            # Call Apache Tika for text extraction
            with httpx.Client(timeout=self.timeout) as client:
                # Extract text
                text_response = client.put(
                    f"{self.tika_url}/tika",
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
                    f"{self.tika_url}/meta",
                    content=file_bytes,
                    headers={
                        "Content-Type": content_type,
                        "Accept": "application/json",
                    },
                )
                metadata = {}
                if metadata_response.status_code == 200:
                    try:
                        metadata = metadata_response.json()
                    except Exception:
                        pass

            language = self._detect_language(extracted_text) if extracted_text else None

            logger.info(
                f"Extracted {len(extracted_text)} characters from {filename} using Tika"
            )

            return ExtractionResult(
                text=extracted_text,
                language=language,
                metadata={
                    "file_extension": ext or "",
                    "tika_content_type": metadata.get("Content-Type", content_type),
                    "tika_creator": metadata.get("dc:creator") or metadata.get("Author"),
                    "tika_title": metadata.get("dc:title") or metadata.get("title"),
                    "tika_created": metadata.get("dcterms:created") or metadata.get("Creation-Date"),
                },
                num_characters=len(extracted_text),
                content_type=content_type,
            )

        except httpx.TimeoutException as exc:
            logger.error(f"Tika timeout extracting {filename}: {exc}")
            raise TextExtractionError(f"Tika timeout: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            logger.error(f"Tika HTTP error extracting {filename}: {exc}")
            raise TextExtractionError(f"Tika error: {exc.response.status_code}") from exc
        except Exception as exc:
            logger.exception(f"Failed to extract text from {filename}")
            raise TextExtractionError(str(exc)) from exc


# Shared service instance
extraction_service = TextExtractionService()
