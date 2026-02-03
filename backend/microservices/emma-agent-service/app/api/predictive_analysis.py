"""
API endpoints for Predictive Analysis.

Provides REST endpoints for sector-agnostic predictive analysis:
- POST /predictive/analyze/stream — SSE streaming with real-time progress
- POST /predictive/analyze — Synchronous analysis
- GET  /predictive/analysis/{session_id} — Cached result
- GET  /predictive/analysis/{session_id}/pdf — Export as PDF
- DELETE /predictive/analysis/{session_id} — Clear session

All endpoints require authentication via X-API-Key header.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.core.security import verify_api_key
from app.schemas.predictive_analysis import (
    PredictionRequest,
    PredictionResponse,
    PredictionSessionResponse,
)
from app.services.predictive_analysis import (
    get_predictive_analysis_service,
    get_predictive_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictive", tags=["predictive-analysis"])


@router.post(
    "/analyze/stream",
    summary="Run predictive analysis with SSE streaming",
    description="""
    Run predictive analysis with Server-Sent Events for real-time progress.

    Events include:
    - `factor_extracted`: A new factor was identified
    - `factor_verification_started`: Searching for evidence
    - `factor_weighted`: Factor was weighted with evidence
    - `factor_rejected`: Factor rejected (insufficient evidence)
    - `synthesis_started`: Aggregating prediction
    - `prediction_complete`: Final result ready
    - `error`: An error occurred

    Example:
    ```bash
    curl -N -X POST http://localhost:8009/predictive/analyze/stream \\
      -H "Content-Type: application/json" \\
      -H "X-API-Key: your-api-key" \\
      -d '{"case_description": "Analiza el caso...", "tenant_id": "tenant-123"}'
    ```
    """,
)
async def analyze_stream(
    request: PredictionRequest,
    _: None = Depends(verify_api_key),
) -> StreamingResponse:
    """Run predictive analysis with SSE streaming."""
    logger.info(
        f"📊 Predictive analysis stream: tenant={request.tenant_id}, "
        f"max_factors={request.max_factors}, sector_override={request.sector_override}"
    )

    async def event_generator():
        try:
            service = get_predictive_analysis_service()
            async for event in service.analyze(request):
                yield event.to_sse()
        except Exception as e:
            logger.error(f"❌ Predictive stream error: {e}")
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
    "/analyze",
    response_model=PredictionResponse,
    summary="Run predictive analysis (synchronous)",
)
async def analyze_sync(
    request: PredictionRequest,
    _: None = Depends(verify_api_key),
) -> PredictionResponse:
    """Run predictive analysis and wait for complete result."""
    logger.info(f"📊 Predictive analysis sync: tenant={request.tenant_id}")

    try:
        service = get_predictive_analysis_service()
        return await service.analyze_sync(request)
    except Exception as e:
        logger.error(f"❌ Predictive analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get(
    "/analysis/{session_id}",
    response_model=PredictionSessionResponse,
    summary="Get cached prediction result",
)
async def get_analysis(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> PredictionSessionResponse:
    """Get a previously computed prediction from cache."""
    try:
        cache = get_predictive_cache()
        await cache.connect()

        result = await cache.get_result(tenant_id, session_id)
        factors = await cache.get_weighted_factors(tenant_id, session_id)
        ttl = await cache.get_ttl_remaining(tenant_id, session_id)

        return PredictionSessionResponse(
            session_id=session_id,
            tenant_id=tenant_id,
            result=result,
            factors=factors,
            total_factors=len(factors),
            cache_ttl_remaining_seconds=ttl,
        )
    except Exception as e:
        logger.error(f"❌ Failed to get analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analysis/{session_id}/pdf",
    summary="Export prediction as PDF",
)
async def export_analysis_pdf(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> Response:
    """Export a prediction analysis as a downloadable PDF report."""
    logger.info(f"📄 Predictive PDF export: session={session_id[:16]}...")

    try:
        cache = get_predictive_cache()
        await cache.connect()

        result = await cache.get_result(tenant_id, session_id)
        if not result:
            raise HTTPException(status_code=404, detail="Analysis not found or expired")

        meta = await cache.get_session_metadata(tenant_id, session_id)

        from app.services.pdf_renderer import get_pdf_renderer
        renderer = get_pdf_renderer()

        # Build PDF data using the predictive report template
        pdf_data = {
            "case_description": meta.get("case_description", "N/A"),
            "session_id": session_id,
            "created_at": meta.get("created_at", "N/A"),
            "probability": result.probability,
            "primary_outcome": result.primary_outcome,
            "confidence_interval": result.confidence_interval,
            "outcome_probabilities": result.outcome_probabilities,
            "factors": [f.to_dict() for f in result.factors],
            "recommendation": result.recommendation,
            "disclaimer": result.disclaimer,
            "execution_time_ms": result.execution_time_ms,
        }

        # Try predictive-specific template, fall back to verified report
        try:
            pdf_bytes = renderer.render_predictive_report(pdf_data)
        except AttributeError:
            # Fallback: render as verified report format
            pdf_bytes = renderer.render_verified_report({
                "query": meta.get("case_description", "Análisis Predictivo"),
                "session_id": session_id,
                "created_at": meta.get("created_at", "N/A"),
                "document_text": (
                    f"**Predicción:** {result.primary_outcome} ({result.probability:.0%})\n\n"
                    f"**Recomendación:** {result.recommendation}\n\n"
                    f"**Factores analizados:** {len(result.factors)}\n\n"
                    f"**Disclaimer:** {result.disclaimer}"
                ),
                "claims": [
                    {
                        "text": f"[{f.factor_type}] {f.description}",
                        "confidence": f.confidence,
                        "status": "verified",
                    }
                    for f in result.factors
                ],
                "claims_verified": len(result.factors),
                "claims_corrected": 0,
                "claims_rejected": 0,
                "average_confidence": (
                    sum(f.confidence for f in result.factors) / len(result.factors)
                    if result.factors else 0
                ),
                "execution_time_ms": result.execution_time_ms,
            })

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="predictive_report_{session_id[:8]}.pdf"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Predictive PDF export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analysis/{session_id}/docx",
    summary="Export prediction as DOCX",
)
async def export_analysis_docx(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> Response:
    """Export a prediction analysis as a downloadable Word document."""
    logger.info(f"📄 Predictive DOCX export: session={session_id[:16]}...")

    try:
        cache = get_predictive_cache()
        await cache.connect()

        result = await cache.get_result(tenant_id, session_id)
        if not result:
            raise HTTPException(status_code=404, detail="Analysis not found or expired")

        meta = await cache.get_session_metadata(tenant_id, session_id)

        from app.services.docx_renderer import get_docx_renderer
        renderer = get_docx_renderer()

        # Build DOCX data using predictive report format
        # WeightedFactor uses 'outcome' (favorable/unfavorable) and 'weight' (0-1)
        # All factors in result.factors are weighted (verified), rejected ones are not stored
        docx_data = {
            "query": meta.get("case_description", "Análisis Predictivo"),
            "session_id": session_id,
            "created_at": meta.get("created_at", "N/A"),
            "document_text": (
                f"**Predicción:** {result.primary_outcome} ({result.probability:.0%})\n\n"
                f"**Recomendación:** {result.recommendation}\n\n"
                f"**Factores analizados:** {len(result.factors)}\n\n"
                f"**Disclaimer:** {result.disclaimer}"
            ),
            "claims": [
                {
                    "text": f"[{f.factor_type}] {f.description} → {f.outcome}",
                    "confidence": f.confidence,
                    "status": "verified",  # All weighted factors are verified
                }
                for f in result.factors
            ],
            "claims_verified": len(result.factors),
            "claims_corrected": 0,
            "claims_rejected": 0,
            "average_confidence": (
                sum(f.confidence for f in result.factors if f.confidence) / len(result.factors)
                if result.factors else 0
            ),
            "execution_time_ms": result.execution_time_ms,
            "sources": [],
        }

        docx_bytes = renderer.render_verified_report(docx_data)

        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="informe_predictivo_{session_id[:8]}.docx"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Predictive DOCX export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/analysis/{session_id}",
    summary="Clear analysis session",
)
async def clear_analysis(
    session_id: str,
    tenant_id: str,
    _: None = Depends(verify_api_key),
) -> dict:
    """Clear a predictive analysis session."""
    try:
        cache = get_predictive_cache()
        await cache.connect()
        success = await cache.clear_session(tenant_id, session_id)
        return {
            "success": success,
            "session_id": session_id,
            "message": "Session cleared" if success else "Failed to clear",
        }
    except Exception as e:
        logger.error(f"❌ Failed to clear session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", summary="Health check")
async def health_check() -> dict:
    try:
        cache = get_predictive_cache()
        await cache.connect()
        return {
            "status": "healthy",
            "service": "predictive-analysis",
            "redis": "connected",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "predictive-analysis",
            "error": str(e),
        }
