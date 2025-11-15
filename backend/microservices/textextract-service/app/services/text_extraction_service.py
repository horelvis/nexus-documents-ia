"""
Service responsible for extracting text using the unstructured library.
"""
from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from langdetect import detect, LangDetectException
from loguru import logger
from unstructured.partition.auto import partition
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.text import partition_text

from app.core.config import settings


@dataclass
class ExtractionResult:
    """Result of a text extraction operation."""

    text: str
    language: Optional[str]
    metadata: Dict[str, Optional[str]]
    num_characters: int
    num_elements: int


class TextExtractionError(Exception):
    """Raised when extraction fails."""


class TextExtractionService:
    """Wrapper around unstructured partitioners."""

    def __init__(self) -> None:
        self.allowed_extensions = {ext.lower() for ext in settings.allowed_extensions}

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

    def _partition(
        self,
        file_path: str,
        file_extension: str,
        strategy: str,
    ) -> List:
        """
        Partition a document into unstructured elements.
        """
        file_extension = file_extension.lower()

        if file_extension == ".pdf":
            strategy = strategy if strategy in {"hi_res", "fast"} else settings.default_strategy
            return partition_pdf(filename=file_path, strategy=strategy)

        if file_extension in {".docx", ".doc"}:
            return partition_docx(filename=file_path)

        if file_extension in {".txt", ".md"}:
            return partition_text(filename=file_path)

        # Fallback to auto partition
        return partition(filename=file_path)

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        strategy: str = "auto",
    ) -> ExtractionResult:
        """
        Extract text from the provided document bytes.
        """
        if not file_bytes:
            raise TextExtractionError("The provided file is empty.")

        _, ext = os.path.splitext(filename or "")
        ext = ext.lower()

        if ext and ext not in self.allowed_extensions:
            raise TextExtractionError(f"Unsupported extension '{ext}'.")

        if len(file_bytes) > settings.max_file_size_mb * 1024 * 1024:
            raise TextExtractionError("File size exceeds the configured limit.")

        # Persist to a temporary file because unstructured expects a path
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext or ".bin") as tmp_file:
            tmp_file.write(file_bytes)
            tmp_file.flush()
            tmp_path = tmp_file.name

        try:
            elements = self._partition(tmp_path, ext or "", strategy)
            texts = [element.text.strip() for element in elements if getattr(element, "text", None)]
            combined_text = "\n\n".join(filter(None, texts)).strip()

            language = self._detect_language(combined_text) if combined_text else None

            metadata = {
                "file_extension": ext or "",
                "strategy": strategy,
            }

            return ExtractionResult(
                text=combined_text,
                language=language,
                metadata=metadata,
                num_characters=len(combined_text),
                num_elements=len(texts),
            )

        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Failed to extract text from %s", filename)
            raise TextExtractionError(str(exc)) from exc
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass


# Shared service instance
extraction_service = TextExtractionService()
