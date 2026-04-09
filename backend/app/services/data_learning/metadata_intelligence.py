"""
Metadata Intelligence Service

Maps connector-specific properties to normalized semantic fields
and calculates search importance weights based on:
- Property type and constraints
- Value distribution and uniqueness
- User search patterns (from interaction history)

Example: "gdapm:numExpediente" → "identifier" with weight 2.0
"""
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models import (
    Connector,
    ConnectorContentModel,
    LearnedPropertyMapping,
    DataLearningJob,
    IndexedDocument,
    UserInteractionHistory,
)
from app.schemas.data_learning import (
    LearnedPropertyMappingCreate,
    LearnedPropertyMappingUpdate,
)

logger = logging.getLogger(__name__)


# Standard field mappings for common properties
STANDARD_FIELD_MAPPINGS = {
    # Alfresco common properties
    "cm:title": ("title", 1.5, True),
    "cm:name": ("filename", 1.0, True),
    "cm:description": ("description", 0.8, True),
    "cm:creator": ("author", 0.5, False),
    "cm:modifier": ("modifier", 0.3, False),
    "cm:created": ("created_date", 0.5, False),
    "cm:modified": ("modified_date", 0.5, False),
    "cm:author": ("author", 0.5, False),
    "cm:content": ("content", 1.0, True),

    # SharePoint common properties (future)
    "Title": ("title", 1.5, True),
    "FileLeafRef": ("filename", 1.0, True),
    "Author": ("author", 0.5, False),
    "Editor": ("modifier", 0.3, False),
    "Created": ("created_date", 0.5, False),
    "Modified": ("modified_date", 0.5, False),
}

# Keywords that indicate identifier properties
IDENTIFIER_KEYWORDS = [
    "id", "numero", "number", "code", "codigo", "código",
    "expediente", "referencia", "reference", "identifier",
]

# Keywords that indicate high importance
HIGH_IMPORTANCE_KEYWORDS = [
    "title", "titulo", "name", "nombre", "subject", "asunto",
]


class MetadataIntelligenceService:
    """
    Service for mapping properties to semantic fields and calculating weights.

    Combines:
    - Static mapping rules for common properties
    - Heuristics based on property names and types
    - Learning from user search patterns (future)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the service.

        Args:
            db: Database session
        """
        self.db = db

    async def generate_property_mappings(
        self,
        connector_id: UUID,
        use_content_model: bool = True,
        update_job: Optional[DataLearningJob] = None,
    ) -> List[LearnedPropertyMapping]:
        """
        Generate property mappings for a connector.

        Args:
            connector_id: UUID of the connector
            use_content_model: Whether to use discovered content model
            update_job: Optional job to update progress

        Returns:
            List of generated property mappings
        """
        # Fetch connector
        result = await self.db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        # Update job progress
        if update_job:
            update_job.current_phase = "Loading content model"
            update_job.progress_percent = 10
            await self.db.commit()

        # Get content model if available
        content_model = None
        if use_content_model:
            cm_result = await self.db.execute(
                select(ConnectorContentModel)
                .where(ConnectorContentModel.connector_id == connector_id)
            )
            content_model = cm_result.scalar_one_or_none()

        # Update job progress
        if update_job:
            update_job.current_phase = "Generating property mappings"
            update_job.progress_percent = 30
            await self.db.commit()

        # Generate mappings
        mappings_to_create = []

        if content_model and content_model.property_definitions:
            for prop_name, prop_info in content_model.property_definitions.items():
                mapping = self._create_mapping_for_property(
                    prop_name, prop_info, content_model.property_semantics
                )
                mappings_to_create.append(mapping)

        # Also add standard mappings that might not be in the model
        for prop_name, (target, weight, embed) in STANDARD_FIELD_MAPPINGS.items():
            if not any(m["source_property"] == prop_name for m in mappings_to_create):
                mappings_to_create.append({
                    "source_property": prop_name,
                    "source_type": None,
                    "target_field": target,
                    "search_weight": weight,
                    "include_in_embedding": embed,
                    "is_filterable": False,
                    "is_facetable": False,
                    "transformation": None,
                    "default_value": None,
                })

        # Update job progress
        if update_job:
            update_job.current_phase = "Storing property mappings"
            update_job.progress_percent = 70
            await self.db.commit()

        # Store mappings
        created_mappings = []
        for mapping_data in mappings_to_create:
            # Check if mapping already exists
            existing = await self.db.execute(
                select(LearnedPropertyMapping)
                .where(LearnedPropertyMapping.connector_id == connector_id)
                .where(LearnedPropertyMapping.source_property == mapping_data["source_property"])
                .where(
                    LearnedPropertyMapping.source_type == mapping_data.get("source_type")
                    if mapping_data.get("source_type")
                    else LearnedPropertyMapping.source_type.is_(None)
                )
            )
            mapping = existing.scalar_one_or_none()

            if mapping:
                # Update if not manually verified
                if not mapping.learned_from_usage:
                    mapping.target_field = mapping_data["target_field"]
                    mapping.search_weight = mapping_data["search_weight"]
                    mapping.include_in_embedding = mapping_data["include_in_embedding"]
            else:
                mapping = LearnedPropertyMapping(
                    connector_id=connector_id,
                    source_property=mapping_data["source_property"],
                    source_type=mapping_data.get("source_type"),
                    target_field=mapping_data["target_field"],
                    search_weight=mapping_data["search_weight"],
                    include_in_embedding=mapping_data["include_in_embedding"],
                    is_filterable=mapping_data.get("is_filterable", False),
                    is_facetable=mapping_data.get("is_facetable", False),
                    transformation=mapping_data.get("transformation"),
                    default_value=mapping_data.get("default_value"),
                )
                self.db.add(mapping)

            created_mappings.append(mapping)

        await self.db.commit()

        # Update job progress
        if update_job:
            update_job.current_phase = "Property mapping completed"
            update_job.progress_percent = 100
            await self.db.commit()

        logger.info(
            f"Property mapping completed for connector {connector_id}: "
            f"{len(created_mappings)} mappings"
        )

        return created_mappings

    def _create_mapping_for_property(
        self,
        prop_name: str,
        prop_info: Dict[str, Any],
        property_semantics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a mapping dict for a property.

        Args:
            prop_name: Property name
            prop_info: Property definition info
            property_semantics: Optional LLM-enriched semantics

        Returns:
            Mapping dict
        """
        # Check for standard mapping first
        if prop_name in STANDARD_FIELD_MAPPINGS:
            target, weight, embed = STANDARD_FIELD_MAPPINGS[prop_name]
            return {
                "source_property": prop_name,
                "source_type": None,
                "target_field": target,
                "search_weight": weight,
                "include_in_embedding": embed,
                "is_filterable": False,
                "is_facetable": False,
            }

        # Use semantics if available
        if property_semantics and prop_name in property_semantics:
            semantic = property_semantics[prop_name]
            return {
                "source_property": prop_name,
                "source_type": None,
                "target_field": semantic.get("normalized_name", prop_name.split(":")[-1]),
                "search_weight": semantic.get("search_weight", 1.0),
                "include_in_embedding": semantic.get("include_in_embedding", True),
                "is_filterable": semantic.get("is_identifier", False),
                "is_facetable": False,
            }

        # Apply heuristics
        lower_name = prop_name.lower()

        # Check if identifier
        is_identifier = any(kw in lower_name for kw in IDENTIFIER_KEYWORDS)

        # Check if high importance
        is_high_importance = any(kw in lower_name for kw in HIGH_IMPORTANCE_KEYWORDS)

        # Check data type for date fields
        data_type = prop_info.get("data_type", "")
        is_date = "date" in data_type.lower() or "datetime" in data_type.lower()

        # Calculate weight
        weight = 1.0
        if is_identifier:
            weight = 2.0
        elif is_high_importance:
            weight = 1.5
        elif is_date:
            weight = 0.5

        # Include in embedding?
        include_in_embedding = not is_date

        # Target field name
        target_field = prop_name.split(":")[-1] if ":" in prop_name else prop_name

        return {
            "source_property": prop_name,
            "source_type": None,
            "target_field": target_field,
            "search_weight": weight,
            "include_in_embedding": include_in_embedding,
            "is_filterable": is_identifier,
            "is_facetable": False,
            "transformation": "date_normalize" if is_date else None,
        }

    async def update_weights_from_usage(
        self,
        connector_id: UUID,
    ) -> int:
        """
        Update property weights based on user search patterns.

        Analyzes user interaction history to find which properties
        are involved in successful searches and adjusts weights.

        Args:
            connector_id: UUID of the connector

        Returns:
            Number of mappings updated
        """
        # Get interaction history for successful searches
        result = await self.db.execute(
            select(UserInteractionHistory)
            .where(UserInteractionHistory.interaction_type == "query")
            .where(UserInteractionHistory.results_clicked > 0)
            .order_by(UserInteractionHistory.created_at.desc())
            .limit(1000)
        )
        interactions = result.scalars().all()

        if not interactions:
            return 0

        # Analyze which terms led to clicks
        # This is a simplified version - real implementation would
        # track which document properties matched the query terms

        # Get property mappings
        mappings_result = await self.db.execute(
            select(LearnedPropertyMapping)
            .where(LearnedPropertyMapping.connector_id == connector_id)
        )
        mappings = {m.source_property: m for m in mappings_result.scalars().all()}

        updated_count = 0

        # For now, just increment usage_count for properties that might match
        for interaction in interactions:
            query_text = interaction.query_text or ""
            query_terms = query_text.lower().split()

            for prop_name, mapping in mappings.items():
                # Simple heuristic: if property name contains query term
                prop_lower = prop_name.lower()
                if any(term in prop_lower for term in query_terms):
                    mapping.usage_count += 1
                    mapping.learned_from_usage = True
                    updated_count += 1

        if updated_count > 0:
            await self.db.commit()

        return updated_count

    async def get_property_mappings(
        self,
        connector_id: UUID,
        source_type: Optional[str] = None,
    ) -> List[LearnedPropertyMapping]:
        """
        Get property mappings for a connector.

        Args:
            connector_id: UUID of the connector
            source_type: Optional filter by source type

        Returns:
            List of property mappings
        """
        query = select(LearnedPropertyMapping).where(
            LearnedPropertyMapping.connector_id == connector_id
        )

        if source_type:
            query = query.where(
                (LearnedPropertyMapping.source_type == source_type) |
                (LearnedPropertyMapping.source_type.is_(None))
            )

        result = await self.db.execute(query.order_by(LearnedPropertyMapping.search_weight.desc()))
        return list(result.scalars().all())

    async def update_property_mapping(
        self,
        mapping_id: UUID,
        update: LearnedPropertyMappingUpdate,
    ) -> Optional[LearnedPropertyMapping]:
        """
        Update a property mapping.

        Args:
            mapping_id: UUID of the mapping
            update: Update data

        Returns:
            Updated mapping or None if not found
        """
        result = await self.db.execute(
            select(LearnedPropertyMapping)
            .where(LearnedPropertyMapping.id == mapping_id)
        )
        mapping = result.scalar_one_or_none()

        if not mapping:
            return None

        update_data = update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(mapping, key, value)

        await self.db.commit()
        await self.db.refresh(mapping)

        return mapping

    async def get_normalized_metadata(
        self,
        connector_id: UUID,
        raw_metadata: Dict[str, Any],
        document_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Normalize raw metadata using property mappings.

        Args:
            connector_id: UUID of the connector
            raw_metadata: Raw metadata from connector
            document_type: Optional document type for type-specific mappings

        Returns:
            Normalized metadata dict
        """
        mappings = await self.get_property_mappings(connector_id, document_type)

        # Build mapping lookup
        mapping_lookup = {}
        for m in mappings:
            key = m.source_property
            if key not in mapping_lookup or m.source_type == document_type:
                mapping_lookup[key] = m

        # Normalize
        normalized = {}
        property_weights = {}

        for prop_name, value in raw_metadata.items():
            mapping = mapping_lookup.get(prop_name)
            if mapping:
                # Apply transformation if needed
                transformed_value = value
                if mapping.transformation == "lowercase":
                    transformed_value = str(value).lower() if value else None
                elif mapping.transformation == "uppercase":
                    transformed_value = str(value).upper() if value else None

                normalized[mapping.target_field] = transformed_value
                property_weights[mapping.target_field] = mapping.search_weight
            else:
                # Keep unmapped properties with default weight
                normalized[prop_name] = value
                property_weights[prop_name] = 1.0

        return {
            "properties": normalized,
            "weights": property_weights,
        }
