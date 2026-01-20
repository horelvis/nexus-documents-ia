"""
Pre-LLM Reasoning Engine

The core of the Structural Intelligence Layer.
Processes queries BEFORE they reach the LLM to determine:
1. Can this be answered structurally (without reading documents)?
2. If content is needed, which specific documents?
3. What structural context should accompany the LLM prompt?

This engine significantly reduces token usage by:
- Answering structural questions directly via Cypher
- Focusing RAG on specific documents when content IS needed
- Providing rich structural context to the LLM

Typical Flow:
┌──────────────────────────────────────────────────────────────────┐
│  User Query                                                       │
│       │                                                           │
│       ▼                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│  │   Intent     │ →  │   Cypher     │ →  │   Execute    │        │
│  │   Detector   │    │   Builder    │    │   Query      │        │
│  └──────────────┘    └──────────────┘    └──────────────┘        │
│       │                                         │                 │
│       ▼                                         ▼                 │
│  ┌──────────────┐                      ┌──────────────┐          │
│  │  Structural? │  YES →               │  Graph       │          │
│  │              │ ─────────────────────│  Result      │──→ Done  │
│  └──────────────┘                      └──────────────┘          │
│       │ NO (Content needed)                                       │
│       ▼                                                           │
│  ┌──────────────┐    ┌──────────────┐                            │
│  │  Locate Docs │ →  │  Focused     │ → RAG (specific docs only) │
│  │  (Cypher)    │    │  RAG         │                            │
│  └──────────────┘    └──────────────┘                            │
└──────────────────────────────────────────────────────────────────┘
"""

import logging
import time
from typing import Optional, List, Dict, Any

from .schemas import (
    Intent,
    IntentType,
    ReasoningType,
    ReasoningResult,
    StructuralContext,
    CypherQueryResult,
    StructuralEntities,
)
from .intent_detector import IntentDetector, intent_detector
from .cypher_builder import CypherBuilder, cypher_builder
from ...services.knowledge.age_graph_service import AGEKnowledgeGraphService, age_knowledge_graph
from ...core.config import settings

logger = logging.getLogger(__name__)


class PreLLMReasoningEngine:
    """
    Pre-LLM Reasoning Engine.

    Processes queries before the LLM to:
    1. Detect if the query is structural (can be answered from graph)
    2. Execute structural queries via Cypher
    3. Build structural context for the LLM
    4. Identify target documents for focused RAG
    """

    def __init__(
        self,
        detector: Optional[IntentDetector] = None,
        builder: Optional[CypherBuilder] = None,
        graph_service: Optional[AGEKnowledgeGraphService] = None,
    ):
        self._detector = detector or intent_detector
        self._builder = builder or cypher_builder
        self._graph = graph_service or age_knowledge_graph
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the reasoning engine."""
        if self._initialized:
            return

        await self._detector.initialize()
        await self._builder.initialize()
        await self._graph.initialize()

        self._initialized = True
        logger.info("✅ PreLLMReasoningEngine initialized")

    async def process_query(
        self,
        query: str,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Process a query with structural intelligence.

        Args:
            query: The user's query
            tenant_id: Tenant identifier

        Returns:
            ReasoningResult with structural context and/or target documents
        """
        start_time = time.time()

        await self.initialize()

        # Step 1: Detect intent
        intent = await self._detector.detect_intent(query)

        logger.info(
            f"🧠 Intent detected: {intent.type.value} "
            f"(confidence: {intent.confidence:.2f})"
        )

        # Step 2: Route based on intent type
        if self._is_purely_structural(intent):
            # Can answer from graph alone
            result = await self._answer_structurally(intent, tenant_id)
        elif self._is_temporal(intent):
            # Temporal query
            result = await self._answer_temporally(intent, tenant_id)
        elif self._is_multihop(intent):
            # Multi-hop traversal
            result = await self._answer_multihop(intent, tenant_id)
        elif self._is_focused_content(intent):
            # Need content, but from specific documents
            result = await self._prepare_focused_rag(intent, tenant_id)
        else:
            # Full RAG needed
            result = self._prepare_full_rag(intent, tenant_id)

        result.processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"  Reasoning type: {result.type.value}, "
            f"requires_rag: {result.requires_rag}, "
            f"time: {result.processing_time_ms:.0f}ms"
        )

        return result

    def _is_purely_structural(self, intent: Intent) -> bool:
        """Check if query can be answered from structure alone."""
        structural_intents = {
            IntentType.STRUCTURAL,
            IntentType.STRUCTURAL_COUNT,
            IntentType.STRUCTURAL_LIST,
            IntentType.STRUCTURAL_EXISTS,
            IntentType.STRUCTURAL_LOCATION,
        }
        return intent.type in structural_intents and not intent.requires_content

    def _is_temporal(self, intent: Intent) -> bool:
        """Check if query involves temporal reasoning."""
        temporal_intents = {
            IntentType.TEMPORAL_POINT,
            IntentType.TEMPORAL_RANGE,
            IntentType.TEMPORAL_EVOLUTION,
            IntentType.TEMPORAL_COMPARISON,
        }
        return intent.type in temporal_intents

    def _is_multihop(self, intent: Intent) -> bool:
        """Check if query requires multi-hop traversal."""
        return intent.type in {IntentType.MULTIHOP_SIMPLE, IntentType.MULTIHOP_COMPLEX}

    def _is_focused_content(self, intent: Intent) -> bool:
        """Check if we need content but from specific documents."""
        return intent.type == IntentType.CONTENT_SPECIFIC

    async def _answer_structurally(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a purely structural query from the graph.

        No RAG needed - the graph contains all the information.
        """
        # Build and execute Cypher query
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build structural context
        structural_context = self._build_structural_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        return ReasoningResult(
            type=ReasoningType.STRUCTURAL,
            structural_context=structural_context,
            cypher_result=cypher_result,
            requires_rag=False,
            requires_llm_interpretation=True,  # LLM still formats the answer
            reasoning_explanation=(
                f"Query answered structurally via Cypher. "
                f"Found {cypher_result.row_count} results."
            ),
        )

    async def _answer_temporally(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a temporal query using the temporal aspects of the graph.
        """
        # Build temporal Cypher query
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build temporal context
        structural_context = self._build_temporal_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        return ReasoningResult(
            type=ReasoningType.TEMPORAL,
            structural_context=structural_context,
            cypher_result=cypher_result,
            requires_rag=False,
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Temporal query answered from graph. "
                f"Found {cypher_result.row_count} temporal results."
            ),
        )

    async def _answer_multihop(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Answer a multi-hop query by traversing the graph.
        """
        # Build multi-hop Cypher query
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Build structural context with traversal info
        structural_context = self._build_multihop_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        # Multi-hop queries might still need focused RAG for content
        needs_content = intent.requires_content

        return ReasoningResult(
            type=ReasoningType.MULTIHOP if not needs_content else ReasoningType.HYBRID,
            structural_context=structural_context,
            cypher_result=cypher_result,
            target_document_ids=[
                row.get("document_id") for row in cypher_result.rows
                if row.get("document_id")
            ] if needs_content else [],
            requires_rag=needs_content,
            rag_scope="focused" if needs_content else "none",
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Multi-hop traversal completed with {intent.multihop_query.estimated_hops if intent.multihop_query else 'N/A'} hops. "
                f"Found {cypher_result.row_count} results."
            ),
        )

    async def _prepare_focused_rag(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Prepare for focused RAG by identifying specific target documents.

        Instead of searching the entire corpus, we:
        1. Use the graph to find relevant documents structurally
        2. Pass only those document IDs to RAG
        3. Include structural context for the LLM
        """
        # First, locate documents structurally
        cypher_query = self._builder.build_query(intent, tenant_id)
        cypher_result = await self._execute_cypher(cypher_query, tenant_id)

        # Extract document IDs for focused RAG
        target_doc_ids = [
            row.get("document_id") for row in cypher_result.rows
            if row.get("document_id")
        ]

        # Build structural context
        structural_context = self._build_structural_context(
            intent=intent,
            cypher_result=cypher_result,
        )

        return ReasoningResult(
            type=ReasoningType.FOCUSED_RAG,
            structural_context=structural_context,
            cypher_result=cypher_result,
            target_document_ids=target_doc_ids,
            requires_rag=True,
            rag_scope="focused",
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Content needed from {len(target_doc_ids)} specific documents. "
                f"RAG will be focused on these documents only."
            ),
        )

    def _prepare_full_rag(
        self,
        intent: Intent,
        tenant_id: str,
    ) -> ReasoningResult:
        """
        Prepare for full RAG when structural filtering isn't sufficient.
        """
        # Still build some structural context if we have entities
        structural_context = StructuralContext(
            query_type="general",
            query_result={"intent": intent.type.value},
            details={"entities": self._entities_to_dict(intent.entities)},
        )

        return ReasoningResult(
            type=ReasoningType.FULL_RAG,
            structural_context=structural_context,
            requires_rag=True,
            rag_scope="full_corpus",
            requires_llm_interpretation=True,
            reasoning_explanation=(
                f"Full corpus search needed. Intent: {intent.type.value}"
            ),
        )

    async def _execute_cypher(
        self,
        cypher_query: str,
        tenant_id: str,
    ) -> CypherQueryResult:
        """Execute a Cypher query against the structural graph."""
        start_time = time.time()

        try:
            # Parse the query to determine return columns
            # This is a simplified approach - in production, parse properly
            return_columns = self._extract_return_columns(cypher_query)

            async with self._graph._get_connection() as conn:
                results = await self._graph._execute_cypher(
                    conn,
                    cypher_query,
                    return_columns,
                )

                execution_time = (time.time() - start_time) * 1000

                # Process results
                rows = results if results else []

                # Check for count result
                count = None
                if rows and "total" in rows[0]:
                    count = rows[0]["total"]
                elif rows and "count" in rows[0]:
                    count = rows[0]["count"]

                return CypherQueryResult(
                    query=cypher_query,
                    success=True,
                    rows=rows,
                    row_count=len(rows),
                    count=count,
                    items=rows,
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            logger.error(f"Cypher query failed: {e}")
            return CypherQueryResult(
                query=cypher_query,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _extract_return_columns(self, cypher_query: str) -> List[tuple]:
        """
        Extract return column specifications from a Cypher query.

        This is a simplified parser - in production, use proper parsing.
        """
        import re

        # Find the RETURN clause
        return_match = re.search(
            r"RETURN\s+(.+?)(?:ORDER BY|LIMIT|$)",
            cypher_query,
            re.IGNORECASE | re.DOTALL,
        )

        if not return_match:
            return [("result", "agtype")]

        return_clause = return_match.group(1).strip()

        # Split by comma, handling AS aliases
        columns = []
        for col in return_clause.split(","):
            col = col.strip()

            # Check for alias
            alias_match = re.search(r"\s+as\s+(\w+)\s*$", col, re.IGNORECASE)
            if alias_match:
                col_name = alias_match.group(1)
            else:
                # Extract simple name
                col_name = re.sub(r"[^\w]", "_", col.split(".")[-1])

            columns.append((col_name, "agtype"))

        return columns if columns else [("result", "agtype")]

    def _build_structural_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
    ) -> StructuralContext:
        """Build structural context from query results."""
        context = StructuralContext()

        # Determine query type
        if intent.entities.count_requested:
            context.query_type = "count"
            if cypher_result.count is not None:
                context.query_result = {"count": cypher_result.count}
        elif intent.entities.exists_check:
            context.query_type = "exists"
            exists = cypher_result.row_count > 0
            context.query_result = {
                "exists": exists,
                "count": cypher_result.row_count,
            }
        elif intent.type == IntentType.STRUCTURAL_LOCATION:
            context.query_type = "location"
        else:
            context.query_type = "list"

        # Extract document info
        context.document_count = cypher_result.row_count
        context.document_ids = [
            row.get("document_id", "") for row in cypher_result.rows
            if row.get("document_id")
        ]
        context.document_titles = [
            row.get("title", "Untitled") for row in cypher_result.rows
            if row.get("title")
        ]
        context.document_types = [
            row.get("semantic_type", "") for row in cypher_result.rows
            if row.get("semantic_type")
        ]

        # Extract folder paths
        folder_paths = set()
        for row in cypher_result.rows:
            if row.get("folder_path"):
                folder_paths.add(row["folder_path"])

        if folder_paths:
            context.folder_path = list(folder_paths)[0] if len(folder_paths) == 1 else None
            context.folder_hierarchy = list(folder_paths)

        # Extract domains
        domains = set()
        for row in cypher_result.rows:
            if row.get("domain"):
                domains.add(row["domain"])
        context.semantic_domain = list(domains)[0] if len(domains) == 1 else None
        context.semantic_types = list(set(context.document_types))

        # Full query result in details
        context.query_result = {
            "type": context.query_type,
            "count": context.document_count,
            "items": cypher_result.rows[:20],  # Limit for context size
        }

        return context

    def _build_temporal_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
    ) -> StructuralContext:
        """Build context for temporal queries."""
        context = self._build_structural_context(intent, cypher_result)

        # Add temporal-specific information
        if intent.temporal_markers:
            context.query_type = f"temporal_{intent.type.value.replace('temporal_', '')}"

            if intent.temporal_markers.start_date:
                context.details["start_date"] = intent.temporal_markers.start_date.isoformat()
            if intent.temporal_markers.end_date:
                context.details["end_date"] = intent.temporal_markers.end_date.isoformat()
            if intent.temporal_markers.point_in_time:
                context.details["point_in_time"] = intent.temporal_markers.point_in_time.isoformat()

        return context

    def _build_multihop_context(
        self,
        intent: Intent,
        cypher_result: CypherQueryResult,
    ) -> StructuralContext:
        """Build context for multi-hop queries."""
        context = self._build_structural_context(intent, cypher_result)

        # Add multi-hop specific info
        if intent.multihop_query:
            context.query_type = f"multihop_{intent.multihop_query.estimated_hops}hop"
            context.details["hops"] = intent.multihop_query.estimated_hops
            context.details["start_entity"] = intent.multihop_query.start_entity_value

        return context

    def _entities_to_dict(self, entities: StructuralEntities) -> Dict[str, Any]:
        """Convert entities to dictionary for context."""
        return {
            "clients": entities.client_names,
            "document_types": [t.value for t in entities.document_types],
            "domains": [d.value for d in entities.domains],
            "years": entities.years,
            "folders": entities.folder_names,
        }


# Global singleton instance
pre_llm_engine = PreLLMReasoningEngine()
