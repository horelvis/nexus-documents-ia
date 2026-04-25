"""
Dropbox Metadata Adapter

Extracts and normalizes metadata from Dropbox.
Dropbox has basic metadata similar to Google Drive but with fewer features.
"""

import logging
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
from .base import MetadataAdapter, MetadataAdapterRegistry

logger = logging.getLogger(__name__)


class DropboxMetadataAdapter(MetadataAdapter):
    """
    Metadata adapter for Dropbox.

    Dropbox provides basic metadata:
    - File info: name, size, path, timestamps
    - Sharing: shared_folder info, shared links
    - Limited custom properties via property groups

    Richness Level: MINIMAL to BASIC
    - Less rich than Google Drive
    - Path intelligence is important for inference
    """

    connector_type = "dropbox"
    richness_level = MetadataRichness.MINIMAL

    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """
        Normalize Dropbox metadata into common schema.

        Dropbox raw_metadata typically contains:
        - name: File name
        - path_display: Full path with proper casing
        - path_lower: Lowercase path
        - id: Dropbox file ID
        - client_modified: Client timestamp
        - server_modified: Server timestamp
        - size: File size
        - content_hash: SHA256 hash
        - sharing_info: Sharing details
        - property_groups: Custom properties (if configured)
        """
        # Determine file path
        external_path = file_path or raw_metadata.get("path_display", "")
        if not external_path:
            external_path = "/" + raw_metadata.get("name", "")

        # Create base metadata
        metadata = self._create_base_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            external_id=raw_metadata.get("id", document_id),
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

        # Extract ownership
        metadata.ownership = self._extract_ownership(raw_metadata)

        # Classification from path intelligence
        metadata.classification = ClassificationInfo()

        # Business properties from property groups
        metadata.business = self._extract_business_properties(raw_metadata)

        # Apply path inference
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
        """Extract temporal information from Dropbox metadata."""
        temporal = TemporalInfo()

        def parse_date(date_str: Optional[str]) -> Optional[datetime]:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                return None

        # Dropbox uses client_modified for user's edit time
        # and server_modified for when it was uploaded/synced
        temporal.modified_at = parse_date(raw_metadata.get("client_modified"))
        temporal.created_at = parse_date(raw_metadata.get("server_modified"))

        # Rev is a version identifier
        if "rev" in raw_metadata:
            temporal.version_label = raw_metadata["rev"]

        return temporal

    def _extract_ownership(self, raw_metadata: Dict[str, Any]) -> OwnershipInfo:
        """Extract ownership information from Dropbox metadata."""
        ownership = OwnershipInfo()

        # Sharing info
        sharing_info = raw_metadata.get("sharing_info", {})
        if sharing_info:
            # If in a shared folder, it's not fully public but shared
            if sharing_info.get("shared_folder_id"):
                ownership.is_public = False  # Shared folder, not public

        # Team member info (if team Dropbox)
        if "team_member_info" in raw_metadata:
            team_info = raw_metadata["team_member_info"]
            ownership.owner_name = team_info.get("display_name")
            ownership.owner_email = team_info.get("email")

        return ownership

    def _extract_business_properties(self, raw_metadata: Dict[str, Any]) -> BusinessProperties:
        """Extract business properties from Dropbox property groups."""
        business = BusinessProperties()

        # Dropbox supports custom property groups (if configured)
        property_groups = raw_metadata.get("property_groups", [])

        for group in property_groups:
            fields = group.get("fields", [])
            for field in fields:
                name = field.get("name", "").lower()
                value = field.get("value")

                if not value:
                    continue

                # Map common property names
                if "client" in name:
                    business.client_name = value
                elif "project" in name:
                    business.project_name = value
                elif "department" in name or "dept" in name:
                    business.department = value
                elif "reference" in name or "ref" in name:
                    business.reference_number = value
                elif "status" in name:
                    business.status = value
                else:
                    # Store as custom
                    business.custom[name] = value

        return business


# Register the adapter
MetadataAdapterRegistry.register("dropbox", DropboxMetadataAdapter)
