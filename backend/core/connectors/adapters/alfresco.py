"""
Alfresco Metadata Adapter

Extracts and normalizes metadata from Alfresco Content Services.
Alfresco is the richest metadata source with full content models,
aspects, custom properties, and categories.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..metadata_schema import (
    NormalizedMetadata,
    MetadataRichness,
    DocumentOrigin,
    TemporalInfo,
    OwnershipInfo,
    ClassificationInfo,
    BusinessProperties,
)
from .base import MetadataAdapter, MetadataAdapterRegistry, PathIntelligence

logger = logging.getLogger(__name__)


# Mapping of Alfresco content model types to semantic types
ALFRESCO_TYPE_TO_SEMANTIC = {
    # Expediente model
    "exp:expediente": "case_file",
    "exp:documentoExpediente": "case_document",
    # Project management
    "pm:project": "project",
    "pm:task": "task",
    "pm:milestone": "milestone",
    # Records management
    "rma:record": "record",
    "rma:recordFolder": "record_folder",
    # Financial
    "fin:invoice": "invoice",
    "fin:contract": "contract",
    "fin:budget": "budget",
    # HR
    "hr:employee": "employee_record",
    "hr:contract": "employment_contract",
    # Legal
    "legal:contract": "contract",
    "legal:agreement": "agreement",
    "legal:litigation": "litigation",
    # Generic content
    "cm:content": "document",
    "cm:folder": "folder",
}

class AlfrescoMetadataAdapter(MetadataAdapter):
    """
    Metadata adapter for Alfresco Content Services.

    Alfresco provides the richest metadata:
    - Content models with custom types (exp:*, pm:*, etc.)
    - Aspects for cross-cutting concerns
    - Custom properties with full typing
    - Categories and tags
    - Full audit trail (creator, modifier, dates)
    - Site structure and paths
    """

    connector_type = "alfresco"
    richness_level = MetadataRichness.RICH

    # Common Alfresco property prefixes that contain business data
    BUSINESS_PROPERTY_PREFIXES = [
        "exp:",    # Expediente (case file)
        "pmreg:",  # Project/process registration
        "pm:",     # Project management
        "fin:",    # Financial
        "hr:",     # HR
        "legal:",  # Legal
        "custom:", # Custom properties
    ]

    def normalize(
        self,
        document_id: str,
        tenant_id: str,
        raw_metadata: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> NormalizedMetadata:
        """
        Normalize Alfresco metadata into common schema.

        Alfresco raw_metadata typically contains:
        - alfresco_properties: Dict of all cm:*, exp:*, etc. properties
        - alfresco_aspects: List of applied aspects
        - alfresco_content_type: The node type
        - alfresco_path_elements: Path components with metadata
        - parent_folder_properties: Properties from parent folder
        """
        # Get the Alfresco-specific fields
        alfresco_props = raw_metadata.get("alfresco_properties", {})
        aspects = raw_metadata.get("alfresco_aspects", [])
        content_type = raw_metadata.get("alfresco_content_type", "cm:content")
        path_elements = raw_metadata.get("alfresco_path_elements", [])
        parent_props = raw_metadata.get("parent_folder_properties", {})

        # Determine file path
        external_path = file_path or raw_metadata.get("external_path", "")
        if not external_path and path_elements:
            external_path = "/" + "/".join(
                elem.get("name", "") for elem in path_elements
            )

        # Create base metadata
        metadata = self._create_base_metadata(
            document_id=document_id,
            tenant_id=tenant_id,
            external_id=raw_metadata.get("external_id", document_id),
            file_path=external_path,
            raw_metadata=raw_metadata,
        )

        # Update origin with connector ID
        if "connector_id" in raw_metadata:
            metadata.origin.connector_id = str(raw_metadata["connector_id"])

        # Extract file info
        metadata.file_size = raw_metadata.get("size") or raw_metadata.get("size_bytes")
        metadata.mime_type = raw_metadata.get("mime_type") or alfresco_props.get("cm:content", {}).get("mimeType")

        # Extract temporal info
        metadata.temporal = self._extract_temporal_info(alfresco_props, raw_metadata)

        # Extract ownership
        metadata.ownership = self._extract_ownership(alfresco_props, raw_metadata)

        # Extract classification (type, categories)
        metadata.classification = self._extract_classification(
            content_type, aspects, alfresco_props, parent_props
        )

        # Extract business properties
        metadata.business = self._extract_business_properties(
            alfresco_props, parent_props, metadata.path
        )

        # Apply path inference for any remaining gaps
        self._apply_path_inference(metadata)

        return metadata

    def _extract_temporal_info(
        self,
        alfresco_props: Dict[str, Any],
        raw_metadata: Dict[str, Any],
    ) -> TemporalInfo:
        """Extract temporal information from Alfresco properties."""
        temporal = TemporalInfo()

        # Parse dates from Alfresco format
        def parse_date(date_str: Optional[str]) -> Optional[datetime]:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                return None

        temporal.created_at = parse_date(alfresco_props.get("cm:created"))
        temporal.modified_at = parse_date(alfresco_props.get("cm:modified"))

        # Version info
        temporal.version_label = alfresco_props.get("cm:versionLabel")
        if temporal.version_label:
            try:
                temporal.version_number = int(float(temporal.version_label))
            except (ValueError, TypeError):
                pass

        # Also check raw metadata for indexed_at
        if "indexed_at" in raw_metadata:
            temporal.indexed_at = parse_date(raw_metadata["indexed_at"]) or datetime.utcnow()

        return temporal

    def _extract_ownership(
        self,
        alfresco_props: Dict[str, Any],
        raw_metadata: Dict[str, Any],
    ) -> OwnershipInfo:
        """Extract ownership information from Alfresco properties."""
        ownership = OwnershipInfo()

        # Creator and modifier
        ownership.creator_id = alfresco_props.get("cm:creator")
        ownership.creator_name = alfresco_props.get("cm:creator")
        ownership.last_modifier_id = alfresco_props.get("cm:modifier")
        ownership.last_modifier_name = alfresco_props.get("cm:modifier")

        # Owner (from raw metadata)
        if "owner_id" in raw_metadata:
            ownership.owner_id = str(raw_metadata["owner_id"])

        # ACL info from raw metadata
        ownership.is_public = raw_metadata.get("is_tenant_public", False)
        ownership.shared_with_users = raw_metadata.get("shared_with_users", [])
        ownership.shared_with_groups = raw_metadata.get("shared_with_groups", [])

        return ownership

    def _extract_classification(
        self,
        content_type: str,
        aspects: List[str],
        alfresco_props: Dict[str, Any],
        parent_props: Dict[str, Any],
    ) -> ClassificationInfo:
        """Extract classification from Alfresco content model and aspects."""
        classification = ClassificationInfo()

        # Content model type
        classification.content_model = content_type

        # Map Alfresco type to semantic type
        semantic_type = ALFRESCO_TYPE_TO_SEMANTIC.get(content_type)
        if semantic_type:
            classification.semantic_type = semantic_type
            classification.semantic_type_confidence = 0.95
            classification.semantic_type_source = "metadata"

        # Aspects
        classification.aspects = aspects

        # Extract categories from Alfresco
        categories = alfresco_props.get("cm:categories", [])
        if isinstance(categories, list):
            classification.categories = [
                cat.get("name", cat) if isinstance(cat, dict) else str(cat)
                for cat in categories
            ]

        # Extract tags
        tags = alfresco_props.get("cm:taggable", [])
        if isinstance(tags, list):
            classification.tags = [
                tag.get("name", tag) if isinstance(tag, dict) else str(tag)
                for tag in tags
            ]

        return classification

    def _extract_business_properties(
        self,
        alfresco_props: Dict[str, Any],
        parent_props: Dict[str, Any],
        path_components: Any,
    ) -> BusinessProperties:
        """Extract business-specific properties from Alfresco custom properties."""
        business = BusinessProperties()

        # Merge document and parent folder properties for lookup
        all_props = {**parent_props, **alfresco_props}

        # Common property patterns for business data
        property_mappings = {
            # Client information
            "client_name": ["exp:cliente", "pm:client", "custom:cliente", "fin:cliente"],
            "client_id": ["exp:clienteId", "pm:clientId", "custom:clienteId"],
            # Project information
            "project_name": ["pm:projectName", "exp:proyecto", "custom:proyecto"],
            "project_id": ["pm:projectId", "exp:proyectoId"],
            # Department
            "department": ["exp:departamento", "hr:department", "custom:departamento"],
            # Reference number
            "reference_number": [
                "exp:codExpDocExp",  # Expediente code
                "exp:numeroExpediente",
                "fin:invoiceNumber",
                "legal:contractNumber",
                "pm:projectCode",
                "custom:referencia",
            ],
            # Status
            "status": ["exp:estado", "pm:status", "custom:estado", "wf:status"],
            # Financial
            "amount": ["fin:amount", "fin:importe", "custom:importe"],
            "currency": ["fin:currency", "fin:moneda"],
        }

        for field_name, prop_names in property_mappings.items():
            for prop_name in prop_names:
                if prop_name in all_props and all_props[prop_name]:
                    value = all_props[prop_name]
                    if field_name in ["amount"]:
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            continue
                    setattr(business, field_name, value)
                    break

        # Date properties
        date_mappings = {
            "effective_date": ["exp:fechaInicio", "legal:effectiveDate", "pm:startDate"],
            "expiration_date": ["exp:fechaFin", "legal:expirationDate", "pm:endDate"],
        }

        for field_name, prop_names in date_mappings.items():
            for prop_name in prop_names:
                if prop_name in all_props and all_props[prop_name]:
                    try:
                        date_str = all_props[prop_name]
                        date_val = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        setattr(business, field_name, date_val)
                        break
                    except Exception:
                        continue

        # Store all custom properties (exp:*, pm:*, etc.) in custom dict
        for prop_name, prop_value in alfresco_props.items():
            if any(prop_name.startswith(prefix) for prefix in self.BUSINESS_PROPERTY_PREFIXES):
                if prop_value is not None:
                    business.custom[prop_name] = prop_value

        # Also include parent folder custom properties
        for prop_name, prop_value in parent_props.items():
            key = f"folder_{prop_name}"
            if prop_value is not None:
                business.custom[key] = prop_value

        return business


# Register the adapter
MetadataAdapterRegistry.register("alfresco", AlfrescoMetadataAdapter)
