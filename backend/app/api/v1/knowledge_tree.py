"""
Knowledge Tree proxy endpoints.

Proxies requests to the knowledge-tree-service microservice (port 8011).
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.api.async_dependencies import get_current_tenant_id_async

logger = logging.getLogger(__name__)
router = APIRouter()

KNOWLEDGE_TREE_SERVICE_URL = os.getenv(
    "KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011"
)


async def _proxy_get(path: str, tenant_id: str, timeout: float = 30.0):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.get(
                f"{KNOWLEDGE_TREE_SERVICE_URL}{path}",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Knowledge tree service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Knowledge tree proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _proxy_post(path: str, tenant_id: str, body: dict, timeout: float = 30.0):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(
                f"{KNOWLEDGE_TREE_SERVICE_URL}{path}",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
                json=body,
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Knowledge tree service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Knowledge tree proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree/stats")
async def tree_stats(tenant_id: str = Depends(get_current_tenant_id_async)):
    return await _proxy_get("/tree/stats", tenant_id)


@router.get("/tree/graph/structure")
async def tree_graph_structure(tenant_id: str = Depends(get_current_tenant_id_async)):
    return await _proxy_get("/tree/graph/structure", tenant_id, timeout=60.0)


@router.post("/tree/graph/subgraph")
async def tree_graph_subgraph(request: Request, tenant_id: str = Depends(get_current_tenant_id_async)):
    body = await request.json()
    # Inject tenant_id into body (required by microservice)
    body["tenant_id"] = tenant_id
    # Adapt frontend field: entity → entities list
    if "entity" in body and "entities" not in body:
        entity_val = body.pop("entity")
        if entity_val == "*":
            body["entities"] = [{"value": "*"}]
        else:
            body["entities"] = [{"value": entity_val}]
    # Cap max_nodes to microservice limit
    if body.get("max_nodes", 0) > 100:
        body["max_nodes"] = 100
    return await _proxy_post("/tree/graph/subgraph", tenant_id, body, timeout=60.0)


# ── TrustGraph Phase 2: triple-based endpoints ──


@router.get("/triples/stats")
async def triples_stats(tenant_id: str = Depends(get_current_tenant_id_async)):
    return await _proxy_get("/triples/stats", tenant_id)


@router.get("/triples/top-entities")
async def triples_top_entities(tenant_id: str = Depends(get_current_tenant_id_async)):
    return await _proxy_get("/triples/top-entities", tenant_id)


@router.post("/triples/query")
async def triples_query(request: Request, tenant_id: str = Depends(get_current_tenant_id_async)):
    body = await request.json()
    body["tenant_id"] = tenant_id
    return await _proxy_post("/triples/query", tenant_id, body)


@router.post("/triples/neighbors")
async def triples_neighbors(request: Request, tenant_id: str = Depends(get_current_tenant_id_async)):
    body = await request.json()
    body["tenant_id"] = tenant_id
    return await _proxy_post("/triples/neighbors", tenant_id, body, timeout=60.0)
