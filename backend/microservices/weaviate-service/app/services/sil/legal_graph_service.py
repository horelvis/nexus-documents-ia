"""
Legal Graph Service

Manages the public knowledge graph (knowledge_graph_public) for legal references
between BOE legislation. Separated from tenant knowledge_graph to avoid mixing
public law data with tenant document entities.

Graph structure:
- Nodes: LegalLaw (boe_id, title, short_name, domain, status)
         LegalArticle (article_number, boe_id_parent, content_hash)
- Edges: CONTAINS (LegalLaw → LegalArticle)
         MODIFIES (LegalLaw → LegalLaw)
         DEROGATES (LegalLaw → LegalLaw)
         REFERENCES (LegalLaw → LegalLaw)
         CITES (LegalArticle → LegalArticle)

Usage:
    from app.services.sil.legal_graph_service import legal_graph

    await legal_graph.add_law(law)
    await legal_graph.store_references(boe_id, legal_refs)
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class LawStatus(str, Enum):
    VIGENTE = "vigente"
    DEROGADA = "derogada"
    PARCIALMENTE_DEROGADA = "parcialmente_derogada"


class LegalDomain(str, Enum):
    LABOR = "labor"
    PRIVACY = "privacy"
    FISCAL = "fiscal"
    MERCANTILE = "mercantile"
    CIVIL = "civil"
    ADMINISTRATIVE = "administrative"
    COMPLIANCE = "compliance"
    IP = "ip"
    COMMERCE = "commerce"
    REAL_ESTATE = "real_estate"
    EDUCATION = "education"
    GENERAL = "general"


@dataclass
class LegalLaw:
    """A law node in the legal knowledge graph."""
    boe_id: str
    title: str
    short_name: str
    domain: LegalDomain = LegalDomain.GENERAL
    status: LawStatus = LawStatus.VIGENTE
    publication_date: str = ""
    effective_date: str = ""
    eli_uri: str = ""
    summary: str = ""
    keywords: List[str] = field(default_factory=list)
    weaviate_uuid: Optional[str] = None


class LegalGraphService:
    """
    Service for managing the public legal knowledge graph.

    Uses Apache AGE with a separate graph (knowledge_graph_public) to store
    relationships between laws, keeping it isolated from tenant graphs.
    """

    PUBLIC_GRAPH_NAME = "knowledge_graph_public"

    def __init__(self):
        self._age_service = None
        self._initialized = False

    async def initialize(self):
        """Initialize the service and ensure public graph exists."""
        if self._initialized:
            return

        try:
            from app.services.knowledge.age_graph_service import age_knowledge_graph
            self._age_service = age_knowledge_graph
            await self._age_service.initialize()

            # Ensure public graph exists
            await self._ensure_public_graph()
            self._initialized = True
            logger.info("✅ LegalGraphService initialized")

        except Exception as e:
            logger.warning(f"⚠️ LegalGraphService initialization failed: {e}")
            self._initialized = True  # Prevent retries

    async def _ensure_public_graph(self):
        """Create the public knowledge graph if it doesn't exist."""
        if not self._age_service or not self._age_service._pool:
            return

        try:
            async with self._age_service._get_connection() as conn:
                result = await conn.fetchval(
                    "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1",
                    self.PUBLIC_GRAPH_NAME,
                )
                if result == 0:
                    await conn.execute(
                        f"SELECT create_graph('{self.PUBLIC_GRAPH_NAME}');"
                    )
                    logger.info(f"✅ Created public legal graph: {self.PUBLIC_GRAPH_NAME}")

        except Exception as e:
            logger.warning(f"Failed to ensure public graph: {e}")

    async def _execute_public_cypher(
        self,
        conn,
        cypher_query: str,
        return_columns: List[tuple],
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query against the public graph."""
        import json

        col_specs = ", ".join([f"{name} agtype" for name, _ in return_columns])
        sql = f"""
            SELECT * FROM cypher('{self.PUBLIC_GRAPH_NAME}', $$
                {cypher_query}
            $$) AS ({col_specs});
        """

        try:
            rows = await conn.fetch(sql)
            results = []
            for row in rows:
                result = {}
                for i, (col_name, _) in enumerate(return_columns):
                    value = row[i]
                    if value is not None:
                        if isinstance(value, str):
                            try:
                                result[col_name] = json.loads(value)
                            except (json.JSONDecodeError, ValueError):
                                result[col_name] = value
                        else:
                            result[col_name] = value
                    else:
                        result[col_name] = None
                results.append(result)
            return results

        except Exception as e:
            logger.error(f"Public graph Cypher failed: {e}\nQuery: {cypher_query}")
            raise

    async def add_law(self, law: LegalLaw) -> bool:
        """
        Add or update a LegalLaw node in the public graph.

        Args:
            law: LegalLaw dataclass with law metadata

        Returns:
            True if successful
        """
        if not self._age_service or not self._age_service._pool:
            await self.initialize()
        if not self._age_service or not self._age_service._pool:
            return False

        try:
            boe_id = law.boe_id.replace("'", "''")
            title = law.title.replace("'", "''")[:500]
            short_name = law.short_name.replace("'", "''")
            summary = law.summary.replace("'", "''")[:500]
            weaviate_uuid = (law.weaviate_uuid or "").replace("'", "''")

            async with self._age_service._get_connection() as conn:
                # MERGE: create or update
                cypher = f"""
                    MERGE (l:LegalLaw {{boe_id: '{boe_id}'}})
                    ON CREATE SET
                        l.title = '{title}',
                        l.short_name = '{short_name}',
                        l.domain = '{law.domain.value}',
                        l.status = '{law.status.value}',
                        l.publication_date = '{law.publication_date}',
                        l.effective_date = '{law.effective_date}',
                        l.eli_uri = '{law.eli_uri}',
                        l.summary = '{summary}',
                        l.weaviate_uuid = '{weaviate_uuid}'
                    ON MATCH SET
                        l.title = '{title}',
                        l.short_name = '{short_name}',
                        l.status = '{law.status.value}',
                        l.weaviate_uuid = '{weaviate_uuid}'
                    RETURN id(l)
                """

                await self._execute_public_cypher(conn, cypher, [("id", "bigint")])
                logger.info(f"Added/updated LegalLaw: {law.short_name} ({law.boe_id})")
                return True

        except Exception as e:
            logger.error(f"Failed to add law {law.boe_id}: {e}")
            return False

    async def add_reference(
        self,
        source_boe_id: str,
        target_boe_id: str,
        relationship_type: str,
        context_snippet: str = "",
        articles_affected: Optional[List[str]] = None,
    ) -> bool:
        """
        Add a relationship edge between two laws in the public graph.

        Args:
            source_boe_id: Source law BOE ID
            target_boe_id: Target law BOE ID
            relationship_type: MODIFIES, DEROGATES, REFERENCES, or CITES
            context_snippet: Optional context text
            articles_affected: Optional list of affected article numbers

        Returns:
            True if successful
        """
        if not self._age_service or not self._age_service._pool:
            await self.initialize()
        if not self._age_service or not self._age_service._pool:
            return False

        try:
            src = source_boe_id.replace("'", "''")
            tgt = target_boe_id.replace("'", "''")
            snippet = (context_snippet or "")[:300].replace("'", "''")
            rel = relationship_type.upper()
            articles = articles_affected or []
            articles_str = str(articles).replace("'", '"')

            async with self._age_service._get_connection() as conn:
                cypher = f"""
                    MATCH (s:LegalLaw {{boe_id: '{src}'}})
                    MATCH (t:LegalLaw {{boe_id: '{tgt}'}})
                    MERGE (s)-[r:{rel}]->(t)
                    ON CREATE SET
                        r.context_snippet = '{snippet}',
                        r.articles_affected = '{articles_str}'
                    RETURN id(r)
                """

                await self._execute_public_cypher(conn, cypher, [("id", "bigint")])
                logger.debug(f"Added {rel}: {source_boe_id} → {target_boe_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to add reference {source_boe_id} → {target_boe_id}: {e}")
            return False

    async def store_references(
        self,
        boe_id: str,
        legal_refs: "LegalReferences",
    ) -> Dict[str, int]:
        """
        Store all extracted legal references as graph edges.

        Args:
            boe_id: Source law BOE ID
            legal_refs: Extracted references from LegalReferenceExtractor

        Returns:
            Dict with counts of stored references by type
        """
        counts = {"references": 0, "modifications": 0, "derogations": 0}

        # Store cross-BOE references
        for cited_id in legal_refs.cited_boe_ids:
            if await self.add_reference(boe_id, cited_id, "REFERENCES"):
                counts["references"] += 1

        # Store modifications
        for mod in legal_refs.modifications:
            # Try to find the modifying law's BOE ID from the text
            # For now, store as a reference with context
            if mod.modifying_law:
                # Try to resolve BOE ID from the modifying law text
                boe_ids_in_text = legal_refs.cited_boe_ids
                for candidate_id in boe_ids_in_text:
                    if candidate_id in mod.modifying_text:
                        if await self.add_reference(
                            candidate_id,
                            boe_id,
                            "MODIFIES",
                            context_snippet=mod.modifying_text,
                            articles_affected=mod.articles_affected,
                        ):
                            counts["modifications"] += 1
                        break

        # Store derogations
        for derog in legal_refs.derogations:
            if derog.derogating_law:
                for candidate_id in legal_refs.cited_boe_ids:
                    if candidate_id in derog.derogating_text:
                        if await self.add_reference(
                            candidate_id,
                            boe_id,
                            "DEROGATES",
                            context_snippet=derog.derogating_text,
                            articles_affected=derog.articles_affected,
                        ):
                            counts["derogations"] += 1
                        break

        logger.info(
            f"[{boe_id}] Stored graph references: "
            f"{counts['references']} REFERENCES, "
            f"{counts['modifications']} MODIFIES, "
            f"{counts['derogations']} DEROGATES"
        )

        return counts

    async def get_law_neighbors(
        self,
        boe_id: str,
        max_depth: int = 2,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring laws via graph traversal in the public graph.

        Args:
            boe_id: Starting law BOE ID
            max_depth: Maximum traversal depth
            relationship_types: Filter by relationship types

        Returns:
            List of neighbor law dicts with relationship info
        """
        if not self._age_service or not self._age_service._pool:
            await self.initialize()
        if not self._age_service or not self._age_service._pool:
            return []

        try:
            boe_escaped = boe_id.replace("'", "''")

            async with self._age_service._get_connection() as conn:
                cypher = f"""
                    MATCH (start:LegalLaw {{boe_id: '{boe_escaped}'}})
                          -[r*1..{max_depth}]-(neighbor:LegalLaw)
                    RETURN DISTINCT
                        neighbor.boe_id AS boe_id,
                        neighbor.short_name AS short_name,
                        neighbor.title AS title,
                        neighbor.domain AS domain,
                        type(r[0]) AS rel_type,
                        length(r) AS depth
                    LIMIT 20
                """

                results = await self._execute_public_cypher(
                    conn,
                    cypher,
                    [
                        ("boe_id", "text"),
                        ("short_name", "text"),
                        ("title", "text"),
                        ("domain", "text"),
                        ("rel_type", "text"),
                        ("depth", "int"),
                    ],
                )

                return results

        except Exception as e:
            logger.error(f"Failed to get law neighbors for {boe_id}: {e}")
            return []

    async def get_graph_stats(self) -> Dict[str, Any]:
        """Get statistics about the public legal graph."""
        if not self._age_service or not self._age_service._pool:
            return {"initialized": False}

        try:
            async with self._age_service._get_connection() as conn:
                # Count laws
                law_results = await self._execute_public_cypher(
                    conn,
                    "MATCH (l:LegalLaw) RETURN count(l) AS total",
                    [("total", "int")],
                )
                total_laws = law_results[0]["total"] if law_results else 0

                # Count edges
                edge_results = await self._execute_public_cypher(
                    conn,
                    "MATCH ()-[r]->() RETURN count(r) AS total",
                    [("total", "int")],
                )
                total_edges = edge_results[0]["total"] if edge_results else 0

                return {
                    "initialized": True,
                    "graph_name": self.PUBLIC_GRAPH_NAME,
                    "total_laws": total_laws,
                    "total_edges": total_edges,
                }

        except Exception as e:
            logger.error(f"Failed to get public graph stats: {e}")
            return {"initialized": True, "error": str(e)}


# Global singleton
legal_graph = LegalGraphService()
