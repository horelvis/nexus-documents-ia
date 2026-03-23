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

        # Step 2: N-hop traversal from seeds
        raw_nodes, raw_edges = await self._traverse(
            tenant_id, seed_names, max_hops, max_nodes * 3,
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
        Returns (seed_nodes, seed_names).
        """
        all_seeds = []
        seed_names: Set[str] = set()

        for entity in entities[:5]:  # Cap at 5 seed entities
            value = entity.get("value", "").strip()
            if not value or len(value) < 2:
                continue

            query = """
                MATCH (n)
                WHERE n.tenant_id = $tenant_id
                  AND (n.name =~ $pattern
                       OR n.associated_person =~ $pattern
                       OR n.title =~ $pattern)
                RETURN id(n) as node_id, labels(n)[0] as label,
                       n.name as name, n.title as title,
                       n.document_id as document_id,
                       n.semantic_type as semantic_type,
                       n.domain as domain,
                       n.associated_person as associated_person
                LIMIT 5
            """
            pattern = f"(?i).*{value}.*"
            try:
                rows = await falkordb_client.execute_cypher(
                    query, {"tenant_id": tenant_id, "pattern": pattern}
                )
                for row in rows:
                    label = row.get("label") or "unknown"
                    name = row.get("name") or row.get("title") or value
                    node_id = row.get("node_id")
                    if node_id is None:
                        node_id = name

                    node = {
                        "id": str(node_id),
                        "label": label,
                        "name": name,
                        "properties": _extract_properties(row),
                        "graph_source": "tenant",
                    }
                    all_seeds.append(node)
                    seed_names.add(name)
            except Exception as e:
                logger.warning(f"Seed resolution failed for '{value}': {e}")

        return all_seeds, seed_names

    async def _traverse(
        self,
        tenant_id: str,
        seed_names: Set[str],
        max_hops: int,
        limit: int,
    ) -> Tuple[List[Dict], List[Dict]]:
        """Multi-hop traversal from seed entities.

        Returns (nodes, edges) discovered in the neighborhood.
        """
        if not seed_names:
            return [], []

        nodes: List[Dict] = []
        edges: List[Dict] = []
        seen_nodes: Set[str] = set()

        for seed_name in list(seed_names)[:5]:
            # FalkorDB does not support variable-length relationship binding
            # for UNWIND, so we use a 2-step approach: find neighbors then
            # collect the connecting edges.
            query = f"""
                MATCH (seed)
                WHERE seed.tenant_id = $tenant_id
                  AND (seed.name = $seed_name
                       OR seed.associated_person = $seed_name
                       OR seed.title = $seed_name)
                WITH seed LIMIT 3
                MATCH (seed)-[r*1..{max_hops}]-(neighbor)
                WHERE neighbor.tenant_id = $tenant_id
                   OR neighbor.shared = true
                UNWIND r as rel
                RETURN DISTINCT
                    id(startNode(rel)) as src_id,
                    labels(startNode(rel))[0] as src_label,
                    startNode(rel).name as src_name,
                    startNode(rel).title as src_title,
                    startNode(rel).document_id as src_doc_id,
                    startNode(rel).semantic_type as src_stype,
                    startNode(rel).domain as src_domain,
                    type(rel) as edge_label,
                    rel.confidence as edge_confidence,
                    rel.source as edge_source,
                    rel.article as edge_article,
                    id(endNode(rel)) as tgt_id,
                    labels(endNode(rel))[0] as tgt_label,
                    endNode(rel).name as tgt_name,
                    endNode(rel).title as tgt_title,
                    endNode(rel).document_id as tgt_doc_id,
                    endNode(rel).semantic_type as tgt_stype,
                    endNode(rel).domain as tgt_domain
                LIMIT $limit
            """
            try:
                rows = await falkordb_client.execute_cypher(
                    query,
                    {"tenant_id": tenant_id, "seed_name": seed_name, "limit": limit},
                )
                for row in rows:
                    # Source node
                    src_id = str(row.get("src_id") or "")
                    if src_id and src_id not in seen_nodes:
                        seen_nodes.add(src_id)
                        nodes.append({
                            "id": src_id,
                            "label": row.get("src_label") or "unknown",
                            "name": row.get("src_name") or row.get("src_title") or "",
                            "properties": {
                                "document_id": row.get("src_doc_id"),
                                "semantic_type": row.get("src_stype"),
                                "domain": row.get("src_domain"),
                            },
                            "graph_source": "tenant",
                        })

                    # Target node
                    tgt_id = str(row.get("tgt_id") or "")
                    if tgt_id and tgt_id not in seen_nodes:
                        seen_nodes.add(tgt_id)
                        nodes.append({
                            "id": tgt_id,
                            "label": row.get("tgt_label") or "unknown",
                            "name": row.get("tgt_name") or row.get("tgt_title") or "",
                            "properties": {
                                "document_id": row.get("tgt_doc_id"),
                                "semantic_type": row.get("tgt_stype"),
                                "domain": row.get("tgt_domain"),
                            },
                            "graph_source": "tenant",
                        })

                    # Edge
                    el = row.get("edge_label") or ""
                    if src_id and tgt_id and el:
                        edge_props = {}
                        if el == "REFERENCES_LAW":
                            edge_props = {
                                "confidence": row.get("edge_confidence"),
                                "source": row.get("edge_source"),
                                "article": row.get("edge_article"),
                            }
                            edge_props = {k: v for k, v in edge_props.items() if v}
                        edges.append({
                            "source_id": src_id,
                            "target_id": tgt_id,
                            "label": el,
                            "properties": edge_props,
                        })
            except Exception as e:
                logger.warning(f"Traversal failed for seed '{seed_name}': {e}")

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

        Also retrieves CONTRADICTS/SUPPORTS edges between claims.
        """
        nodes: List[Dict] = []
        edges: List[Dict] = []

        # Query: Entity <- ABOUT - Claim - EXTRACTED_FROM -> Document
        # Plus optional CONTRADICTS / SUPPORTS between claims
        for eid in entity_ids[:10]:  # Cap to avoid huge queries
            query = """
                MATCH (e) WHERE id(e) = $entity_id
                MATCH (c:Claim)-[:ABOUT]->(e)
                WHERE c.tenant_id = $tenant_id
                OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(d:Document)
                RETURN id(c) AS claim_id,
                       c.claim_id AS claim_uuid,
                       c.statement AS statement,
                       c.claim_type AS claim_type,
                       c.confidence AS confidence,
                       c.source_chunk AS source_chunk,
                       c.verified AS verified,
                       id(e) AS entity_id,
                       id(d) AS doc_id
                LIMIT 20
            """
            try:
                rows = await falkordb_client.execute_cypher(
                    query, {"tenant_id": tenant_id, "entity_id": int(eid)},
                )
            except Exception as e:
                logger.debug(f"Claim fetch failed for entity {eid}: {e}")
                continue

            claim_ids_in_batch: List[str] = []

            for row in rows:
                cid = str(row.get("claim_id") or "")
                if not cid or cid in seen_nodes:
                    continue
                seen_nodes.add(cid)
                claim_ids_in_batch.append(cid)

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

                # ABOUT edge
                edges.append({
                    "source_id": cid,
                    "target_id": str(eid),
                    "label": "ABOUT",
                    "properties": {},
                })

                # EXTRACTED_FROM edge
                doc_id = row.get("doc_id")
                if doc_id is not None:
                    edges.append({
                        "source_id": cid,
                        "target_id": str(doc_id),
                        "label": "EXTRACTED_FROM",
                        "properties": {},
                    })

            # Fetch CONTRADICTS edges between claims in this batch
            if len(claim_ids_in_batch) >= 2:
                try:
                    contra_query = """
                        MATCH (c1:Claim)-[r:CONTRADICTS]->(c2:Claim)
                        WHERE c1.tenant_id = $tenant_id
                          AND c2.tenant_id = $tenant_id
                        RETURN id(c1) AS src, id(c2) AS tgt,
                               r.contradiction_type AS contra_type
                    """
                    contra_rows = await falkordb_client.execute_cypher(
                        contra_query, {"tenant_id": tenant_id},
                    )
                    batch_set = set(claim_ids_in_batch)
                    for cr in contra_rows:
                        src = str(cr.get("src") or "")
                        tgt = str(cr.get("tgt") or "")
                        if src in batch_set or tgt in batch_set:
                            edges.append({
                                "source_id": src,
                                "target_id": tgt,
                                "label": "CONTRADICTS",
                                "properties": {
                                    "contradiction_type": cr.get("contra_type"),
                                },
                            })
                except Exception as e:
                    logger.debug(f"Contradiction edge fetch failed: {e}")

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
