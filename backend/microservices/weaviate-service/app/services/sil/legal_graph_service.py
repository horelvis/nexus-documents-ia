"""
DEPRECATED: Legal Graph Service

The canonical implementation now lives in knowledge-tree-service.
Runtime API consumers should use the HTTP client:
    from app.clients.knowledge_tree_client import knowledge_tree_legal_client

This module is kept ONLY for scripts (seed_legal_graph.py,
populate_legal_edges.py, connect_orphan_laws.py) that run
inside the weaviate-service container and need direct AGE access.

TODO: Migrate scripts to knowledge-tree-service and delete this file.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import settings

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
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection with AGE loaded and search path set."""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute('SET search_path = ag_catalog, "$user", public;')
            yield conn

    async def initialize(self):
        """Initialize the service with its own asyncpg pool."""
        if self._initialized:
            return

        try:
            db_url = settings.database_url
            if "+asyncpg" in db_url:
                db_url = db_url.replace("+asyncpg", "")

            self._pool = await asyncpg.create_pool(
                db_url, min_size=1, max_size=5, command_timeout=30,
            )

            # Ensure public graph exists
            await self._ensure_public_graph()
            self._initialized = True
            logger.info("✅ LegalGraphService initialized (self-contained pool)")

        except Exception as e:
            logger.warning(f"⚠️ LegalGraphService initialization failed: {e}")
            self._initialized = True  # Prevent retries

    async def _ensure_public_graph(self):
        """Create the public knowledge graph if it doesn't exist."""
        if not self._pool:
            return

        try:
            async with self._get_connection() as conn:
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
        if not self._pool:
            await self.initialize()
        if not self._pool:
            return False

        try:
            boe_id = law.boe_id.replace("'", "''")
            title = law.title.replace("'", "''")[:500]
            short_name = law.short_name.replace("'", "''")
            summary = law.summary.replace("'", "''")[:500]
            weaviate_uuid = (law.weaviate_uuid or "").replace("'", "''")

            async with self._get_connection() as conn:
                # MERGE + SET (Apache AGE doesn't support ON CREATE/ON MATCH)
                cypher = f"""
                    MERGE (l:LegalLaw {{boe_id: '{boe_id}'}})
                    SET l.title = '{title}',
                        l.short_name = '{short_name}',
                        l.domain = '{law.domain.value}',
                        l.status = '{law.status.value}',
                        l.publication_date = '{law.publication_date}',
                        l.effective_date = '{law.effective_date}',
                        l.eli_uri = '{law.eli_uri}',
                        l.summary = '{summary}',
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
        if not self._pool:
            await self.initialize()
        if not self._pool:
            return False

        try:
            src = source_boe_id.replace("'", "''")
            tgt = target_boe_id.replace("'", "''")
            snippet = (context_snippet or "")[:300].replace("'", "''")
            rel = relationship_type.upper()
            articles = articles_affected or []
            articles_str = str(articles).replace("'", '"')

            async with self._get_connection() as conn:
                # Check if edge already exists to avoid duplicates
                check_cypher = f"""
                    MATCH (s:LegalLaw {{boe_id: '{src}'}})-[r:{rel}]->(t:LegalLaw {{boe_id: '{tgt}'}})
                    RETURN count(r) AS cnt
                """
                existing = await self._execute_public_cypher(conn, check_cypher, [("cnt", "bigint")])
                if existing and existing[0].get("cnt", 0) > 0:
                    logger.debug(f"Edge already exists: {src} -{rel}-> {tgt}")
                    return False

                cypher = f"""
                    MATCH (s:LegalLaw {{boe_id: '{src}'}})
                    MATCH (t:LegalLaw {{boe_id: '{tgt}'}})
                    CREATE (s)-[r:{rel} {{context_snippet: '{snippet}', articles_affected: '{articles_str}'}}]->(t)
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
        if not self._pool:
            await self.initialize()
        if not self._pool:
            return []

        try:
            boe_escaped = boe_id.replace("'", "''")

            async with self._get_connection() as conn:
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
        if not self._pool:
            return {"initialized": False}

        try:
            async with self._get_connection() as conn:
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


    # Alias for API compatibility
    async def get_stats(self) -> Dict[str, Any]:
        return await self.get_graph_stats()

    async def get_all_laws(self) -> List[Dict[str, Any]]:
        """Get all LegalLaw nodes from the public graph."""
        if not self._pool:
            await self.initialize()
        if not self._pool:
            return []

        try:
            async with self._get_connection() as conn:
                results = await self._execute_public_cypher(
                    conn,
                    """
                    MATCH (l:LegalLaw)
                    RETURN l.boe_id AS boe_id, l.title AS title,
                           l.short_name AS short_name, l.domain AS domain,
                           l.status AS status, l.publication_date AS publication_date,
                           l.weaviate_uuid AS weaviate_uuid
                    """,
                    [
                        ("boe_id", "text"), ("title", "text"),
                        ("short_name", "text"), ("domain", "text"),
                        ("status", "text"), ("publication_date", "text"),
                        ("weaviate_uuid", "text"),
                    ],
                )
                # Clean agtype quoting
                for r in results:
                    for k, v in r.items():
                        if isinstance(v, str) and v.startswith('"') and v.endswith('"'):
                            r[k] = v.strip('"')
                return results
        except Exception as e:
            logger.error(f"Failed to get all laws: {e}")
            return []

    async def get_laws_by_domain(self, domain) -> List[Dict[str, Any]]:
        """Get laws filtered by domain."""
        all_laws = await self.get_all_laws()
        domain_val = domain.value if hasattr(domain, 'value') else str(domain)
        return [l for l in all_laws if l.get("domain") == domain_val]

    async def get_graph_structure(self) -> Dict[str, Any]:
        """
        Get full graph structure (nodes + edges) for D3 visualization.

        Returns dict with 'nodes' and 'edges' arrays.
        """
        if not self._pool:
            await self.initialize()
        if not self._pool:
            return {"nodes": [], "edges": []}

        try:
            async with self._get_connection() as conn:
                # Get all law nodes
                law_nodes = await self._execute_public_cypher(
                    conn,
                    """
                    MATCH (l:LegalLaw)
                    RETURN id(l) AS nid, l.boe_id AS boe_id,
                           l.short_name AS short_name, l.title AS title,
                           l.domain AS domain, l.status AS status
                    """,
                    [
                        ("nid", "bigint"), ("boe_id", "text"),
                        ("short_name", "text"), ("title", "text"),
                        ("domain", "text"), ("status", "text"),
                    ],
                )

                nodes = []
                for n in law_nodes:
                    boe_id = n.get("boe_id", "")
                    if isinstance(boe_id, str) and boe_id.startswith('"'):
                        boe_id = boe_id.strip('"')
                    short_name = n.get("short_name", "")
                    if isinstance(short_name, str) and short_name.startswith('"'):
                        short_name = short_name.strip('"')
                    domain = n.get("domain", "")
                    if isinstance(domain, str) and domain.startswith('"'):
                        domain = domain.strip('"')
                    status = n.get("status", "")
                    if isinstance(status, str) and status.startswith('"'):
                        status = status.strip('"')
                    title = n.get("title", "")
                    if isinstance(title, str) and title.startswith('"'):
                        title = title.strip('"')
                    nodes.append({
                        "id": boe_id,
                        "label": short_name or boe_id,
                        "node_type": "law",
                        "domain": domain,
                        "status": status,
                        "title": title,
                    })

                # Get all edges (deduplicated)
                edges = []
                seen_edges = set()
                try:
                    edge_results = await self._execute_public_cypher(
                        conn,
                        """
                        MATCH (s:LegalLaw)-[r]->(t:LegalLaw)
                        RETURN DISTINCT s.boe_id AS source, t.boe_id AS target,
                               type(r) AS rel_type
                        """,
                        [
                            ("source", "text"), ("target", "text"),
                            ("rel_type", "text"),
                        ],
                    )
                    for e in edge_results:
                        src = e.get("source", "")
                        tgt = e.get("target", "")
                        rel = e.get("rel_type", "")
                        if isinstance(src, str) and src.startswith('"'):
                            src = src.strip('"')
                        if isinstance(tgt, str) and tgt.startswith('"'):
                            tgt = tgt.strip('"')
                        if isinstance(rel, str) and rel.startswith('"'):
                            rel = rel.strip('"')
                        key = (src, tgt, rel)
                        if key in seen_edges:
                            continue
                        seen_edges.add(key)
                        edges.append({
                            "id": f"e{len(edges)}",
                            "source": src,
                            "target": tgt,
                            "label": rel,
                        })
                except Exception as edge_err:
                    logger.warning(f"Failed to get edges: {edge_err}")

                return {"nodes": nodes, "edges": edges}

        except Exception as e:
            logger.error(f"Failed to get graph structure: {e}")
            return {"nodes": [], "edges": []}

    async def get_enriched_graph_structure(self) -> Dict[str, Any]:
        """
        Get enriched graph structure with domain clusters, topics, and metrics.

        Returns dict with:
        - nodes: Law nodes + Domain nodes + Topic nodes
        - edges: Law relationships + Domain membership + Topic connections
        - stats: Graph statistics and metrics
        """
        # Get base structure
        base = await self.get_graph_structure()
        nodes = base.get("nodes", [])
        edges = base.get("edges", [])

        if not nodes:
            return {"nodes": [], "edges": [], "stats": {}}

        # Calculate node degrees (connection counts)
        degree_map: Dict[str, Dict[str, int]] = {}
        for node in nodes:
            degree_map[node["id"]] = {"in": 0, "out": 0, "total": 0}

        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            if src in degree_map:
                degree_map[src]["out"] += 1
                degree_map[src]["total"] += 1
            if tgt in degree_map:
                degree_map[tgt]["in"] += 1
                degree_map[tgt]["total"] += 1

        # Enrich law nodes with degree info
        for node in nodes:
            node_id = node["id"]
            deg = degree_map.get(node_id, {"in": 0, "out": 0, "total": 0})
            node["degree_in"] = deg["in"]
            node["degree_out"] = deg["out"]
            node["degree_total"] = deg["total"]
            # Hub score: nodes with many connections are hubs
            node["is_hub"] = deg["total"] >= 5

        # Create domain cluster nodes
        domains_seen: Dict[str, List[str]] = {}
        for node in nodes:
            domain = node.get("domain", "general")
            if domain not in domains_seen:
                domains_seen[domain] = []
            domains_seen[domain].append(node["id"])

        domain_nodes = []
        domain_edges = []
        domain_labels = {
            "labor": "Laboral",
            "fiscal": "Fiscal",
            "civil": "Civil",
            "mercantile": "Mercantil",
            "administrative": "Administrativo",
            "compliance": "Compliance",
            "privacy": "Privacidad",
            "ip": "Propiedad Intelectual",
            "commerce": "Comercio",
            "real_estate": "Inmobiliario",
            "education": "Educación",
            "general": "General",
        }

        for domain, law_ids in domains_seen.items():
            domain_node_id = f"domain_{domain}"
            domain_nodes.append({
                "id": domain_node_id,
                "label": domain_labels.get(domain, domain.title()),
                "node_type": "domain",
                "domain": domain,
                "law_count": len(law_ids),
            })
            # Create edges from domain to laws
            for law_id in law_ids:
                domain_edges.append({
                    "id": f"d_{domain}_{law_id}",
                    "source": domain_node_id,
                    "target": law_id,
                    "label": "CONTAINS",
                    "edge_type": "domain_membership",
                })

        # Try to get topics/keywords from Weaviate for topic nodes
        topic_nodes = []
        topic_edges = []
        try:
            from app.services.weaviate_service import weaviate_service
            await weaviate_service.initialize()

            # Query unique keywords from PublicKnowledge
            client = weaviate_service.client
            result = client.query.get(
                "PublicKnowledge",
                ["boe_id", "keywords"]
            ).with_limit(100).do()

            docs = result.get("data", {}).get("Get", {}).get("PublicKnowledge", [])

            # Build keyword -> laws mapping
            keyword_laws: Dict[str, List[str]] = {}
            for doc in docs:
                boe_id = doc.get("boe_id", "")
                keywords = doc.get("keywords", []) or []
                for kw in keywords[:5]:  # Limit keywords per law
                    if kw and len(kw) > 2:
                        kw_lower = kw.lower()
                        if kw_lower not in keyword_laws:
                            keyword_laws[kw_lower] = []
                        if boe_id not in keyword_laws[kw_lower]:
                            keyword_laws[kw_lower].append(boe_id)

            # Create topic nodes for keywords shared by multiple laws
            for keyword, law_ids in keyword_laws.items():
                if len(law_ids) >= 2:  # Only topics shared by 2+ laws
                    topic_id = f"topic_{keyword.replace(' ', '_')}"
                    topic_nodes.append({
                        "id": topic_id,
                        "label": keyword.title(),
                        "node_type": "topic",
                        "law_count": len(law_ids),
                    })
                    for law_id in law_ids[:10]:  # Limit edges per topic
                        topic_edges.append({
                            "id": f"t_{keyword[:10]}_{law_id}",
                            "source": topic_id,
                            "target": law_id,
                            "label": "COVERS",
                            "edge_type": "topic_coverage",
                        })

        except Exception as e:
            logger.warning(f"Could not fetch topics from Weaviate: {e}")

        # Combine all nodes and edges
        all_nodes = nodes + domain_nodes + topic_nodes[:30]  # Limit topic nodes
        all_edges = edges + domain_edges + topic_edges[:100]  # Limit topic edges

        # Calculate statistics
        stats = {
            "total_laws": len(nodes),
            "total_relationships": len(edges),
            "total_domains": len(domain_nodes),
            "total_topics": len(topic_nodes),
            "hub_laws": [n["label"] for n in nodes if n.get("is_hub")],
            "domains": {d: len(laws) for d, laws in domains_seen.items()},
            "edge_types": {},
        }

        # Count edge types
        for edge in edges:
            rel = edge.get("label", "UNKNOWN")
            stats["edge_types"][rel] = stats["edge_types"].get(rel, 0) + 1

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "stats": stats,
        }


# Global singleton
legal_graph = LegalGraphService()
