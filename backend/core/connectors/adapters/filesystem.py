"""
Filesystem Metadata Adapter

Extracts and normalizes metadata from local or network filesystem sources.
This is a minimal metadata source that relies heavily on path intelligence.
"""

import logging
import os
import stat
from datetime import datetime
from typing import Any, Dict, Optional

from ..metadata_schema import (
    NormalizedMetadata,
    MetadataRichness,
    TemporalInfo,
    OwnershipInfo,
    ClassificationInfo,
    BusinessProperties,
)
from .base import MetadataAdapter, MetadataAdapterRegistry, PathIntelligence

logger = logging.getLogger(__name__)


# Extension to semantic type mapping
EXTENSION_TO_SEMANTIC = {
    # Documents
    "pdf": "document",
    "doc": "document",
    "docx": "document",
    "odt": "document",
    "rtf": "document",
    "txt": "text",
    # Spreadsheets
    "xls": "spreadsheet",
    "xlsx": "spreadsheet",
    "ods": "spreadsheet",
    "csv": "data",
    # Presentations
    "ppt": "presentation",
    "pptx": "presentation",
    "odp": "presentation",
    # Images
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "gif": "image",
    "bmp": "image",
    "svg": "image",
    "tiff": "image",
    # Media
    "mp3": "audio",
    "wav": "audio",
    "mp4": "video",
    "avi": "video",
    "mkv": "video",
    "mov": "video",
    # Archives
    "zip": "archive",
    "rar": "archive",
    "7z": "archive",
    "tar": "archive",
    "gz": "archive",
    # Code
    "py": "code",
    "js": "code",
    "ts": "code",
    "java": "code",
    "c": "code",
    "cpp": "code",
    "h": "code",
    "cs": "code",
    "go": "code",
    "rs": "code",
    "rb": "code",
    "php": "code",
    # Data
    "json": "data",
    "xml": "data",
    "yaml": "data",
    "yml": "data",
    "sql": "data",
    # Email
    "eml": "email",
    "msg": "email",
}


class FilesystemMetadataAdapter(MetadataAdapter):
    """
    Metadata adapter for filesystem sources.

    Filesystem provides minimal metadata:
    - Path and filename
    - File size
    - Timestamps (created, modified, accessed)
    - POSIX permissions (owner, group, mode)
    - No custom properties or categories

    Richness Level: MINIMAL
    - Relies heavily on PathIntelligence for inference
    - Best used with well-organized folder structures
    """

    connector_type = "filesystem"
    richness_level = MetadataRichness.MINIMAL

    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """
        Normalize filesystem metadata into common schema.

        Filesystem raw_metadata typically contains:
        - path: Full file path
        - name or filename: File name
        - size: File size in bytes
        - created: Creation timestamp
        - modified: Modification timestamp
        - accessed: Access timestamp
        - mode: POSIX file mode
        - uid: Owner user ID
        - gid: Owner group ID
        - owner: Owner username (if resolved)
        - group: Group name (if resolved)
        """
        # Determine file path
        external_path = file_path or raw_metadata.get("path", "")
        if not external_path:
            external_path = "/" + raw_metadata.get("name", raw_metadata.get("filename", ""))

        # Create base metadata with path parsing
        metadata = self._create_base_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            external_id=raw_metadata.get("id", external_path),  # Use path as ID if no ID
            file_path=external_path,
            raw_metadata=raw_metadata,
        )

        # Extract file info
        if "size" in raw_metadata:
            try:
                metadata.file_size = int(raw_metadata["size"])
            except (ValueError, TypeError):
                pass

        # Infer MIME type from extension
        if metadata.path.extension:
            metadata.mime_type = self._get_mime_type(metadata.path.extension)

        # Extract temporal info
        metadata.temporal = self._extract_temporal_info(raw_metadata)

        # Extract ownership (from POSIX info if available)
        metadata.ownership = self._extract_ownership(raw_metadata)

        # Extract classification (mainly from extension and path)
        metadata.classification = self._extract_classification(raw_metadata, metadata.path)

        # Business properties (inferred from path only)
        metadata.business = BusinessProperties()

        # Apply path inference heavily for filesystem sources
        self._apply_path_inference(metadata)

        return metadata

    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type from file extension."""
        mime_types = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "ppt": "application/vnd.ms-powerpoint",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "txt": "text/plain",
            "csv": "text/csv",
            "json": "application/json",
            "xml": "application/xml",
            "html": "text/html",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "mp3": "audio/mpeg",
            "mp4": "video/mp4",
            "zip": "application/zip",
        }
        return mime_types.get(extension.lower(), "application/octet-stream")

    def _extract_temporal_info(self, raw_metadata: Dict[str, Any]) -> TemporalInfo:
        """Extract temporal information from filesystem metadata."""
        temporal = TemporalInfo()

        def parse_timestamp(ts: Any) -> Optional[datetime]:
            if ts is None:
                return None
            if isinstance(ts, datetime):
                return ts
            if isinstance(ts, (int, float)):
                try:
                    return datetime.fromtimestamp(ts)
                except Exception:
                    return None
            if isinstance(ts, str):
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    return None
            return None

        # Various possible field names for timestamps
        temporal.created_at = (
            parse_timestamp(raw_metadata.get("created")) or
            parse_timestamp(raw_metadata.get("created_at")) or
            parse_timestamp(raw_metadata.get("ctime")) or
            parse_timestamp(raw_metadata.get("birthtime"))
        )

        temporal.modified_at = (
            parse_timestamp(raw_metadata.get("modified")) or
            parse_timestamp(raw_metadata.get("modified_at")) or
            parse_timestamp(raw_metadata.get("mtime"))
        )

        temporal.accessed_at = (
            parse_timestamp(raw_metadata.get("accessed")) or
            parse_timestamp(raw_metadata.get("accessed_at")) or
            parse_timestamp(raw_metadata.get("atime"))
        )

        return temporal

    def _extract_ownership(self, raw_metadata: Dict[str, Any]) -> OwnershipInfo:
        """Extract ownership information from POSIX metadata."""
        ownership = OwnershipInfo()

        # Owner info from POSIX
        if "owner" in raw_metadata:
            ownership.owner_name = raw_metadata["owner"]
        if "uid" in raw_metadata:
            ownership.owner_id = str(raw_metadata["uid"])

        # POSIX group is no longer mirrored anywhere (the per-group share
        # list was dropped with the legacy ACL columns).

        # Parse permissions from mode
        mode = raw_metadata.get("mode")
        if mode:
            try:
                mode_int = int(mode) if isinstance(mode, str) else mode
                perms = []
                if mode_int & stat.S_IRUSR:
                    perms.append("owner_read")
                if mode_int & stat.S_IWUSR:
                    perms.append("owner_write")
                if mode_int & stat.S_IRGRP:
                    perms.append("group_read")
                if mode_int & stat.S_IWGRP:
                    perms.append("group_write")
                if mode_int & stat.S_IROTH:
                    perms.append("other_read")
                    ownership.is_public = True
                ownership.permissions = perms
            except (ValueError, TypeError):
                pass

        return ownership

    def _extract_classification(
        self,
        raw_metadata: Dict[str, Any],
        path_components: Any,
    ) -> ClassificationInfo:
        """Extract classification from extension and path."""
        classification = ClassificationInfo()

        # Map extension to semantic type
        extension = path_components.extension or ""
        semantic_type = EXTENSION_TO_SEMANTIC.get(extension.lower())
        if semantic_type:
            classification.semantic_type = semantic_type
            classification.semantic_type_confidence = 0.6  # Low confidence, just from extension
            classification.semantic_type_source = "extension"

        # The rest will be filled by path inference
        return classification


# Register the adapter
MetadataAdapterRegistry.register("filesystem", FilesystemMetadataAdapter)
MetadataAdapterRegistry.register("local", FilesystemMetadataAdapter)  # Alias
MetadataAdapterRegistry.register("smb", FilesystemMetadataAdapter)  # SMB/CIFS shares
MetadataAdapterRegistry.register("nfs", FilesystemMetadataAdapter)  # NFS mounts
