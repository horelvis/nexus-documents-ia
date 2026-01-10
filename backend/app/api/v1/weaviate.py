"""Weaviate API endpoints as gateway to Weaviate microservice

Uses the normalized WeaviateClient with standardized X-API-Key authentication.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, AsyncGenerator
import logging

from app.api.async_dependencies import get_current_tenant_id_async
from app.services.weaviate_client import weaviate_client
from app.clients.exceptions import HTTPClientError, ServiceTimeoutError

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# EMMA AI ENDPOINTS (AutoGen multi-agent)
# ============================================================================

@router.post("/emma/query")
async def emma_query(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Proxy Emma AI queries to Weaviate service"""
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        return await weaviate_client.emma_query(body)
    except HTTPClientError as e:
        logger.error(f"❌ Emma AI service error: {e}")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except ServiceTimeoutError:
        logger.error("⏱️ Emma AI service timeout")
        raise HTTPException(status_code=504, detail="Emma AI service timeout")
    except Exception as e:
        logger.error(f"❌ Emma AI proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/query/stream")
async def emma_query_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Proxy Emma AI streaming queries to Weaviate service.

    Returns Server-Sent Events (SSE) with progress updates during analysis.
    """
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id

        async def stream_sse() -> AsyncGenerator[bytes, None]:
            """Stream SSE events from Weaviate service to client."""
            async with weaviate_client.stream_client(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{weaviate_client.base_url}/emma/query/stream",
                    json=body,
                    headers={
                        **weaviate_client.get_stream_headers(),
                        "Content-Type": "application/json",
                    },
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"❌ Emma stream error: {response.status_code} - {error_text}")
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
        logger.error(f"❌ Emma stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emma/health")
async def emma_health():
    """Check Emma AI service health"""
    return await weaviate_client.emma_health()


@router.get("/emma/tools")
async def emma_list_tools():
    """List available Emma AI tools"""
    try:
        return await weaviate_client.emma_list_tools()
    except HTTPClientError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
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
