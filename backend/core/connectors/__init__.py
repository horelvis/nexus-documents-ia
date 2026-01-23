"""
Connector Metadata Normalization Layer

This module provides connector-agnostic metadata handling for the SIL.
Each connector type has an adapter that normalizes its metadata to a common schema.

Usage:
    from core.connectors import MetadataAdapterRegistry, NormalizedMetadata

    # Get adapter for a connector type
    adapter = MetadataAdapterRegistry.get_adapter("alfresco")

    # Normalize metadata
    normalized = adapter.normalize(
        document_id="doc-123",
        tenant_id="tenant-456",
        raw_metadata=alfresco_properties,
        file_path="/Sites/legal/contracts/contract_001.pdf"
    )

    # Use normalized metadata
    description = normalized.get_structural_description()
    key_props = normalized.get_key_properties()
"""

from .metadata_schema import (
    MetadataRichness,
    NormalizedMetadata,
    DocumentOrigin,
    TemporalInfo,
    OwnershipInfo,
    ClassificationInfo,
    BusinessProperties,
    PathComponents,
)

from .adapters import (
    MetadataAdapter,
    MetadataAdapterRegistry,
    AlfrescoMetadataAdapter,
    GoogleDriveMetadataAdapter,
    DropboxMetadataAdapter,
    FilesystemMetadataAdapter,
    DatabaseMetadataAdapter,
)

from .adapters.base import PathIntelligence

__all__ = [
    # Schema classes
    "MetadataRichness",
    "NormalizedMetadata",
    "DocumentOrigin",
    "TemporalInfo",
    "OwnershipInfo",
    "ClassificationInfo",
    "BusinessProperties",
    "PathComponents",
    # Adapter base
    "MetadataAdapter",
    "MetadataAdapterRegistry",
    "PathIntelligence",
    # Concrete adapters
    "AlfrescoMetadataAdapter",
    "GoogleDriveMetadataAdapter",
    "DropboxMetadataAdapter",
    "FilesystemMetadataAdapter",
    "DatabaseMetadataAdapter",
]
