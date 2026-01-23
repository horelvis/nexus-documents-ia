"""
Temporal Reasoning Engine

Handles time-based structural queries:
- Point-in-time: "What documents existed on January 1st?"
- Range: "What changed this week?"
- Evolution: "How has the Contracts folder evolved?"
- Comparison: "Compare structure now vs. 3 months ago"

Key Concepts:
- valid_from/valid_to: Temporal validity of document in structure
- created_at: When document was added
- modified_at: When document was last changed

The temporal graph maintains history, not just current state.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

from .schemas import (
    Intent,
    TemporalMarkers,
    TemporalResult,
    StructuralContext,
    CypherQueryResult,
)
from .cypher_builder import CypherBuilder, cypher_builder
from ...services.knowledge.age_graph_service import AGEKnowledgeGraphService, age_knowledge_graph

logger = logging.getLogger(__name__)


def _get_enum_value(obj: Union[Enum, str, None]) -> str:
    """Safely get the value from an enum or return the string directly.

    IMPORTANT: Check Enum BEFORE str because string enums (class X(str, Enum))
    satisfy both isinstance(obj, str) and isinstance(obj, Enum), but we need
    to use .value for correct extraction.
    """
    if obj is None:
        return ""
    # Check Enum FIRST - string enums (str, Enum) satisfy both str and Enum checks
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, str):
        return obj
    if hasattr(obj, 'value'):
        return obj.value
    return str(obj)


class TemporalReasoningEngine:
    """
    Engine for temporal structural reasoning.

    Supports queries about:
    - Historical state: "What was there on date X?"
    - Changes: "What changed between date A and B?"
    - Evolution: "Show me the growth of folder X over time"
    """

    def __init__(
        self,
        builder: Optional[CypherBuilder] = None,
        graph_service: Optional[AGEKnowledgeGraphService] = None,
    ):
        self._builder = builder or cypher_builder
        self._graph = graph_service or age_knowledge_graph
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the temporal engine."""
        if self._initialized:
            return

        await self._builder.initialize()
        await self._graph.initialize()

        self._initialized = True
        logger.info("✅ TemporalReasoningEngine initialized")

    async def process_temporal_query(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> TemporalResult:
        """
        Process a temporal query.

        Routes to appropriate handler based on temporal markers.
        """
        await self.initialize()

        if not intent.temporal_markers:
            return TemporalResult(
                query_type="unknown",
            )

        markers = intent.temporal_markers

        # Route based on temporal query type
        if markers.point_in_time:
            return await self.query_at_point_in_time(
                tenant_id=tenant_id,
                point_in_time=markers.point_in_time,
                entities=intent.entities,
            )

        if markers.start_date or markers.end_date:
            return await self.query_changes_in_range(
                tenant_id=tenant_id,
                start_date=markers.start_date,
                end_date=markers.end_date or datetime.now(),
                entities=intent.entities,
            )

        if markers.evolution_requested:
            return await self.get_evolution_timeline(
                tenant_id=tenant_id,
                entities=intent.entities,
                granularity=markers.granularity,
            )

        if len(markers.compare_times) >= 2:
            return await self.get_structure_diff(
                tenant_id=tenant_id,
                time_a=markers.compare_times[0],
                time_b=markers.compare_times[1],
                entities=intent.entities,
            )

        return TemporalResult(
            query_type="unknown",
        )

    async def query_at_point_in_time(
        self,
        tenant_id: str,
        point_in_time: datetime,
        entities: Optional[Any] = None,
    ) -> TemporalResult:
        """
        Query structure as it was at a specific point in time.

        Uses valid_from and valid_to to filter documents that
        were "valid" (present in the structure) at that time.

        Example: "What documents existed in RRHH on January 1st?"
        """
        timestamp = point_in_time.isoformat()

        # Build Cypher query for point-in-time
        where_clauses = [
            f"d.tenant_id = '{tenant_id}'",
            f"d.valid_from <= '{timestamp}'",
            f"(d.valid_to IS NULL OR d.valid_to > '{timestamp}')",
        ]

        # Add entity filters if provided
        if entities:
            if hasattr(entities, 'folder_names') and entities.folder_names:
                folder_conditions = []
                for folder in entities.folder_names:
                    folder_safe = self._escape_string(folder)
                    folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
                where_clauses.append(f"({' OR '.join(folder_conditions)})")

            if hasattr(entities, 'document_types') and entities.document_types:
                types_str = ", ".join(f"'{_get_enum_value(t)}'" for t in entities.document_types)
                where_clauses.append(f"d.semantic_type IN [{types_str}]")

        where_clause = " AND ".join(where_clauses)

        cypher = f"""
            MATCH (d:structural_document)
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.valid_from as valid_from,
                d.created_at as created_at
            ORDER BY d.folder_path, d.prop_title
        """

        result = await self._execute_cypher(cypher, tenant_id)

        return TemporalResult(
            query_type="point_in_time",
            state_at_time={
                "timestamp": timestamp,
                "document_count": result.row_count,
                "documents": result.rows[:50],  # Limit for context
            },
            execution_time_ms=result.execution_time_ms,
        )

    async def query_changes_in_range(
        self,
        tenant_id: str,
        start_date: Optional[datetime],
        end_date: datetime,
        entities: Optional[Any] = None,
        change_type: Optional[str] = None,
    ) -> TemporalResult:
        """
        Query changes that occurred in a time range.

        Returns documents that were:
        - Added: created_at in range
        - Modified: modified_at in range AND created_at < start_date
        - Deleted: valid_to in range

        Example: "What documents were added this week?"
        """
        changes: List[Dict[str, Any]] = []

        start_str = start_date.isoformat() if start_date else None
        end_str = end_date.isoformat()

        # Query for added documents
        if change_type in (None, "added"):
            added_clauses = [
                f"d.tenant_id = '{tenant_id}'",
                f"d.created_at <= '{end_str}'",
            ]
            if start_str:
                added_clauses.append(f"d.created_at >= '{start_str}'")

            if entities:
                if hasattr(entities, 'folder_names') and entities.folder_names:
                    folder_conditions = []
                    for folder in entities.folder_names:
                        folder_safe = self._escape_string(folder)
                        folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
                    added_clauses.append(f"({' OR '.join(folder_conditions)})")

            added_cypher = f"""
                MATCH (d:structural_document)
                WHERE {' AND '.join(added_clauses)}
                RETURN
                    d.document_id as document_id,
                    d.prop_title as title,
                    d.semantic_type as semantic_type,
                    d.folder_path as folder_path,
                    d.created_at as created_at,
                    'added' as change_type
                ORDER BY d.created_at DESC
                LIMIT 100
            """

            added_result = await self._execute_cypher(added_cypher, tenant_id)
            changes.extend(added_result.rows)

        # Query for modified documents
        if change_type in (None, "modified") and start_str:
            modified_clauses = [
                f"d.tenant_id = '{tenant_id}'",
                f"d.modified_at >= '{start_str}'",
                f"d.modified_at <= '{end_str}'",
                f"d.created_at < '{start_str}'",  # Created before range
            ]

            if entities:
                if hasattr(entities, 'folder_names') and entities.folder_names:
                    folder_conditions = []
                    for folder in entities.folder_names:
                        folder_safe = self._escape_string(folder)
                        folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
                    modified_clauses.append(f"({' OR '.join(folder_conditions)})")

            modified_cypher = f"""
                MATCH (d:structural_document)
                WHERE {' AND '.join(modified_clauses)}
                RETURN
                    d.document_id as document_id,
                    d.prop_title as title,
                    d.semantic_type as semantic_type,
                    d.folder_path as folder_path,
                    d.modified_at as modified_at,
                    'modified' as change_type
                ORDER BY d.modified_at DESC
                LIMIT 100
            """

            modified_result = await self._execute_cypher(modified_cypher, tenant_id)
            changes.extend(modified_result.rows)

        # Count by change type
        added_count = sum(1 for c in changes if c.get("change_type") == "added")
        modified_count = sum(1 for c in changes if c.get("change_type") == "modified")
        deleted_count = sum(1 for c in changes if c.get("change_type") == "deleted")

        return TemporalResult(
            query_type="range",
            changes=changes,
            added_count=added_count,
            modified_count=modified_count,
            deleted_count=deleted_count,
            execution_time_ms=0,  # Combined timing
        )

    async def get_evolution_timeline(
        self,
        tenant_id: str,
        entities: Optional[Any] = None,
        granularity: str = "month",
    ) -> TemporalResult:
        """
        Generate a timeline of structural evolution.

        Groups documents by time period to show growth/changes.

        Example: "How has the Contracts folder evolved this year?"
        """
        where_clauses = [f"d.tenant_id = '{tenant_id}'"]

        if entities:
            if hasattr(entities, 'folder_names') and entities.folder_names:
                folder_conditions = []
                for folder in entities.folder_names:
                    folder_safe = self._escape_string(folder)
                    folder_conditions.append(f"d.folder_path CONTAINS '{folder_safe}'")
                where_clauses.append(f"({' OR '.join(folder_conditions)})")

            if hasattr(entities, 'document_types') and entities.document_types:
                types_str = ", ".join(f"'{_get_enum_value(t)}'" for t in entities.document_types)
                where_clauses.append(f"d.semantic_type IN [{types_str}]")

        where_clause = " AND ".join(where_clauses)

        # Get all documents with temporal info
        cypher = f"""
            MATCH (d:structural_document)
            WHERE {where_clause}
            RETURN
                d.document_id as document_id,
                d.prop_title as title,
                d.semantic_type as semantic_type,
                d.folder_path as folder_path,
                d.created_at as created_at,
                d.modified_at as modified_at
            ORDER BY d.created_at ASC
        """

        result = await self._execute_cypher(cypher, tenant_id)

        # Group by time period
        timeline = self._build_timeline(result.rows, granularity)

        return TemporalResult(
            query_type="evolution",
            timeline=timeline,
            execution_time_ms=result.execution_time_ms,
        )

    async def get_structure_diff(
        self,
        tenant_id: str,
        time_a: datetime,
        time_b: datetime,
        entities: Optional[Any] = None,
    ) -> TemporalResult:
        """
        Compare structure between two points in time.

        Returns:
        - Documents added between time_a and time_b
        - Documents removed between time_a and time_b
        - Documents modified between time_a and time_b
        """
        # Get state at time_a
        state_a = await self.query_at_point_in_time(
            tenant_id=tenant_id,
            point_in_time=time_a,
            entities=entities,
        )

        # Get state at time_b
        state_b = await self.query_at_point_in_time(
            tenant_id=tenant_id,
            point_in_time=time_b,
            entities=entities,
        )

        # Compare
        docs_a = set(d.get("document_id") for d in state_a.state_at_time.get("documents", []) if d.get("document_id"))
        docs_b = set(d.get("document_id") for d in state_b.state_at_time.get("documents", []) if d.get("document_id"))

        added = docs_b - docs_a
        removed = docs_a - docs_b
        unchanged = docs_a & docs_b

        diff = {
            "time_a": time_a.isoformat(),
            "time_b": time_b.isoformat(),
            "count_at_a": len(docs_a),
            "count_at_b": len(docs_b),
            "added_count": len(added),
            "removed_count": len(removed),
            "unchanged_count": len(unchanged),
            "added_ids": list(added)[:20],
            "removed_ids": list(removed)[:20],
        }

        return TemporalResult(
            query_type="diff",
            diff=diff,
            added_count=len(added),
            deleted_count=len(removed),
        )

    def _build_timeline(
        self,
        documents: List[Dict[str, Any]],
        granularity: str,
    ) -> List[Dict[str, Any]]:
        """
        Build a timeline grouping documents by time period.
        """
        timeline_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "added": 0, "types": defaultdict(int)}
        )

        for doc in documents:
            created_at_str = doc.get("created_at")
            if not created_at_str:
                continue

            try:
                if isinstance(created_at_str, str):
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                else:
                    created_at = created_at_str

                # Generate period key
                if granularity == "day":
                    period = created_at.strftime("%Y-%m-%d")
                elif granularity == "week":
                    # Start of week
                    week_start = created_at - timedelta(days=created_at.weekday())
                    period = week_start.strftime("%Y-W%W")
                elif granularity == "month":
                    period = created_at.strftime("%Y-%m")
                else:  # year
                    period = created_at.strftime("%Y")

                timeline_data[period]["count"] += 1
                timeline_data[period]["added"] += 1
                timeline_data[period]["period"] = period

                doc_type = doc.get("semantic_type", "unknown")
                timeline_data[period]["types"][doc_type] += 1

            except (ValueError, TypeError):
                continue

        # Convert to sorted list
        timeline = []
        cumulative = 0
        for period in sorted(timeline_data.keys()):
            data = timeline_data[period]
            cumulative += data["added"]
            timeline.append({
                "period": period,
                "added": data["added"],
                "cumulative_total": cumulative,
                "types": dict(data["types"]),
            })

        return timeline

    async def _execute_cypher(
        self,
        cypher_query: str,
        tenant_id: str,
    ) -> CypherQueryResult:
        """Execute a Cypher query."""
        import time
        start_time = time.time()

        try:
            return_columns = self._extract_return_columns(cypher_query)

            async with self._graph._get_connection() as conn:
                results = await self._graph._execute_cypher(
                    conn,
                    cypher_query,
                    return_columns,
                )

                return CypherQueryResult(
                    query=cypher_query,
                    success=True,
                    rows=results or [],
                    row_count=len(results) if results else 0,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            logger.error(f"Temporal query failed: {e}")
            return CypherQueryResult(
                query=cypher_query,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _extract_return_columns(self, cypher_query: str) -> List[tuple]:
        """Extract return columns from Cypher query."""
        import re

        return_match = re.search(
            r"RETURN\s+(.+?)(?:ORDER BY|LIMIT|$)",
            cypher_query,
            re.IGNORECASE | re.DOTALL,
        )

        if not return_match:
            return [("result", "agtype")]

        return_clause = return_match.group(1).strip()

        columns = []
        for col in return_clause.split(","):
            col = col.strip()
            alias_match = re.search(r"\s+as\s+(\w+)\s*$", col, re.IGNORECASE)
            if alias_match:
                col_name = alias_match.group(1)
            else:
                col_name = re.sub(r"[^\w]", "_", col.split(".")[-1])
            columns.append((col_name, "agtype"))

        return columns if columns else [("result", "agtype")]

    def _escape_string(self, value: str) -> str:
        """Escape string for Cypher."""
        if not value:
            return ""
        return value.replace("'", "''").replace("\\", "\\\\")


# Global singleton instance
temporal_engine = TemporalReasoningEngine()
