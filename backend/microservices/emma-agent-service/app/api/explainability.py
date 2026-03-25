"""Explainability API — Knowledge graph + reasoning trace for the UI.

GET /emma/explainability/graph       → Full tenant graph from FalkorDB (via KTS)
GET /emma/explainability/trace/{tid}/{idx} → Per-response reasoning trace
"""
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Query, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/explainability", tags=["explainability"])

KTS_URL = os.getenv("KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
KTS_API_KEY = getattr(settings, "microservices_api_key", "") or os.getenv("MICROSERVICES_API_KEY", "")


def _kts_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if KTS_API_KEY:
        headers["X-API-Key"] = KTS_API_KEY
    return headers


def _map_node_type(kts_type: str) -> str:
    """Map KTS node_type to frontend ExplainabilityNode.type."""
    mapping = {
        "folder": "entity",
        "document": "document",
        "claim": "claim",
        "law": "law",
        "contradiction": "contradiction",
        "entity": "entity",
    }
    return mapping.get(kts_type, "entity")


@router.get("/graph")
async def get_explainability_graph(
    tenant_id: str = Query(..., description="Tenant identifier"),
):
    """Full tenant knowledge graph for 3D visualization.

    Proxies to KTS /graph/structure and transforms to the frontend schema:
    ExplainabilityGraphResponse { nodes, edges, stats }
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{KTS_URL}/tree/graph/structure",
                params={"tenant_id": tenant_id},
                headers=_kts_headers(),
            )
            response.raise_for_status()
            kts_data = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"KTS graph/structure returned {e.response.status_code}: {e.response.text[:200]}")
        raise HTTPException(status_code=502, detail="Knowledge graph service error")
    except Exception as e:
        logger.error(f"KTS graph/structure failed: {e}")
        raise HTTPException(status_code=502, detail="Knowledge graph service unavailable")

    # Transform KTS nodes → ExplainabilityNode[]
    nodes = []
    stats = {
        "total_entities": 0,
        "total_documents": 0,
        "total_claims": 0,
        "total_laws": 0,
        "total_contradictions": 0,
    }

    for kts_node in kts_data.get("nodes", []):
        kts_type = kts_node.get("node_type", "entity")
        frontend_type = _map_node_type(kts_type)

        node = {
            "id": kts_node.get("id", ""),
            "type": frontend_type,
            "label": kts_node.get("label", ""),
            "properties": {
                "domain": kts_node.get("domain", ""),
                "semantic_type": kts_node.get("semantic_type", ""),
                "folder_type": kts_node.get("folder_type", ""),
                "doc_count": kts_node.get("doc_count", 0),
                "path": kts_node.get("path", ""),
                "file_path": kts_node.get("file_path", ""),
            },
        }
        nodes.append(node)

        stats_key = f"total_{frontend_type}s" if frontend_type != "entity" else "total_entities"
        if stats_key in stats:
            stats[stats_key] += 1

    # Transform KTS edges → ExplainabilityEdge[]
    edges = []
    for kts_edge in kts_data.get("edges", []):
        edges.append({
            "id": kts_edge.get("id", ""),
            "source": kts_edge.get("source", ""),
            "target": kts_edge.get("target", ""),
            "type": kts_edge.get("label", "RELATED"),
            "properties": {},
        })

    return {"nodes": nodes, "edges": edges, "stats": stats}


@router.get("/trace/{thread_id}/{message_index}")
async def get_reasoning_trace(
    thread_id: str,
    message_index: int,
):
    """Per-response reasoning trace for the ReasoningModal.

    Returns timeline steps + evidence sub-graph for a specific message
    in a conversation thread.

    NOTE: This is a stub that returns data from the LangGraph checkpointer.
    Full implementation requires reading ReasoningTracker data from the
    checkpoint store.
    """
    # TODO: Read from LangGraph AsyncPostgresSaver checkpointer
    # For now, return empty structure so the UI doesn't break
    return {
        "message_id": f"{thread_id}:{message_index}",
        "thread_id": thread_id,
        "timeline": [],
        "evidence_graph": {"nodes": [], "edges": []},
        "total_execution_ms": 0,
        "tools_used": [],
        "sources_cited": 0,
    }
