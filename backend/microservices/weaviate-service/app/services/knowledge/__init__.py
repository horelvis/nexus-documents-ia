"""
Knowledge Extraction Service for Emma AI.

Extracts structured knowledge from documents to build a knowledge graph.
"""

from .extraction_service import KnowledgeExtractionService, get_knowledge_service
from .schemas import (
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeExtractionResult,
    EntityType,
    RelationshipType,
    DomainType
)

__all__ = [
    "KnowledgeExtractionService",
    "get_knowledge_service",
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "KnowledgeExtractionResult",
    "EntityType",
    "RelationshipType",
    "DomainType",
]
