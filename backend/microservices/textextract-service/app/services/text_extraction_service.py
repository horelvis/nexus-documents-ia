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
        }
        return mime_types.get(ext, "application/octet-stream")

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        strategy: str = "auto",  # ignored, kept for API compatibility
    ) -> ExtractionResult:
        """
        Extract text from the provided document bytes using Apache Tika.
        """
        if not file_bytes:
            raise TextExtractionError("The provided file is empty.")

        _, ext = os.path.splitext(filename or "")
        ext = ext.lower()

        if ext and ext not in self.allowed_extensions:
            raise TextExtractionError(f"Unsupported extension '{ext}'.")

        if len(file_bytes) > settings.max_file_size_mb * 1024 * 1024:
            raise TextExtractionError("File size exceeds the configured limit.")

        content_type = self._get_content_type(filename)

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
