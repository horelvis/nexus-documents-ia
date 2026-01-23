"""
Normalized Metadata Schema for Connector-Agnostic SIL Integration

This module defines a tiered metadata structure that works across all connector types,
from metadata-rich systems (Alfresco, SharePoint) to metadata-poor systems (filesystem,
basic database storage).

The key insight is that different connectors provide vastly different metadata:
- Alfresco: Rich custom properties, content models, aspects, categories
- Google Drive: Labels, properties, basic metadata
- Dropbox: Basic file info, shared status
- Filesystem: Path, timestamps, permissions (POSIX)
- Database: Just a blob with filename

The SIL (Structural Intelligence Layer) needs to work with all of these by:
1. Normalizing metadata to a common schema
2. Tracking what level of metadata is available
3. Inferring missing metadata from paths and patterns when needed
"""

from enum import IntEnum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class MetadataRichness(IntEnum):
    """
    Levels of metadata richness, from poorest to richest.

    This determines what inference strategies the SIL should use:
    - DATABASE/MINIMAL: Heavy path inference, pattern matching
    - BASIC: Moderate inference, use what's available
    - RICH: Trust the metadata, minimal inference needed
    """
    DATABASE = 0      # Just blob + filename
    MINIMAL = 1       # Path + timestamps + basic file info
    BASIC = 2         # Above + categories, labels, basic properties
    RICH = 3          # Full content model, custom properties, aspects


class DocumentOrigin(BaseModel):
    """Where the document came from - connector-agnostic."""
    connector_type: str  # alfresco, google_drive, dropbox, filesystem, database
    connector_id: Optional[str] = None
    external_id: str  # ID in the source system
    external_path: Optional[str] = None  # Full path in source system
    sync_timestamp: datetime = Field(default_factory=datetime.utcnow)


class TemporalInfo(BaseModel):
    """Time-related metadata - universally available."""
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    accessed_at: Optional[datetime] = None
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
    version_number: Optional[int] = None
    version_label: Optional[str] = None


class OwnershipInfo(BaseModel):
    """Ownership and permissions - varies by connector."""
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    last_modifier_id: Optional[str] = None
    last_modifier_name: Optional[str] = None
    # ACL fields (for on-premise connectors)
    is_public: bool = False
    shared_with_users: List[str] = Field(default_factory=list)
    shared_with_groups: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class ClassificationInfo(BaseModel):
    """Document classification - may be from metadata or inferred."""
    # Semantic type (contract, invoice, report, email, etc.)
    semantic_type: Optional[str] = None
    semantic_type_confidence: float = 0.0  # 0-1, how sure are we?
    semantic_type_source: str = "unknown"  # "metadata", "path_inference", "ml_classification"

    # Business domain (legal, hr, finance, etc.)
    domain: Optional[str] = None
    domain_confidence: float = 0.0
    domain_source: str = "unknown"

    # Categories and tags
    categories: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # Content model (Alfresco-specific but normalized)
    content_model: Optional[str] = None  # e.g., "exp:expediente"
    aspects: List[str] = Field(default_factory=list)  # e.g., ["exp:documentoExpediente"]


class BusinessProperties(BaseModel):
    """Business-specific properties extracted from rich metadata systems."""
    # Common properties across systems
    client_name: Optional[str] = None
    client_id: Optional[str] = None
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    department: Optional[str] = None

    # Document-specific
    reference_number: Optional[str] = None  # Contract number, invoice number, etc.
    status: Optional[str] = None  # draft, approved, archived, etc.

    # Dates
    effective_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None

    # Financial
    amount: Optional[float] = None
    currency: Optional[str] = None

    # Custom properties (key-value for anything else)
    custom: Dict[str, Any] = Field(default_factory=dict)


class PathComponents(BaseModel):
    """Parsed path components for inference."""
    full_path: str
    filename: str
    extension: Optional[str] = None
    parent_folder: Optional[str] = None
    folder_chain: List[str] = Field(default_factory=list)  # All folders from root
    depth: int = 0

    # Inferred from path
    year_from_path: Optional[int] = None
    month_from_path: Optional[int] = None
    client_from_path: Optional[str] = None
    project_from_path: Optional[str] = None


class NormalizedMetadata(BaseModel):
    """
    Connector-agnostic metadata schema for SIL.

    This is the common format that all connector adapters produce.
    The SIL works with this format regardless of source system.
    """
    # Core identification
    document_id: str
    tenant_id: str

    # Metadata richness indicator
    richness_level: MetadataRichness = MetadataRichness.MINIMAL

    # Origin information (always available)
    origin: DocumentOrigin

    # Path components (always available)
    path: PathComponents

    # File information (usually available)
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

    # Temporal information (usually available)
    temporal: TemporalInfo = Field(default_factory=TemporalInfo)

    # Ownership (varies)
    ownership: OwnershipInfo = Field(default_factory=OwnershipInfo)

    # Classification (may be inferred)
    classification: ClassificationInfo = Field(default_factory=ClassificationInfo)

    # Business properties (rich systems only)
    business: BusinessProperties = Field(default_factory=BusinessProperties)

    # Raw source metadata (for debugging/audit)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_structural_description(self) -> str:
        """
        Generate a structural description for embedding.

        This is what gets embedded in the SIL StructuralDocument collection.
        It describes WHERE and WHAT TYPE the document is, not its content.
        """
        parts = []

        # Location description
        if self.path.folder_chain:
            location = " > ".join(self.path.folder_chain[-3:])  # Last 3 folders
            parts.append(f"Located in: {location}")

        # Type description
        if self.classification.semantic_type:
            type_desc = f"Type: {self.classification.semantic_type}"
            if self.classification.semantic_type_confidence < 0.8:
                type_desc += " (inferred)"
            parts.append(type_desc)

        # Domain description
        if self.classification.domain:
            parts.append(f"Domain: {self.classification.domain}")

        # Business context (if rich metadata)
        if self.richness_level >= MetadataRichness.BASIC:
            if self.business.client_name:
                parts.append(f"Client: {self.business.client_name}")
            if self.business.project_name:
                parts.append(f"Project: {self.business.project_name}")
            if self.business.reference_number:
                parts.append(f"Reference: {self.business.reference_number}")

        # Temporal context
        if self.temporal.created_at:
            year = self.temporal.created_at.year
            parts.append(f"Year: {year}")
        elif self.path.year_from_path:
            parts.append(f"Year: {self.path.year_from_path} (from path)")

        # Content model (for Alfresco)
        if self.classification.content_model:
            parts.append(f"Content Model: {self.classification.content_model}")

        # Categories
        if self.classification.categories:
            parts.append(f"Categories: {', '.join(self.classification.categories[:5])}")

        return ". ".join(parts) if parts else f"Document: {self.path.filename}"

    def get_key_properties(self) -> Dict[str, Any]:
        """
        Extract key properties for SIL indexing.

        These are the filterable properties in the StructuralDocument collection.
        """
        props = {
            "filename": self.path.filename,
            "extension": self.path.extension,
            "folder": self.path.parent_folder,
            "semantic_type": self.classification.semantic_type,
            "domain": self.classification.domain,
            "richness_level": self.richness_level.name,
        }

        # Add year
        if self.temporal.created_at:
            props["year"] = self.temporal.created_at.year
        elif self.path.year_from_path:
            props["year"] = self.path.year_from_path

        # Add client if available
        if self.business.client_name:
            props["client"] = self.business.client_name
        elif self.path.client_from_path:
            props["client"] = self.path.client_from_path

        # Add reference number if available
        if self.business.reference_number:
            props["reference_number"] = self.business.reference_number

        return {k: v for k, v in props.items() if v is not None}
