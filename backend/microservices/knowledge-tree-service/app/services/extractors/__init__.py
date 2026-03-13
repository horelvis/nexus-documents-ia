"""Entity and reference extraction services."""

from .legal_reference_extractor import (
    LegalReferenceExtractor,
    legal_reference_extractor,
    LegalReferences,
    ArticleRef,
    Modification,
    Derogation,
    BOEAnalysis,
)

__all__ = [
    "LegalReferenceExtractor",
    "legal_reference_extractor",
    "LegalReferences",
    "ArticleRef",
    "Modification",
    "Derogation",
    "BOEAnalysis",
]
