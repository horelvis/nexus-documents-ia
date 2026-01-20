"""
Multi-Hop Query Planner

Plans complex queries that require traversing multiple relationships.

Examples:
- "Contracts of clients that also have support tickets" (2 hops)
- "Documents created by people in Juan's department" (3 hops)
- "Expedientes related to contracts expiring this month" (2 hops + temporal)

The planner:
1. Decomposes complex queries into traversal steps
2. Identifies start/end entities
3. Optimizes hop order (start from most selective)
4. Generates efficient Cypher
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from .schemas import (
    Intent,
    StructuralEntities,
    MultiHopQuery,
    QueryPlan,
)

logger = logging.getLogger(__name__)


@dataclass
class Hop:
    """A single hop in a multi-hop traversal."""
    step: int
    pattern: str  # Cypher pattern fragment
    description: str  # Human-readable description
    source_type: str  # Starting node type
    relationship: str  # Edge label
    target_type: str  # Ending node type
    filters: Dict[str, Any] = field(default_factory=dict)
    connection: Optional[str] = None  # How to connect to previous hop


# Common multi-hop patterns
COMMON_PATTERNS = {
    # Pattern: Entities sharing a relationship
    "shared_relationship": """
        MATCH (a:{type_a})-[:{rel}]->(shared:{shared_type})<-[:{rel}]-(b:{type_b})
        WHERE a.{filter_field} = $filter_value
        RETURN DISTINCT b
    """,

    # Pattern: Path between entities
    "path_between": """
        MATCH path = shortestPath((a:{type_a})-[*..{max_hops}]-(b:{type_b}))
        WHERE a.{filter_a} = $value_a AND b.{filter_b} = $value_b
        RETURN path
    """,

    # Pattern: Transitive expansion
    "transitive": """
        MATCH (start:{type})-[:{rel}*1..{depth}]->(related)
        WHERE start.{filter_field} = $filter_value
        RETURN DISTINCT related
    """,

    # Pattern: Documents by owner attribute
    "docs_by_owner_attribute": """
        MATCH (owner:{owner_type})-[:CREATED]->(doc:structural_document)
        WHERE owner.{attribute} = $attribute_value
        RETURN doc
    """,

    # Pattern: Documents related via intermediate entity
    "docs_via_intermediate": """
        MATCH (doc1:structural_document)-[:RELATES_TO]->(entity:{entity_type})<-[:RELATES_TO]-(doc2:structural_document)
        WHERE doc1.{filter_field} = $filter_value
        RETURN DISTINCT doc2
    """,
}


class MultiHopQueryPlanner:
    """
    Plans multi-hop queries by decomposing them into traversal steps.

    The planner analyzes the query structure and entities to:
    1. Identify required hops
    2. Determine optimal traversal order
    3. Generate efficient Cypher
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the planner."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ MultiHopQueryPlanner initialized")

    async def plan_query(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> QueryPlan:
        """
        Plan a multi-hop query.

        Args:
            intent: Detected intent with entities
            tenant_id: Tenant identifier

        Returns:
            QueryPlan with hops and generated Cypher
        """
        await self.initialize()

        entities = intent.entities
        multihop = intent.multihop_query

        # Identify hops needed
        hops = self._identify_hops(intent)

        # Optimize hop order (most selective first)
        optimized_hops = self._optimize_hop_order(hops, entities)

        # Generate Cypher
        cypher = self._generate_multihop_cypher(optimized_hops, entities, tenant_id)

        # Estimate complexity
        complexity = len(hops)
        estimated_time = self._estimate_execution_time(complexity)

        return QueryPlan(
            original_query=multihop.start_entity_value if multihop else "",
            hops=[{
                "step": hop.step,
                "description": hop.description,
                "pattern": hop.pattern,
            } for hop in optimized_hops],
            cypher=cypher,
            estimated_complexity=complexity,
            estimated_time_ms=estimated_time,
            optimization_notes=self._get_optimization_notes(hops, optimized_hops),
        )

    def _identify_hops(self, intent: Intent) -> List[Hop]:
        """
        Identify the hops needed for this query.

        Analyzes the query structure and entities to determine
        what traversals are required.
        """
        hops = []
        entities = intent.entities
        multihop = intent.multihop_query

        # If we have a client, start from client -> documents
        if entities.client_names:
            hops.append(Hop(
                step=1,
                pattern="(start:structural_document)",
                description=f"Start from documents of client {entities.client_names[0]}",
                source_type="structural_document",
                relationship="",
                target_type="structural_document",
                filters={"client": entities.client_names[0]},
            ))

        # If looking for related documents
        if entities.relationship_hints:
            hops.append(Hop(
                step=len(hops) + 1,
                pattern="-[:relates_to]->(related:structural_document)",
                description="Traverse to related documents",
                source_type="structural_document",
                relationship="relates_to",
                target_type="structural_document",
            ))

        # If filtering by document type at the end
        if entities.document_types:
            hops.append(Hop(
                step=len(hops) + 1,
                pattern="",
                description=f"Filter by type: {[t.value for t in entities.document_types]}",
                source_type="",
                relationship="",
                target_type="structural_document",
                filters={"semantic_types": [t.value for t in entities.document_types]},
            ))

        # If no specific hops identified, create a generic traversal
        if not hops:
            hops.append(Hop(
                step=1,
                pattern="(d:structural_document)",
                description="Query documents",
                source_type="structural_document",
                relationship="",
                target_type="structural_document",
            ))

        return hops

    def _optimize_hop_order(
        self,
        hops: List[Hop],
        entities: StructuralEntities,
    ) -> List[Hop]:
        """
        Optimize hop order for efficiency.

        Principle: Start from the most selective filter.
        - Specific entity values are more selective
        - Rare types are more selective
        - Temporal filters can be selective
        """
        # Score each hop by selectivity
        scored_hops = []
        for hop in hops:
            selectivity = self._estimate_selectivity(hop, entities)
            scored_hops.append((selectivity, hop))

        # Sort by selectivity (higher = more selective = do first)
        scored_hops.sort(key=lambda x: x[0], reverse=True)

        # Reorder hops
        optimized = []
        for i, (_, hop) in enumerate(scored_hops):
            new_hop = Hop(
                step=i + 1,
                pattern=hop.pattern,
                description=hop.description,
                source_type=hop.source_type,
                relationship=hop.relationship,
                target_type=hop.target_type,
                filters=hop.filters,
                connection=hop.connection,
            )
            optimized.append(new_hop)

        return optimized

    def _estimate_selectivity(
        self,
        hop: Hop,
        entities: StructuralEntities,
    ) -> float:
        """
        Estimate how selective a hop filter is.

        Higher score = more selective = fewer results.
        """
        score = 0.0

        # Specific entity values are highly selective
        if hop.filters.get("client"):
            score += 0.8  # Client filter is very selective

        if hop.filters.get("document_id"):
            score += 1.0  # Specific document is most selective

        # Type filters are moderately selective
        if hop.filters.get("semantic_types"):
            score += 0.4

        # Year filters are somewhat selective
        if entities.years:
            score += 0.3

        # Relationship traversals reduce selectivity
        if hop.relationship:
            score -= 0.2

        return max(score, 0.1)  # Minimum score

    def _generate_multihop_cypher(
        self,
        hops: List[Hop],
        entities: StructuralEntities,
        tenant_id: str,
    ) -> str:
        """
        Generate Cypher query from optimized hops.
        """
        # Build MATCH clause
        match_parts = []
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        for hop in hops:
            if hop.pattern:
                match_parts.append(hop.pattern)

            # Add filters to WHERE
            if hop.filters.get("client"):
                client = self._escape_string(hop.filters["client"])
                where_clauses.append(
                    f"(d.prop_client = '{client}' OR d.folder_path CONTAINS '{client}')"
                )

            if hop.filters.get("semantic_types"):
                types_str = ", ".join(f"'{t}'" for t in hop.filters["semantic_types"])
                where_clauses.append(f"d.semantic_type IN [{types_str}]")

        # Add entity-based filters
        if entities.years:
            year_conditions = []
            for year in entities.years:
                year_conditions.append(f"d.prop_year = '{year}'")
                year_conditions.append(f"d.folder_path CONTAINS '{year}'")
            where_clauses.append(f"({' OR '.join(year_conditions)})")

        if entities.folder_names:
            folder_conditions = []
            for folder in entities.folder_names:
                folder_safe = self._escape_string(folder)
                folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
            where_clauses.append(f"({' OR '.join(folder_conditions)})")

        # Build the query
        match_clause = "MATCH (d:structural_document)"
        if match_parts:
            match_clause = "MATCH " + "".join(match_parts)

        where_clause = " AND ".join(where_clauses)

        cypher = f"""
            {match_clause}
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.domain as domain,
                d.folder_path as folder_path,
                d.importance as importance
            ORDER BY d.importance DESC
            LIMIT 50
        """

        return cypher

    def _estimate_execution_time(self, complexity: int) -> int:
        """Estimate query execution time in milliseconds."""
        # Base time + time per hop
        base_ms = 100
        per_hop_ms = 200

        return base_ms + (complexity * per_hop_ms)

    def _get_optimization_notes(
        self,
        original_hops: List[Hop],
        optimized_hops: List[Hop],
    ) -> List[str]:
        """Generate optimization notes."""
        notes = []

        if len(original_hops) != len(optimized_hops):
            notes.append("Hops were merged or split for efficiency")

        # Check if order changed
        original_order = [h.description for h in original_hops]
        optimized_order = [h.description for h in optimized_hops]
        if original_order != optimized_order:
            notes.append("Hop order optimized for selectivity")

        if not notes:
            notes.append("Query structure preserved as optimal")

        return notes

    def _escape_string(self, value: str) -> str:
        """Escape string for Cypher."""
        if not value:
            return ""
        return value.replace("'", "''").replace("\\", "\\\\")


# Global singleton instance
multihop_planner = MultiHopQueryPlanner()
