"""Emma AI API endpoints

Dedicated router for Emma AI assistant, proxying to emma-agent-service.
This replaces the legacy /weaviate/emma/* endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
import logging
import httpx

from app.api.async_dependencies import get_current_tenant_id_async, get_current_user_async
from app.db.models import User
from app.core.config import settings
from app.core.sse_proxy import proxy_sse_stream

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

        return await proxy_sse_stream(
            f"{EMMA_SERVICE_URL}/emma/query/stream", body,
            timeout=300.0, log_prefix="Emma stream",
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


@router.post("/verified/generate/stream")
async def emma_verified_generate_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Stream verified document generation with real-time claim-by-claim progress.

    Proxies to Emma Agent Service verified generation endpoint with ACL context.
    Returns SSE events: claim_generated, claim_verified, claim_rejected, document_complete, error.
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)

        return await proxy_sse_stream(
            f"{EMMA_SERVICE_URL}/verified/generate/stream", body,
            timeout=600.0, log_prefix="Verified stream",
        )

    except Exception as e:
        logger.error(f"❌ Verified stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predictive/analyze/stream")
async def emma_predictive_analyze_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Stream predictive analysis with real-time factor extraction progress.

    Proxies to Emma Agent Service predictive analysis endpoint with ACL context.
    Returns SSE events: factor_extracted, factor_weighted, prediction_complete, error.
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)

        return await proxy_sse_stream(
            f"{EMMA_SERVICE_URL}/predictive/analyze/stream", body,
            timeout=600.0, log_prefix="Predictive stream",
        )

    except Exception as e:
        logger.error(f"❌ Predictive stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictive/analysis/{session_id}/pdf")
async def emma_predictive_analysis_pdf(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Export a predictive analysis session as PDF. Proxies to Emma Agent Service.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/predictive/analysis/{session_id}/pdf",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"❌ Predictive PDF error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="application/pdf",
                headers=dict(response.headers),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Predictive PDF proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictive/analysis/{session_id}/docx")
async def emma_predictive_analysis_docx(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Export a predictive analysis session as DOCX. Proxies to Emma Agent Service.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/predictive/analysis/{session_id}/docx",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"❌ Predictive DOCX error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers=dict(response.headers),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Predictive DOCX proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verified/session/{session_id}/claims")
async def emma_verified_session_claims(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Get verified claims for a session. Proxies to Emma Agent Service.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/verified/session/{session_id}/claims",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"❌ Verified claims error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Verified claims proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verified/session/{session_id}/docx")
async def emma_verified_session_docx(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Export a verified session as DOCX. Proxies to Emma Agent Service.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/verified/session/{session_id}/docx",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"❌ Verified DOCX error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers=dict(response.headers),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Verified DOCX proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verified/session/{session_id}/pdf")
async def emma_verified_session_pdf(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Export a verified session as PDF. Proxies to Emma Agent Service.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/verified/session/{session_id}/pdf",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"❌ Verified PDF error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="application/pdf",
                headers=dict(response.headers),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Verified PDF proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verified/session/{session_id}")
async def emma_verified_session(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Get full session data for recovery. Proxies to Emma Agent Service.
    Used when the frontend navigates away during generation and needs
    to recover the completed result.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/verified/session/{session_id}",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"Verified session error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verified session proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Training Endpoints (proxy to emma-agent-service /training/*)
# ============================================================================

@router.get("/training/status")
async def emma_training_status(
    current_user: User = Depends(get_current_user_async)
):
    """Get sector QA embedding training status."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/training/status",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Training status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training/start")
async def emma_training_start(
    request: Request,
    current_user: User = Depends(get_current_user_async)
):
    """Start sector QA embedding training."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Solo administradores pueden iniciar entrenamiento")
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/training/start",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Training start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/progress")
async def emma_training_progress(
    current_user: User = Depends(get_current_user_async)
):
    """Get current training progress."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/training/progress",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Training progress error: {e}")
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


# ============================================================================
# Heartbeat Endpoints (proxy to emma-agent-service /heartbeat/*)
# ============================================================================

@router.get("/heartbeat/config")
async def emma_heartbeat_config(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get heartbeat configuration for the tenant."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/config",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/heartbeat/config")
async def emma_heartbeat_config_update(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Update heartbeat configuration for the tenant."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar la configuración")
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.patch(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/config",
                params={"tenant_id": tenant_id},
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat config update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heartbeat/status")
async def emma_heartbeat_status(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get heartbeat status for the tenant."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/status",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat/run")
async def emma_heartbeat_run(
    force: bool = False,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Manually trigger a heartbeat evaluation for the tenant."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Solo administradores pueden ejecutar el heartbeat")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/run",
                params={"tenant_id": tenant_id, "force": str(force).lower()},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heartbeat/insights")
async def emma_heartbeat_insights(
    status: str = None,
    insight_type: str = None,
    limit: int = 20,
    page: int = 1,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """List proactive insights for the tenant."""
    try:
        params = {"tenant_id": tenant_id, "limit": limit, "page": page}
        if status:
            params["status"] = status
        if insight_type:
            params["insight_type"] = insight_type

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/insights",
                params=params,
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat insights error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat/insights/{insight_id}/dismiss")
async def emma_heartbeat_dismiss(
    insight_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Dismiss a proactive insight."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/insights/{insight_id}/dismiss",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat dismiss error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat/insights/{insight_id}/acted")
async def emma_heartbeat_acted(
    insight_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Mark a proactive insight as acted upon."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/insights/{insight_id}/acted",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat acted error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heartbeat/digest")
async def emma_heartbeat_digest(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get daily digest of insights and activity."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/heartbeat/digest",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Heartbeat digest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CENDOJ Endpoints (proxy to emma-agent-service /emma/cendoj/*)
# ============================================================================

@router.get("/cendoj/status")
async def emma_cendoj_status(
    current_user: User = Depends(get_current_user_async)
):
    """Get CENDOJ jurisprudence search status."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/cendoj/status",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CENDOJ status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Proactive Welcome Message (proxy to emma-agent-service /emma/welcome)
# ============================================================================

@router.get("/welcome")
async def emma_welcome(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Get a personalized, proactive welcome message for the current user.

    Uses LLM + user context (memory facts, recent sessions) to generate
    a contextual greeting like "Hola Horelvis, ¿seguimos con los contratos?"
    """
    try:
        user_name = current_user.full_name or current_user.email.split("@")[0]
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/welcome",
                params={
                    "tenant_id": tenant_id,
                    "user_id": str(current_user.id),
                    "user_name": user_name,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Emma welcome error: {response.status_code}")
            return {"message": f"¡Hola! ¿En qué puedo ayudarte hoy?", "personalized": False}
    except Exception as e:
        logger.debug(f"Welcome proxy error: {e}")
        return {"message": f"¡Hola! ¿En qué puedo ayudarte hoy?", "personalized": False}


# ============================================================================
# Session REST Endpoints (proxy to emma-agent-service /emma/sessions/*)
# For sidebar, session management. LangGraph protocol is in threads.py.
# ============================================================================

@router.get("/sessions")
async def emma_sessions_list(
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """
    List Emma chat sessions for the current user.

    Returns paginated sessions ordered by pinned first, then most recent.
    Used to build the conversation history sidebar.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/sessions",
                params={
                    "user_id": str(current_user.id),
                    "tenant_id": tenant_id,
                    "include_archived": str(include_archived).lower(),
                    "limit": limit,
                    "offset": offset,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sessions list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def emma_session_get(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get a full Emma session with all messages.

    Returns complete conversation history including messages, sources, and metadata.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/sessions/{session_id}",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/continue")
async def emma_session_continue(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """
    Continue an old Emma session (SSE stream).

    Loads session from cold storage (PostgreSQL) into hot cache (Redis).
    Returns text/event-stream matching the same format as /query/stream.
    """
    try:
        return await proxy_sse_stream(
            f"{EMMA_SERVICE_URL}/emma/sessions/{session_id}/continue?tenant_id={tenant_id}",
            body={},
            timeout=30.0,
            log_prefix="Session continue",
        )
    except Exception as e:
        logger.error(f"Session continue error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sessions/{session_id}")
async def emma_session_update(
    session_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """
    Update session properties (title, archived, pinned).
    """
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.patch(
                f"{EMMA_SERVICE_URL}/emma/sessions/{session_id}",
                params={
                    "user_id": str(current_user.id),
                    "tenant_id": tenant_id,
                },
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def emma_session_delete(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """
    Permanently delete an Emma session.

    Removes from PostgreSQL and Redis. Cannot be undone.
    Consider archiving (PATCH with is_archived=true) for recoverable deletion.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.delete(
                f"{EMMA_SERVICE_URL}/emma/sessions/{session_id}",
                params={
                    "user_id": str(current_user.id),
                    "tenant_id": tenant_id,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# User Memory Endpoints (proxy to emma-agent-service /emma/memory/*)
# ============================================================================

@router.get("/memory/facts")
async def emma_memory_facts(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    List all memory facts Emma has learned about the current user.

    Returns cross-session facts like name, department, and preferences.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/memory/facts",
                params={"tenant_id": tenant_id, "user_id": str(current_user.id)},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory facts list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memory/facts")
async def emma_memory_facts_clear(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Delete ALL memory facts for the current user (GDPR right-to-erasure).

    Permanently removes all facts Emma has learned across conversations.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.delete(
                f"{EMMA_SERVICE_URL}/emma/memory/facts",
                params={"tenant_id": tenant_id, "user_id": str(current_user.id)},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory facts clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memory/facts/{fact_id}")
async def emma_memory_fact_delete(
    fact_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Delete a single memory fact by ID.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.delete(
                f"{EMMA_SERVICE_URL}/emma/memory/facts/{fact_id}",
                params={"tenant_id": tenant_id, "user_id": str(current_user.id)},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory fact delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Notification Endpoints (proxy to emma-agent-service /emma/notifications/*)
# ============================================================================

@router.get("/notifications")
async def emma_notifications_list(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """List recent notifications for the current user."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/notifications",
                params={
                    **dict(request.query_params),
                    "tenant_id": tenant_id,
                    "user_id": str(current_user.id),
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notifications list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/notifications/{notification_id}/read")
async def emma_notification_mark_read(
    notification_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Mark a single notification as read."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.patch(
                f"{EMMA_SERVICE_URL}/emma/notifications/{notification_id}/read",
                params={"tenant_id": tenant_id, "user_id": str(current_user.id)},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notification mark read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/read-all")
async def emma_notifications_read_all(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Mark all notifications as read."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/notifications/read-all",
                params={"tenant_id": tenant_id, "user_id": str(current_user.id)},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notifications read-all error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/cendoj/status")
async def emma_cendoj_status_update(
    request: Request,
    current_user: User = Depends(get_current_user_async)
):
    """Toggle CENDOJ jurisprudence search on/off."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar CENDOJ")
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.patch(
                f"{EMMA_SERVICE_URL}/emma/cendoj/status",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CENDOJ status update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Generated Document Download (proxy to emma-agent-service)
# ============================================================================

@router.get("/generated/{doc_id}/download")
async def emma_generated_download(
    doc_id: str,
    current_user: User = Depends(get_current_user_async)
):
    """
    Download a DOCX document generated by the generate_document tool.
    Documents are available for 1 hour after generation.
    Proxies to Emma Agent Service.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/generated/{doc_id}/download",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)

            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers=dict(response.headers),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Generated doc download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generated/{doc_id}/info")
async def emma_generated_info(
    doc_id: str,
    current_user: User = Depends(get_current_user_async)
):
    """Get metadata about a generated document without downloading it."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/generated/{doc_id}/info",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Generated doc info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Explainability Endpoints (proxy to emma-agent-service /emma/explainability/*)
# =============================================================================

@router.get("/explainability/graph")
async def explainability_graph(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Full tenant knowledge graph for 3D visualization."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/explainability/graph",
                params={"tenant_id": tenant_id},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explainability graph error: {e}")
        raise HTTPException(status_code=502, detail="Explainability service unavailable")


@router.get("/explainability/trace/{thread_id}/{message_index}")
async def explainability_trace(
    thread_id: str,
    message_index: int,
    current_user: User = Depends(get_current_user_async),
):
    """Per-response reasoning trace for the ReasoningModal."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/explainability/trace/{thread_id}/{message_index}",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explainability trace error: {e}")
        raise HTTPException(status_code=502, detail="Explainability service unavailable")


# ── Knowledge Report Document Generation ──────────────────────────────


@router.post("/reports/{report_id}/generate-document")
async def report_generate_document(
    report_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_async),
):
    """Generate DOCX from a stored knowledge report. Proxies to Emma."""
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{EMMA_SERVICE_URL}/emma/reports/{report_id}/generate-document",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report generate-document error: {e}")
        raise HTTPException(status_code=502, detail="Report generation service unavailable")


@router.get("/reports/{report_id}/download")
async def report_download(
    report_id: str,
    current_user: User = Depends(get_current_user_async),
):
    """Download a generated report DOCX. Proxies to Emma."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/reports/{report_id}/download",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return Response(
                content=response.content,
                media_type=response.headers.get("content-type", "application/octet-stream"),
                headers={
                    "Content-Disposition": response.headers.get(
                        "content-disposition", f'attachment; filename="report_{report_id}.docx"'
                    ),
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report download error: {e}")
        raise HTTPException(status_code=502, detail="Report download service unavailable")
