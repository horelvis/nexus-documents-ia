"""Pydantic schemas for Data Learning System.

The Data Learning System allows Emma to learn the nature of data from connectors:
- Content model discovery (types, aspects, properties)
- Folder structure semantic analysis
- Property-to-field mappings with search weights
- Relationship types for Knowledge Graph
- Indexing strategy optimization
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class DiscoveryMethod(str, Enum):
    """Methods for discovering content model."""
    API = "api"  # Via connector API (Dictionary API for Alfresco)
    SAMPLING = "sampling"  # Inferred from document samples
    MANUAL = "manual"  # Manually configured


class LevelSemanticType(str, Enum):
    """Types of semantic meaning for folder levels."""
    FIXED = "fixed"  # Fixed value (e.g., "documentLibrary")
    SITE_IDENTIFIER = "site_identifier"  # Site name
    CLASSIFICATION = "classification"  # Category (department, project)
    TEMPORAL = "temporal"  # Date-based (year, month)
    USER = "user"  # User-specific folder
    DOCUMENT_TYPE = "document_type"  # Type of documents


class RelationshipCategory(str, Enum):
    """Categories of relationships."""
    PEER = "peer"  # Bidirectional relationship
    CHILD = "child"  # Hierarchical (parent-child)
    REFERENCE = "reference"  # Unidirectional reference


class ChunkingType(str, Enum):
    """Types of document chunking strategies."""
    SEMANTIC = "semantic"  # Semantic boundaries
    FIXED_SIZE = "fixed_size"  # Fixed character/token count
    LEGAL_SECTIONS = "legal_sections"  # Legal document sections
    MARKDOWN_HEADERS = "markdown_headers"  # By markdown headers
    PAGE_BASED = "page_based"  # By page boundaries


class DataLearningJobType(str, Enum):
    """Types of learning jobs."""
    CONTENT_MODEL_DISCOVERY = "content_model_discovery"
    FOLDER_ANALYSIS = "folder_analysis"
    PROPERTY_MAPPING = "property_mapping"
    RELATIONSHIP_LEARNING = "relationship_learning"
    STRATEGY_OPTIMIZATION = "strategy_optimization"
    FULL_LEARNING = "full_learning"


class DataLearningJobStatus(str, Enum):
    """Status of learning jobs."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobTriggerType(str, Enum):
    """How the job was triggered."""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    CONNECTOR_CREATED = "connector_created"
    CONNECTOR_UPDATED = "connector_updated"


# =============================================================================
# Content Model Schemas
# =============================================================================

class ContentTypeDefinition(BaseModel):
    """Definition of a content type from the connector."""
    name: str = Field(..., description="Type name (e.g., cm:content, gdapm:expediente)")
    title: Optional[str] = Field(None, description="Human-readable title")
    parent: Optional[str] = Field(None, description="Parent type name")
    properties: List[str] = Field(default_factory=list, description="Property names")
    mandatory_aspects: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class AspectDefinition(BaseModel):
    """Definition of an aspect from the connector."""
    name: str = Field(..., description="Aspect name (e.g., cm:titled)")
    title: Optional[str] = None
    properties: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class PropertyDefinition(BaseModel):
    """Definition of a property from the connector."""
    name: str = Field(..., description="Property name (e.g., cm:title)")
    data_type: str = Field(..., description="Data type (d:text, d:datetime, etc.)")
    mandatory: bool = False
    multi_valued: bool = False
    constraints: Optional[List[Dict[str, Any]]] = None
    default_value: Optional[str] = None


class TypeSemantic(BaseModel):
    """LLM-enriched semantic information for a content type."""
    semantic_type: str = Field(..., description="Normalized type (e.g., administrative_file)")
    domain: str = Field(..., description="Domain (legal, hr, finance, general)")
    description: Optional[str] = None
    chunking_strategy: Optional[ChunkingType] = None
    importance: float = Field(default=1.0, ge=0, le=2.0)


class PropertySemantic(BaseModel):
    """Semantic information for a property."""
    search_weight: float = Field(default=1.0, ge=0, le=5.0)
    include_in_embedding: bool = True
    is_identifier: bool = False
    is_date_field: bool = False
    normalized_name: Optional[str] = None


class ConnectorContentModelResponse(BaseModel):
    """Response schema for connector content model."""
    id: UUID
    connector_id: UUID

    # Raw model
    content_types: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    aspects: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    property_definitions: Optional[Dict[str, Dict[str, Any]]] = None
    association_types: Optional[Dict[str, Dict[str, Any]]] = None

    # Enriched semantics
    type_semantics: Optional[Dict[str, TypeSemantic]] = None
    property_semantics: Optional[Dict[str, PropertySemantic]] = None

    # Metadata
    discovery_method: DiscoveryMethod
    discovered_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ContentModelSummary(BaseModel):
    """Summary of discovered content model."""
    total_types: int = 0
    total_aspects: int = 0
    total_properties: int = 0
    total_associations: int = 0
    custom_types: List[str] = Field(default_factory=list)
    semantic_domains: List[str] = Field(default_factory=list)


# =============================================================================
# Folder Pattern Schemas
# =============================================================================

class LevelSemantic(BaseModel):
    """Semantic meaning of a folder level."""
    name: str = Field(..., description="Semantic name (e.g., department, year)")
    type: LevelSemanticType
    values: Optional[List[str]] = Field(None, description="Known values for classification")
    format: Optional[str] = Field(None, description="Format pattern (e.g., YYYY for year)")


class LearnedFolderPatternCreate(BaseModel):
    """Schema for creating a folder pattern."""
    path_pattern: str = Field(..., description="Pattern with placeholders")
    level_semantics: Dict[str, LevelSemantic] = Field(..., description="Level index to semantic")
    example_paths: Optional[List[str]] = None
    is_verified: bool = False


class LearnedFolderPatternUpdate(BaseModel):
    """Schema for updating a folder pattern."""
    path_pattern: Optional[str] = None
    level_semantics: Optional[Dict[str, LevelSemantic]] = None
    is_verified: Optional[bool] = None


class LearnedFolderPatternResponse(BaseModel):
    """Response schema for folder pattern."""
    id: UUID
    connector_id: UUID
    path_pattern: str
    level_semantics: Dict[str, Dict[str, Any]]
    example_paths: Optional[List[str]] = None
    match_count: int
    confidence: float
    learned_from_sample_size: Optional[int] = None
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FolderContext(BaseModel):
    """Extracted folder context for a document path."""
    path: str
    pattern_id: Optional[UUID] = None
    semantics: Dict[str, Any] = Field(default_factory=dict)
    # Example: {"department": "RRHH", "year": "2024", "classification": "expedientes"}
    confidence: float = 0.0


# =============================================================================
# Property Mapping Schemas
# =============================================================================

class LearnedPropertyMappingCreate(BaseModel):
    """Schema for creating a property mapping."""
    source_property: str = Field(..., description="Connector property name")
    source_type: Optional[str] = Field(None, description="Applies to this type only")
    target_field: str = Field(..., description="Normalized field name")
    search_weight: float = Field(default=1.0, ge=0, le=5.0)
    include_in_embedding: bool = True
    is_filterable: bool = False
    is_facetable: bool = False
    transformation: Optional[str] = None
    default_value: Optional[str] = None


class LearnedPropertyMappingUpdate(BaseModel):
    """Schema for updating a property mapping."""
    target_field: Optional[str] = None
    search_weight: Optional[float] = Field(None, ge=0, le=5.0)
    include_in_embedding: Optional[bool] = None
    is_filterable: Optional[bool] = None
    is_facetable: Optional[bool] = None
    transformation: Optional[str] = None
    default_value: Optional[str] = None


class LearnedPropertyMappingResponse(BaseModel):
    """Response schema for property mapping."""
    id: UUID
    connector_id: UUID
    source_property: str
    source_type: Optional[str] = None
    target_field: str
    search_weight: float
    include_in_embedding: bool
    is_filterable: bool
    is_facetable: bool
    transformation: Optional[str] = None
    default_value: Optional[str] = None
    learned_from_usage: bool
    usage_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Relationship Type Schemas
# =============================================================================

class LearnedRelationshipTypeCreate(BaseModel):
    """Schema for creating a relationship type mapping."""
    source_relationship: str = Field(..., description="Connector relationship name")
    relationship_category: RelationshipCategory
    kg_edge_type: str = Field(..., description="Knowledge Graph edge type")
    description: Optional[str] = None
    include_in_retrieval: bool = True
    expansion_depth: int = Field(default=1, ge=1, le=3)
    weight: float = Field(default=1.0, ge=0, le=2.0)


class LearnedRelationshipTypeUpdate(BaseModel):
    """Schema for updating a relationship type mapping."""
    kg_edge_type: Optional[str] = None
    description: Optional[str] = None
    include_in_retrieval: Optional[bool] = None
    expansion_depth: Optional[int] = Field(None, ge=1, le=3)
    weight: Optional[float] = Field(None, ge=0, le=2.0)


class LearnedRelationshipTypeResponse(BaseModel):
    """Response schema for relationship type."""
    id: UUID
    connector_id: UUID
    source_relationship: str
    relationship_category: RelationshipCategory
    kg_edge_type: str
    description: Optional[str] = None
    include_in_retrieval: bool
    expansion_depth: int
    weight: float
    instance_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Indexing Strategy Schemas
# =============================================================================

class ChunkingConfig(BaseModel):
    """Configuration for document chunking."""
    target_chunk_size: int = Field(default=512, ge=100, le=4000)
    overlap: int = Field(default=50, ge=0, le=500)
    section_markers: Optional[List[str]] = None  # For legal_sections
    header_levels: Optional[List[int]] = None  # For markdown_headers


class ConnectorIndexingStrategyCreate(BaseModel):
    """Schema for creating an indexing strategy."""
    document_type: Optional[str] = Field(None, description="Applies to this type")
    mime_type_pattern: Optional[str] = Field(None, description="MIME type pattern")
    chunking_type: ChunkingType = ChunkingType.SEMANTIC
    chunking_config: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding_fields: List[str] = Field(default_factory=lambda: ["content", "title"])
    embedding_weights: Optional[Dict[str, float]] = None
    extract_entities: bool = True
    entity_types: Optional[List[str]] = None
    extract_to_knowledge_graph: bool = True
    priority: int = Field(default=0, ge=0, le=100)
    is_active: bool = True


class ConnectorIndexingStrategyUpdate(BaseModel):
    """Schema for updating an indexing strategy."""
    chunking_type: Optional[ChunkingType] = None
    chunking_config: Optional[ChunkingConfig] = None
    embedding_fields: Optional[List[str]] = None
    embedding_weights: Optional[Dict[str, float]] = None
    extract_entities: Optional[bool] = None
    entity_types: Optional[List[str]] = None
    extract_to_knowledge_graph: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None


class ConnectorIndexingStrategyResponse(BaseModel):
    """Response schema for indexing strategy."""
    id: UUID
    connector_id: UUID
    document_type: Optional[str] = None
    mime_type_pattern: Optional[str] = None
    chunking_type: ChunkingType
    chunking_config: Dict[str, Any]
    embedding_fields: List[str]
    embedding_weights: Optional[Dict[str, float]] = None
    extract_entities: bool
    entity_types: Optional[List[str]] = None
    extract_to_knowledge_graph: bool
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Learning Job Schemas
# =============================================================================

class DataLearningJobCreate(BaseModel):
    """Schema for creating a learning job."""
    job_type: DataLearningJobType
    config: Optional[Dict[str, Any]] = None


class DataLearningJobResponse(BaseModel):
    """Response schema for learning job."""
    id: UUID
    connector_id: UUID
    job_type: DataLearningJobType
    status: DataLearningJobStatus
    status_message: Optional[str] = None
    progress_percent: int
    current_phase: Optional[str] = None
    results_summary: Optional[Dict[str, Any]] = None
    errors: Optional[List[Dict[str, Any]]] = None
    config: Optional[Dict[str, Any]] = None
    triggered_by: JobTriggerType
    triggered_by_user_id: Optional[UUID] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DataLearningJobListResponse(BaseModel):
    """Paginated list of learning jobs."""
    items: List[DataLearningJobResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Learned Context Schema (for indexed documents)
# =============================================================================

class LearnedContext(BaseModel):
    """
    Normalized context learned from connector data.

    This is stored in indexed_documents.learned_context and provides
    connector-agnostic semantic information for RAG retrieval.
    """
    semantic_type: Optional[str] = Field(None, description="Normalized document type")
    domain: Optional[str] = Field(None, description="Domain (legal, hr, finance)")
    folder_semantics: Dict[str, Any] = Field(default_factory=dict)
    # Example: {"department": "RRHH", "year": "2024", "classification": "expedientes"}

    property_weights: Dict[str, float] = Field(default_factory=dict)
    # Example: {"identifier": 2.0, "title": 1.5}

    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    # Example: [{"type": "references", "target_id": "...", "strength": 0.8}]

    source_connector_type: Optional[str] = None
    # alfresco, sharepoint, etc.


# =============================================================================
# API Request/Response Schemas
# =============================================================================

class TriggerLearningRequest(BaseModel):
    """Request to trigger learning for a connector."""
    job_type: DataLearningJobType = DataLearningJobType.FULL_LEARNING
    force_rediscovery: bool = Field(
        default=False,
        description="Force re-discovery even if model exists"
    )
    config: Optional[Dict[str, Any]] = None


class TriggerLearningResponse(BaseModel):
    """Response from triggering learning."""
    job_id: UUID
    connector_id: UUID
    job_type: DataLearningJobType
    status: DataLearningJobStatus
    message: str


class ConnectorLearningStatusResponse(BaseModel):
    """Overall learning status for a connector."""
    connector_id: UUID
    connector_name: str

    # Content model status
    has_content_model: bool = False
    content_model_discovered_at: Optional[datetime] = None
    content_model_summary: Optional[ContentModelSummary] = None

    # Folder patterns status
    folder_patterns_count: int = 0
    verified_patterns_count: int = 0

    # Property mappings status
    property_mappings_count: int = 0
    custom_mappings_count: int = 0

    # Relationship types status
    relationship_types_count: int = 0

    # Indexing strategies status
    indexing_strategies_count: int = 0
    active_strategies_count: int = 0

    # Latest job
    latest_job: Optional[DataLearningJobResponse] = None

    # Recommendations
    recommendations: List[str] = Field(default_factory=list)
    # Example: ["Run folder analysis to improve context", "Review property mappings"]


class BulkPropertyMappingUpdate(BaseModel):
    """Bulk update for property mappings."""
    mappings: List[LearnedPropertyMappingUpdate]


class ApplyFolderContextRequest(BaseModel):
    """Request to apply folder context to a document path."""
    path: str = Field(..., description="Document path to analyze")


# =============================================================================
# TOON Serialization Schema (for Emma context)
# =============================================================================

class TOONLearnedContext(BaseModel):
    """
    TOON-optimized learned context for Emma.

    TOON (Token-Oriented Object Notation) reduces token usage by 30-60%
    compared to JSON when passed to LLMs.
    """
    st: Optional[str] = Field(None, alias="semantic_type")
    d: Optional[str] = Field(None, alias="domain")
    fs: Dict[str, str] = Field(default_factory=dict, alias="folder_semantics")
    pw: Dict[str, float] = Field(default_factory=dict, alias="property_weights")

    class Config:
        populate_by_name = True

    def to_toon_string(self) -> str:
        """Convert to TOON format string for LLM context."""
        lines = ["learned_context"]
        if self.st:
            lines.append(f"  semantic_type: {self.st}")
        if self.d:
            lines.append(f"  domain: {self.d}")
        if self.fs:
            lines.append("  folder_semantics")
            for k, v in self.fs.items():
                lines.append(f"    {k}: {v}")
        return "\n".join(lines)
