"""
Subgraph Formatter — GraphRAG Phase 5c

Converts a SubgraphResponse (nodes + edges) from knowledge-tree-service
into a tree-indented text format optimized for LLM comprehension.

Output format:
    [SUBGRAFO RELEVANTE]
    Entidades principales:
    - Javier Martínez (Entity, person)
      → MENTIONED_IN → Contrato-Servicios-2024.pdf (contrato, domain=mercantil) [ID: abc-123]
        → REFERENCES_LAW → Estatuto de los Trabajadores (BOE-A-2015-11430)
      → MENTIONED_IN → Informe-RRHH-Q1.pdf (informe) [ID: ghi-789]

    Relaciones: 7 nodos, 6 aristas, profundidad máx. 2
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def format_subgraph(
    subgraph: Dict[str, Any],
    token_budget: int = 1500,
) -> Optional[str]:
    """Format a subgraph response as indented text for LLM injection.

    Args:
        subgraph: Response from /tree/graph/subgraph endpoint
        token_budget: Approximate max tokens (~4 chars/token)

    Returns:
        Formatted text string, or None if subgraph is empty.
    """
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])
    root_entities = subgraph.get("root_entities", [])

    if not nodes or not edges:
        return None

    # Build lookup structures
    node_map: Dict[str, Dict] = {n["id"]: n for n in nodes}
    adjacency: Dict[str, List[Dict]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["source_id"]].append(edge)
        # Also track reverse for undirected traversal
        adjacency[edge["target_id"]].append({
            "source_id": edge["target_id"],
            "target_id": edge["source_id"],
            "label": edge["label"],
            "properties": edge.get("properties", {}),
        })

    # Find root nodes (seeds or nodes matching root_entities)
    root_ids = _find_roots(nodes, root_entities)
    if not root_ids:
        # Fallback: use nodes with most connections
        root_ids = sorted(adjacency.keys(), key=lambda k: len(adjacency[k]), reverse=True)[:3]

    # Build tree text via DFS from each root
    char_budget = token_budget * 4
    lines: List[str] = [
        "[SUBGRAFO RELEVANTE -- relaciones verificadas del repositorio]",
        "Entidades principales:",
    ]
    visited: Set[str] = set()

    for root_id in root_ids:
        if root_id not in node_map:
            continue
        _render_tree(root_id, node_map, adjacency, visited, lines, depth=0, max_depth=3)

        if sum(len(l) for l in lines) > char_budget:
            break

    # Summary line
    lines.append("")
    lines.append(f"Relaciones: {len(nodes)} nodos, {len(edges)} aristas")

    # Guard footer (anti-hallucination)
    lines.append("")
    lines.append(
        "IMPORTANTE: Solo se muestran relaciones verificadas del grafo. "
        "No inventes relaciones adicionales entre documentos y leyes."
    )

    result = "\n".join(lines)

    # Hard truncate if over budget
    if len(result) > char_budget:
        result = result[:char_budget] + "\n[... subgrafo truncado]"

    return result


def _find_roots(nodes: List[Dict], root_entities: List[str]) -> List[str]:
    """Find root node IDs based on root_entities names."""
    root_ids = []
    root_lower = {r.lower() for r in root_entities}

    for node in nodes:
        name = (node.get("name") or "").lower()
        if name in root_lower:
            root_ids.append(node["id"])

    return root_ids


def _render_tree(
    node_id: str,
    node_map: Dict[str, Dict],
    adjacency: Dict[str, List[Dict]],
    visited: Set[str],
    lines: List[str],
    depth: int,
    max_depth: int,
) -> None:
    """Render a node and its children as indented tree lines."""
    if node_id in visited or depth > max_depth:
        return
    visited.add(node_id)

    node = node_map.get(node_id)
    if not node:
        return

    indent = "  " * depth
    label = _format_node(node)

    if depth == 0:
        lines.append(f"- {label}")
    # depth > 0 nodes are rendered as part of edge traversal below

    # Traverse outgoing edges
    for edge in adjacency.get(node_id, []):
        target_id = edge["target_id"]
        if target_id in visited:
            continue

        target_node = node_map.get(target_id)
        if not target_node:
            continue

        # Skip low-value edges at deeper levels
        # NOTE: INSTANCE_OF and HAS_MEMORY are legacy AGE labels — may need updating
        # for TrustGraph Phase 2 where all edges are :Rel with URI predicates.
        edge_label = edge["label"]
        if depth >= 2 and edge_label in ("INSTANCE_OF", "HAS_MEMORY"):
            continue

        child_indent = "  " * (depth + 1)
        child_label = _format_node(target_node)

        # Add traceability for REFERENCES_LAW edges
        # NOTE: APLICA is a legacy label kept for backward compat during migration.
        edge_suffix = ""
        edge_props = edge.get("properties", {})
        if edge_label in ("REFERENCES_LAW", "APLICA") and edge_props:
            parts = []
            if edge_props.get("confidence"):
                parts.append(f"confidence: {edge_props['confidence']}")
            if edge_props.get("source"):
                parts.append(f"source: {edge_props['source']}")
            if parts:
                edge_suffix = f" [{', '.join(parts)}]"

        lines.append(f"{child_indent}→ {edge_label} → {child_label}{edge_suffix}")

        # Recurse into children
        _render_tree(target_id, node_map, adjacency, visited, lines, depth + 1, max_depth)

    # Note absence of legal reference edges for root document nodes
    if depth == 0 and node.get("label") in ("Document",):
        has_aplica = any(
            e["label"] in ("REFERENCES_LAW", "APLICA")
            for e in adjacency.get(node_id, [])
        )
        if not has_aplica:
            child_indent = "  " * (depth + 1)
            lines.append(f"{child_indent}(sin referencias legales detectadas)")


def _format_node(node: Dict) -> str:
    """Format a single node as a compact string."""
    name = node.get("name", "?")
    label = node.get("label", "")
    props = node.get("properties") or {}

    parts = [name]

    # Node type in parentheses
    type_parts = []
    if label and label not in ("unknown", "Document", "Folder"):
        type_parts.append(label)

    stype = props.get("semantic_type")
    if stype:
        type_parts.append(stype)

    domain = props.get("domain")
    if domain:
        type_parts.append(f"domain={domain}")

    if type_parts:
        parts.append(f"({', '.join(type_parts)})")

    # Document ID for cross-reference
    doc_id = props.get("document_id")
    if doc_id:
        parts.append(f"[ID: {doc_id[:12]}]")

    # BOE ID for legal nodes
    boe_id = props.get("boe_id")
    if boe_id:
        parts.append(f"({boe_id})")

    return " ".join(parts)
