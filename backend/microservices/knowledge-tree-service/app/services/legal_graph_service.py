"""
Legal Graph Service (Consolidated)

Manages the public knowledge graph (knowledge_graph_public) for legal references
between BOE legislation. This is the single source of truth for all legal graph
operations, consolidating logic previously split between weaviate-service and
knowledge-tree-service.

Graph structure:
- Nodes: LegalLaw (boe_id, title, short_name, domain, status)
         LegalArticle (article_number, boe_id_parent, content_hash)
- Edges: CONTAINS (LegalLaw -> LegalArticle)
         MODIFIES (LegalLaw -> LegalLaw)
         DEROGATES (LegalLaw -> LegalLaw)
         REFERENCES (LegalLaw -> LegalLaw)
         CITES (LegalArticle -> LegalArticle)

Usage:
    from app.services.legal_graph_service import legal_graph

    await legal_graph.add_law(law)
    await legal_graph.store_references(boe_id, legal_refs)
"""

import json
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from app.services.age_client import age_client

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

    Consolidated from weaviate-service into knowledge-tree-service as the
    single source of truth for all graph operations.
    """

    PUBLIC_GRAPH_NAME = "knowledge_graph_public"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Initialize the service and ensure public graph exists."""
        if self._initialized:
            return

        try:
            await age_client.initialize()
            await self._ensure_public_graph()
            self._initialized = True
            logger.info("LegalGraphService initialized")
        except Exception as e:
            logger.warning(f"LegalGraphService initialization failed: {e}")
            self._initialized = True

    async def _ensure_public_graph(self):
        """Create the public knowledge graph if it doesn't exist."""
        if not age_client._pool:
            return

        try:
            async with age_client._get_connection() as conn:
                result = await conn.fetchval(
                    "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1",
                    self.PUBLIC_GRAPH_NAME,
                )
                if result == 0:
                    await conn.execute(
                        f"SELECT create_graph('{self.PUBLIC_GRAPH_NAME}');"
                    )
                    logger.info(f"Created public legal graph: {self.PUBLIC_GRAPH_NAME}")
        except Exception as e:
            logger.warning(f"Failed to ensure public graph: {e}")

    async def _execute_public_cypher(
        self,
        conn,
        cypher_query: str,
        return_columns: List[tuple],
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query against the public graph."""
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

    def _clean_agtype_strings(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip agtype quoting from string results."""
        for r in results:
            for k, v in r.items():
                if isinstance(v, str) and v.startswith('"') and v.endswith('"'):
                    r[k] = v.strip('"')
        return results

    async def _get_conn(self):
        """Get a connection context manager from the AGE client."""
        return age_client._get_connection()

    # ── Law CRUD ──────────────────────────────────────────────────────

    async def add_law(self, law: LegalLaw) -> bool:
        """Add or update a LegalLaw node in the public graph."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return False

        try:
            boe_id = law.boe_id.replace("'", "''")
            title = law.title.replace("'", "''")[:500]
            short_name = law.short_name.replace("'", "''")
            summary = law.summary.replace("'", "''")[:500]
            weaviate_uuid = (law.weaviate_uuid or "").replace("'", "''")

            async with age_client._get_connection() as conn:
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

    async def get_law(self, boe_id: str) -> Optional[Dict[str, Any]]:
        """Get a single law by BOE ID."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return None

        try:
            boe_escaped = boe_id.replace("'", "''")
            async with age_client._get_connection() as conn:
                results = await self._execute_public_cypher(
                    conn,
                    f"""
                    MATCH (l:LegalLaw {{boe_id: '{boe_escaped}'}})
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
                if results:
                    return self._clean_agtype_strings(results)[0]
                return None
        except Exception as e:
            logger.error(f"Failed to get law {boe_id}: {e}")
            return None

    # ── References ────────────────────────────────────────────────────

    async def add_reference(
        self,
        source_boe_id: str,
        target_boe_id: str,
        relationship_type: str,
        context_snippet: str = "",
        articles_affected: Optional[List[str]] = None,
    ) -> bool:
        """Add a relationship edge between two laws in the public graph."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return False

        try:
            src = source_boe_id.replace("'", "''")
            tgt = target_boe_id.replace("'", "''")
            snippet = (context_snippet or "")[:300].replace("'", "''")
            rel = relationship_type.upper()
            articles = articles_affected or []
            articles_str = str(articles).replace("'", '"')

            async with age_client._get_connection() as conn:
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
                logger.debug(f"Added {rel}: {source_boe_id} -> {target_boe_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to add reference {source_boe_id} -> {target_boe_id}: {e}")
            return False

    async def store_references(
        self,
        boe_id: str,
        legal_refs: "LegalReferences",
    ) -> Dict[str, int]:
        """Store all extracted legal references as graph edges."""
        counts = {"references": 0, "modifications": 0, "derogations": 0}

        for cited_id in legal_refs.cited_boe_ids:
            if await self.add_reference(boe_id, cited_id, "REFERENCES"):
                counts["references"] += 1

        for mod in legal_refs.modifications:
            if mod.modifying_law:
                boe_ids_in_text = legal_refs.cited_boe_ids
                for candidate_id in boe_ids_in_text:
                    if candidate_id in mod.modifying_text:
                        if await self.add_reference(
                            candidate_id, boe_id, "MODIFIES",
                            context_snippet=mod.modifying_text,
                            articles_affected=mod.articles_affected,
                        ):
                            counts["modifications"] += 1
                        break

        for derog in legal_refs.derogations:
            if derog.derogating_law:
                for candidate_id in legal_refs.cited_boe_ids:
                    if candidate_id in derog.derogating_text:
                        if await self.add_reference(
                            candidate_id, boe_id, "DEROGATES",
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

    # ── Traversal ─────────────────────────────────────────────────────

    async def get_law_neighbors(
        self,
        boe_id: str,
        max_depth: int = 2,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Get neighboring laws via graph traversal in the public graph."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return []

        try:
            boe_escaped = boe_id.replace("'", "''")
            async with age_client._get_connection() as conn:
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
                    conn, cypher,
                    [
                        ("boe_id", "text"), ("short_name", "text"),
                        ("title", "text"), ("domain", "text"),
                        ("rel_type", "text"), ("depth", "int"),
                    ],
                )
                return self._clean_agtype_strings(results)
        except Exception as e:
            logger.error(f"Failed to get law neighbors for {boe_id}: {e}")
            return []

    # ── Stats & Structure ─────────────────────────────────────────────

    async def get_graph_stats(self) -> Dict[str, Any]:
        """Get statistics about the public legal graph."""
        if not age_client._pool:
            return {"initialized": False}

        try:
            async with age_client._get_connection() as conn:
                law_results = await self._execute_public_cypher(
                    conn,
                    "MATCH (l:LegalLaw) RETURN count(l) AS total",
                    [("total", "int")],
                )
                total_laws = law_results[0]["total"] if law_results else 0

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

    async def get_stats(self) -> Dict[str, Any]:
        """Alias for get_graph_stats."""
        return await self.get_graph_stats()

    async def get_all_laws(self) -> List[Dict[str, Any]]:
        """Get all LegalLaw nodes from the public graph."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return []

        try:
            async with age_client._get_connection() as conn:
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
                return self._clean_agtype_strings(results)
        except Exception as e:
            logger.error(f"Failed to get all laws: {e}")
            return []

    async def get_laws_by_domain(self, domain) -> List[Dict[str, Any]]:
        """Get laws filtered by domain."""
        all_laws = await self.get_all_laws()
        domain_val = domain.value if hasattr(domain, 'value') else str(domain)
        return [law for law in all_laws if law.get("domain") == domain_val]

    async def get_graph_structure(self) -> Dict[str, Any]:
        """Get full graph structure (nodes + edges) for D3 visualization."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return {"nodes": [], "edges": []}

        try:
            async with age_client._get_connection() as conn:
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
                for n in self._clean_agtype_strings(law_nodes):
                    nodes.append({
                        "id": n.get("boe_id", ""),
                        "label": n.get("short_name") or n.get("boe_id", ""),
                        "node_type": "law",
                        "domain": n.get("domain", ""),
                        "status": n.get("status", ""),
                        "title": n.get("title", ""),
                    })

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
                        [("source", "text"), ("target", "text"), ("rel_type", "text")],
                    )
                    for e in self._clean_agtype_strings(edge_results):
                        src = e.get("source", "")
                        tgt = e.get("target", "")
                        rel = e.get("rel_type", "")
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
        Get enriched graph structure with domain clusters and metrics.

        Returns dict with nodes, edges, and stats including degree centrality
        and domain clustering.
        """
        base = await self.get_graph_structure()
        nodes = base.get("nodes", [])
        edges = base.get("edges", [])

        if not nodes:
            return {"nodes": [], "edges": [], "stats": {}}

        # Calculate node degrees
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

        for node in nodes:
            node_id = node["id"]
            deg = degree_map.get(node_id, {"in": 0, "out": 0, "total": 0})
            node["degree_in"] = deg["in"]
            node["degree_out"] = deg["out"]
            node["degree_total"] = deg["total"]
            node["is_hub"] = deg["total"] >= 5

        # Create domain cluster nodes
        domains_seen: Dict[str, List[str]] = {}
        for node in nodes:
            domain = node.get("domain", "general")
            if domain not in domains_seen:
                domains_seen[domain] = []
            domains_seen[domain].append(node["id"])

        domain_labels = {
            "labor": "Laboral", "fiscal": "Fiscal", "civil": "Civil",
            "mercantile": "Mercantil", "administrative": "Administrativo",
            "compliance": "Compliance", "privacy": "Privacidad",
            "ip": "Propiedad Intelectual", "commerce": "Comercio",
            "real_estate": "Inmobiliario", "education": "Educacion",
            "general": "General",
        }

        domain_nodes = []
        domain_edges = []
        for domain, law_ids in domains_seen.items():
            domain_node_id = f"domain_{domain}"
            domain_nodes.append({
                "id": domain_node_id,
                "label": domain_labels.get(domain, domain.title()),
                "node_type": "domain",
                "domain": domain,
                "law_count": len(law_ids),
            })
            for law_id in law_ids:
                domain_edges.append({
                    "id": f"d_{domain}_{law_id}",
                    "source": domain_node_id,
                    "target": law_id,
                    "label": "CONTAINS",
                    "edge_type": "domain_membership",
                })

        all_nodes = nodes + domain_nodes
        all_edges = edges + domain_edges

        stats = {
            "total_laws": len(nodes),
            "total_relationships": len(edges),
            "total_domains": len(domain_nodes),
            "hub_laws": [n["label"] for n in nodes if n.get("is_hub")],
            "domains": {d: len(laws) for d, laws in domains_seen.items()},
            "edge_types": {},
        }
        for edge in edges:
            rel = edge.get("label", "UNKNOWN")
            stats["edge_types"][rel] = stats["edge_types"].get(rel, 0) + 1

        return {"nodes": all_nodes, "edges": all_edges, "stats": stats}

    # ── Articles ──────────────────────────────────────────────────────

    async def get_articles_for_law(self, boe_id: str) -> List[Dict[str, Any]]:
        """Get all articles for a specific law."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return []

        try:
            boe_escaped = boe_id.replace("'", "''")
            async with age_client._get_connection() as conn:
                results = await self._execute_public_cypher(
                    conn,
                    f"""
                    MATCH (l:LegalLaw {{boe_id: '{boe_escaped}'}})-[:CONTAINS]->(a:LegalArticle)
                    RETURN a.article_number AS article_number,
                           a.content_hash AS content_hash
                    """,
                    [("article_number", "text"), ("content_hash", "text")],
                )
                return self._clean_agtype_strings(results)
        except Exception as e:
            logger.error(f"Failed to get articles for {boe_id}: {e}")
            return []

    async def add_article(
        self, boe_id: str, article_number: str, content_hash: str = ""
    ) -> bool:
        """Add an article node linked to a law."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return False

        try:
            boe_escaped = boe_id.replace("'", "''")
            art_escaped = article_number.replace("'", "''")
            hash_escaped = content_hash.replace("'", "''")

            async with age_client._get_connection() as conn:
                cypher = f"""
                    MATCH (l:LegalLaw {{boe_id: '{boe_escaped}'}})
                    MERGE (a:LegalArticle {{boe_id_parent: '{boe_escaped}', article_number: '{art_escaped}'}})
                    SET a.content_hash = '{hash_escaped}'
                    MERGE (l)-[:CONTAINS]->(a)
                    RETURN id(a)
                """
                await self._execute_public_cypher(conn, cypher, [("id", "bigint")])
                return True
        except Exception as e:
            logger.error(f"Failed to add article {article_number} to {boe_id}: {e}")
            return False

    # ── Document-Law Linking ──────────────────────────────────────────

    async def link_document_to_law(
        self, document_id: str, law_boe_id: str, tenant_id: str, relationship: str = "GOVERNED_BY"
    ) -> bool:
        """Link a tenant document to a law in the public graph."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return False

        try:
            doc_escaped = document_id.replace("'", "''")
            boe_escaped = law_boe_id.replace("'", "''")
            tenant_escaped = tenant_id.replace("'", "''")

            async with age_client._get_connection() as conn:
                cypher = f"""
                    MATCH (l:LegalLaw {{boe_id: '{boe_escaped}'}})
                    MERGE (d:DocumentRef {{document_id: '{doc_escaped}', tenant_id: '{tenant_escaped}'}})
                    MERGE (d)-[:{relationship}]->(l)
                    RETURN id(d)
                """
                await self._execute_public_cypher(conn, cypher, [("id", "bigint")])
                return True
        except Exception as e:
            logger.error(f"Failed to link document {document_id} to law {law_boe_id}: {e}")
            return False

    async def get_applicable_laws(
        self, document_id: str, tenant_id: str
    ) -> List[Dict[str, Any]]:
        """Get laws linked to a document."""
        if not age_client._pool:
            await self.initialize()
        if not age_client._pool:
            return []

        try:
            doc_escaped = document_id.replace("'", "''")
            tenant_escaped = tenant_id.replace("'", "''")

            async with age_client._get_connection() as conn:
                results = await self._execute_public_cypher(
                    conn,
                    f"""
                    MATCH (d:DocumentRef {{document_id: '{doc_escaped}', tenant_id: '{tenant_escaped}'}})
                          -[r]->(l:LegalLaw)
                    RETURN l.boe_id AS boe_id, l.short_name AS short_name,
                           l.title AS title, l.domain AS domain,
                           type(r) AS relationship
                    """,
                    [
                        ("boe_id", "text"), ("short_name", "text"),
                        ("title", "text"), ("domain", "text"),
                        ("relationship", "text"),
                    ],
                )
                return self._clean_agtype_strings(results)
        except Exception as e:
            logger.error(f"Failed to get applicable laws for {document_id}: {e}")
            return []

    async def find_applicable_laws_for_domain(
        self, document_type: str, domain: str
    ) -> List[Dict[str, Any]]:
        """Suggest applicable laws based on document type and domain."""
        return await self.get_laws_by_domain(domain)


# Global singleton
legal_graph = LegalGraphService()
