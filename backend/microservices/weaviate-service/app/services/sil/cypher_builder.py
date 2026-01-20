"""
Cypher Query Builder for SIL

Builds Cypher queries for Apache AGE to answer structural questions.
These queries operate on the STRUCTURAL GRAPH (folders, documents, relationships)
without reading document content.

Query Types:
- COUNT queries: "How many contracts does ACME have?"
- LIST queries: "Show me all contracts from 2024"
- EXISTS queries: "Is there a contract with ACME?"
- LOCATION queries: "Where is the ACME contract?"
- RELATIONSHIP queries: "What documents are related to contract X?"
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .schemas import (
    Intent,
    IntentType,
    StructuralEntities,
    TemporalMarkers,
    MultiHopQuery,
    SemanticType,
    DomainType,
)

logger = logging.getLogger(__name__)


class CypherBuilder:
    """
    Builds Cypher queries for structural reasoning.

    The builder translates detected intents and entities into
    Cypher queries that can be executed against Apache AGE.
    """

    # Vertex labels in the structural graph
    VERTEX_DOCUMENT = "structural_document"
    VERTEX_FOLDER = "structural_folder"
    VERTEX_SITE = "structural_site"

    # Edge labels
    EDGE_CONTAINS = "contains"
    EDGE_VERSION_OF = "version_of"
    EDGE_RELATES_TO = "relates_to"
    EDGE_SIBLING_OF = "sibling_of"
    EDGE_CHILD_OF = "child_of"

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the builder."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ CypherBuilder initialized")

    def build_query(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> str:
        """
        Build a Cypher query based on detected intent.

        Args:
            intent: Detected intent with entities and type
            tenant_id: Tenant identifier for isolation

        Returns:
            Cypher query string
        """
        # Route to appropriate query builder
        builders = {
            IntentType.STRUCTURAL_COUNT: self._build_count_query,
            IntentType.STRUCTURAL_LIST: self._build_list_query,
            IntentType.STRUCTURAL_EXISTS: self._build_exists_query,
            IntentType.STRUCTURAL_LOCATION: self._build_location_query,
            IntentType.STRUCTURAL: self._build_general_structural_query,
            IntentType.TEMPORAL_POINT: self._build_temporal_point_query,
            IntentType.TEMPORAL_RANGE: self._build_temporal_range_query,
            IntentType.TEMPORAL_EVOLUTION: self._build_temporal_evolution_query,
            IntentType.MULTIHOP_SIMPLE: self._build_multihop_query,
            IntentType.MULTIHOP_COMPLEX: self._build_multihop_query,
        }

        builder = builders.get(intent.type)
        if builder:
            return builder(intent, tenant_id)

        # Default: return a general structural query
        return self._build_general_structural_query(intent, tenant_id)

    def _build_count_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a COUNT query.

        Example: "How many contracts does ACME have?"
        → MATCH (d:structural_document) WHERE d.tenant_id = 'X' AND ...
          RETURN count(d)
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        # Add semantic type filter
        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        # Add domain filter
        if intent.entities.domains:
            domains_str = ", ".join(f"'{d.value}'" for d in intent.entities.domains)
            where_clauses.append(f"d.domain IN [{domains_str}]")

        # Add client filter (in key_properties or folder path)
        if intent.entities.client_names:
            client_conditions = []
            for client in intent.entities.client_names:
                client_safe = self._escape_string(client)
                client_conditions.append(f"d.prop_client = '{client_safe}'")
                client_conditions.append(f"d.folder_path CONTAINS '{client_safe}'")
            where_clauses.append(f"({' OR '.join(client_conditions)})")

        # Add year filter
        if intent.entities.years:
            year_conditions = []
            for year in intent.entities.years:
                year_conditions.append(f"d.prop_year = '{year}'")
                year_conditions.append(f"d.folder_path CONTAINS '{year}'")
            where_clauses.append(f"({' OR '.join(year_conditions)})")

        # Add folder filter
        if intent.entities.folder_names:
            folder_conditions = []
            for folder in intent.entities.folder_names:
                folder_safe = self._escape_string(folder)
                folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
            where_clauses.append(f"({' OR '.join(folder_conditions)})")

        where_clause = " AND ".join(where_clauses)

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN count(d) as total
        """

    def _build_list_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a LIST query.

        Example: "Show me all contracts from 2024"
        → Returns list of document titles, types, and paths
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        # Same filters as count query
        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        if intent.entities.domains:
            domains_str = ", ".join(f"'{d.value}'" for d in intent.entities.domains)
            where_clauses.append(f"d.domain IN [{domains_str}]")

        if intent.entities.client_names:
            client_conditions = []
            for client in intent.entities.client_names:
                client_safe = self._escape_string(client)
                client_conditions.append(f"d.prop_client = '{client_safe}'")
                client_conditions.append(f"d.folder_path CONTAINS '{client_safe}'")
            where_clauses.append(f"({' OR '.join(client_conditions)})")

        if intent.entities.years:
            year_conditions = []
            for year in intent.entities.years:
                year_conditions.append(f"d.prop_year = '{year}'")
                year_conditions.append(f"d.folder_path CONTAINS '{year}'")
            where_clauses.append(f"({' OR '.join(year_conditions)})")

        if intent.entities.folder_names:
            folder_conditions = []
            for folder in intent.entities.folder_names:
                folder_safe = self._escape_string(folder)
                folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
            where_clauses.append(f"({' OR '.join(folder_conditions)})")

        where_clause = " AND ".join(where_clauses)

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.domain as domain,
                d.folder_path as folder_path,
                d.importance as importance,
                d.created_at as created_at
            ORDER BY d.importance DESC, d.created_at DESC
            LIMIT 50
        """

    def _build_exists_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build an EXISTS query.

        Example: "Is there a contract with ACME?"
        → Returns boolean-like result (count > 0)
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        if intent.entities.client_names:
            client_conditions = []
            for client in intent.entities.client_names:
                client_safe = self._escape_string(client)
                client_conditions.append(f"d.prop_client = '{client_safe}'")
                client_conditions.append(f"d.folder_path CONTAINS '{client_safe}'")
            where_clauses.append(f"({' OR '.join(client_conditions)})")

        where_clause = " AND ".join(where_clauses)

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                CASE WHEN count(d) > 0 THEN true ELSE false END as exists,
                count(d) as count
            LIMIT 1
        """

    def _build_location_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a LOCATION query.

        Example: "Where is the ACME contract?"
        → Returns folder path and hierarchy
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        if intent.entities.client_names:
            client_conditions = []
            for client in intent.entities.client_names:
                client_safe = self._escape_string(client)
                client_conditions.append(f"d.prop_client = '{client_safe}'")
                client_conditions.append(f"d.folder_path CONTAINS '{client_safe}'")
                client_conditions.append(f"d.prop_title CONTAINS '{client_safe}'")
            where_clauses.append(f"({' OR '.join(client_conditions)})")

        where_clause = " AND ".join(where_clauses)

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.folder_path as folder_path,
                d.semantic_type as semantic_type,
                d.domain as domain,
                d.site_id as site_id
            ORDER BY d.importance DESC
            LIMIT 10
        """

    def _build_general_structural_query(self, intent: Intent, tenant_id: str) -> str:
        """Build a general structural query when specific type isn't clear."""
        return self._build_list_query(intent, tenant_id)

    def _build_temporal_point_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a temporal point-in-time query.

        Example: "What documents existed on January 1st?"
        → Filter by valid_from <= date AND (valid_to IS NULL OR valid_to > date)
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        if intent.temporal_markers and intent.temporal_markers.point_in_time:
            timestamp = intent.temporal_markers.point_in_time.isoformat()
            where_clauses.append(f"d.valid_from <= '{timestamp}'")
            where_clauses.append(
                f"(d.valid_to IS NULL OR d.valid_to > '{timestamp}')"
            )

        # Add other entity filters
        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        if intent.entities.folder_names:
            folder_conditions = []
            for folder in intent.entities.folder_names:
                folder_safe = self._escape_string(folder)
                folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
            where_clauses.append(f"({' OR '.join(folder_conditions)})")

        where_clause = " AND ".join(where_clauses)

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.valid_from as valid_from,
                d.created_at as created_at
            ORDER BY d.created_at DESC
            LIMIT 50
        """

    def _build_temporal_range_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a temporal range query.

        Example: "What documents were added this week?"
        → Filter by created_at BETWEEN start AND end
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        if intent.temporal_markers:
            if intent.temporal_markers.start_date:
                start = intent.temporal_markers.start_date.isoformat()
                where_clauses.append(f"d.created_at >= '{start}'")

            if intent.temporal_markers.end_date:
                end = intent.temporal_markers.end_date.isoformat()
                where_clauses.append(f"d.created_at <= '{end}'")

        # Add other filters
        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        if intent.entities.folder_names:
            folder_conditions = []
            for folder in intent.entities.folder_names:
                folder_safe = self._escape_string(folder)
                folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
            where_clauses.append(f"({' OR '.join(folder_conditions)})")

        where_clause = " AND ".join(where_clauses)

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.created_at as created_at,
                d.modified_at as modified_at,
                'added' as change_type
            ORDER BY d.created_at DESC
            LIMIT 100
        """

    def _build_temporal_evolution_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a temporal evolution query.

        Example: "How has the Contracts folder evolved this year?"
        → Group documents by time periods and show growth
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        # Filter by folder if specified
        if intent.entities.folder_names:
            folder_conditions = []
            for folder in intent.entities.folder_names:
                folder_safe = self._escape_string(folder)
                folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
            where_clauses.append(f"({' OR '.join(folder_conditions)})")

        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        where_clause = " AND ".join(where_clauses)

        # Return documents with temporal info for post-processing
        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.created_at as created_at,
                d.modified_at as modified_at,
                d.valid_from as valid_from,
                d.valid_to as valid_to
            ORDER BY d.created_at ASC
        """

    def _build_multihop_query(self, intent: Intent, tenant_id: str) -> str:
        """
        Build a multi-hop traversal query.

        Example: "Contracts of clients that also have support tickets"
        → Multi-hop traversal through relationships
        """
        if not intent.multihop_query:
            # Fall back to list query
            return self._build_list_query(intent, tenant_id)

        mhq = intent.multihop_query

        # Build the pattern based on estimated hops
        # This is a simplified implementation
        # A full implementation would build complex patterns

        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        # Start from specific entity if provided
        if mhq.start_entity_value:
            start_safe = self._escape_string(mhq.start_entity_value)
            where_clauses.append(
                f"(d.prop_client = '{start_safe}' OR d.folder_path CONTAINS '{start_safe}')"
            )

        if intent.entities.document_types:
            types_str = ", ".join(f"'{t.value}'" for t in intent.entities.document_types)
            where_clauses.append(f"d.semantic_type IN [{types_str}]")

        where_clause = " AND ".join(where_clauses)

        # For now, return a list query with the filters
        # A full implementation would build variable-length path queries
        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.domain as domain,
                d.importance as importance
            ORDER BY d.importance DESC
            LIMIT 50
        """

    def build_relationship_query(
        self,
        document_id: str,
        tenant_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 2,
    ) -> str:
        """
        Build a query to find related documents.

        Args:
            document_id: Source document ID
            tenant_id: Tenant identifier
            relationship_type: Optional specific relationship type
            max_depth: Maximum traversal depth

        Returns:
            Cypher query for relationship traversal
        """
        document_id_safe = self._escape_string(document_id)

        if relationship_type:
            rel_filter = f":{relationship_type}"
        else:
            rel_filter = ""

        return f"""
            MATCH (source:{self.VERTEX_DOCUMENT} {{document_id: '{document_id_safe}', tenant_id: '{tenant_id}'}})
                  -[r{rel_filter}*1..{max_depth}]-
                  (related:{self.VERTEX_DOCUMENT})
            WHERE related.tenant_id = '{tenant_id}'
            RETURN DISTINCT
                related.document_id as document_id,
                related.prop_title as title,
                related.semantic_type as semantic_type,
                related.folder_path as folder_path,
                type(r[0]) as relationship_type,
                length(r) as depth
            ORDER BY length(r), related.importance DESC
            LIMIT 20
        """

    def build_folder_contents_query(
        self,
        folder_path: str,
        tenant_id: str,
        recursive: bool = False,
    ) -> str:
        """
        Build a query to list contents of a folder.

        Args:
            folder_path: Folder path to list
            tenant_id: Tenant identifier
            recursive: Include subfolders

        Returns:
            Cypher query for folder contents
        """
        folder_safe = self._escape_string(folder_path)

        if recursive:
            path_filter = f"d.folder_path STARTS WITH '{folder_safe}'"
        else:
            path_filter = f"d.folder_path = '{folder_safe}'"

        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE d.tenant_id = '{tenant_id}'
              AND {path_filter}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.created_at as created_at,
                d.importance as importance
            ORDER BY d.folder_path, d.prop_title
        """

    def build_graph_stats_query(self, tenant_id: str) -> str:
        """Build a query to get structural graph statistics."""
        return f"""
            MATCH (d:{self.VERTEX_DOCUMENT})
            WHERE d.tenant_id = '{tenant_id}'
            RETURN
                count(d) as total_documents,
                count(DISTINCT d.semantic_type) as unique_types,
                count(DISTINCT d.domain) as unique_domains,
                count(DISTINCT d.folder_path) as unique_folders
        """

    def _escape_string(self, value: str) -> str:
        """Escape a string for safe use in Cypher queries."""
        if not value:
            return ""
        # Escape single quotes by doubling them
        return value.replace("'", "''").replace("\\", "\\\\")


# Global singleton instance
cypher_builder = CypherBuilder()
