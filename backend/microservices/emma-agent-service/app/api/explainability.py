"""Explainability API — Knowledge graph + reasoning trace for the UI.

GET /emma/explainability/graph       → Full knowledge graph from FalkorDB (via KTS)
GET /emma/explainability/trace/{tid}/{idx} → Per-response reasoning trace (from Redis)
"""
import json
import logging
import os

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException

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
async def get_explainability_graph():
    """Full knowledge graph for 3D visualization.

    Proxies to KTS /graph/structure and transforms to the frontend schema:
    ExplainabilityGraphResponse { nodes, edges, stats }
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{KTS_URL}/tree/graph/structure",
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
    in a conversation thread. Data is stored in Redis with 24h TTL
    during SSE streaming.
    """
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)

        # Try exact key first
        trace_key = f"reasoning_trace:{thread_id}:{message_index}"
        raw = await r.get(trace_key)

        # If not found and message_index == 0, try latest
        if not raw and message_index == 0:
            latest = await r.get(f"reasoning_trace:{thread_id}:latest")
            if latest:
                raw = await r.get(f"reasoning_trace:{thread_id}:{latest}")

        await r.close()

        if raw:
            trace = json.loads(raw)
            return {
                "message_id": f"{thread_id}:{message_index}",
                "thread_id": thread_id,
                "timeline": trace.get("timeline", []),
                "evidence_graph": {"nodes": [], "edges": []},
                "total_execution_ms": trace.get("total_execution_ms", 0),
                "tools_used": trace.get("tools_used", []),
                "sources_cited": trace.get("sources_cited", 0),
            }
    except Exception as e:
        logger.warning(f"Failed to read reasoning trace from Redis: {e}")

    # Fallback: empty structure
    return {
        "message_id": f"{thread_id}:{message_index}",
        "thread_id": thread_id,
        "timeline": [],
        "evidence_graph": {"nodes": [], "edges": []},
        "total_execution_ms": 0,
        "tools_used": [],
        "sources_cited": 0,
    }
