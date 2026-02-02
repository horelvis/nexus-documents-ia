"""
SIL (Structural Intelligence Layer)

Legal graph service for public knowledge graph (Apache AGE).
"""

from .legal_graph_service import (
    legal_graph,
    LegalGraphService,
    LegalLaw,
    LegalDomain,
    LawStatus,
)

__all__ = [
    "legal_graph",
    "LegalGraphService",
    "LegalLaw",
    "LegalDomain",
    "LawStatus",
]
