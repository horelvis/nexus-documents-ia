# microservices/langchain-service/app/api/recommendations.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import logging
from app.services.document_recommender import DocumentRecommender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

class RecommendationResponse(BaseModel):
    document_id: str
    title: str
    filename: str
    score: float
    reason: str

class RecommendationsRequest(BaseModel):
    user_id: str
    tenant_id: str
    limit: Optional[int] = 5
    database_url: Optional[str] = None

@router.post("/documents", response_model=List[RecommendationResponse])
async def get_document_recommendations(request: RecommendationsRequest):
    """
    Obtiene recomendaciones de documentos para un usuario basado en usuarios similares
    """
    try:
        logger.info(f"🎯 Getting recommendations for user {request.user_id} in tenant {request.tenant_id}")
        
        # Crear instancia del recomendador
        recommender = DocumentRecommender(
            tenant_id=request.tenant_id,
            db_url=request.database_url
        )
        
        # Obtener recomendaciones
        recommendations = recommender.recommend_documents(
            user_id=request.user_id,
            n=request.limit
        )
        
        logger.info(f"✅ Found {len(recommendations)} recommendations")
        
        # Convertir a formato de respuesta
        return [
            RecommendationResponse(
                document_id=str(rec["document_id"]),
                title=rec["title"],
                filename=rec["filename"],
                score=rec["score"],
                reason=rec["reason"]
            )
            for rec in recommendations
        ]
        
    except Exception as e:
        logger.error(f"❌ Error getting recommendations: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendations: {str(e)}"
        )

@router.get("/similar-users/{user_id}")
async def get_similar_users(
    user_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(5, ge=1, le=20),
    database_url: Optional[str] = Query(None)
):
    """
    Obtiene usuarios similares basado en patrones de visualización
    """
    try:
        logger.info(f"👥 Getting similar users for {user_id} in tenant {tenant_id}")
        
        recommender = DocumentRecommender(
            tenant_id=tenant_id,
            db_url=database_url
        )
        
        similar_users = recommender.get_similar_users(user_id, n=limit)
        
        return {
            "user_id": user_id,
            "similar_users": [
                {"user_id": str(user), "similarity_score": score}
                for user, score in similar_users
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting similar users: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error finding similar users: {str(e)}"
        )