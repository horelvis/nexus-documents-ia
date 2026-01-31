"""
API endpoints for Verified Document Generation.

Provides REST endpoints for the "Agent Self-Verifies" pattern:
- POST /verified/generate - Synchronous document generation
- POST /verified/generate/stream - SSE streaming with real-time progress
- GET /verified/session/{session_id}/claims - Get claims for a session
- DELETE /verified/session/{session_id} - Clear session cache

All endpoints require authentication via X-API-Key header.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.core.security import verify_api_key
from app.schemas.verified_generation import (
    SessionClaimsResponse,
    VerificationSessionStatus,
    VerifiedDocumentRequest,
    VerifiedDocumentResponse,
)
from app.services.verified_generation import (
    get_verified_cache,
    get_verified_document_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verified", tags=["verified-generation"])


@router.post(
    "/generate",
    response_model=VerifiedDocumentResponse,
    summary="Generate a verified document",
    description="""
    Generate a document where each claim is verified against Weaviate before acceptance.

    This is the synchronous endpoint that waits for the complete document.
    For real-time progress updates, use the `/generate/stream` endpoint.

    The process:
    1. Writer generates ONE claim at a time
    2. Each claim is verified against source documents in Weaviate
    3. Only verified claims are included in the final document
    4. Rejected claims are logged and skipped
    5. Corrected claims can be auto-accepted

    **Verification reduces hallucinations by ~70%** compared to standard generation.
    """,
)
async def generate_verified_document(
    request: VerifiedDocumentRequest,
    _: None = Depends(verify_api_key),
) -> VerifiedDocumentResponse:
    """
    Generate a verified document (synchronous).

    Returns the complete document after all claims have been generated
    and verified.
    """
    logger.info(
        f"📝 Verified document request: tenant={request.tenant_id}, "
        f"max_claims={request.max_claims}, query={request.query[:50]}..."
    )

    try:
        service = get_verified_document_service()
        response = await service.generate_verified_document_sync(request)

        logger.info(
            f"✅ Verified document complete: "
            f"verified={response.claims_verified}, "
            f"corrected={response.claims_corrected}, "
            f"rejected={response.claims_rejected}, "
            f"time={response.execution_time_ms}ms"
        )

        return response

    except Exception as e:
        logger.error(f"❌ Verified document generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Document generation failed: {str(e)}"
        )


@router.post(
    "/generate/stream",
    summary="Generate a verified document with streaming",
    description="""
    Generate a verified document with Server-Sent Events (SSE) for real-time progress.

    Connect with an SSE client to receive events as the document is generated.
    Events include:
    - `claim_generated`: A new claim was generated
    - `verification_started`: Claim is being verified
    - `claim_verified`: Claim passed verification
    - `claim_corrected`: Claim was corrected and accepted
    - `claim_rejected`: Claim was rejected
    - `document_complete`: Final document is ready
    - `error`: An error occurred

    Example usage with curl:
    ```bash
    curl -N -X POST http://localhost:8009/verified/generate/stream \\
      -H "Content-Type: application/json" \\
      -H "X-API-Key: your-api-key" \\
      -d '{"query": "Resume el contrato", "tenant_id": "tenant-123"}'
    ```
    """,
)
async def generate_verified_document_stream(
    request: VerifiedDocumentRequest,
    _: None = Depends(verify_api_key),
) -> StreamingResponse:
    """
    Generate a verified document with SSE streaming.

    Returns a streaming response with progress events.
    """
    logger.info(
        f"📝 Verified document stream request: tenant={request.tenant_id}, "
        f"max_claims={request.max_claims}"
    )

    async def event_generator():
        """Generate SSE events."""
        try:
            service = get_verified_document_service()

            async for event in service.generate_verified_document(request):
                yield event.to_sse()

        except Exception as e:
            logger.error(f"❌ Stream error: {e}")
            # Send error event
            import json
            error_data = json.dumps({
                "event_type": "error",
                "data": {"error": str(e)},
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@router.post(
    "/generate/pdf",
    summary="Generate a verified document as PDF",
    description="Generate and verify a document, then return it as a downloadable PDF report.",
)
async def generate_verified_document_pdf(
    request: VerifiedDocumentRequest,
    _: None = Depends(verify_api_key),
) -> Response:
    """Generate a verified document and return as PDF."""
    logger.info(f"📄 PDF generation request: tenant={request.tenant_id}, query={request.query[:50]}...")

    try:
        service = get_verified_document_service()
        response = await service.generate_verified_document_sync(request)

        from app.services.pdf_renderer import get_pdf_renderer
        renderer = get_pdf_renderer()
        pdf_bytes = renderer.render_verified_report({
            "query": response.query,
            "session_id": response.session_id,
            "created_at": response.created_at.strftime("%Y-%m-%d %H:%M"),
            "document_text": response.document_text,
            "claims": [c.model_dump() for c in response.claims],
            "claims_verified": response.claims_verified,
            "claims_corrected": response.claims_corrected,
            "claims_rejected": response.claims_rejected,
            "average_confidence": response.average_confidence,
            "execution_time_ms": response.execution_time_ms,
        })

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="verified_report_{response.session_id[:8]}.pdf"'
            },
        )

    except Exception as e:
        logger.error(f"❌ PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.get(
    "/session/{session_id}/pdf",
    summary="Export existing session as PDF",
    description="Export a previously generated verification session as a downloadable PDF.",
)
async def export_session_pdf(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> Response:
    """Export an existing verification session as PDF without re-generating."""
    logger.info(f"📄 PDF export request: session={session_id[:16]}...")

    try:
        cache = get_verified_cache()
        await cache.connect()

        claims = await cache.get_verified_claims(tenant_id, session_id)
        stats = await cache.get_session_stats(tenant_id, session_id)
        meta = await cache.get_session_metadata(tenant_id, session_id)

        if not claims:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        # Build document text from accepted claims
        document_text = "\n\n".join(
            c.text for c in claims
            if c.status.value in ("verified", "corrected")
        )

        from app.services.pdf_renderer import get_pdf_renderer
        renderer = get_pdf_renderer()
        pdf_bytes = renderer.render_verified_report({
            "query": meta.get("query", "N/A"),
            "session_id": session_id,
            "created_at": meta.get("created_at", "N/A"),
            "document_text": document_text,
            "claims": [
                {
                    "text": c.text,
                    "confidence": c.confidence,
                    "status": c.status.value,
                    "evidence_document_ids": c.evidence_document_ids,
                }
                for c in claims
            ],
            "claims_verified": stats.get("verified_count", 0),
            "claims_corrected": stats.get("corrected_count", 0),
            "claims_rejected": stats.get("rejected_count", 0),
            "average_confidence": stats.get("average_confidence", 0.0),
            "execution_time_ms": meta.get("execution_time_ms", 0),
            "sources": meta.get("sources", []),
        })

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="verified_report_{session_id[:8]}.pdf"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ PDF export failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")


@router.get(
    "/session/{session_id}/claims",
    response_model=SessionClaimsResponse,
    summary="Get verified claims for a session",
    description="""
    Retrieve all verified claims stored for a generation session.

    Claims are cached in Redis with automatic expiration (default 1 hour).
    This endpoint is useful for:
    - Resuming interrupted generations
    - Reviewing generated claims
    - Building UI progress indicators
    """,
)
async def get_session_claims(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> SessionClaimsResponse:
    """
    Get verified claims for a session.
    """
    logger.info(f"📖 Getting claims for session: {session_id[:16]}...")

    try:
        cache = get_verified_cache()
        await cache.connect()

        claims = await cache.get_verified_claims(tenant_id, session_id)
        ttl = await cache.get_ttl_remaining(tenant_id, session_id)

        return SessionClaimsResponse(
            session_id=session_id,
            tenant_id=tenant_id,
            claims=claims,
            total_claims=len(claims),
            cache_ttl_remaining_seconds=ttl,
        )

    except Exception as e:
        logger.error(f"❌ Failed to get session claims: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get claims: {str(e)}"
        )


@router.get(
    "/session/{session_id}/stats",
    response_model=dict,
    summary="Get session statistics",
    description="Get statistics for a verification session.",
)
async def get_session_stats(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> dict:
    """
    Get statistics for a verification session.
    """
    try:
        cache = get_verified_cache()
        await cache.connect()

        stats = await cache.get_session_stats(tenant_id, session_id)
        return stats

    except Exception as e:
        logger.error(f"❌ Failed to get session stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.delete(
    "/session/{session_id}",
    summary="Clear session cache",
    description="""
    Clear all cached claims for a session.

    Use this to:
    - Cancel an in-progress generation
    - Clear stale data
    - Start fresh
    """,
)
async def clear_session(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> dict:
    """
    Clear a verification session.
    """
    logger.info(f"🗑️ Clearing session: {session_id[:16]}...")

    try:
        cache = get_verified_cache()
        await cache.connect()

        success = await cache.clear_session(tenant_id, session_id)

        return {
            "success": success,
            "session_id": session_id,
            "message": "Session cleared" if success else "Failed to clear session",
        }

    except Exception as e:
        logger.error(f"❌ Failed to clear session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear session: {str(e)}"
        )


@router.get(
    "/health",
    summary="Health check",
    description="Check if the verified generation service is healthy.",
)
async def health_check() -> dict:
    """
    Health check for verified generation service.
    """
    try:
        # Check Redis connection
        cache = get_verified_cache()
        await cache.connect()

        return {
            "status": "healthy",
            "service": "verified-generation",
            "redis": "connected",
        }

    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "verified-generation",
            "error": str(e),
        }
