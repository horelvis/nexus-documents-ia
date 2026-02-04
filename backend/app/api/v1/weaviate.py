"""Weaviate API endpoints as gateway to Weaviate microservice

Uses the normalized WeaviateClient with standardized X-API-Key authentication.
Emma endpoints are proxied to emma-agent-service.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, AsyncGenerator, List
import logging
import os
import httpx

from app.api.async_dependencies import get_current_tenant_id_async, get_current_user_async
from app.db.models import User
from app.services.weaviate_client import weaviate_client
from app.clients.exceptions import HTTPClientError, ServiceTimeoutError
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Emma Agent Service URL
EMMA_SERVICE_URL = settings.EMMA_SERVICE_URL.rstrip("/")


# ============================================================================
# EMMA AI ENDPOINTS (AutoGen multi-agent)
# ============================================================================

@router.post("/emma/query")
async def emma_query(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Proxy Emma AI queries to Emma Agent Service with ACL context"""
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id

        # Extract ACL context from authenticated user
        body["user_id"] = str(current_user.id)
        body["user_role_ids"] = [str(role.id) for role in current_user.roles] if current_user.roles else []
        body["is_admin"] = current_user.is_admin

        logger.debug(f"🔐 Emma query with ACL: user={current_user.id}, roles={len(body['user_role_ids'])}, admin={body['is_admin']}")

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


@router.post("/emma/query/stream")
async def emma_query_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Proxy Emma AI streaming queries to Emma Agent Service with ACL context.

    Returns Server-Sent Events (SSE) with progress updates during analysis.
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


@router.post("/emma/uploads/temp")
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


@router.get("/emma/health")
async def emma_health():
    """Check Emma AI service health from Emma Agent Service"""
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


# ============================================================================
# EMMA V2 ENDPOINTS (New architecture with SIL integration)
# ============================================================================

@router.post("/emma/v2/query")
async def emma_v2_query(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Proxy Emma v2 queries to Emma Agent Service with ACL context.

    Emma v2 features:
    - LangGraph multi-agent orchestration
    - Domain-specific specialist agents
    - Interleaved thinking with reasoning steps
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)
        body["user_role_ids"] = [str(role.id) for role in current_user.roles] if current_user.roles else []
        body["is_admin"] = current_user.is_admin

        logger.debug(f"🧠 Emma v2 query with ACL: user={current_user.id}, admin={body['is_admin']}")

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
                logger.error(f"❌ Emma v2 service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        logger.error("⏱️ Emma v2 service timeout")
        raise HTTPException(status_code=504, detail="Emma v2 service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Emma v2 proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/v2/query/stream")
async def emma_v2_query_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Proxy Emma v2 streaming queries to Emma Agent Service with ACL context.

    Returns Server-Sent Events (SSE) with progress updates during analysis.
    Emma v2 uses LangGraph multi-agent orchestration with interleaved thinking.
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)
        body["user_role_ids"] = [str(role.id) for role in current_user.roles] if current_user.roles else []
        body["is_admin"] = current_user.is_admin

        async def stream_sse() -> AsyncGenerator[bytes, None]:
            """Stream SSE events from Emma Agent Service to client."""
            import asyncio
            transport = httpx.AsyncHTTPTransport(retries=0)
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=10.0),
                transport=transport,
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
                        logger.error(f"❌ Emma v2 stream error: {response.status_code} - {error_text}")
                        yield f"event: error\ndata: {{\"error\": \"Service error: {response.status_code}\"}}\n\n".encode()
                        return

                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
                            await asyncio.sleep(0)

        return StreamingResponse(
            stream_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Transfer-Encoding": "chunked",
            }
        )

    except Exception as e:
        logger.error(f"❌ Emma v2 stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emma/tools")
async def emma_list_tools():
    """List available Emma AI tools from Emma Agent Service"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{EMMA_SERVICE_URL}/emma/tools",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Emma tools service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to list Emma tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/feedback")
async def emma_feedback(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Submit feedback to Emma AI for learning"""
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        return await weaviate_client.emma_feedback(body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Emma feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emma/analysis/{job_id}")
async def emma_get_analysis(
    job_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get a stored analysis result by job ID.

    Returns the full analysis data including summary, risks, recommendations,
    findings, and annotations.
    """
    try:
        return await weaviate_client.emma_get_analysis(job_id)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Emma get analysis proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/document/markdown")
async def emma_document_markdown(
    document_id: str = Form(...),
    pdf_file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Convert a PDF document to Markdown format.

    Returns the document content as structured Markdown pages.
    """
    try:
        file_content = await pdf_file.read()
        return await weaviate_client.emma_document_markdown(
            document_id=document_id,
            file_content=file_content,
            filename=pdf_file.filename or "document.pdf",
            content_type=pdf_file.content_type or "application/pdf"
        )
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Emma document/markdown proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/analyze-with-annotations")
async def emma_analyze_with_annotations(
    document_id: str = Form(...),
    analysis_type: str = Form("legal"),
    file: Optional[UploadFile] = File(None),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Analyze document and return annotated PDF with highlights.

    The PDF will have native PDF annotations (highlights) for risks
    and recommendations identified by Emma AI.
    """
    try:
        file_content = None
        filename = None
        content_type = "application/pdf"

        if file:
            file_content = await file.read()
            filename = file.filename
            content_type = file.content_type or "application/pdf"

        return await weaviate_client.emma_analyze_with_annotations(
            document_id=document_id,
            tenant_id=tenant_id,
            analysis_type=analysis_type,
            file_content=file_content,
            filename=filename,
            content_type=content_type
        )
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Analysis timeout - document may be too large")
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Emma analyze-with-annotations proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/analyze-with-annotations/stream")
async def emma_analyze_with_annotations_stream(
    document_id: str = Form(...),
    analysis_type: str = Form("legal"),
    file: Optional[UploadFile] = File(None),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Analyze document with streaming progress updates.

    Returns Server-Sent Events (SSE) with real-time progress as each
    agent executes. The final event contains the annotated PDF.
    """
    try:
        form_data = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "analysis_type": analysis_type,
        }

        files = {}
        if file:
            file_content = await file.read()
            files["file"] = (file.filename, file_content, file.content_type or "application/pdf")

        async def stream_sse() -> AsyncGenerator[bytes, None]:
            """Stream SSE events from Weaviate service to client."""
            async with weaviate_client.stream_client(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{weaviate_client.base_url}/emma/analyze-with-annotations/stream",
                    data=form_data,
                    files=files if files else None,
                    headers=weaviate_client.get_stream_headers(),
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"❌ Emma stream analysis error: {response.status_code} - {error_text}")
                        yield f"event: error\ndata: {{\"error\": \"Service error: {response.status_code}\"}}\n\n".encode()
                        return

                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            stream_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(f"❌ Emma analyze-with-annotations stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PUBLIC KNOWLEDGE BASE ENDPOINTS
# ============================================================================

@router.get("/public-knowledge/health")
async def public_knowledge_health():
    """Check public knowledge base health"""
    return await weaviate_client.public_knowledge_health()


@router.get("/public-knowledge/stats")
async def public_knowledge_stats():
    """Get public knowledge base statistics"""
    try:
        return await weaviate_client.public_knowledge_stats()
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Service timeout")
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Public knowledge stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/categories")
async def public_knowledge_categories():
    """Get available categories"""
    try:
        return await weaviate_client.public_knowledge_categories()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Public knowledge categories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/jurisdictions")
async def public_knowledge_jurisdictions():
    """Get available jurisdictions"""
    try:
        return await weaviate_client.public_knowledge_jurisdictions()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Public knowledge jurisdictions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/public-knowledge/search")
async def public_knowledge_search(request: Request):
    """Search public knowledge base"""
    try:
        body = await request.json()
        return await weaviate_client.public_knowledge_search(body)
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Search timeout")
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Public knowledge search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/documents/{doc_id}")
async def public_knowledge_get_document(doc_id: str):
    """Get a specific document from public knowledge base"""
    try:
        return await weaviate_client.public_knowledge_get_document(doc_id)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Public knowledge get document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# KNOWLEDGE GRAPH ENDPOINTS
# ============================================================================

@router.post("/knowledge/search")
async def knowledge_search(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Search knowledge entities semantically with ACL filtering"""
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)
        body["user_role_ids"] = [str(role.id) for role in current_user.roles] if current_user.roles else []
        body["is_admin"] = current_user.is_admin

        return await weaviate_client.knowledge_search(body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Knowledge search proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/entities")
async def knowledge_list_entities(
    entity_type: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 50,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """List knowledge entities for current tenant"""
    try:
        return await weaviate_client.knowledge_list_entities(
            tenant_id=tenant_id,
            entity_type=entity_type,
            domain=domain,
            limit=limit
        )
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Knowledge list entities proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/entities/{entity_id}")
async def knowledge_get_entity(
    entity_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get a specific knowledge entity"""
    try:
        return await weaviate_client.knowledge_get_entity(entity_id, tenant_id)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Knowledge get entity proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/knowledge/entities/{entity_id}")
async def knowledge_delete_entity(
    entity_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Delete a knowledge entity"""
    try:
        return await weaviate_client.knowledge_delete_entity(entity_id, tenant_id)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Knowledge delete entity proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/knowledge/documents/{document_id}")
async def knowledge_delete_by_document(
    document_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Delete all knowledge entities from a document"""
    try:
        return await weaviate_client.knowledge_delete_by_document(document_id, tenant_id)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Knowledge delete by document proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/stats")
async def knowledge_stats(
    tenant_id: str = Depends(get_current_tenant_id_async),
    include_public: bool = True
):
    """Get knowledge graph statistics for current tenant.

    Combines tenant-specific entities with public_knowledge entities
    which are extracted from public legislation/regulations.
    """
    try:
        # Get tenant-specific stats
        tenant_stats = await weaviate_client.knowledge_stats(tenant_id)

        if not include_public:
            return tenant_stats

        # Also get public_knowledge stats (shared across all tenants)
        try:
            public_stats = await weaviate_client.knowledge_stats("public_knowledge")

            # Merge stats - public entities are accessible to all tenants
            combined_stats = {
                "tenant_id": tenant_id,
                "total_entities": (tenant_stats.get("total_entities", 0) +
                                   public_stats.get("total_entities", 0)),
                "entities_by_type": {},
                "entities_by_domain": {},
                "tenant_entities": tenant_stats.get("total_entities", 0),
                "public_entities": public_stats.get("total_entities", 0),
            }

            # Merge by type
            for entity_type, count in tenant_stats.get("entities_by_type", {}).items():
                combined_stats["entities_by_type"][entity_type] = count
            for entity_type, count in public_stats.get("entities_by_type", {}).items():
                combined_stats["entities_by_type"][entity_type] = (
                    combined_stats["entities_by_type"].get(entity_type, 0) + count
                )

            # Merge by domain
            for domain, count in tenant_stats.get("entities_by_domain", {}).items():
                combined_stats["entities_by_domain"][domain] = count
            for domain, count in public_stats.get("entities_by_domain", {}).items():
                combined_stats["entities_by_domain"][domain] = (
                    combined_stats["entities_by_domain"].get(domain, 0) + count
                )

            return combined_stats
        except Exception as public_err:
            logger.warning(f"Could not fetch public_knowledge stats: {public_err}")
            return tenant_stats

    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Knowledge stats proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# USER LEARNING ENDPOINTS
# ============================================================================

@router.get("/learning/profile")
async def learning_get_profile(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get current user's learning profile"""
    try:
        return await weaviate_client.learning_get_profile(tenant_id, str(current_user.id))
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning get profile proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/learning/profile")
async def learning_update_profile(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Update current user's learning profile preferences"""
    try:
        body = await request.json()
        return await weaviate_client.learning_update_profile(tenant_id, str(current_user.id), body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning update profile proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learning/feedback")
async def learning_record_feedback(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Record user feedback for learning"""
    try:
        body = await request.json()
        return await weaviate_client.learning_record_feedback(tenant_id, str(current_user.id), body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning record feedback proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learning/document-view")
async def learning_record_document_view(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Record document view for learning"""
    try:
        body = await request.json()
        return await weaviate_client.learning_record_document_view(tenant_id, str(current_user.id), body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning record document view proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/stats")
async def learning_get_stats(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get learning statistics for current user"""
    try:
        return await weaviate_client.learning_get_stats(tenant_id, str(current_user.id))
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning get stats proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/context")
async def learning_get_context(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get full user context for Emma"""
    try:
        return await weaviate_client.learning_get_context(tenant_id, str(current_user.id))
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning get context proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/ranking-weights")
async def learning_get_ranking_weights(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Get personalized ranking weights for RAG"""
    try:
        return await weaviate_client.learning_get_ranking_weights(tenant_id, str(current_user.id))
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Learning get ranking weights proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WEAVIATE SERVICE HEALTH
# ============================================================================

# ============================================================================
# STRUCTURAL INTELLIGENCE LAYER (SIL) ENDPOINTS
# ============================================================================

@router.post("/sil/query")
async def sil_query(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Process a query through the Structural Intelligence Layer.

    SIL analyzes queries and determines if they can be answered structurally
    (without reading document content) or if RAG is needed.

    Returns:
    - Direct answer for structural queries (count, exists, location)
    - Structural context for augmented RAG
    - Target documents for focused RAG
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)

        return await weaviate_client.sil_query(body)
    except HTTPClientError as e:
        logger.error(f"❌ SIL query error: {e}")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="SIL query timeout")
    except Exception as e:
        logger.error(f"❌ SIL query proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sil/structure/{document_id}")
async def sil_get_structure(
    document_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get structural metadata for a specific document"""
    try:
        return await weaviate_client.sil_get_structure(document_id, tenant_id)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found in SIL")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL get structure proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sil/graph/stats")
async def sil_graph_stats(
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get statistics about the structural graph.

    Returns total documents, folders, breakdown by semantic type, etc.
    """
    try:
        return await weaviate_client.sil_graph_stats(tenant_id)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL graph stats proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sil/search-structural")
async def sil_search_structural(
    query: str,
    limit: int = 10,
    semantic_type: Optional[str] = None,
    domain: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Search structural documents by semantic similarity.

    This searches structural description embeddings, NOT document content.
    Useful for finding documents by their structural characteristics.
    """
    try:
        return await weaviate_client.sil_search_structural(
            query=query,
            tenant_id=tenant_id,
            limit=limit,
            semantic_type=semantic_type,
            domain=domain
        )
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL search structural proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sil/folder/{folder_path:path}")
async def sil_get_folder_contents(
    folder_path: str,
    include_subfolders: bool = False,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get contents of a structural folder"""
    try:
        return await weaviate_client.sil_get_folder_contents(
            folder_path=folder_path,
            tenant_id=tenant_id,
            include_subfolders=include_subfolders
        )
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL folder contents proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sil/related/{document_id}")
async def sil_get_related_documents(
    document_id: str,
    relationship_type: Optional[str] = None,
    max_depth: int = 2,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get documents related to a given document through the structural graph"""
    try:
        return await weaviate_client.sil_get_related_documents(
            document_id=document_id,
            tenant_id=tenant_id,
            relationship_type=relationship_type,
            max_depth=max_depth
        )
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL related documents proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sil/graph/document-ids")
async def sil_get_document_ids(
    limit: int = 10000,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get list of document IDs already indexed in the SIL graph"""
    try:
        return await weaviate_client.sil_get_document_ids(tenant_id=tenant_id, limit=limit)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL document IDs proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SIL ADMIN ENDPOINTS (requires admin permissions)
# ============================================================================

@router.post("/sil/index-structural")
async def sil_index_structural(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Index structural metadata for a document.

    Admin endpoint - typically called during document indexing.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        return await weaviate_client.sil_index_structural(body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL index structural proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sil/structure/{document_id}")
async def sil_mark_document_removed(
    document_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """Mark a document as removed in the structural graph (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        return await weaviate_client.sil_mark_document_removed(document_id, tenant_id)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL mark removed proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sil/graph/clear")
async def sil_clear_graph(
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Clear the structural graph for the current tenant.

    WARNING: This is a destructive operation. All structural metadata will be deleted.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        logger.warning(f"🚨 Admin {current_user.id} clearing SIL graph for tenant {tenant_id}")
        return await weaviate_client.sil_clear_graph(tenant_id)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ SIL clear graph proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sil/reindex")
async def sil_reindex(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async)
):
    """
    Re-index documents to the structural graph.

    Modes:
    - full_reindex=true: Clear graph and re-index ALL documents
    - full_reindex=false: Only index NEW documents not in graph

    Admin only. For large datasets, this may take several minutes.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        body = await request.json()
        body["tenant_id"] = tenant_id

        logger.info(
            f"🔄 Admin {current_user.id} starting SIL reindex | "
            f"tenant={tenant_id} full={body.get('full_reindex', False)}"
        )

        return await weaviate_client.sil_reindex(body)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Reindex timeout - operation may still be running")
    except Exception as e:
        logger.error(f"❌ SIL reindex proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BOE LEGISLATION ENDPOINTS (Public Knowledge Indexing)
# ============================================================================

@router.get("/boe/presets")
async def boe_list_presets():
    """List available BOE legislation presets (categories)"""
    try:
        return await weaviate_client.boe_list_presets()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ BOE list presets proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boe/presets/{preset_name}")
async def boe_get_preset(preset_name: str):
    """Get details of a specific BOE preset"""
    try:
        return await weaviate_client.boe_get_preset(preset_name)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ BOE get preset proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boe/legislation/{boe_id}")
async def boe_get_legislation_info(boe_id: str):
    """Get information about a BOE legislation document (without downloading)"""
    try:
        return await weaviate_client.boe_get_legislation_info(boe_id)
    except HTTPClientError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Legislation '{boe_id}' not found in BOE")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ BOE legislation info proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boe/search")
async def boe_search(
    query: str,
    limit: int = 10
):
    """Search BOE for legislation (does not download or index)"""
    try:
        return await weaviate_client.boe_search(query=query, limit=limit)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ BOE search proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boe/all-legislation-ids")
async def boe_get_all_legislation_ids():
    """Get all BOE IDs across all presets (for bulk operations)"""
    try:
        return await weaviate_client.boe_get_all_legislation_ids()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ BOE all legislation IDs proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# BOE Admin endpoints (require admin permissions)

@router.post("/boe/download")
async def boe_download_legislation(
    request: Request,
    current_user: User = Depends(get_current_user_async)
):
    """
    Download and index a specific BOE legislation document.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        body = await request.json()
        boe_id = body.get("boe_id")
        index = body.get("index_to_weaviate", True)

        if not boe_id:
            raise HTTPException(status_code=400, detail="boe_id is required")

        logger.info(f"📥 Admin {current_user.id} downloading BOE legislation: {boe_id}")
        return await weaviate_client.boe_download_legislation(boe_id, index=index)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Download timeout - document may be too large")
    except Exception as e:
        logger.error(f"❌ BOE download proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boe/download/preset")
async def boe_download_preset(
    request: Request,
    current_user: User = Depends(get_current_user_async)
):
    """
    Download all legislation in a preset category.
    This can take a while for large presets.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        body = await request.json()
        preset = body.get("preset")
        index = body.get("index_to_weaviate", True)

        if not preset:
            raise HTTPException(status_code=400, detail="preset is required")

        logger.info(f"📥 Admin {current_user.id} downloading BOE preset: {preset}")
        return await weaviate_client.boe_download_preset(preset, index=index)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Download timeout - try with a smaller preset")
    except Exception as e:
        logger.error(f"❌ BOE preset download proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boe/sync/{boe_id}")
async def boe_sync_legislation(
    boe_id: str,
    force: bool = False,
    current_user: User = Depends(get_current_user_async)
):
    """
    Sync a specific legislation with BOE and detect article-level changes.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        logger.info(f"🔄 Admin {current_user.id} syncing BOE legislation: {boe_id}")
        return await weaviate_client.boe_sync_legislation(boe_id, force=force)
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Sync timeout")
    except Exception as e:
        logger.error(f"❌ BOE sync proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boe/sync/all")
async def boe_sync_all(
    current_user: User = Depends(get_current_user_async)
):
    """
    Sync all tracked legislation and detect changes.
    This can take a while if many laws are tracked.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        logger.info(f"🔄 Admin {current_user.id} syncing all BOE legislation")
        return await weaviate_client.boe_sync_all()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(status_code=504, detail="Sync timeout - operation may still be running")
    except Exception as e:
        logger.error(f"❌ BOE sync all proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boe/updates")
async def boe_get_pending_updates(
    current_user: User = Depends(get_current_user_async)
):
    """
    Get list of legislation with pending updates from BOE.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        return await weaviate_client.boe_get_pending_updates()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ BOE pending updates proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PUBLIC KNOWLEDGE ENTITY EXTRACTION
# ============================================================================

@router.post("/public-knowledge/extract")
async def public_knowledge_extract_entities(
    limit: int = 100,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user_async)
):
    """
    Extract knowledge entities from public documents into the Knowledge Graph.

    Processes existing public documents (legislation, regulations, etc.) and extracts
    entities like articles, terms, references, organizations, and dates.

    These entities are stored in the Knowledge Graph for:
    - Semantic search across entity types
    - Entity-based queries ("¿Cuántas leyes hablan de vacaciones?")
    - Relationship discovery between concepts

    Parameters:
    - limit: Maximum documents to process (default 100)
    - category: Optional filter by category (legislation, regulation, etc.)

    Admin only. Can take several minutes for large document sets.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        logger.info(
            f"🧠 Admin {current_user.id} extracting knowledge from public documents | "
            f"limit={limit} category={category}"
        )
        return await weaviate_client.public_knowledge_extract_entities(
            limit=limit,
            category=category
        )
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Extraction timeout - operation may still be running"
        )
    except Exception as e:
        logger.error(f"❌ Public knowledge extraction proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/stats")
async def public_knowledge_stats():
    """Get public knowledge base statistics"""
    try:
        return await weaviate_client.public_knowledge_stats()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Public knowledge stats proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WEAVIATE SERVICE HEALTH
# ============================================================================

@router.get("/health")
async def weaviate_service_health():
    """Overall Weaviate service health including Emma AI"""
    try:
        weaviate_health = await weaviate_client.health_check()
        emma_health = await weaviate_client.emma_health()

        return {
            "weaviate_service": weaviate_health,
            "emma_ai": emma_health,
            "overall_status": "healthy" if (
                weaviate_health.get("status") == "healthy" and
                emma_health.get("status") == "healthy"
            ) else "unhealthy"
        }

    except Exception as e:
        logger.error(f"❌ Weaviate service health check failed: {e}")
        return {
            "overall_status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# KNOWLEDGE TREE ENDPOINTS (Apache AGE graph visualization)
# ============================================================================

KNOWLEDGE_TREE_SERVICE_URL = os.getenv("KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")


@router.get("/tree/stats")
async def tree_stats(
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Get knowledge tree stats from Apache AGE via knowledge-tree-service"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{KNOWLEDGE_TREE_SERVICE_URL}/tree/stats",
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
        logger.error(f"Knowledge tree stats proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree/graph/structure")
async def tree_graph_structure(
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Get full graph structure (nodes + edges) for visualization"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(
                f"{KNOWLEDGE_TREE_SERVICE_URL}/tree/graph/structure",
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
        logger.error(f"Knowledge tree graph structure proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Legal Knowledge Graph (Public) — proxied to weaviate-service
# =============================================================================

@router.get("/legal/graph/structure")
async def legal_graph_structure():
    """Get full legal graph structure (nodes + edges) for visualization."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/legal/graph/structure",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Legal graph service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Legal graph structure proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/legal/stats")
async def legal_graph_stats():
    """Get legal knowledge graph statistics."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/legal/stats",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Legal graph service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Legal graph stats proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


