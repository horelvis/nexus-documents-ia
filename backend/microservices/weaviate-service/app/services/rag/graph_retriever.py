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
        """Initialize the retriever and graph service."""
        if self._initialized:
            return

        if not settings.rag_knowledge_graph_enabled:
            logger.info("ℹ️ Graph-enhanced retrieval disabled")
            return

        try:
            if settings.rag_graph_use_age:
                # Use Apache AGE backend (PostgreSQL native graph)
                from ..knowledge.age_graph_service import age_knowledge_graph
                self._graph_service = age_knowledge_graph
                logger.info("📊 Using Apache AGE backend for knowledge graph")
            else:
                # Fallback to NetworkX + Redis backend
                from ..knowledge.graph_service import knowledge_graph_service
                self._graph_service = knowledge_graph_service
                logger.info("📊 Using NetworkX+Redis backend for knowledge graph")

            await self._graph_service.initialize()

            # Initialize public legal graph service for PublicKnowledge queries
            try:
                from ..sil.legal_graph_service import legal_graph
                await legal_graph.initialize()
                self._legal_graph_service = legal_graph
                logger.info("📊 Public legal graph available for query expansion")
            except Exception as e:
                logger.debug(f"Public legal graph not available: {e}")

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
            # Step 1: Detect entities in the query
            query_text = query_analysis.original_query
            detected = await self._graph_service.find_entities_in_text(
                tenant_id=tenant_id,
                text=query_text,
                limit=5,
            )

            if not detected:
                logger.debug(f"No graph entities found in query: {query_text[:50]}...")
                return query_analysis

            logger.info(f"🔍 Graph expansion: found {len(detected)} entities in query")

            # Step 2: Get neighbors for each detected entity
            all_neighbors: List[Dict[str, Any]] = []
            seen_values: Set[str] = {d.get("entity_value", "").lower() for d in detected}

            for entity in detected:
                entity_id = entity.get("entity_id")
                if not entity_id:
                    continue

                neighbors = await self._graph_service.get_neighbors(
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    max_depth=settings.rag_graph_traversal_depth,
                )

                for neighbor in neighbors:
                    value = neighbor.get("entity_value", "")
                    if value.lower() not in seen_values:
                        seen_values.add(value.lower())
                        all_neighbors.append(neighbor)

            if not all_neighbors:
                logger.debug("No new neighbors found via graph traversal")
                return query_analysis

            # Step 3: Select best expansion terms
            # Sort by relationship strength and select top N
            all_neighbors.sort(key=lambda x: x.get("relationship_strength", 0), reverse=True)
            expansion_terms = [
                n.get("entity_value", "")
                for n in all_neighbors[:self._max_expansion_terms]
                if len(n.get("entity_value", "")) >= self._min_entity_length
            ]

            if not expansion_terms:
                return query_analysis

            # Step 4: Create expanded query variation
            expansion_text = " ".join(expansion_terms)
            expanded_variation = f"{query_text} {expansion_text}"

            # Add to query variations (will be searched alongside original)
            if expanded_variation not in query_analysis.query_variations:
                query_analysis.query_variations.append(expanded_variation)

            # Store graph expansion metadata
            if not hasattr(query_analysis, 'graph_expansion') or query_analysis.graph_expansion is None:
                # Add metadata to the existing object
                query_analysis.graph_expansion = {
                    "applied": True,
                    "detected_entities": [e.get("entity_value") for e in detected],
                    "expanded_terms": expansion_terms,
                    "expansion_variation": expanded_variation,
                }

            logger.info(
                f"📊 Graph expansion: added {len(expansion_terms)} terms "
                f"from {len(detected)} detected entities"
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
            from ..sil.legal_graph_service import legal_graph
            # Try to find laws mentioned by short name
            # This is a simple approach — check known abbreviations
            from app.api.boe_legislation import LAW_SHORT_NAMES
            short_to_boe = {v: k for k, v in LAW_SHORT_NAMES.items()}

            # Find short names in query (case-sensitive, word boundary)
            for short_name, law_boe_id in short_to_boe.items():
                if re.search(rf'\b{re.escape(short_name)}\b', query_text):
                    boe_ids.append(law_boe_id)

            if not boe_ids:
                return query_analysis

            # Get neighbors from legal graph
            all_neighbors = []
            seen = set(boe_ids)

            for bid in boe_ids:
                neighbors = await legal_graph.get_law_neighbors(bid, max_depth=1)
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
            # Detect entities
            detected = await self._graph_service.find_entities_in_text(
                tenant_id=tenant_id,
                text=query,
                limit=5,
            )
            result.detected_entities = detected

            if not detected:
                return result

            # Get all neighbors
            all_neighbors = []
            seen_values = {d.get("entity_value", "").lower() for d in detected}

            for entity in detected:
                entity_id = entity.get("entity_id")
                if not entity_id:
                    continue

                neighbors = await self._graph_service.get_neighbors(
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    max_depth=settings.rag_graph_traversal_depth,
                )

                for neighbor in neighbors:
                    value = neighbor.get("entity_value", "")
                    if value.lower() not in seen_values:
                        seen_values.add(value.lower())
                        all_neighbors.append(neighbor)

            result.neighbor_entities = all_neighbors

            # Build expansion terms
            all_neighbors.sort(key=lambda x: x.get("relationship_strength", 0), reverse=True)
            expansion_terms = [
                n.get("entity_value", "")
                for n in all_neighbors[:self._max_expansion_terms]
                if len(n.get("entity_value", "")) >= self._min_entity_length
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
