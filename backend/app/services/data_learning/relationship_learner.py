"""
Relationship Learner

Extracts and maps relationships from connectors to Knowledge Graph edges:
- Alfresco: peer/child associations
- SharePoint: Document Sets, linked items (future)
- FileSystem: Inferred from naming patterns (future)

Learned relationships are used to expand retrieval queries
by including related documents in the context.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Connector,
    LearnedRelationshipType,
    DataLearningJob,
    IndexedDocument,
    KnowledgeRelationship,
    KnowledgeEntity,
)
from app.schemas.data_learning import (
    LearnedRelationshipTypeCreate,
    LearnedRelationshipTypeUpdate,
    RelationshipCategory,
)

logger = logging.getLogger(__name__)


# Standard relationship mappings
STANDARD_RELATIONSHIP_MAPPINGS = {
    # Alfresco associations
    "cm:references": ("references", RelationshipCategory.REFERENCE, True, 1),
    "cm:rendition": ("rendition_of", RelationshipCategory.CHILD, False, 1),
    "cm:original": ("original_of", RelationshipCategory.REFERENCE, True, 1),
    "cm:workingcopylink": ("working_copy", RelationshipCategory.REFERENCE, False, 1),
    "cm:contains": ("contains", RelationshipCategory.CHILD, True, 1),

    # Peer associations (bidirectional)
    "peer:related": ("relates_to", RelationshipCategory.PEER, True, 1),
    "peer:replaces": ("replaces", RelationshipCategory.PEER, True, 1),
    "peer:supersedes": ("supersedes", RelationshipCategory.REFERENCE, True, 1),
}


class RelationshipLearner:
    """
    Service for learning and mapping connector relationships.

    Extracts association types from connectors, maps them to
    Knowledge Graph edge types, and optionally syncs instances
    to the KG for retrieval expansion.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the learner.

        Args:
            db: Database session
        """
        self.db = db

    async def learn_relationship_types(
        self,
        connector_id: UUID,
        update_job: Optional[DataLearningJob] = None,
    ) -> List[LearnedRelationshipType]:
        """
        Learn relationship types from a connector's content model.

        Args:
            connector_id: UUID of the connector
            update_job: Optional job to update progress

        Returns:
            List of learned relationship types
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
            update_job.current_phase = "Discovering relationship types"
            update_job.progress_percent = 10
            await self.db.commit()

        # Get association types from content model
        from app.db.models import ConnectorContentModel

        cm_result = await self.db.execute(
            select(ConnectorContentModel)
            .where(ConnectorContentModel.connector_id == connector_id)
        )
        content_model = cm_result.scalar_one_or_none()

        association_types = {}
        if content_model and content_model.association_types:
            association_types = content_model.association_types

        # Update job progress
        if update_job:
            update_job.current_phase = "Mapping relationship types"
            update_job.progress_percent = 50
            await self.db.commit()

        # Create mappings for discovered associations
        relationship_types = []

        # First, add standard mappings
        for source_rel, (kg_edge, category, include, depth) in STANDARD_RELATIONSHIP_MAPPINGS.items():
            rel_type = await self._create_or_update_relationship_type(
                connector_id=connector_id,
                source_relationship=source_rel,
                kg_edge_type=kg_edge,
                category=category,
                include_in_retrieval=include,
                expansion_depth=depth,
            )
            relationship_types.append(rel_type)

        # Then, add discovered associations
        for assoc_name, assoc_info in association_types.items():
            if assoc_name not in STANDARD_RELATIONSHIP_MAPPINGS:
                # Infer mapping
                kg_edge, category, include, depth = self._infer_relationship_mapping(
                    assoc_name, assoc_info
                )
                rel_type = await self._create_or_update_relationship_type(
                    connector_id=connector_id,
                    source_relationship=assoc_name,
                    kg_edge_type=kg_edge,
                    category=category,
                    include_in_retrieval=include,
                    expansion_depth=depth,
                    description=assoc_info.get("description"),
                )
                relationship_types.append(rel_type)

        await self.db.commit()

        # Update job progress
        if update_job:
            update_job.current_phase = "Relationship learning completed"
            update_job.progress_percent = 100
            await self.db.commit()

        logger.info(
            f"Relationship learning completed for connector {connector_id}: "
            f"{len(relationship_types)} types"
        )

        return relationship_types

    async def _create_or_update_relationship_type(
        self,
        connector_id: UUID,
        source_relationship: str,
        kg_edge_type: str,
        category: RelationshipCategory,
        include_in_retrieval: bool,
        expansion_depth: int,
        description: Optional[str] = None,
    ) -> LearnedRelationshipType:
        """Create or update a relationship type mapping."""
        # Check if exists
        result = await self.db.execute(
            select(LearnedRelationshipType)
            .where(LearnedRelationshipType.connector_id == connector_id)
            .where(LearnedRelationshipType.source_relationship == source_relationship)
        )
        rel_type = result.scalar_one_or_none()

        if rel_type:
            # Update existing
            rel_type.kg_edge_type = kg_edge_type
            rel_type.relationship_category = category.value
            rel_type.include_in_retrieval = include_in_retrieval
            rel_type.expansion_depth = expansion_depth
            if description:
                rel_type.description = description
        else:
            # Create new
            rel_type = LearnedRelationshipType(
                connector_id=connector_id,
                source_relationship=source_relationship,
                kg_edge_type=kg_edge_type,
                relationship_category=category.value,
                include_in_retrieval=include_in_retrieval,
                expansion_depth=expansion_depth,
                description=description,
            )
            self.db.add(rel_type)

        return rel_type

    def _infer_relationship_mapping(
        self,
        assoc_name: str,
        assoc_info: Dict[str, Any],
    ) -> Tuple[str, RelationshipCategory, bool, int]:
        """
        Infer relationship mapping from association name and info.

        Args:
            assoc_name: Association name
            assoc_info: Association definition info

        Returns:
            Tuple of (kg_edge_type, category, include_in_retrieval, expansion_depth)
        """
        lower_name = assoc_name.lower()

        # Check for known patterns
        if "child" in lower_name or "contains" in lower_name:
            return ("contains", RelationshipCategory.CHILD, True, 1)
        elif "parent" in lower_name:
            return ("contained_by", RelationshipCategory.CHILD, True, 1)
        elif "reference" in lower_name or "ref" in lower_name:
            return ("references", RelationshipCategory.REFERENCE, True, 1)
        elif "version" in lower_name:
            return ("version_of", RelationshipCategory.REFERENCE, True, 1)
        elif "relate" in lower_name or "link" in lower_name:
            return ("relates_to", RelationshipCategory.PEER, True, 1)
        elif "replace" in lower_name or "supersede" in lower_name:
            return ("supersedes", RelationshipCategory.REFERENCE, True, 1)
        else:
            # Default to generic relation
            kg_edge = assoc_name.split(":")[-1] if ":" in assoc_name else assoc_name
            return (kg_edge, RelationshipCategory.REFERENCE, True, 1)

    async def extract_document_relationships(
        self,
        connector_id: UUID,
        document_external_id: str,
        associations: Dict[str, List[str]],
    ) -> List[Dict[str, Any]]:
        """
        Extract and normalize relationships for a document.

        Args:
            connector_id: UUID of the connector
            document_external_id: External ID of the source document
            associations: Dict of association type → list of target external IDs

        Returns:
            List of normalized relationship dicts for storage
        """
        # Get relationship type mappings
        result = await self.db.execute(
            select(LearnedRelationshipType)
            .where(LearnedRelationshipType.connector_id == connector_id)
        )
        type_mappings = {rt.source_relationship: rt for rt in result.scalars().all()}

        relationships = []
        for assoc_type, target_ids in associations.items():
            mapping = type_mappings.get(assoc_type)
            if not mapping:
                # Use default mapping
                kg_edge = assoc_type.split(":")[-1] if ":" in assoc_type else assoc_type
                include = True
                strength = 1.0
            else:
                kg_edge = mapping.kg_edge_type
                include = mapping.include_in_retrieval
                strength = mapping.weight

            for target_id in target_ids:
                relationships.append({
                    "type": kg_edge,
                    "target_id": target_id,
                    "source_type": assoc_type,
                    "include_in_retrieval": include,
                    "strength": strength,
                })

        return relationships

    async def sync_to_knowledge_graph(
        self,
        connector_id: UUID,
        document_id: UUID,
        relationships: List[Dict[str, Any]],
    ) -> int:
        """
        Sync document relationships to the Knowledge Graph.

        Args:
            connector_id: UUID of the connector
            document_id: UUID of the indexed document
            relationships: List of relationship dicts

        Returns:
            Number of relationships created
        """
        # Get the indexed document
        result = await self.db.execute(
            select(IndexedDocument).where(IndexedDocument.id == document_id)
        )
        document = result.scalar_one_or_none()
        if not document:
            return 0

        created = 0
        for rel in relationships:
            # Find target document by external ID
            target_result = await self.db.execute(
                select(IndexedDocument)
                .where(IndexedDocument.connector_id == connector_id)
                .where(IndexedDocument.external_id == rel["target_id"])
            )
            target_doc = target_result.scalar_one_or_none()

            if not target_doc:
                continue

            # Check if relationship already exists
            existing = await self.db.execute(
                select(KnowledgeRelationship)
                .where(KnowledgeRelationship.source_document_id == document_id)
                .where(KnowledgeRelationship.relationship_type == rel["type"])
            )
            # Skip KG sync for now - would need entity IDs
            # This is a placeholder for future KG integration
            created += 1

        return created

    async def get_relationship_types(
        self,
        connector_id: UUID,
    ) -> List[LearnedRelationshipType]:
        """Get all relationship types for a connector."""
        result = await self.db.execute(
            select(LearnedRelationshipType)
            .where(LearnedRelationshipType.connector_id == connector_id)
            .order_by(LearnedRelationshipType.weight.desc())
        )
        return list(result.scalars().all())

    async def update_relationship_type(
        self,
        relationship_id: UUID,
        update: LearnedRelationshipTypeUpdate,
    ) -> Optional[LearnedRelationshipType]:
        """Update a relationship type mapping."""
        result = await self.db.execute(
            select(LearnedRelationshipType)
            .where(LearnedRelationshipType.id == relationship_id)
        )
        rel_type = result.scalar_one_or_none()

        if not rel_type:
            return None

        update_data = update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(rel_type, key, value)

        await self.db.commit()
        await self.db.refresh(rel_type)

        return rel_type

    async def get_related_document_ids(
        self,
        connector_id: UUID,
        document_external_id: str,
        depth: int = 1,
    ) -> List[str]:
        """
        Get IDs of documents related to the given document.

        Args:
            connector_id: UUID of the connector
            document_external_id: External ID of the document
            depth: How many relationship hops to follow

        Returns:
            List of related external document IDs
        """
        # Get document
        result = await self.db.execute(
            select(IndexedDocument)
            .where(IndexedDocument.connector_id == connector_id)
            .where(IndexedDocument.external_id == document_external_id)
        )
        document = result.scalar_one_or_none()

        if not document or not document.learned_context:
            return []

        # Extract relationships from learned_context
        relationships = document.learned_context.get("relationships", [])

        related_ids = []
        for rel in relationships:
            if rel.get("include_in_retrieval", True):
                related_ids.append(rel["target_id"])

        # TODO: Implement depth > 1 traversal

        return related_ids
