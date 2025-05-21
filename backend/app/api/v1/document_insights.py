# app/api/endpoints/document_insights.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from app.api.deps import get_current_user
from app.schemas.document import DocumentWithMetrics, DocumentBasic
from app.services.document_insights_service import DocumentInsightsService

router = APIRouter()

@router.get("/trending", response_model=List[DocumentWithMetrics])
def get_trending_documents(
    limit: int = Query(10, ge=1, le=50),
    time_period_days: int = Query(30, ge=1, le=365),
    current_user = Depends(get_current_user)
):
    """Obtiene los documentos más populares/tendencia en el tenant"""
    insights_service = DocumentInsightsService(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id)
    )
    
    return insights_service.get_trending_documents(
        limit=limit,
        time_period_days=time_period_days
    )

@router.get("/recently-viewed", response_model=List[DocumentBasic])
def get_recently_viewed_documents(
    limit: int = Query(10, ge=1, le=50),
    user_specific: bool = Query(True),
    current_user = Depends(get_current_user)
):
    """Obtiene los documentos vistos recientemente por el usuario o en el tenant"""
    insights_service = DocumentInsightsService(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id)
    )
    
    return insights_service.get_recently_viewed_documents(
        limit=limit,
        user_specific=user_specific
    )

@router.get("/recommendations", response_model=List[DocumentBasic])
def get_document_recommendations(
    limit: int = Query(5, ge=1, le=20),
    current_user = Depends(get_current_user)
):
    """Obtiene recomendaciones de documentos para el usuario"""
    insights_service = DocumentInsightsService(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id)
    )
    
    return insights_service.get_document_recommendations(limit=limit)