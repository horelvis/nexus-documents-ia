"""
Base protocol for extraction backends.

Each backend must implement extract() and health_check().
Using Protocol (structural subtyping) so backends don't need to inherit —
they just need to match the shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, runtime_checkable


@dataclass
class BackendResult:
    """Unified result returned by any extraction backend."""

    text: str
    metadata: Dict[str, Optional[str]] = field(default_factory=dict)


@runtime_checkable
class ExtractionBackend(Protocol):
    """Protocol that all extraction backends must satisfy."""

    @property
    def name(self) -> str:
        """Human-readable backend name (e.g. 'tika', 'docling')."""
        ...

    def extract(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str,
    ) -> BackendResult:
        """
        Extract text and metadata from file bytes.

        Args:
            file_bytes: Raw document bytes.
            content_type: MIME type detected from magic bytes.
            filename: Original filename (for logging).

        Returns:
            BackendResult with extracted text and metadata.

        Raises:
            Exception on failure (caller handles fallback).
        """
        ...

    def health_check(self) -> bool:
        """Return True if the backend service is reachable."""
        ...
