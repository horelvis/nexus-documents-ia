"""
Learning Profile API endpoints for Emma AI.

Provides REST endpoints for managing user learning profiles and
recording feedback/interactions.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import logging

from app.core.security import verify_api_key as get_api_key
from app.services.memory.service import get_memory_service, MemoryService
from app.services.memory.learning_service import get_learning_service, PreferenceLearningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learning", tags=["learning"])

# Singleton services
_memory_service: Optional[MemoryService] = None
_learning_service: Optional[PreferenceLearningService] = None


async def get_memory() -> MemoryService:
    """Get or create Memory service."""
    global _memory_service
    if _memory_service is None:
        _memory_service = get_memory_service()
        await _memory_service.initialize()
    return _memory_service


async def get_learning() -> PreferenceLearningService:
    """Get or create Learning service."""
    global _learning_service
    if _learning_service is None:
        _learning_service = get_learning_service()
        await _learning_service.initialize()
    return _learning_service


# ============================================================================
# Request/Response Schemas
# ============================================================================

class LearningProfileResponse(BaseModel):
    """Response for user learning profile."""
    user_id: str
    tenant_id: str
    response_style: str = "balanced"
    expertise_level: str = "general"
    preferred_language: str = "es"
    preferred_document_types: List[str] = []
    preferred_topics: List[str] = []
    search_patterns: Dict[str, Any] = {}
    total_queries: int = 0
    total_document_views: int = 0
    ranking_weights: Dict[str, float] = {}
    frequent_document_ids: List[str] = []
    frequent_queries: List[str] = []


class UpdateProfileRequest(BaseModel):
    """Request to update learning profile preferences."""
    response_style: Optional[str] = Field(None, description="balanced, detailed, concise")
    expertise_level: Optional[str] = Field(None, description="general, technical, expert")
    preferred_language: Optional[str] = Field(None, description="es, en, etc.")


class FeedbackRequest(BaseModel):
    """Request to record user feedback."""
    session_id: str = Field(..., description="Session identifier")
    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    feedback_text: Optional[str] = Field(None, description="Optional feedback comment")


class DocumentViewRequest(BaseModel):
    """Request to record document view."""
    document_id: str = Field(..., description="Document identifier")
    dwell_time_seconds: Optional[int] = Field(None, ge=0, description="Time spent viewing")
    scroll_depth: Optional[float] = Field(None, ge=0, le=100, description="Scroll depth 0-100%")
    actions: Optional[List[str]] = Field(None, description="Actions taken: download, share, etc.")


class LearningStatsResponse(BaseModel):
    """Response for learning statistics."""
    user_id: str
    tenant_id: str
    total_queries: int
    total_document_views: int
    frequent_queries_count: int
    frequent_documents_count: int
    search_patterns: Dict[str, Any]
    ranking_weights: Dict[str, float]
    learning_enabled: bool
    profile_age_days: int


class UserContextResponse(BaseModel):
    """Response for user context (used by Emma)."""
    name: Optional[str] = None
    language: str
    preferences: Dict[str, str]
    visualization_preference: Optional[str] = None
    enable_suggestions: bool = True
    frequent_queries: List[str]
    frequent_documents: List[str]
    favorite_tools: List[str] = []
    custom_settings: Dict[str, Any] = {}
    learning_enabled: bool
    learning_applied: bool
    learning: Optional[Dict[str, Any]] = None
    ranking_weights: Dict[str, float] = {}


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/profile", response_model=LearningProfileResponse)
async def get_learning_profile(
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Get user learning profile.

    Returns the learning profile including preferences, metrics,
    and personalized ranking weights.
    """
    try:
        learning = await get_learning()
        profile = await learning.get_user_profile(user_id, tenant_id)

        return LearningProfileResponse(
            user_id=profile.user_id,
            tenant_id=profile.tenant_id,
            response_style=profile.response_style,
            expertise_level=profile.expertise_level,
            preferred_language=profile.preferred_language,
            preferred_document_types=profile.preferred_document_types,
            preferred_topics=profile.preferred_topics,
            search_patterns=profile.search_patterns,
            total_queries=profile.total_queries,
            total_document_views=profile.total_document_views,
            ranking_weights=profile.ranking_weights,
            frequent_document_ids=profile.frequent_document_ids,
            frequent_queries=profile.frequent_queries
        )

    except Exception as e:
        logger.error(f"❌ Get learning profile failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profile", response_model=LearningProfileResponse)
async def update_learning_profile(
    request: UpdateProfileRequest,
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Update user learning profile preferences.

    Updates explicit preferences (not learned ones).
    """
    try:
        learning = await get_learning()

        profile = await learning.update_preferences(
            user_id=user_id,
            tenant_id=tenant_id,
            response_style=request.response_style,
            expertise_level=request.expertise_level,
            preferred_language=request.preferred_language
        )

        return LearningProfileResponse(
            user_id=profile.user_id,
            tenant_id=profile.tenant_id,
            response_style=profile.response_style,
            expertise_level=profile.expertise_level,
            preferred_language=profile.preferred_language,
            preferred_document_types=profile.preferred_document_types,
            preferred_topics=profile.preferred_topics,
            search_patterns=profile.search_patterns,
            total_queries=profile.total_queries,
            total_document_views=profile.total_document_views,
            ranking_weights=profile.ranking_weights,
            frequent_document_ids=profile.frequent_document_ids,
            frequent_queries=profile.frequent_queries
        )

    except Exception as e:
        logger.error(f"❌ Update learning profile failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def record_feedback(
    request: FeedbackRequest,
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Record user feedback.

    Feedback is used to adjust ranking weights and improve
    personalization over time.
    """
    try:
        memory = await get_memory()

        await memory.record_feedback(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=request.session_id,
            rating=request.rating,
            feedback_text=request.feedback_text
        )

        return {
            "status": "recorded",
            "rating": request.rating,
            "message": "Feedback recorded for learning"
        }

    except Exception as e:
        logger.error(f"❌ Record feedback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/document-view")
async def record_document_view(
    request: DocumentViewRequest,
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Record document view for learning.

    Tracks document access patterns to improve relevance ranking.
    """
    try:
        memory = await get_memory()

        await memory.record_document_view(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=request.document_id,
            dwell_time_seconds=request.dwell_time_seconds,
            scroll_depth=request.scroll_depth,
            actions=request.actions
        )

        return {
            "status": "recorded",
            "document_id": request.document_id,
            "message": "Document view recorded for learning"
        }

    except Exception as e:
        logger.error(f"❌ Record document view failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=LearningStatsResponse)
async def get_learning_stats(
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Get learning statistics for a user.

    Returns metrics about learned patterns and preferences.
    """
    try:
        memory = await get_memory()
        stats = await memory.get_learning_stats(tenant_id, user_id)

        return LearningStatsResponse(
            user_id=stats.get("user_id", user_id),
            tenant_id=stats.get("tenant_id", tenant_id),
            total_queries=stats.get("total_queries", 0),
            total_document_views=stats.get("total_document_views", 0),
            frequent_queries_count=stats.get("frequent_queries_count", 0),
            frequent_documents_count=stats.get("frequent_documents_count", 0),
            search_patterns=stats.get("search_patterns", {}),
            ranking_weights=stats.get("ranking_weights", {}),
            learning_enabled=stats.get("learning_enabled", False),
            profile_age_days=stats.get("profile_age_days", 0)
        )

    except Exception as e:
        logger.error(f"❌ Get learning stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context", response_model=UserContextResponse)
async def get_user_context(
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Get full user context for Emma.

    Returns combined preferences and learning data useful
    for personalizing Emma's responses.
    """
    try:
        memory = await get_memory()
        context = await memory.get_user_context(tenant_id, user_id)

        return UserContextResponse(
            name=context.get("name"),
            language=context.get("language", "es"),
            preferences=context.get("preferences", {}),
            visualization_preference=context.get("visualization_preference"),
            enable_suggestions=context.get("enable_suggestions", True),
            frequent_queries=context.get("frequent_queries", []),
            frequent_documents=context.get("frequent_documents", []),
            favorite_tools=context.get("favorite_tools", []),
            custom_settings=context.get("custom_settings", {}),
            learning_enabled=context.get("learning_enabled", False),
            learning_applied=context.get("learning_applied", False),
            learning=context.get("learning"),
            ranking_weights=context.get("ranking_weights", {})
        )

    except Exception as e:
        logger.error(f"❌ Get user context failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ranking-weights")
async def get_ranking_weights(
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Get personalized ranking weights for RAG.

    Returns weights used to re-rank search results based
    on user preferences.
    """
    try:
        memory = await get_memory()
        weights = await memory.get_ranking_weights(tenant_id, user_id)

        return {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "weights": weights,
            "description": {
                "recency": "Weight for recently accessed documents",
                "frequency": "Weight for frequently accessed documents",
                "relevance": "Weight for semantic similarity"
            }
        }

    except Exception as e:
        logger.error(f"❌ Get ranking weights failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flush")
async def flush_learning_data(
    tenant_id: str = Query(..., description="Tenant identifier"),
    user_id: str = Query(..., description="User identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Flush pending learning data.

    Call this when a user session ends to ensure all
    pending interactions are processed.
    """
    try:
        memory = await get_memory()
        await memory.flush_learning_data(tenant_id, user_id)

        return {
            "status": "flushed",
            "message": "Pending learning data has been processed"
        }

    except Exception as e:
        logger.error(f"❌ Flush learning data failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
