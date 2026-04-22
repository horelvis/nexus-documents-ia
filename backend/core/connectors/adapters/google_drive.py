"""
Google Drive Metadata Adapter

Extracts and normalizes metadata from Google Drive.
Google Drive has moderate metadata richness with:
- Labels and properties
- Basic file info (owner, dates)
- Sharing permissions
- Folder structure
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

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


# Google Drive MIME types to semantic types
GDRIVE_MIME_TO_SEMANTIC = {
    # Google Workspace types
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.presentation": "presentation",
    "application/vnd.google-apps.form": "form",
    "application/vnd.google-apps.drawing": "drawing",
    # Standard types
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.ms-excel": "spreadsheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "spreadsheet",
    "application/vnd.ms-powerpoint": "presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "presentation",
    "text/plain": "text",
    "text/csv": "data",
    "application/json": "data",
    "image/jpeg": "image",
    "image/png": "image",
    "video/mp4": "video",
    "audio/mpeg": "audio",
}


class GoogleDriveMetadataAdapter(MetadataAdapter):
    """
    Metadata adapter for Google Drive.

    Google Drive provides moderate metadata:
    - File info: name, size, mime type, dates
    - Ownership: owner, shared with, permissions
    - Labels: Custom labels (if enabled for workspace)
    - Properties: Key-value custom properties
    - Path: Full folder hierarchy (reconstructed from parents)

    Richness Level: BASIC
    - Has categories/labels and some custom properties
    - Lacks the rich content models of Alfresco
    """

    connector_type = "google_drive"
    richness_level = MetadataRichness.BASIC

    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """
        Normalize Google Drive metadata into common schema.

        Google Drive raw_metadata typically contains:
        - name: File name
        - mimeType: MIME type
        - size: File size in bytes
        - createdTime: ISO date
        - modifiedTime: ISO date
        - owners: List of owner info
        - lastModifyingUser: Who last modified
        - parents: List of parent folder IDs
        - properties: Custom properties dict
        - appProperties: App-specific properties
        - labels: Labels (if enabled)
        - permissions: Sharing permissions
        - path: Reconstructed path (from connector)
        """
        # Determine file path
        external_path = file_path or raw_metadata.get("path", "")
        if not external_path:
            # Reconstruct from name if no path
            external_path = "/" + raw_metadata.get("name", "")

        # Create base metadata
        metadata = self._create_base_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            external_id=raw_metadata.get("id", document_id),
            file_path=external_path,
            raw_metadata=raw_metadata,
        )

        # Update origin with connector ID
        if "connector_id" in raw_metadata:
            metadata.origin.connector_id = str(raw_metadata["connector_id"])

        # Extract file info
        if "size" in raw_metadata:
            try:
                metadata.file_size = int(raw_metadata["size"])
            except (ValueError, TypeError):
                pass
        metadata.mime_type = raw_metadata.get("mimeType")

        # Extract temporal info
        metadata.temporal = self._extract_temporal_info(raw_metadata)

        # Extract ownership
        metadata.ownership = self._extract_ownership(raw_metadata)

        # Extract classification
        metadata.classification = self._extract_classification(raw_metadata)

        # Extract business properties from custom properties
        metadata.business = self._extract_business_properties(raw_metadata)

        # Apply path inference for gaps
        self._apply_path_inference(metadata)

        return metadata

    def _extract_temporal_info(self, raw_metadata: Dict[str, Any]) -> TemporalInfo:
        """Extract temporal information from Google Drive metadata."""
        temporal = TemporalInfo()

        def parse_date(date_str: Optional[str]) -> Optional[datetime]:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                return None

        temporal.created_at = parse_date(raw_metadata.get("createdTime"))
        temporal.modified_at = parse_date(raw_metadata.get("modifiedTime"))
        temporal.accessed_at = parse_date(raw_metadata.get("viewedByMeTime"))

        # Version info (Drive uses revision IDs, not simple numbers)
        if "version" in raw_metadata:
            try:
                temporal.version_number = int(raw_metadata["version"])
            except (ValueError, TypeError):
                pass

        return temporal

    def _extract_ownership(self, raw_metadata: Dict[str, Any]) -> OwnershipInfo:
        """Extract ownership information from Google Drive metadata."""
        ownership = OwnershipInfo()

        # Owners
        owners = raw_metadata.get("owners", [])
        if owners and isinstance(owners, list) and len(owners) > 0:
            primary_owner = owners[0]
            ownership.owner_id = primary_owner.get("permissionId")
            ownership.owner_name = primary_owner.get("displayName")
            ownership.owner_email = primary_owner.get("emailAddress")

        # Creator (same as owner for Drive)
        ownership.creator_id = ownership.owner_id
        ownership.creator_name = ownership.owner_name

        # Last modifier
        last_modifier = raw_metadata.get("lastModifyingUser", {})
        if last_modifier:
            ownership.last_modifier_id = last_modifier.get("permissionId")
            ownership.last_modifier_name = last_modifier.get("displayName")

        # Sharing from permissions
        permissions = raw_metadata.get("permissions", [])
        for perm in permissions:
            perm_type = perm.get("type")
            if perm_type == "anyone":
                ownership.is_public = True
            elif perm_type == "user":
                email = perm.get("emailAddress")
                if email and email != ownership.owner_email:
                    ownership.shared_with_users.append(email)
            elif perm_type == "group":
                email = perm.get("emailAddress")
                if email:
                    ownership.shared_with_groups.append(email)

            # Collect permission roles
            role = perm.get("role")
            if role and role not in ownership.permissions:
                ownership.permissions.append(role)

        return ownership

    def _extract_classification(self, raw_metadata: Dict[str, Any]) -> ClassificationInfo:
        """Extract classification from Google Drive metadata."""
        classification = ClassificationInfo()

        # Map MIME type to semantic type
        mime_type = raw_metadata.get("mimeType", "")
        semantic_type = GDRIVE_MIME_TO_SEMANTIC.get(mime_type)
        if semantic_type:
            classification.semantic_type = semantic_type
            classification.semantic_type_confidence = 0.8
            classification.semantic_type_source = "metadata"

        # Labels (if workspace has them enabled)
        labels = raw_metadata.get("labelInfo", {}).get("labels", [])
        for label in labels:
            label_name = label.get("name", "")
            if label_name:
                classification.categories.append(label_name)

        # Properties as tags (appProperties are app-specific)
        properties = raw_metadata.get("properties", {})
        if "category" in properties:
            classification.categories.append(properties["category"])
        if "type" in properties:
            if not classification.semantic_type:
                classification.semantic_type = properties["type"]
                classification.semantic_type_confidence = 0.85
                classification.semantic_type_source = "metadata"

        # Description as content model hint
        description = raw_metadata.get("description", "")
        if description:
            # Look for hashtags or keywords
            import re
            hashtags = re.findall(r'#(\w+)', description)
            classification.tags.extend(hashtags)

        return classification

    def _extract_business_properties(self, raw_metadata: Dict[str, Any]) -> BusinessProperties:
        """Extract business properties from Google Drive custom properties."""
        business = BusinessProperties()

        # Google Drive supports custom properties
        properties = raw_metadata.get("properties", {})
        app_properties = raw_metadata.get("appProperties", {})

        # Merge properties (prefer properties over appProperties)
        all_props = {**app_properties, **properties}

        # Common property names
        property_mappings = {
            "client_name": ["client", "cliente", "customer"],
            "client_id": ["clientId", "clienteId", "customerId"],
            "project_name": ["project", "proyecto"],
            "project_id": ["projectId", "proyectoId"],
            "department": ["department", "departamento", "dept"],
            "reference_number": ["reference", "referencia", "ref", "invoice", "contract"],
            "status": ["status", "estado"],
        }

        for field_name, prop_names in property_mappings.items():
            for prop_name in prop_names:
                if prop_name in all_props and all_props[prop_name]:
                    setattr(business, field_name, all_props[prop_name])
                    break

        # Store all custom properties
        for prop_name, prop_value in all_props.items():
            if prop_value is not None:
                business.custom[prop_name] = prop_value

        return business


# Register the adapter
MetadataAdapterRegistry.register("google_drive", GoogleDriveMetadataAdapter)
