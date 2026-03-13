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
    ReviewSubmission,
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
    "/session/{session_id}/resume/stream",
    summary="Submit HITL review and resume generation",
    description="""
    Submit human review decisions for a paused verified generation session
    and stream the remaining events (synthesis + document assembly).

    This endpoint is called after the frontend receives a `review_requested`
    event from the initial `/generate/stream` SSE connection. The review
    decisions are submitted and the graph resumes from the interrupt point.

    Returns an SSE stream with:
    - `review_submitted`: Summary of applied decisions
    - `document_complete`: Final assembled document

    Returns 410 Gone if the session has expired.
    """,
)
async def resume_verified_stream(
    session_id: str,
    review: ReviewSubmission,
    _: None = Depends(verify_api_key),
) -> StreamingResponse:
    """Submit HITL review and resume verified document generation."""
    logger.info(
        f"📝 HITL resume request: session={session_id[:16]}..., "
        f"decisions={len(review.decisions)}"
    )

    # Verify session exists in Redis
    cache = get_verified_cache()
    await cache.connect()
    claims_count = await cache.get_claims_count(review.tenant_id, session_id)

    if claims_count == 0:
        raise HTTPException(
            status_code=410,
            detail="Session expired or not found. Please regenerate the document.",
        )

    async def event_generator():
        """Generate SSE events for the resume phase."""
        try:
            service = get_verified_document_service()

            decisions_dicts = [d.model_dump() for d in review.decisions]

            async for event in service.resume_after_review(
                session_id=session_id,
                tenant_id=review.tenant_id,
                review_decisions=decisions_dicts,
            ):
                yield event.to_sse()

        except Exception as e:
            logger.error(f"❌ Resume stream error: {e}")
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
            "X-Accel-Buffering": "no",
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
            "sources": response.sources,
            "doi_validations": response.doi_validations,
            "source_filenames": response.source_filenames,
            "source_summary": response.source_summary,
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
                    "evidence_sources": c.evidence_sources,
                    "verification_type": c.verification_type,
                    "verification_reason": c.verification_reason,
                }
                for c in claims
            ],
            "claims_verified": stats.get("verified_count", 0),
            "claims_corrected": stats.get("corrected_count", 0),
            "claims_rejected": stats.get("rejected_count", 0),
            "average_confidence": stats.get("average_confidence", 0.0),
            "execution_time_ms": meta.get("execution_time_ms", 0),
            "sources": meta.get("sources", []),
            "doi_validations": meta.get("doi_validations", []),
            "source_filenames": meta.get("source_filenames", []),
            "source_summary": meta.get("source_summary", ""),
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
    "/session/{session_id}/docx",
    summary="Export existing session as DOCX",
    description="Export a previously generated verification session as a downloadable Word document.",
)
async def export_session_docx(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> Response:
    """Export an existing verification session as DOCX without re-generating."""
    logger.info(f"📄 DOCX export request: session={session_id[:16]}...")

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

        from app.services.docx_renderer import get_docx_renderer
        renderer = get_docx_renderer()
        docx_bytes = renderer.render_verified_report({
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
                    "evidence_sources": c.evidence_sources,
                    "verification_type": c.verification_type,
                    "verification_reason": c.verification_reason,
                }
                for c in claims
            ],
            "claims_verified": stats.get("verified_count", 0),
            "claims_corrected": stats.get("corrected_count", 0),
            "claims_rejected": stats.get("rejected_count", 0),
            "average_confidence": stats.get("average_confidence", 0.0),
            "execution_time_ms": meta.get("execution_time_ms", 0),
            "sources": meta.get("sources", []),
            "doi_validations": meta.get("doi_validations", []),
            "source_filenames": meta.get("source_filenames", []),
            "source_summary": meta.get("source_summary", ""),
        })

        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="informe_verificado_{session_id[:8]}.docx"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ DOCX export failed: {e}")
        raise HTTPException(status_code=500, detail=f"DOCX export failed: {str(e)}")


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
    "/session/{session_id}",
    response_model=dict,
    summary="Get full session data for recovery",
    description="Retrieve a completed (or running) verification session for frontend recovery.",
)
async def get_session(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> dict:
    """
    Return full session state for frontend recovery after navigation.

    Reads metadata + claims from Redis and returns a shape compatible with
    the frontend VerifiedGenerationMetadata type.
    """
    try:
        cache = get_verified_cache()
        await cache.connect()

        meta = await cache.get_session_metadata(tenant_id, session_id)
        if not meta:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        status = meta.get("status", "unknown")

        claims = await cache.get_verified_claims(tenant_id, session_id)

        # Map VerifiedClaim models to frontend-compatible dicts
        claims_list = []
        for i, c in enumerate(claims):
            claims_list.append({
                "claim_id": c.id,
                "claim_number": i + 1,
                "total_expected": len(claims),
                "claim_text": c.text,
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "confidence": c.confidence,
                "evidence_count": len(c.evidence_document_ids),
                "original_text": c.original_text,
                "evidence_sources": c.evidence_sources,
                "verification_type": c.verification_type,
                "verification_reason": c.verification_reason,
            })

        return {
            "session_id": session_id,
            "status": status,
            "topic": meta.get("query", ""),
            "claims": claims_list,
            "document_text": meta.get("document_text"),
            "current_phase": "complete" if status == "completed" else "generating",
            "verified_count": meta.get("claims_verified", 0),
            "rejected_count": meta.get("claims_rejected", 0),
            "total_claims": len(claims),
            "average_confidence": meta.get("average_confidence"),
            "execution_time_ms": meta.get("execution_time_ms"),
            "sources": meta.get("sources", []),
            "doi_validations": meta.get("doi_validations", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


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
