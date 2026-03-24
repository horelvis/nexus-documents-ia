"""
Subgraph Extractor — BKG Phases 5-6

Extracts multi-hop subgraphs from the FalkorDB knowledge graph rooted at query entities.
Returns structured node/edge data for LLM consumption (not flat document IDs).

Architecture:
    1. Entity Resolution: Find seed nodes matching query entities
    2. N-hop Traversal: Expand neighborhood including shared nodes
    3. Pruning & Scoring: Rank paths, cap at max_nodes

Node labels (FalkorDB schema):
    Document, Folder, Entity, Law, Memory

Edge labels (FalkorDB schema):
    MENTIONED_IN, RELATED_TO, CONTAINED_IN, REFERENCES_LAW, HAS_MEMORY, INSTANCE_OF
"""

import logging
from typing import Any, Dict, List, Set, Tuple

from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)


# Edge relevance weights for pruning (higher = more important)
_EDGE_WEIGHTS: Dict[str, float] = {
    "MENTIONED_IN": 1.0,
    "RELATED_TO": 0.5,
    "CONTAINED_IN": 0.6,
    "REFERENCES_LAW": 0.85,
    "HAS_MEMORY": 0.2,
    "INSTANCE_OF": 0.3,
    "EXTRACTED_FROM": 0.9,
    "ABOUT": 0.85,
    "CONTRADICTS": 1.0,
    "SUPPORTS": 0.7,
}

# Node type bonus (higher = more useful for LLM context)
_NODE_TYPE_BONUS: Dict[str, float] = {
    "Document": 1.0,
    "Entity": 0.9,
    "Claim": 0.95,
    "Law": 0.8,
    "Folder": 0.4,
    "Memory": 0.3,
}


class SubgraphExtractor:
    """Extracts multi-hop subgraphs from FalkorDB knowledge graph."""

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await falkordb_client.initialize()
        self._initialized = True

    async def extract(
        self,
        tenant_id: str,
        entities: List[Dict[str, Any]],
        max_hops: int = 2,
        max_nodes: int = 30,
        include_legal: bool = True,
        include_memories: bool = False,
    ) -> Dict[str, Any]:
        """Extract a subgraph rooted at the given entities.

        Args:
            tenant_id: Tenant identifier
            entities: List of {"value": str, "type": str|None} seed entities
            max_hops: Maximum traversal depth (1-3)
            max_nodes: Maximum nodes in response
            include_legal: Whether to include Law nodes
            include_memories: Whether to include Memory nodes

        Returns:
            {"nodes": [...], "edges": [...], "root_entities": [...], "pruned_count": int}
        """
        if not self._initialized:
            await self.initialize()

        max_hops = min(max(max_hops, 1), 3)

        # Step 1: Resolve seed entities
        seeds, seed_names = await self._resolve_seeds(tenant_id, entities)
        if not seeds:
            return {"nodes": [], "edges": [], "root_entities": [], "pruned_count": 0}

        # Step 2: N-hop traversal from seeds — batch by node ID
        seed_nids = [s["nid"] for s in seeds if s.get("nid") is not None]
        raw_nodes, raw_edges = await self._traverse(
            seed_nids, tenant_id, max_nodes * 3,
        )

        # Merge seed nodes into raw_nodes
        for seed in seeds:
            node_key = seed.get("id", seed.get("name", ""))
            if node_key and node_key not in {n.get("id") for n in raw_nodes}:
                raw_nodes.append(seed)

        # Step 3: Filter out Memory nodes if not requested
        if not include_memories:
            memory_ids = {n["id"] for n in raw_nodes if n.get("label") == "Memory"}
            raw_nodes = [n for n in raw_nodes if n.get("label") != "Memory"]
            raw_edges = [e for e in raw_edges
                         if e.get("source_id") not in memory_ids
                         and e.get("target_id") not in memory_ids]

        # Step 4: Prune and score
        nodes, edges, pruned_count = self._prune(
            raw_nodes, raw_edges, seed_names, max_nodes,
        )

        return {
            "nodes": nodes,
            "edges": edges,
            "root_entities": list(seed_names),
            "pruned_count": pruned_count,
        }

    async def _resolve_seeds(
        self, tenant_id: str, entities: List[Dict[str, Any]],
    ) -> Tuple[List[Dict], Set[str]]:
        """Find graph nodes matching the query entities.

        Searches by name, associated_person, and title properties.
        Uses a single UNWIND batch query instead of one query per entity.
        Returns (seed_nodes, seed_names).
        """
        # Collect search values from entities (cap at 5, skip blanks)
        search_vals = []
        for entity in entities[:5]:
            value = entity.get("value", "").strip()
            if value and len(value) >= 2:
                search_vals.append(value.lower())

        if not search_vals:
            return [], set()

        query = """
            UNWIND $search_vals AS search_val
            MATCH (n)
            WHERE n.tenant_id = $tenant_id
              AND (toLower(n.name) CONTAINS search_val
                   OR toLower(n.associated_person) CONTAINS search_val
                   OR toLower(n.title) CONTAINS search_val)
            RETURN id(n) as node_id, labels(n)[0] as label,
                   n.name as name, n.title as title,
                   n.document_id as document_id,
                   n.semantic_type as semantic_type,
                   n.domain as domain,
                   n.associated_person as associated_person,
                   search_val as matched_query
            LIMIT 25
        """
        all_seeds: List[Dict] = []
        seed_names: Set[str] = set()
        seen_ids: Set[str] = set()

        try:
            rows = await falkordb_client.execute_cypher(
                query, {"tenant_id": tenant_id, "search_vals": search_vals}
            )
            for row in rows:
                node_id = row.get("node_id")
                node_id_str = str(node_id) if node_id is not None else None

                # Deduplicate by node ID
                if node_id_str is None or node_id_str in seen_ids:
                    continue
                seen_ids.add(node_id_str)

                label = row.get("label") or "unknown"
                matched_query = row.get("matched_query") or ""
                name = row.get("name") or row.get("title") or matched_query

                node = {
                    "id": node_id_str,
                    "label": label,
                    "name": name,
                    "properties": _extract_properties(row),
                    "graph_source": "tenant",
                    "nid": node_id,
                }
                all_seeds.append(node)
                seed_names.add(name)
        except Exception as e:
            logger.warning(f"Batch seed resolution failed: {e}")

        return all_seeds, seed_names

    async def _traverse(
        self,
        seed_nids: List[int],
        tenant_id: str,
        limit: int,
    ) -> Tuple[List[Dict], List[Dict]]:
        """Batch 2-hop traversal from all seed nodes in a single Cypher query.

        Uses explicit hop1 + OPTIONAL hop2 instead of variable-length paths
        so FalkorDB can bind individual relationship variables.  One query
        replaces the previous per-seed loop (N seeds → N queries → 1 query).

        Args:
            seed_nids: Integer node IDs returned by _resolve_seeds.
            tenant_id: Tenant identifier for neighbour visibility filter.
            limit: Maximum rows to fetch (applied at Cypher level).

        Returns:
            (nodes, edges) discovered in the neighbourhood.
        """
        if not seed_nids:
            return [], []

        nodes: List[Dict] = []
        edges: List[Dict] = []
        seen_nodes: Set[str] = set()

        query = """
            MATCH (seed)
            WHERE id(seed) IN $seed_ids
            MATCH (seed)-[r1]-(hop1)
            WHERE hop1.tenant_id = $tid OR hop1.shared = true
            OPTIONAL MATCH (hop1)-[r2]-(hop2)
            WHERE (hop2.tenant_id = $tid OR hop2.shared = true)
              AND id(hop2) <> id(seed)
            RETURN
              id(seed)        AS seed_id,
              seed.name       AS seed_name,
              type(r1)        AS r1_type,
              r1.confidence   AS r1_confidence,
              r1.source       AS r1_source,
              r1.article      AS r1_article,
              id(hop1)                   AS h1_id,
              labels(hop1)[0]            AS h1_label,
              hop1.name                  AS h1_name,
              hop1.title                 AS h1_title,
              hop1.document_id           AS h1_doc_id,
              hop1.semantic_type         AS h1_stype,
              hop1.domain                AS h1_domain,
              type(r2)        AS r2_type,
              r2.confidence   AS r2_confidence,
              r2.source       AS r2_source,
              r2.article      AS r2_article,
              id(hop2)                   AS h2_id,
              labels(hop2)[0]            AS h2_label,
              hop2.name                  AS h2_name,
              hop2.title                 AS h2_title,
              hop2.document_id           AS h2_doc_id,
              hop2.semantic_type         AS h2_stype,
              hop2.domain                AS h2_domain
            LIMIT $limit
        """
        try:
            rows = await falkordb_client.execute_cypher(
                query,
                {"seed_ids": seed_nids, "tid": tenant_id, "limit": limit},
            )
        except Exception as e:
            logger.warning(f"Batch traversal failed: {e}")
            return [], []

        for row in rows:
            seed_id = str(row.get("seed_id") or "")

            # --- hop1 node ---
            h1_id = str(row.get("h1_id") or "")
            if h1_id and h1_id not in seen_nodes:
                seen_nodes.add(h1_id)
                nodes.append({
                    "id": h1_id,
                    "label": row.get("h1_label") or "unknown",
                    "name": row.get("h1_name") or row.get("h1_title") or "",
                    "properties": {
                        "document_id": row.get("h1_doc_id"),
                        "semantic_type": row.get("h1_stype"),
                        "domain": row.get("h1_domain"),
                    },
                    "graph_source": "tenant",
                })

            # --- r1 edge: seed → hop1 ---
            r1_type = row.get("r1_type") or ""
            if seed_id and h1_id and r1_type:
                edge_props: Dict[str, Any] = {}
                if r1_type == "REFERENCES_LAW":
                    edge_props = {
                        k: v for k, v in {
                            "confidence": row.get("r1_confidence"),
                            "source": row.get("r1_source"),
                            "article": row.get("r1_article"),
                        }.items() if v is not None
                    }
                edges.append({
                    "source_id": seed_id,
                    "target_id": h1_id,
                    "label": r1_type,
                    "properties": edge_props,
                })

            # --- hop2 node (OPTIONAL) ---
            h2_id_raw = row.get("h2_id")
            if h2_id_raw is None:
                continue
            h2_id = str(h2_id_raw)
            if h2_id and h2_id not in seen_nodes:
                seen_nodes.add(h2_id)
                nodes.append({
                    "id": h2_id,
                    "label": row.get("h2_label") or "unknown",
                    "name": row.get("h2_name") or row.get("h2_title") or "",
                    "properties": {
                        "document_id": row.get("h2_doc_id"),
                        "semantic_type": row.get("h2_stype"),
                        "domain": row.get("h2_domain"),
                    },
                    "graph_source": "tenant",
                })

            # --- r2 edge: hop1 → hop2 ---
            r2_type = row.get("r2_type") or ""
            if h1_id and h2_id and r2_type:
                edge_props2: Dict[str, Any] = {}
                if r2_type == "REFERENCES_LAW":
                    edge_props2 = {
                        k: v for k, v in {
                            "confidence": row.get("r2_confidence"),
                            "source": row.get("r2_source"),
                            "article": row.get("r2_article"),
                        }.items() if v is not None
                    }
                edges.append({
                    "source_id": h1_id,
                    "target_id": h2_id,
                    "label": r2_type,
                    "properties": edge_props2,
                })

        # --- Phase 3: Fetch Claims connected to discovered entities ---
        entity_ids = [
            n["id"] for n in nodes
            if n.get("label") == "Entity" and n.get("id")
        ]
        if entity_ids:
            claim_nodes, claim_edges = await self._fetch_entity_claims(
                tenant_id, entity_ids, seen_nodes,
            )
            nodes.extend(claim_nodes)
            edges.extend(claim_edges)

        return nodes, edges

    async def _fetch_entity_claims(
        self,
        tenant_id: str,
        entity_ids: List[str],
        seen_nodes: Set[str],
    ) -> Tuple[List[Dict], List[Dict]]:
        """Fetch Claims connected to discovered entities via ABOUT edges.

        Single batch query replaces the previous per-entity loop (up to 20
        queries → 1 query).  Retrieves claims, their document sources, and
        any CONTRADICTS edges between claims in one round-trip.

        Args:
            tenant_id: Tenant identifier.
            entity_ids: String node IDs of Entity nodes (from traversal results).
            seen_nodes: Mutable set used for cross-call deduplication.

        Returns:
            (claim_nodes, claim_edges) to be appended to the traversal result.
        """
        if not entity_ids:
            return [], []

        # Convert string node IDs (stored in traversal nodes) to int for Cypher
        int_ids: List[int] = []
        for eid in entity_ids[:10]:  # Cap to avoid oversized queries
            try:
                int_ids.append(int(eid))
            except (ValueError, TypeError):
                logger.debug(f"Skipping non-integer entity ID: {eid!r}")
        if not int_ids:
            return [], []

        nodes: List[Dict] = []
        edges: List[Dict] = []

        # Single batch query: claims + document sources + contradictions
        query = """
            MATCH (e)
            WHERE id(e) IN $entity_ids
            MATCH (c:Claim)-[:ABOUT]->(e)
            WHERE c.tenant_id = $tid
            OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(d:Document)
            OPTIONAL MATCH (c)-[:CONTRADICTS]-(contra:Claim)
            RETURN
              id(e)                  AS entity_nid,
              id(c)                  AS claim_nid,
              c.claim_id             AS claim_uuid,
              c.statement            AS statement,
              c.claim_type           AS claim_type,
              c.confidence           AS confidence,
              c.source_chunk         AS source_chunk,
              c.verified             AS verified,
              id(d)                  AS doc_nid,
              id(contra)             AS contra_nid,
              contra.claim_id        AS contra_uuid,
              contra.statement       AS contra_statement
            ORDER BY c.confidence DESC
            LIMIT 200
        """
        try:
            rows = await falkordb_client.execute_cypher(
                query, {"entity_ids": int_ids, "tid": tenant_id},
            )
        except Exception as e:
            logger.warning(f"Batch claim fetch failed: {e}")
            return [], []

        # Track CONTRADICTS edges seen to avoid duplicates (undirected match
        # can produce the same pair twice: c→contra and contra→c)
        seen_contra_pairs: Set[Tuple[str, str]] = set()

        for row in rows:
            entity_nid = str(row.get("entity_nid") or "")
            cid = str(row.get("claim_nid") or "")
            if not cid:
                continue

            # Add claim node once (first occurrence)
            if cid not in seen_nodes:
                seen_nodes.add(cid)
                nodes.append({
                    "id": cid,
                    "label": "Claim",
                    "name": row.get("statement") or "",
                    "properties": {
                        "claim_id": row.get("claim_uuid"),
                        "claim_type": row.get("claim_type"),
                        "confidence": row.get("confidence"),
                        "source_chunk": row.get("source_chunk"),
                        "verified": row.get("verified"),
                    },
                    "graph_source": "tenant",
                })

                # ABOUT edge (claim → entity)
                if entity_nid:
                    edges.append({
                        "source_id": cid,
                        "target_id": entity_nid,
                        "label": "ABOUT",
                        "properties": {},
                    })

                # EXTRACTED_FROM edge (claim → document)
                doc_nid = row.get("doc_nid")
                if doc_nid is not None:
                    edges.append({
                        "source_id": cid,
                        "target_id": str(doc_nid),
                        "label": "EXTRACTED_FROM",
                        "properties": {},
                    })

            # CONTRADICTS edge — deduplicate undirected pairs
            contra_nid_raw = row.get("contra_nid")
            if contra_nid_raw is not None:
                contra_nid = str(contra_nid_raw)
                pair = (min(cid, contra_nid), max(cid, contra_nid))
                if pair not in seen_contra_pairs:
                    seen_contra_pairs.add(pair)
                    edges.append({
                        "source_id": cid,
                        "target_id": contra_nid,
                        "label": "CONTRADICTS",
                        "properties": {},
                    })

        return nodes, edges

    def _prune(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        seed_names: Set[str],
        max_nodes: int,
    ) -> Tuple[List[Dict], List[Dict], int]:
        """Score and prune the subgraph to max_nodes.

        Scoring heuristic per node:
            0.4 * edge_relevance (best incoming/outgoing edge)
            0.3 * name_match (is this a seed entity?)
            0.3 * node_type_bonus
        """
        if len(nodes) <= max_nodes:
            return nodes, edges, 0

        # Build adjacency for scoring
        node_edges: Dict[str, List[str]] = {}
        for edge in edges:
            src = edge["source_id"]
            tgt = edge["target_id"]
            label = edge["label"]
            node_edges.setdefault(src, []).append(label)
            node_edges.setdefault(tgt, []).append(label)

        # Score each node
        scored: List[Tuple[float, Dict]] = []
        seed_names_lower = {s.lower() for s in seed_names}

        for node in nodes:
            # Edge relevance: best edge weight connected to this node
            connected_labels = node_edges.get(node["id"], [])
            edge_score = max((_EDGE_WEIGHTS.get(l, 0.3) for l in connected_labels), default=0.0)

            # Seed match bonus
            name = (node.get("name") or "").lower()
            seed_score = 1.0 if name in seed_names_lower else 0.0

            # Node type bonus
            type_score = _NODE_TYPE_BONUS.get(node.get("label", ""), 0.3)

            total = 0.4 * edge_score + 0.3 * seed_score + 0.3 * type_score
            scored.append((total, node))

        # Sort descending, keep top max_nodes
        scored.sort(key=lambda x: x[0], reverse=True)
        kept_nodes = [n for _, n in scored[:max_nodes]]
        kept_ids = {n["id"] for n in kept_nodes}
        pruned_count = len(nodes) - len(kept_nodes)

        # Filter edges to only connect kept nodes
        kept_edges = [
            e for e in edges
            if e["source_id"] in kept_ids and e["target_id"] in kept_ids
        ]

        return kept_nodes, kept_edges, pruned_count


def _extract_properties(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract properties from a FalkorDB result row."""
    props = {}
    for key in ("document_id", "semantic_type", "domain", "associated_person"):
        val = row.get(key)
        if val is not None:
            props[key] = val
    return props


# Module-level singleton
subgraph_extractor = SubgraphExtractor()
