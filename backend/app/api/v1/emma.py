"""Emma AI API endpoints

Dedicated router for Emma AI assistant, proxying to emma-agent-service.
This replaces the legacy /weaviate/emma/* endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import logging
import httpx

from app.api.async_dependencies import get_current_tenant_id_async, get_current_user_async
from app.db.models import User
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Emma Agent Service URL
EMMA_SERVICE_URL = settings.EMMA_SERVICE_URL.rstrip("/")


@router.post("/query")
async def emma_query(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Query Emma AI assistant.

    Proxies to Emma Agent Service with ACL context for secure document access.
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id

        # Extract ACL context from authenticated user
        body["user_id"] = str(current_user.id)
        body["user_role_ids"] = [str(role.id) for role in current_user.roles] if current_user.roles else []
        body["is_admin"] = current_user.is_admin

        logger.debug(f"🧠 Emma query with ACL: user={current_user.id}, roles={len(body['user_role_ids'])}, admin={body['is_admin']}")

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/query",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                logger.error(f"❌ Emma service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        logger.error("⏱️ Emma AI service timeout")
        raise HTTPException(status_code=504, detail="Emma AI service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Emma AI proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def emma_query_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Stream Emma AI responses with real-time progress updates.

    Returns Server-Sent Events (SSE) with:
    - Reasoning steps (interleaved thinking)
    - Progress updates
    - Tool calls and observations
    - Final response tokens

    Proxies to Emma Agent Service with ACL context.
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id

        # Extract ACL context from authenticated user
        body["user_id"] = str(current_user.id)
        body["user_role_ids"] = [str(role.id) for role in current_user.roles] if current_user.roles else []
        body["is_admin"] = current_user.is_admin

        async def stream_sse() -> AsyncGenerator[bytes, None]:
            """Stream SSE events from Emma Agent Service to client."""
            import asyncio
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=10.0),
                http2=False,  # Disable HTTP/2 to avoid buffering issues
            ) as client:
                async with client.stream(
                    "POST",
                    f"{EMMA_SERVICE_URL}/emma/query/stream",
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                    },
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"❌ Emma stream error: {response.status_code} - {error_text}")
                        yield f"event: error\ndata: {{\"error\": \"Service error: {response.status_code}\"}}\n\n".encode()
                        return

                    # Use aiter_lines for SSE - each line is yielded immediately
                    async for line in response.aiter_lines():
                        if line:
                            yield (line + "\n").encode()
                        else:
                            # Empty line marks end of SSE event
                            yield b"\n"
                        await asyncio.sleep(0)

        return StreamingResponse(
            stream_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    except Exception as e:
        logger.error(f"❌ Emma stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/uploads/temp")
async def emma_upload_temp(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """Proxy temporary upload for non-indexed documents to Emma Agent Service."""
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY or "",
            "X-Tenant-ID": tenant_id,
            "X-User-ID": str(current_user.id),
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/uploads/temp",
                headers=headers,
                files={"file": (file.filename or "document", file_bytes, file.content_type)},
            )
            if response.status_code != 200:
                logger.error(f"❌ Emma upload error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Emma upload proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def emma_health():
    """Check Emma AI service health"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/health",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                return {"status": "unhealthy", "error": f"Status {response.status_code}"}
            return response.json()
    except Exception as e:
        logger.error(f"❌ Emma health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@router.get("/tools")
async def emma_tools(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get available Emma AI tools/capabilities"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/tools",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.warning(f"⚠️ Emma tools endpoint returned {response.status_code}")
                return {"tools": []}
            return response.json()
    except Exception as e:
        logger.error(f"❌ Emma tools error: {e}")
        return {"tools": []}


@router.post("/feedback")
async def emma_feedback(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Submit feedback for Emma AI response quality"""
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/feedback",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                logger.warning(f"⚠️ Emma feedback endpoint returned {response.status_code}")
                return {"status": "error", "message": response.text}
            return response.json()
    except Exception as e:
        logger.error(f"❌ Emma feedback error: {e}")
        return {"status": "error", "message": str(e)}
