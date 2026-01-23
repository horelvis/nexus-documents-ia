"""
Metadata Adapters for Connector-Agnostic SIL Integration

Each adapter knows how to extract and normalize metadata from its source system.

Supported connectors:
- Alfresco (MetadataRichness.RICH)
- Google Drive (MetadataRichness.BASIC)
- Dropbox (MetadataRichness.MINIMAL)
- Filesystem (MetadataRichness.MINIMAL)
- Database (MetadataRichness.DATABASE)
"""

from .base import MetadataAdapter, MetadataAdapterRegistry
from .alfresco import AlfrescoMetadataAdapter
from .google_drive import GoogleDriveMetadataAdapter
from .dropbox import DropboxMetadataAdapter
from .filesystem import FilesystemMetadataAdapter
from .database import DatabaseMetadataAdapter

__all__ = [
    "MetadataAdapter",
    "MetadataAdapterRegistry",
    "AlfrescoMetadataAdapter",
    "GoogleDriveMetadataAdapter",
    "DropboxMetadataAdapter",
    "FilesystemMetadataAdapter",
    "DatabaseMetadataAdapter",
]
