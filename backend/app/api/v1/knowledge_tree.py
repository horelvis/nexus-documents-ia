"""
Knowledge Tree proxy endpoints.

Proxies requests to the knowledge-tree-service microservice (port 8011).
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

KNOWLEDGE_TREE_SERVICE_URL = os.getenv(
    "KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011"
)


async def _proxy_get(path: str, timeout: float = 30.0):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.get(
                f"{KNOWLEDGE_TREE_SERVICE_URL}{path}",
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


async def _proxy_post(path: str, body: dict, timeout: float = 30.0):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(
                f"{KNOWLEDGE_TREE_SERVICE_URL}{path}",
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
async def tree_stats(current_user: UserProfile = Depends(get_current_user_async)):
    return await _proxy_get("/tree/stats")


@router.get("/tree/graph/structure")
async def tree_graph_structure(current_user: UserProfile = Depends(get_current_user_async)):
    return await _proxy_get("/tree/graph/structure", timeout=60.0)


@router.post("/tree/graph/subgraph")
async def tree_graph_subgraph(request: Request, current_user: UserProfile = Depends(get_current_user_async)):
    body = await request.json()
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
    return await _proxy_post("/tree/graph/subgraph", body, timeout=60.0)


# ── TrustGraph Phase 2: triple-based endpoints ──


@router.get("/triples/stats")
async def triples_stats(current_user: UserProfile = Depends(get_current_user_async)):
    return await _proxy_get("/triples/stats")


@router.get("/triples/top-entities")
async def triples_top_entities(current_user: UserProfile = Depends(get_current_user_async)):
    return await _proxy_get("/triples/top-entities")


@router.post("/triples/query")
async def triples_query(request: Request, current_user: UserProfile = Depends(get_current_user_async)):
    body = await request.json()
    return await _proxy_post("/triples/query", body)


@router.post("/triples/neighbors")
async def triples_neighbors(request: Request, current_user: UserProfile = Depends(get_current_user_async)):
    body = await request.json()
    return await _proxy_post("/triples/neighbors", body, timeout=60.0)
