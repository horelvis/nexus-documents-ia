"""Background execution API for Emma Reactive.

These endpoints are called by Celery tasks (via HTTP) to execute
LangGraph pipelines without a user-facing request.
Internal use only — secured by MICROSERVICES_API_KEY.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.emma_background_service import emma_background_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class AnalyzeDocumentRequest(BaseModel):
    document_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    prompt_template: Optional[str] = None
    agent: Optional[str] = None


class DailySummaryRequest(BaseModel):
    collections: Optional[List[str]] = None


class ProactiveAnalysisRequest(BaseModel):
    analysis_type: str
    query: str
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/background/analyze_document")
async def analyze_document(
    request: AnalyzeDocumentRequest,
    x_api_key: str = Header(None),
):
    """Analyze a document in background (called by Celery tasks)."""
    _verify_api_key(x_api_key)
    return await emma_background_service.analyze_document(
        document_id=request.document_id,
        prompt_template=request.prompt_template,
        agent=request.agent,
        metadata=request.metadata,
    )


@router.post("/background/daily_summary")
async def daily_summary(
    request: DailySummaryRequest,
    x_api_key: str = Header(None),
):
    """Generate daily summary (called by Celery Beat)."""
    _verify_api_key(x_api_key)
    return await emma_background_service.generate_daily_summary(
        collections=request.collections,
    )


@router.post("/background/proactive_analysis")
async def proactive_analysis(
    request: ProactiveAnalysisRequest,
    x_api_key: str = Header(None),
):
    """Run proactive analysis (called by trigger engine)."""
    _verify_api_key(x_api_key)
    return await emma_background_service.proactive_analysis(
        analysis_type=request.analysis_type,
        query=request.query,
        context=request.context,
    )
