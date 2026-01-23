"""
Database Metadata Adapter

Extracts and normalizes metadata from database BLOB storage.
This is the poorest metadata source - essentially just filename and binary content.
Relies almost entirely on path intelligence and content analysis.
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


class DatabaseMetadataAdapter(MetadataAdapter):
    """
    Metadata adapter for database BLOB storage.

    Database storage typically provides minimal information:
    - Filename (if stored)
    - MIME type (if stored)
    - File size (if stored or computed from BLOB)
    - Database record timestamps
    - Maybe a few custom columns

    Richness Level: DATABASE (lowest)
    - Relies almost entirely on PathIntelligence
    - May need content-based classification
    - Best used when filename follows naming conventions

    Example scenarios:
    - Legacy systems with binary columns
    - Simple attachment tables
    - Document archives stored in DB
    """

    connector_type = "database"
    richness_level = MetadataRichness.DATABASE

    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """
        Normalize database metadata into common schema.

        Database raw_metadata varies greatly but commonly contains:
        - filename or name: Original filename
        - mime_type or content_type: MIME type
        - size or file_size: File size
        - created_at or created: Record creation time
        - updated_at or modified: Record modification time
        - user_id or uploaded_by: Uploader ID
        - Any custom columns the table might have
        """
        # Try to get a filename
        filename = (
            raw_metadata.get("filename") or
            raw_metadata.get("name") or
            raw_metadata.get("file_name") or
            raw_metadata.get("original_name") or
            f"document_{document_id}"
        )

        # Use filename as path if no path provided
        external_path = file_path or filename
        if not external_path.startswith("/"):
            external_path = "/" + external_path

        # Create base metadata with path parsing
        metadata = self._create_base_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            external_id=raw_metadata.get("id", document_id),
            file_path=external_path,
            raw_metadata=raw_metadata,
        )

        # Extract file info
        metadata.file_size = self._get_file_size(raw_metadata)
        metadata.mime_type = self._get_mime_type(raw_metadata)

        # Extract temporal info (from DB record timestamps)
        metadata.temporal = self._extract_temporal_info(raw_metadata)

        # Extract ownership (usually just uploader ID)
        metadata.ownership = self._extract_ownership(raw_metadata)

        # Classification will mostly come from path inference
        metadata.classification = ClassificationInfo()

        # Business properties (look for any custom columns)
        metadata.business = self._extract_business_properties(raw_metadata)

        # Apply path inference HEAVILY for database sources
        self._apply_path_inference(metadata)

        return metadata

    def _get_file_size(self, raw_metadata: Dict[str, Any]) -> Optional[int]:
        """Extract file size from various possible fields."""
        size_fields = ["size", "file_size", "filesize", "content_length", "length"]
        for field in size_fields:
            if field in raw_metadata:
                try:
                    return int(raw_metadata[field])
                except (ValueError, TypeError):
                    continue
        return None

    def _get_mime_type(self, raw_metadata: Dict[str, Any]) -> Optional[str]:
        """Extract MIME type from various possible fields."""
        mime_fields = ["mime_type", "mimetype", "content_type", "type"]
        for field in mime_fields:
            if field in raw_metadata and raw_metadata[field]:
                return str(raw_metadata[field])
        return None

    def _extract_temporal_info(self, raw_metadata: Dict[str, Any]) -> TemporalInfo:
        """Extract temporal information from database record timestamps."""
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
                    # Try ISO format first
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    pass
                try:
                    # Try common database formats
                    from dateutil import parser
                    return parser.parse(ts)
                except Exception:
                    return None
            return None

        # Various possible field names
        created_fields = ["created_at", "created", "create_date", "date_created", "uploaded_at"]
        modified_fields = ["updated_at", "modified_at", "modified", "update_date", "last_modified"]

        for field in created_fields:
            if field in raw_metadata:
                temporal.created_at = parse_timestamp(raw_metadata[field])
                if temporal.created_at:
                    break

        for field in modified_fields:
            if field in raw_metadata:
                temporal.modified_at = parse_timestamp(raw_metadata[field])
                if temporal.modified_at:
                    break

        # Version from database (if tracked)
        if "version" in raw_metadata:
            try:
                temporal.version_number = int(raw_metadata["version"])
            except (ValueError, TypeError):
                pass

        return temporal

    def _extract_ownership(self, raw_metadata: Dict[str, Any]) -> OwnershipInfo:
        """Extract ownership from database record."""
        ownership = OwnershipInfo()

        # Uploader/creator fields
        owner_fields = ["user_id", "uploaded_by", "created_by", "owner_id", "author_id"]
        for field in owner_fields:
            if field in raw_metadata and raw_metadata[field]:
                ownership.owner_id = str(raw_metadata[field])
                break

        # Owner name if available
        name_fields = ["user_name", "uploaded_by_name", "author_name", "owner_name"]
        for field in name_fields:
            if field in raw_metadata and raw_metadata[field]:
                ownership.owner_name = str(raw_metadata[field])
                break

        # Public flag
        if "is_public" in raw_metadata:
            ownership.is_public = bool(raw_metadata["is_public"])

        return ownership

    def _extract_business_properties(self, raw_metadata: Dict[str, Any]) -> BusinessProperties:
        """Extract any business-related columns from the database record."""
        business = BusinessProperties()

        # Common column names that might contain business data
        property_mappings = {
            "client_name": ["client", "client_name", "cliente", "customer", "customer_name"],
            "client_id": ["client_id", "cliente_id", "customer_id"],
            "project_name": ["project", "project_name", "proyecto"],
            "project_id": ["project_id", "proyecto_id"],
            "department": ["department", "dept", "departamento"],
            "reference_number": ["reference", "ref", "reference_number", "ref_number", "numero"],
            "status": ["status", "estado", "state"],
        }

        for field_name, column_names in property_mappings.items():
            for col in column_names:
                if col in raw_metadata and raw_metadata[col]:
                    setattr(business, field_name, raw_metadata[col])
                    break

        # Store any other non-standard columns as custom properties
        # Skip common system columns
        skip_columns = {
            "id", "uuid", "filename", "name", "size", "file_size",
            "mime_type", "content_type", "content", "data", "blob",
            "created_at", "updated_at", "created", "modified",
            "user_id", "uploaded_by", "tenant_id"
        }

        for key, value in raw_metadata.items():
            if key.lower() not in skip_columns and value is not None:
                # Only include if it's a simple type (string, number, bool)
                if isinstance(value, (str, int, float, bool)):
                    business.custom[key] = value

        return business


# Register the adapter
MetadataAdapterRegistry.register("database", DatabaseMetadataAdapter)
MetadataAdapterRegistry.register("postgresql", DatabaseMetadataAdapter)  # Alias
MetadataAdapterRegistry.register("mysql", DatabaseMetadataAdapter)  # Alias
MetadataAdapterRegistry.register("blob", DatabaseMetadataAdapter)  # Alias
