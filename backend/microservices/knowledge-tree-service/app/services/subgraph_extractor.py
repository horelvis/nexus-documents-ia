"""
Subgraph Extractor — GraphRAG Phase 5a

Extracts multi-hop subgraphs from tenant sector graphs rooted at query entities.
Returns structured node/edge data for LLM consumption (not flat document IDs).

Architecture:
    1. Entity Resolution: Find seed nodes matching query entities
    2. N-hop Traversal: Expand seed neighborhood (configurable depth 1-3)
    3. Legal Cross-Reference: Match document domains to public legal graph (optional)
    4. Pruning & Scoring: Rank paths, cap at max_nodes

The subgraph endpoint replaces the flat graph_expander approach — instead of
returning document IDs for re-ranking, it returns typed relationship chains
that the LLM can reason over directly.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.services.age_client import age_client
from app.services.ontology_service import _clean_agtype

logger = logging.getLogger(__name__)


def _escape(value: str) -> str:
    """Escape single quotes for Cypher."""
    return value.replace("'", "''").replace("\\", "\\\\")


# Edge relevance weights for pruning (higher = more important)
_EDGE_WEIGHTS: Dict[str, float] = {
    "ASOCIADO_A": 1.0,
    "FIRMADO_POR": 1.0,
    "CREADO_POR": 0.9,
    "APLICA": 0.9,
    "REFERENCIA": 0.85,
    "PERTENECE_A": 0.8,
    "EXTRACTED_FROM": 0.7,
    "CONTIENE": 0.6,
    "HAS_DOCUMENT": 0.6,
    "PARTE_DE": 0.5,
    "RELACIONADO": 0.5,
    "DEFINE": 0.4,
    "INSTANCE_OF": 0.3,
    "HAS_MEMORY": 0.2,
}

# Node type bonus (higher = more useful for LLM context)
_NODE_TYPE_BONUS: Dict[str, float] = {
    "structural_document": 1.0,
    "Persona": 0.9,
    "Organizacion": 0.9,
    "LegalLaw": 0.8,
    "Articulo": 0.7,
    "structural_folder": 0.4,
    "EntityType": 0.2,
    "DocumentMemory": 0.3,
}


class SubgraphExtractor:
    """Extracts multi-hop subgraphs from Apache AGE tenant graphs."""

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await age_client.initialize()
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
            include_legal: Whether to cross-reference public legal graph
            include_memories: Whether to include DocumentMemory nodes

        Returns:
            {"nodes": [...], "edges": [...], "root_entities": [...], "pruned_count": int}
        """
        if not self._initialized:
            await self.initialize()

        graph_name = settings.age_graph_name
        if not graph_name:
            return {"nodes": [], "edges": [], "root_entities": [], "pruned_count": 0}

        max_hops = min(max(max_hops, 1), 3)

        # Step 1: Resolve seed entities in the tenant graph
        seeds, seed_names = await self._resolve_seeds(graph_name, tenant_id, entities)
        if not seeds:
            return {"nodes": [], "edges": [], "root_entities": [], "pruned_count": 0}

        # Step 2: N-hop traversal from seeds
        raw_nodes, raw_edges = await self._traverse(
            graph_name, tenant_id, seed_names, max_hops, max_nodes * 3,
        )

        # Merge seed nodes into raw_nodes
        for seed in seeds:
            node_key = seed.get("id", seed.get("name", ""))
            if node_key and node_key not in {n.get("id") for n in raw_nodes}:
                raw_nodes.append(seed)

        # Step 3: Cross-graph legal lookup (optional)
        if include_legal:
            legal_nodes, legal_edges = await self._lookup_legal(raw_nodes)
            raw_nodes.extend(legal_nodes)
            raw_edges.extend(legal_edges)

        # Step 4: Filter out DocumentMemory if not requested
        if not include_memories:
            memory_ids = {n["id"] for n in raw_nodes if n.get("label") == "DocumentMemory"}
            raw_nodes = [n for n in raw_nodes if n.get("label") != "DocumentMemory"]
            raw_edges = [e for e in raw_edges
                         if e.get("source_id") not in memory_ids
                         and e.get("target_id") not in memory_ids]

        # Step 5: Prune and score
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
        self, graph_name: str, tenant_id: str, entities: List[Dict[str, Any]],
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

            escaped = _escape(value)
            query = f"""
                SELECT * FROM cypher('{graph_name}', $$
                    MATCH (n)
                    WHERE n.tenant_id = '{_escape(tenant_id)}'
                      AND (n.name =~ '(?i).*{escaped}.*'
                           OR n.associated_person =~ '(?i).*{escaped}.*'
                           OR n.title =~ '(?i).*{escaped}.*')
                    RETURN id(n) as node_id, labels(n)[0] as label,
                           n.name as name, n.title as title,
                           n.document_id as document_id,
                           n.semantic_type as semantic_type,
                           n.domain as domain,
                           n.associated_person as associated_person
                    LIMIT 5
                $$) as (node_id agtype, label agtype, name agtype, title agtype,
                        document_id agtype, semantic_type agtype, domain agtype,
                        associated_person agtype)
            """
            try:
                rows = await age_client.execute_cypher(query)
                for row in rows:
                    label = _clean_agtype(row.get("label")) or "unknown"
                    name = _clean_agtype(row.get("name")) or _clean_agtype(row.get("title")) or value
                    node_id = _clean_agtype(row.get("node_id")) or name

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
        graph_name: str,
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
            escaped = _escape(seed_name)
            query = f"""
                SELECT * FROM cypher('{graph_name}', $$
                    MATCH (seed)
                    WHERE seed.tenant_id = '{_escape(tenant_id)}'
                      AND (seed.name = '{escaped}'
                           OR seed.associated_person = '{escaped}'
                           OR seed.title = '{escaped}')
                    WITH seed LIMIT 3
                    MATCH (seed)-[r*1..{max_hops}]-(neighbor)
                    WHERE neighbor.tenant_id = '{_escape(tenant_id)}'
                       OR labels(neighbor)[0] = 'EntityType'
                    UNWIND r as rel
                    RETURN DISTINCT
                        id(startnode(rel)) as src_id,
                        labels(startnode(rel))[0] as src_label,
                        startnode(rel).name as src_name,
                        startnode(rel).title as src_title,
                        startnode(rel).document_id as src_doc_id,
                        startnode(rel).semantic_type as src_stype,
                        startnode(rel).domain as src_domain,
                        type(rel) as edge_label,
                        id(endnode(rel)) as tgt_id,
                        labels(endnode(rel))[0] as tgt_label,
                        endnode(rel).name as tgt_name,
                        endnode(rel).title as tgt_title,
                        endnode(rel).document_id as tgt_doc_id,
                        endnode(rel).semantic_type as tgt_stype,
                        endnode(rel).domain as tgt_domain
                    LIMIT {limit}
                $$) as (src_id agtype, src_label agtype, src_name agtype, src_title agtype,
                        src_doc_id agtype, src_stype agtype, src_domain agtype,
                        edge_label agtype,
                        tgt_id agtype, tgt_label agtype, tgt_name agtype, tgt_title agtype,
                        tgt_doc_id agtype, tgt_stype agtype, tgt_domain agtype)
            """
            try:
                rows = await age_client.execute_cypher(query)
                for row in rows:
                    # Source node
                    src_id = str(_clean_agtype(row.get("src_id")) or "")
                    if src_id and src_id not in seen_nodes:
                        seen_nodes.add(src_id)
                        nodes.append({
                            "id": src_id,
                            "label": _clean_agtype(row.get("src_label")) or "unknown",
                            "name": _clean_agtype(row.get("src_name")) or _clean_agtype(row.get("src_title")) or "",
                            "properties": {
                                "document_id": _clean_agtype(row.get("src_doc_id")),
                                "semantic_type": _clean_agtype(row.get("src_stype")),
                                "domain": _clean_agtype(row.get("src_domain")),
                            },
                            "graph_source": "tenant",
                        })

                    # Target node
                    tgt_id = str(_clean_agtype(row.get("tgt_id")) or "")
                    if tgt_id and tgt_id not in seen_nodes:
                        seen_nodes.add(tgt_id)
                        nodes.append({
                            "id": tgt_id,
                            "label": _clean_agtype(row.get("tgt_label")) or "unknown",
                            "name": _clean_agtype(row.get("tgt_name")) or _clean_agtype(row.get("tgt_title")) or "",
                            "properties": {
                                "document_id": _clean_agtype(row.get("tgt_doc_id")),
                                "semantic_type": _clean_agtype(row.get("tgt_stype")),
                                "domain": _clean_agtype(row.get("tgt_domain")),
                            },
                            "graph_source": "tenant",
                        })

                    # Edge
                    el = _clean_agtype(row.get("edge_label")) or ""
                    if src_id and tgt_id and el:
                        edges.append({
                            "source_id": src_id,
                            "target_id": tgt_id,
                            "label": el,
                            "properties": {},
                        })
            except Exception as e:
                logger.warning(f"Traversal failed for seed '{seed_name}': {e}")

        return nodes, edges

    async def _lookup_legal(
        self, tenant_nodes: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """Cross-reference tenant document domains with public legal graph.

        Creates synthetic APLICA edges between tenant documents and
        matching laws from knowledge_graph_public.
        """
        # Collect unique domains from discovered documents
        doc_domains: Dict[str, List[str]] = {}  # domain → [node_ids]
        for node in tenant_nodes:
            domain = (node.get("properties") or {}).get("domain")
            if domain and node.get("label") == "structural_document":
                doc_domains.setdefault(domain, []).append(node["id"])

        if not doc_domains:
            return [], []

        domains_list = ", ".join(f"'{_escape(d)}'" for d in doc_domains.keys())
        query = f"""
            SELECT * FROM cypher('knowledge_graph_public', $$
                MATCH (law:LegalLaw)
                WHERE law.domain IN [{domains_list}]
                  AND law.status = 'vigente'
                RETURN law.boe_id as boe_id,
                       law.title as title,
                       law.short_name as short_name,
                       law.domain as domain
                LIMIT 15
            $$) as (boe_id agtype, title agtype, short_name agtype, domain agtype)
        """

        legal_nodes: List[Dict] = []
        legal_edges: List[Dict] = []

        try:
            rows = await age_client.execute_cypher(query)
            for row in rows:
                boe_id = _clean_agtype(row.get("boe_id"))
                if not boe_id:
                    continue

                domain = _clean_agtype(row.get("domain")) or ""
                short_name = _clean_agtype(row.get("short_name")) or ""
                title = _clean_agtype(row.get("title")) or ""

                node_id = f"law:{boe_id}"
                legal_nodes.append({
                    "id": node_id,
                    "label": "LegalLaw",
                    "name": short_name or title,
                    "properties": {
                        "boe_id": boe_id,
                        "domain": domain,
                        "title": title,
                    },
                    "graph_source": "public",
                })

                # Create synthetic APLICA edges from matching documents
                for doc_node_id in doc_domains.get(domain, []):
                    legal_edges.append({
                        "source_id": doc_node_id,
                        "target_id": node_id,
                        "label": "APLICA",
                        "properties": {"synthetic": True},
                    })
        except Exception as e:
            logger.debug(f"Legal cross-reference skipped: {e}")

        return legal_nodes, legal_edges

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
    """Extract cleaned properties from an AGE result row."""
    props = {}
    for key in ("document_id", "semantic_type", "domain", "associated_person"):
        val = _clean_agtype(row.get(key))
        if val:
            props[key] = val
    return props


# Module-level singleton
subgraph_extractor = SubgraphExtractor()
