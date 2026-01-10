"""
Sharing Insights API Endpoints

REST API for querying document sharing and site guest analytics.
Used by Emma AI via the weaviate-service microservice.

All endpoints require either:
- User authentication (get_current_active_user) for direct frontend calls
- Microservice API key (require_microservice_api_key) for internal service calls

Endpoints are read-only and tenant-isolated.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    require_microservice_api_key
)
from app.api.async_dependencies import get_async_db
from app.db.models import User
from app.services.sharing_insights_service import SharingInsightsService
from app.schemas.sharing_insights import (
    RecentSharesResponse,
    SharesByRecipientResponse,
    ShareStatisticsResponse,
    SiteGuestsResponse,
    GuestDocumentsResponse,
    GuestActivityResponse,
    GuestStatisticsResponse,
    SharingOverviewResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sharing-insights", tags=["Sharing Insights"])


# =============================================================================
# Helper to get service with tenant from either user or header
# =============================================================================

async def get_sharing_service(
    db: AsyncSession,
    current_user: Optional[User] = None,
    tenant_id_header: Optional[str] = None
) -> SharingInsightsService:
    """
    Create SharingInsightsService with tenant_id from user or header.

    Priority:
    1. Current user's tenant_id (for authenticated user calls)
    2. X-Tenant-ID header (for microservice calls)
    """
    if current_user and current_user.tenant_id:
        tenant_id = str(current_user.tenant_id)
    elif tenant_id_header:
        tenant_id = tenant_id_header
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required. Provide via authentication or X-Tenant-ID header."
        )

    return SharingInsightsService(db=db, tenant_id=tenant_id)


# =============================================================================
# Document Shares Endpoints
# =============================================================================

@router.get(
    "/recent-shares",
    response_model=RecentSharesResponse,
    summary="Get recent document shares",
    description="Get documents shared within the last N days"
)
async def get_recent_shares(
    days: int = Query(default=7, ge=1, le=365, description="Days to look back"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get recent document shares for the authenticated user's tenant."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_recent_shares(days=days, limit=limit)


@router.get(
    "/recent-shares/internal",
    response_model=RecentSharesResponse,
    summary="Get recent shares (internal)",
    description="Internal endpoint for microservices"
)
async def get_recent_shares_internal(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI via weaviate-service."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_recent_shares(days=days, limit=limit)


@router.get(
    "/shares-by-recipient",
    response_model=SharesByRecipientResponse,
    summary="Get shares by recipient",
    description="Get all shares sent to a specific email"
)
async def get_shares_by_recipient(
    email: str = Query(..., description="Recipient email to search"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get shares filtered by recipient email."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_shares_by_recipient(email=email, limit=limit)


@router.get(
    "/shares-by-recipient/internal",
    response_model=SharesByRecipientResponse,
    summary="Get shares by recipient (internal)",
    description="Internal endpoint for microservices"
)
async def get_shares_by_recipient_internal(
    email: str = Query(..., description="Recipient email to search"),
    limit: int = Query(default=50, ge=1, le=200),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_shares_by_recipient(email=email, limit=limit)


@router.get(
    "/share-statistics",
    response_model=ShareStatisticsResponse,
    summary="Get sharing statistics",
    description="Get aggregated sharing statistics"
)
async def get_share_statistics(
    days: int = Query(default=30, ge=1, le=365, description="Period to analyze"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get aggregated sharing statistics."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_share_statistics(days=days)


@router.get(
    "/share-statistics/internal",
    response_model=ShareStatisticsResponse,
    summary="Get sharing statistics (internal)",
    description="Internal endpoint for microservices"
)
async def get_share_statistics_internal(
    days: int = Query(default=30, ge=1, le=365),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_share_statistics(days=days)


# =============================================================================
# Site Guests Endpoints
# =============================================================================

@router.get(
    "/site-guests",
    response_model=SiteGuestsResponse,
    summary="Get site guests",
    description="Get list of site guests for the tenant"
)
async def get_site_guests(
    active_only: bool = Query(default=False, description="Only return active guests"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get site guests list."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_site_guests(active_only=active_only, limit=limit)


@router.get(
    "/site-guests/internal",
    response_model=SiteGuestsResponse,
    summary="Get site guests (internal)",
    description="Internal endpoint for microservices"
)
async def get_site_guests_internal(
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_site_guests(active_only=active_only, limit=limit)


@router.get(
    "/guest-documents",
    response_model=GuestDocumentsResponse,
    summary="Get guest documents",
    description="Get documents accessible by a specific guest"
)
async def get_guest_documents(
    email: str = Query(..., description="Guest email"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get documents accessible by a guest."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_guest_documents(email=email)


@router.get(
    "/guest-documents/internal",
    response_model=GuestDocumentsResponse,
    summary="Get guest documents (internal)",
    description="Internal endpoint for microservices"
)
async def get_guest_documents_internal(
    email: str = Query(..., description="Guest email"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_guest_documents(email=email)


@router.get(
    "/guest-activity",
    response_model=GuestActivityResponse,
    summary="Get guest activity",
    description="Get activity logs for a specific guest"
)
async def get_guest_activity(
    email: str = Query(..., description="Guest email"),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get guest activity logs."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_guest_activity(email=email, days=days, limit=limit)


@router.get(
    "/guest-activity/internal",
    response_model=GuestActivityResponse,
    summary="Get guest activity (internal)",
    description="Internal endpoint for microservices"
)
async def get_guest_activity_internal(
    email: str = Query(..., description="Guest email"),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_guest_activity(email=email, days=days, limit=limit)


@router.get(
    "/guest-statistics",
    response_model=GuestStatisticsResponse,
    summary="Get guest statistics",
    description="Get aggregated site guest statistics"
)
async def get_guest_statistics(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get guest statistics."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_guest_statistics()


@router.get(
    "/guest-statistics/internal",
    response_model=GuestStatisticsResponse,
    summary="Get guest statistics (internal)",
    description="Internal endpoint for microservices"
)
async def get_guest_statistics_internal(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_guest_statistics()


# =============================================================================
# Overview Endpoint
# =============================================================================

@router.get(
    "/overview",
    response_model=SharingOverviewResponse,
    summary="Get sharing overview",
    description="Get high-level overview of all sharing activity"
)
async def get_sharing_overview(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get sharing overview."""
    service = await get_sharing_service(db, current_user=current_user)
    return await service.get_sharing_overview()


@router.get(
    "/overview/internal",
    response_model=SharingOverviewResponse,
    summary="Get sharing overview (internal)",
    description="Internal endpoint for microservices"
)
async def get_sharing_overview_internal(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(require_microservice_api_key)
):
    """Internal endpoint for Emma AI."""
    service = await get_sharing_service(db, tenant_id_header=x_tenant_id)
    return await service.get_sharing_overview()
