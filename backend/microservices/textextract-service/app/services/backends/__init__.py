"""
Extraction backends package.

Provides pluggable backends for document text extraction:
- TikaBackend: Apache Tika (default, plain text)
- DoclingBackend: IBM Docling (AI-powered, structured Markdown)
"""

from .base import ExtractionBackend, BackendResult
from .tika_backend import TikaBackend
from .docling_backend import DoclingBackend

__all__ = [
    "ExtractionBackend",
    "BackendResult",
    "TikaBackend",
    "DoclingBackend",
]
