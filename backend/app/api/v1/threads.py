"""LangGraph Protocol Proxy — /api/v1/threads/*

Proxies LangGraph SDK requests to emma-agent-service, injecting
authenticated user context (user_id, user_roles) from the OIDC token.

The SDK (useStream) calls:
    POST /api/v1/threads                          → Create thread
    GET  /api/v1/threads/{id}/state               → Checkpoint state
    POST /api/v1/threads/{id}/history             → Checkpoint history
    POST /api/v1/threads/{id}/runs/stream         → SSE streaming run

These map 1:1 to emma-agent-service's /api/threads/* (langgraph_protocol.py).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
import logging

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.config import settings
from app.core.sse_proxy import proxy_sse_stream

logger = logging.getLogger(__name__)
router = APIRouter()

EMMA_SERVICE_URL = settings.EMMA_SERVICE_URL.rstrip("/")


def _proxy_headers(current_user: UserProfile) -> dict:
    """Build common headers for service-to-service proxy calls."""
    return {
        "X-API-Key": settings.MICROSERVICES_API_KEY or "",
        "X-User-ID": current_user.sub,
        "X-User-Roles": ",".join(current_user.roles or []),
    }


@router.post("")
async def thread_create(
    request: Request,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """Create a new thread (LangGraph protocol)."""
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/api/threads",
                json=body,
                headers={"Content-Type": "application/json", **_proxy_headers(current_user)},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thread create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{thread_id}/state")
async def thread_state(
    thread_id: str,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """Get current LangGraph checkpoint state."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/api/threads/{thread_id}/state",
                headers=_proxy_headers(current_user),
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thread state error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route("/{thread_id}/history", methods=["GET", "POST"])
async def thread_history(
    thread_id: str,
    limit: int = 10,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """Get LangGraph checkpoint history for branching/regeneration."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/api/threads/{thread_id}/history",
                headers=_proxy_headers(current_user),
                params={"limit": limit},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thread history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{thread_id}/runs/stream")
async def thread_run_stream(
    thread_id: str,
    request: Request,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """Execute a LangGraph run with SSE streaming."""
    try:
        body = await request.json()
        return await proxy_sse_stream(
            f"{EMMA_SERVICE_URL}/api/threads/{thread_id}/runs/stream",
            body=body,
            timeout=300.0,
            log_prefix="LangGraph run",
            extra_headers=_proxy_headers(current_user),
        )
    except Exception as e:
        logger.error(f"Thread run stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
