"""Weaviate API endpoints as gateway to Weaviate microservice"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, AsyncGenerator
import logging
import httpx

from app.api.dependencies import get_current_tenant_id
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Weaviate service configuration
WEAVIATE_SERVICE_URL = settings.WEAVIATE_SERVICE_URL

# ============================================================================
# EMMA AI ENDPOINTS (AutoGen multi-agent)
# ============================================================================

@router.post("/emma/query")
async def emma_query(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Proxy Emma AI queries to Weaviate service"""
    try:
        # Get request body
        body = await request.json()

        # Ensure tenant_id is set to current tenant
        body["tenant_id"] = tenant_id

        # Get microservice API key from settings
        microservice_key = settings.microservices_api_key

        # Forward to Weaviate service (Emma endpoint)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/emma/query",
                json=body,
                headers={
                    "Authorization": f"Bearer {microservice_key}",
                    "Content-Type": "application/json"
                },
                timeout=180.0  # 3 minutes - matches frontend EMMA_TIMEOUT
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Emma AI service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Emma AI service error: {response.text}"
                )

    except httpx.TimeoutException:
        logger.error("⏱️ Emma AI service timeout")
        raise HTTPException(status_code=504, detail="Emma AI service timeout")
    except Exception as e:
        logger.error(f"❌ Emma AI proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/query/stream")
async def emma_query_stream(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Proxy Emma AI streaming queries to Weaviate service.

    Returns Server-Sent Events (SSE) with progress updates during analysis.
    """
    try:
        # Get request body
        body = await request.json()

        # Ensure tenant_id is set to current tenant
        body["tenant_id"] = tenant_id

        # Get microservice API key from settings
        microservice_key = settings.microservices_api_key

        async def stream_sse() -> AsyncGenerator[bytes, None]:
            """Stream SSE events from Weaviate service to client."""
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{WEAVIATE_SERVICE_URL}/emma/query/stream",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {microservice_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream"
                    },
                    timeout=300.0  # 5 minutes for streaming
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"❌ Emma stream error: {response.status_code} - {error_text}")
                        yield f"event: error\ndata: {{\"error\": \"Service error: {response.status_code}\"}}\n\n".encode()
                        return

                    # Forward SSE events directly
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            stream_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except Exception as e:
        logger.error(f"❌ Emma stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emma/health")
async def emma_health():
    """Check Emma AI service health"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/emma/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "unhealthy",
                    "service": "emma",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

    except Exception as e:
        logger.error(f"❌ Emma health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "emma",
            "error": str(e)
        }

@router.get("/emma/tools")
async def emma_list_tools():
    """List available Emma AI tools"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/emma/tools",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Tools listing error: {response.text}"
                )

    except Exception as e:
        logger.error(f"❌ Failed to list Emma tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/emma/feedback")
async def emma_feedback(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Submit feedback to Emma AI for learning"""
    try:
        body = await request.json()
        body["tenant_id"] = tenant_id

        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/emma/feedback",
                json=body,
                headers={
                    "Authorization": f"Bearer {microservice_key}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Feedback submission error: {response.text}"
                )

    except Exception as e:
        logger.error(f"❌ Emma feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emma/analysis/{job_id}")
async def emma_get_analysis(
    job_id: str,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get a stored analysis result by job ID.

    Returns the full analysis data including summary, risks, recommendations,
    findings, and annotations. Use this to display previously completed analyses.
    """
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/emma/analysis/{job_id}",
                headers={
                    "Authorization": f"Bearer {microservice_key}"
                },
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")
            else:
                logger.error(f"❌ Emma get analysis error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error getting analysis: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Emma get analysis proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/document/markdown")
async def emma_document_markdown(
    document_id: str = Form(...),
    pdf_file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Convert a PDF document to Markdown format.

    Returns the document content as structured Markdown pages.
    """
    try:
        microservice_key = settings.microservices_api_key

        file_content = await pdf_file.read()
        files = {"pdf_file": (pdf_file.filename, file_content, pdf_file.content_type or "application/pdf")}
        form_data = {"document_id": document_id}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/emma/document/markdown",
                data=form_data,
                files=files,
                headers={
                    "Authorization": f"Bearer {microservice_key}"
                },
                timeout=120.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Emma document/markdown error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Markdown conversion error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Emma document/markdown proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/analyze-with-annotations")
async def emma_analyze_with_annotations(
    document_id: str = Form(...),
    analysis_type: str = Form("legal"),
    file: Optional[UploadFile] = File(None),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Analyze document and return annotated PDF with highlights.

    The PDF will have native PDF annotations (highlights) for risks
    and recommendations identified by Emma AI.
    """
    try:
        microservice_key = settings.microservices_api_key

        # Prepare form data for multipart request
        form_data = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "analysis_type": analysis_type,
        }

        files = {}
        if file:
            file_content = await file.read()
            files["file"] = (file.filename, file_content, file.content_type or "application/pdf")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/emma/analyze-with-annotations",
                data=form_data,
                files=files if files else None,
                headers={
                    "Authorization": f"Bearer {microservice_key}"
                },
                timeout=300.0  # Extended timeout for analysis + PDF annotation
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Emma analyze-with-annotations error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Analysis error: {response.text}"
                )

    except httpx.TimeoutException:
        logger.error("⏱️ Emma analyze-with-annotations timeout")
        raise HTTPException(status_code=504, detail="Analysis timeout - document may be too large")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Emma analyze-with-annotations proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emma/analyze-with-annotations/stream")
async def emma_analyze_with_annotations_stream(
    document_id: str = Form(...),
    analysis_type: str = Form("legal"),
    file: Optional[UploadFile] = File(None),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Analyze document with streaming progress updates.

    Returns Server-Sent Events (SSE) with real-time progress as each
    agent executes. The final event contains the annotated PDF.
    """
    try:
        microservice_key = settings.microservices_api_key

        # Prepare form data
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
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{WEAVIATE_SERVICE_URL}/emma/analyze-with-annotations/stream",
                    data=form_data,
                    files=files if files else None,
                    headers={
                        "Authorization": f"Bearer {microservice_key}",
                        "Accept": "text/event-stream"
                    },
                    timeout=600.0  # 10 minutes for streaming analysis
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"❌ Emma stream analysis error: {response.status_code} - {error_text}")
                        yield f"event: error\ndata: {{\"error\": \"Service error: {response.status_code}\"}}\n\n".encode()
                        return

                    # Forward SSE events directly
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
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

    except Exception as e:
        logger.error(f"Public knowledge health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@router.get("/public-knowledge/stats")
async def public_knowledge_stats():
    """Get public knowledge base statistics"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/stats",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Stats error: {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/categories")
async def public_knowledge_categories():
    """Get available categories"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/categories",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Categories error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge categories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/jurisdictions")
async def public_knowledge_jurisdictions():
    """Get available jurisdictions"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/jurisdictions",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Jurisdictions error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge jurisdictions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/public-knowledge/search")
async def public_knowledge_search(request: Request):
    """Search public knowledge base"""
    try:
        body = await request.json()
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/search",
                json=body,
                headers={
                    "Authorization": f"Bearer {microservice_key}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Search error: {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Search timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-knowledge/documents/{doc_id}")
async def public_knowledge_get_document(doc_id: str):
    """Get a specific document from public knowledge base"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/public-knowledge/documents/{doc_id}",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Document not found")
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Get document error: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public knowledge get document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def weaviate_service_health():
    """Overall Weaviate service health including Emma AI"""
    try:
        microservice_key = settings.microservices_api_key

        async with httpx.AsyncClient() as client:
            # Check Weaviate service health
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            weaviate_health = response.json() if response.status_code == 200 else {
                "status": "unhealthy", "error": f"HTTP {response.status_code}"
            }

            # Check Emma AI health
            emma_response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/emma/health",
                headers={"Authorization": f"Bearer {microservice_key}"},
                timeout=15.0
            )

            emma_health = emma_response.json() if emma_response.status_code == 200 else {
                "status": "unhealthy", "error": f"HTTP {emma_response.status_code}"
            }

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
