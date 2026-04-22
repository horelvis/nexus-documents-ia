"""
Schemas for Knowledge Extraction Service.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class EntityType(str, Enum):
    """Types of knowledge entities that can be extracted."""
    PERSON = "person"
    ORGANIZATION = "organization"
    CLAUSE = "clause"
    TERM = "term"
    DATE = "date"
    AMOUNT = "amount"
    LOCATION = "location"
    CONCEPT = "concept"
    OBLIGATION = "obligation"
    RIGHT = "right"
    REFERENCE = "reference"


class RelationshipType(str, Enum):
    """Types of relationships between entities."""
    MENTIONS = "mentions"
    DEFINES = "defines"
    RELATES_TO = "relates_to"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    PART_OF = "part_of"
    BELONGS_TO = "belongs_to"
    INVOLVES = "involves"
    REFERENCES = "references"


class KnowledgeEntity(BaseModel):
    """A knowledge entity extracted from a document."""

    # Required fields
    entity_type: EntityType
    entity_value: str = Field(..., description="Normalized value of the entity")
    context_text: str = Field(..., description="Surrounding context for embedding")

    # Optional identification
    entity_label: Optional[str] = Field(None, description="Human-readable label")

    # Source information
    source_document_id: Optional[str] = None
    extraction_confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    # Additional attributes specific to the entity type
    attributes: Dict[str, Any] = Field(default_factory=dict)

    # Position in source document (if available)
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page_number: Optional[int] = None

    class Config:
        use_enum_values = True


class KnowledgeRelationship(BaseModel):
    """A relationship between two knowledge entities."""

    source_entity_value: str
    target_entity_value: str
    relationship_type: RelationshipType
    relationship_strength: float = Field(default=0.5, ge=0.0, le=1.0)

    # Context where the relationship was found
    context_snippet: Optional[str] = None
    source_document_id: Optional[str] = None

    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class KnowledgeExtractionResult(BaseModel):
    """Result of knowledge extraction from a document."""

    document_id: str

    # Extracted knowledge
    entities: List[KnowledgeEntity] = Field(default_factory=list)
    relationships: List[KnowledgeRelationship] = Field(default_factory=list)

    # Statistics
    entities_count: int = 0
    relationships_count: int = 0

    # Processing info
    processing_time_ms: int = 0
    extraction_method: str = "langextract"  # langextract, llm, hybrid

    # Status
    success: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EntityNormalizationConfig(BaseModel):
    """Configuration for entity normalization."""

    # Deduplication settings
    enable_deduplication: bool = True
    similarity_threshold: float = 0.85

    # Type classification
    auto_classify_types: bool = True

    # Context extraction
    context_chars_before: int = 100
    context_chars_after: int = 100


class RelationshipDetectionConfig(BaseModel):
    """Configuration for relationship detection."""

    # Detection methods
    use_cooccurrence: bool = True
    use_llm: bool = True

    # Thresholds
    min_confidence: float = 0.5
    max_relationships_per_entity: int = 10

    # LLM settings
    llm_model: str = "default"
    llm_temperature: float = 0.1


class KnowledgeExtractionConfig(BaseModel):
    """Full configuration for knowledge extraction."""

    normalization: EntityNormalizationConfig = Field(default_factory=EntityNormalizationConfig)
    relationship_detection: RelationshipDetectionConfig = Field(default_factory=RelationshipDetectionConfig)

    # General settings
    max_entities_per_document: int = 100
    max_relationships_per_document: int = 200

    # Storage
    store_in_postgresql: bool = True
    store_in_weaviate: bool = True

    # Processing
    batch_size: int = 10
    timeout_seconds: int = 60
