"""
Graph-Enhanced Retriever

Expands queries using knowledge graph traversal to improve retrieval recall.
Finds entities mentioned in the query, then uses BFS to discover related
entities that can be added as query expansions.

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    GraphEnhancedRetriever                    │
├─────────────────────────────────────────────────────────────┤
│  Query: "¿Cuáles son las obligaciones de Juan García?"       │
│                        ↓                                     │
│  Step 1: Detect entities in query                            │
│          → Found: "Juan García" (PERSON)                     │
│                        ↓                                     │
│  Step 2: Traverse graph (BFS, depth=2)                       │
│          → Neighbors: "Acme Corp" (ORGANIZATION),            │
│                       "Contrato 2024-001" (REFERENCE)        │
│                        ↓                                     │
│  Step 3: Add to query variations                             │
│          → "obligaciones Juan García Acme Corp Contrato..."  │
└─────────────────────────────────────────────────────────────┘

This Stage 0 expansion happens BEFORE vector/BM25 search, improving recall
by including semantically related terms discovered through the graph.

Usage:
    from app.services.rag.graph_retriever import graph_retriever

    # Expand query with graph-based terms
    expanded = await graph_retriever.expand_query_with_graph(
        query_analysis=analysis,
        tenant_id="tenant-123"
    )

    # Check if expansion was applied
    if expanded.graph_expansion_applied:
        logger.info(f"Added {len(expanded.graph_expanded_terms)} terms")
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from .models import QueryAnalysis
from ...core.config import settings

logger = logging.getLogger(__name__)



@dataclass
class GraphExpansionResult:
    """Result of graph-based query expansion."""
    original_query: str
    expanded_terms: List[str] = field(default_factory=list)
    detected_entities: List[Dict[str, Any]] = field(default_factory=list)
    neighbor_entities: List[Dict[str, Any]] = field(default_factory=list)
    expansion_applied: bool = False
    expansion_variation: Optional[str] = None


class GraphEnhancedRetriever:
    """
    Graph-Enhanced Retriever for query expansion.

    Uses the knowledge graph to:
    1. Detect entities mentioned in the query
    2. Find related entities via graph traversal
    3. Add related entity values as query expansions

    Supports two graph backends:
    - Tenant graph (knowledge_graph): for tenant document entities
    - Public graph (knowledge_graph_public): for legal law references

    This improves recall for queries about specific entities by including
    their related concepts in the search.
    """

    def __init__(self):
        self._graph_service = None
        self._legal_graph_service = None
        self._initialized = False
        self._max_expansion_terms = 5  # Max terms to add from graph
        self._min_entity_length = 3    # Min chars for entity detection

    async def initialize(self) -> None:
        """Initialize the retriever with knowledge-tree HTTP client."""
        if self._initialized:
            return

        if not settings.rag_knowledge_graph_enabled:
            logger.info("ℹ️ Graph-enhanced retrieval disabled")
            return

        try:
            from app.clients.knowledge_tree_client import knowledge_tree_legal_client
            self._graph_service = knowledge_tree_legal_client
            self._legal_graph_service = knowledge_tree_legal_client
            logger.info("📊 Using knowledge-tree-service HTTP for graph expansion")

            self._initialized = True
            logger.info("✅ GraphEnhancedRetriever initialized")

        except Exception as e:
            logger.warning(f"⚠️ Graph service not available: {e}")
            self._initialized = True  # Mark as initialized to avoid retries

    async def expand_query_with_graph(
        self,
        query_analysis: QueryAnalysis,
        tenant_id: str,
        source_type: str = "tenant",
    ) -> QueryAnalysis:
        """
        Expand query using knowledge graph traversal.

        Modifies query_analysis in-place by adding graph-derived terms
        to query_variations.

        Args:
            query_analysis: Analyzed query from Layer 1
            tenant_id: Tenant identifier
            source_type: "tenant" for tenant graph, "public" for public legal graph

        Returns:
            Modified QueryAnalysis with graph expansions added
        """
        # For public source, use legal graph for expansion
        if source_type == "public" and self._legal_graph_service:
            return await self._expand_with_legal_graph(query_analysis)

        if not settings.rag_knowledge_graph_enabled or not self._graph_service:
            return query_analysis

        await self.initialize()

        if not self._graph_service:
            return query_analysis

        try:
            # Use knowledge-tree-service HTTP to search entities in query
            query_text = query_analysis.original_query

            # Extract potential entity terms (words > 3 chars) and search graph
            result = await self._graph_service.search_entity(
                tenant_id=tenant_id,
                value=query_text,
                max_depth=settings.rag_graph_traversal_depth,
                limit=self._max_expansion_terms,
            )

            entity = result.get("entity")
            neighbors = result.get("neighbors", [])

            if not entity and not neighbors:
                logger.debug(f"No graph entities found in query: {query_text[:50]}...")
                return query_analysis

            logger.info(f"🔍 Graph expansion: found entity + {len(neighbors)} neighbors")

            # Collect expansion terms from neighbors
            seen_values: Set[str] = set()
            if entity:
                seen_values.add(entity.get("value", "").lower())

            expansion_terms = []
            for neighbor in neighbors:
                value = neighbor.get("value", "") or neighbor.get("entity_value", "")
                if value and value.lower() not in seen_values and len(value) >= self._min_entity_length:
                    seen_values.add(value.lower())
                    expansion_terms.append(value)

            if not expansion_terms:
                return query_analysis

            # Create expanded query variation
            expansion_text = " ".join(expansion_terms[:self._max_expansion_terms])
            expanded_variation = f"{query_text} {expansion_text}"

            if expanded_variation not in query_analysis.query_variations:
                query_analysis.query_variations.append(expanded_variation)

            if not hasattr(query_analysis, 'graph_expansion') or query_analysis.graph_expansion is None:
                query_analysis.graph_expansion = {
                    "applied": True,
                    "detected_entities": [entity.get("value")] if entity else [],
                    "expanded_terms": expansion_terms,
                    "expansion_variation": expanded_variation,
                }

            logger.info(
                f"📊 Graph expansion: added {len(expansion_terms)} terms via knowledge-tree"
            )

            return query_analysis

        except Exception as e:
            logger.warning(f"⚠️ Graph expansion failed: {e}")
            return query_analysis

    async def _expand_with_legal_graph(
        self,
        query_analysis: QueryAnalysis,
    ) -> QueryAnalysis:
        """
        Expand query using the public legal knowledge graph.

        Detects BOE IDs and law short names in the query, then finds
        related laws via the legal graph for query expansion.
        """
        import re

        try:
            query_text = query_analysis.original_query

            # Detect BOE IDs in the query
            boe_pattern = re.compile(r'BOE-[A-Z]-\d{4}-\d+')
            boe_ids = boe_pattern.findall(query_text)

            # Also check for law short names (ET, LPRL, etc.)
            from app.api.boe_legislation import LAW_SHORT_NAMES
            short_to_boe = {v: k for k, v in LAW_SHORT_NAMES.items()}

            # Find short names in query (case-sensitive, word boundary)
            for short_name, law_boe_id in short_to_boe.items():
                if re.search(rf'\b{re.escape(short_name)}\b', query_text):
                    boe_ids.append(law_boe_id)

            if not boe_ids:
                return query_analysis

            # Get neighbors from legal graph via HTTP client
            from app.clients.knowledge_tree_client import knowledge_tree_legal_client
            all_neighbors = []
            seen = set(boe_ids)

            for bid in boe_ids:
                neighbors = await knowledge_tree_legal_client.get_law_neighbors(bid, max_depth=1)
                for n in neighbors:
                    n_id = n.get("boe_id", "")
                    if n_id and n_id not in seen:
                        seen.add(n_id)
                        all_neighbors.append(n)

            if not all_neighbors:
                return query_analysis

            # Add short names of related laws as expansion terms
            expansion_terms = [
                n.get("short_name", "")
                for n in all_neighbors[:self._max_expansion_terms]
                if n.get("short_name")
            ]

            if expansion_terms:
                expansion_text = " ".join(expansion_terms)
                expanded_variation = f"{query_text} {expansion_text}"

                if expanded_variation not in query_analysis.query_variations:
                    query_analysis.query_variations.append(expanded_variation)

                if not hasattr(query_analysis, 'graph_expansion') or query_analysis.graph_expansion is None:
                    query_analysis.graph_expansion = {
                        "applied": True,
                        "source": "public_legal_graph",
                        "detected_boe_ids": boe_ids,
                        "expanded_terms": expansion_terms,
                    }

                logger.info(
                    f"📊 Legal graph expansion: added {len(expansion_terms)} related laws "
                    f"from {len(boe_ids)} detected laws"
                )

        except Exception as e:
            logger.warning(f"⚠️ Legal graph expansion failed: {e}")

        return query_analysis

    async def get_expansion_details(
        self,
        query: str,
        tenant_id: str,
    ) -> GraphExpansionResult:
        """
        Get detailed expansion information without modifying the query.

        Useful for debugging and understanding graph expansion behavior.

        Args:
            query: Query text
            tenant_id: Tenant identifier

        Returns:
            GraphExpansionResult with expansion details
        """
        result = GraphExpansionResult(original_query=query)

        if not settings.rag_knowledge_graph_enabled or not self._graph_service:
            return result

        await self.initialize()

        if not self._graph_service:
            return result

        try:
            search_result = await self._graph_service.search_entity(
                tenant_id=tenant_id,
                value=query,
                max_depth=settings.rag_graph_traversal_depth,
                limit=self._max_expansion_terms,
            )

            entity = search_result.get("entity")
            neighbors = search_result.get("neighbors", [])

            if entity:
                result.detected_entities = [entity]
            result.neighbor_entities = neighbors

            if not neighbors:
                return result

            expansion_terms = [
                n.get("value", "") or n.get("entity_value", "")
                for n in neighbors[:self._max_expansion_terms]
                if len(n.get("value", "") or n.get("entity_value", "")) >= self._min_entity_length
            ]

            result.expanded_terms = expansion_terms

            if expansion_terms:
                result.expansion_applied = True
                expansion_text = " ".join(expansion_terms)
                result.expansion_variation = f"{query} {expansion_text}"

            return result

        except Exception as e:
            logger.warning(f"⚠️ Expansion details failed: {e}")
            return result


# Global singleton instance
graph_retriever = GraphEnhancedRetriever()
