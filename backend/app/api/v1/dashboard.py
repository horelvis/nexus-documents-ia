"""
Dashboard API endpoints for aggregated statistics and analytics
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case
from uuid import UUID

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.async_database import get_async_db
from app.db.models import User, Document, DocumentView, DocumentShare
from app.schemas.dashboard import (
    DashboardStats, 
    DocumentTrend, 
    ActivityLog, 
    RecentActivityResponse,
    AnalyticsTrends,
    AIInsight,
    AIInsightsResponse
)

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get aggregated dashboard statistics for the current tenant
    """
    tenant_uuid = UUID(tenant_id)
    
    # Get document statistics
    doc_stats = await db.execute(
        select(
            func.count(Document.id).label('total'),
            func.sum(case((Document.processing_status == 'completed', 1), else_=0)).label('processed'),
            func.sum(case((Document.processing_status == 'processing', 1), else_=0)).label('processing'),
            func.sum(case((Document.processing_status == 'error', 1), else_=0)).label('error'),
            func.sum(Document.file_size).label('total_size')
        ).where(Document.tenant_id == tenant_uuid)
    )
    doc_result = doc_stats.one()
    
    # Get active users (users who accessed documents in last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    active_users_query = await db.execute(
        select(func.count(func.distinct(DocumentView.viewer_id)))
        .where(
            and_(
                DocumentView.viewed_at >= thirty_days_ago,
                DocumentView.tenant_id == tenant_uuid
            )
        )
    )
    active_users = active_users_query.scalar() or 0
    
    # Get recent uploads (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_uploads_query = await db.execute(
        select(func.count(Document.id))
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.created_at >= seven_days_ago
            )
        )
    )
    recent_uploads = recent_uploads_query.scalar() or 0
    
    # Calculate trends (compare with previous period)
    # Documents trend
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    prev_period_docs = await db.execute(
        select(func.count(Document.id))
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.created_at >= fourteen_days_ago,
                Document.created_at < seven_days_ago
            )
        )
    )
    prev_docs_count = prev_period_docs.scalar() or 0
    current_docs_count = recent_uploads
    
    docs_trend = 0.0
    if prev_docs_count > 0:
        docs_trend = ((current_docs_count - prev_docs_count) / prev_docs_count) * 100
    elif current_docs_count > 0:
        docs_trend = 100.0
    
    # Storage trend (compare total size growth)
    storage_week_ago = await db.execute(
        select(func.sum(Document.file_size))
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.created_at < seven_days_ago
            )
        )
    )
    prev_storage = storage_week_ago.scalar() or 0
    current_storage = doc_result.total_size or 0
    
    storage_trend = 0.0
    if prev_storage > 0:
        storage_trend = ((current_storage - prev_storage) / prev_storage) * 100
    
    # Active users trend
    sixty_days_ago = datetime.utcnow() - timedelta(days=60)
    prev_active_users = await db.execute(
        select(func.count(func.distinct(DocumentView.viewer_id)))
        .where(
            and_(
                DocumentView.viewed_at >= sixty_days_ago,
                DocumentView.viewed_at < thirty_days_ago,
                DocumentView.tenant_id == tenant_uuid
            )
        )
    )
    prev_users_count = prev_active_users.scalar() or 0
    
    users_trend = 0.0
    if prev_users_count > 0:
        users_trend = ((active_users - prev_users_count) / prev_users_count) * 100
    elif active_users > 0:
        users_trend = 100.0
    
    # Processing success rate trend
    processed_trend = 0.0
    if doc_result.total > 0:
        success_rate = (doc_result.processed / doc_result.total) * 100
        processed_trend = success_rate - 90.0  # Assuming 90% is baseline
    
    return DashboardStats(
        total_documents=doc_result.total or 0,
        processed_documents=doc_result.processed or 0,
        processing_documents=doc_result.processing or 0,
        error_documents=doc_result.error or 0,
        total_storage_bytes=doc_result.total_size or 0,
        active_users=active_users,
        recent_uploads=recent_uploads,
        trends={
            "documents": round(docs_trend, 1),
            "storage": round(storage_trend, 1),
            "active_users": round(users_trend, 1),
            "processed": round(processed_trend, 1),
            "recent_uploads": round(docs_trend, 1),  # Same as documents trend
            "error_rate": round(-processed_trend if processed_trend < 0 else 0, 1)
        }
    )


@router.get("/activity/recent", response_model=RecentActivityResponse)
async def get_recent_activity(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get recent activity logs for the tenant
    """
    tenant_uuid = UUID(tenant_id)
    activities: List[ActivityLog] = []
    
    # Get recent document uploads
    recent_docs = await db.execute(
        select(Document, User)
        .join(User, Document.created_by == User.id)
        .where(Document.tenant_id == tenant_uuid)
        .order_by(Document.created_at.desc())
        .limit(limit // 3)
    )
    
    for doc, user in recent_docs:
        activities.append(ActivityLog(
            id=str(doc.id),
            type="document_upload",
            title=f"New document uploaded",
            description=doc.filename,
            user_name=user.full_name or user.email,
            user_email=user.email,
            timestamp=doc.created_at,
            metadata={
                "document_id": str(doc.id),
                "filename": doc.filename,
                "file_size": doc.file_size
            }
        ))
    
    # Get recent document views
    recent_views = await db.execute(
        select(DocumentView, Document, User)
        .join(Document, DocumentView.document_id == Document.id)
        .join(User, DocumentView.viewer_id == User.id)
        .where(DocumentView.tenant_id == tenant_uuid)
        .order_by(DocumentView.viewed_at.desc())
        .limit(limit // 3)
    )
    
    for view, doc, user in recent_views:
        activities.append(ActivityLog(
            id=str(view.id),
            type="document_view",
            title="Document viewed",
            description=doc.filename,
            user_name=user.full_name or user.email,
            user_email=user.email,
            timestamp=view.viewed_at,
            metadata={
                "document_id": str(doc.id),
                "filename": doc.filename
            }
        ))
    
    # Get recent document shares
    recent_shares = await db.execute(
        select(DocumentShare, Document, User)
        .join(Document, DocumentShare.document_id == Document.id)
        .join(User, DocumentShare.created_by == User.id)
        .where(DocumentShare.tenant_id == tenant_uuid)
        .order_by(DocumentShare.created_at.desc())
        .limit(limit // 3)
    )
    
    for share, doc, user in recent_shares:
        activities.append(ActivityLog(
            id=str(share.id),
            type="document_share",
            title="Document shared",
            description=doc.filename,
            user_name=user.full_name or user.email,
            user_email=user.email,
            timestamp=share.created_at,
            metadata={
                "document_id": str(doc.id),
                "filename": doc.filename,
                "share_type": share.share_type,
                "recipient": share.recipient_email
            }
        ))
    
    # Sort all activities by timestamp
    activities.sort(key=lambda x: x.timestamp, reverse=True)
    
    return RecentActivityResponse(
        activities=activities[:limit],
        total=len(activities)
    )


@router.get("/analytics/trends", response_model=AnalyticsTrends)
async def get_analytics_trends(
    period: str = Query("7d", regex="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get analytics trends for the specified period
    """
    tenant_uuid = UUID(tenant_id)
    
    # Determine date range
    days = {"7d": 7, "30d": 30, "90d": 90}[period]
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get document uploads by date
    uploads_by_date = await db.execute(
        select(
            func.date(Document.created_at).label('date'),
            func.count(Document.id).label('count')
        )
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.created_at >= start_date
            )
        )
        .group_by(func.date(Document.created_at))
        .order_by(func.date(Document.created_at))
    )
    
    # Get views by date
    views_by_date = await db.execute(
        select(
            func.date(DocumentView.viewed_at).label('date'),
            func.count(DocumentView.id).label('count')
        )
        .where(
            and_(
                DocumentView.tenant_id == tenant_uuid,
                DocumentView.viewed_at >= start_date
            )
        )
        .group_by(func.date(DocumentView.viewed_at))
        .order_by(func.date(DocumentView.viewed_at))
    )
    
    # Get storage growth
    storage_by_date = await db.execute(
        select(
            func.date(Document.created_at).label('date'),
            func.sum(Document.file_size).label('size')
        )
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.created_at >= start_date
            )
        )
        .group_by(func.date(Document.created_at))
        .order_by(func.date(Document.created_at))
    )
    
    # Format results
    uploads_data = {str(row.date): row.count for row in uploads_by_date}
    views_data = {str(row.date): row.count for row in views_by_date}
    storage_data = {str(row.date): row.size for row in storage_by_date}
    
    # Get most accessed documents
    top_documents = await db.execute(
        select(
            Document.id,
            Document.filename,
            func.count(DocumentView.id).label('view_count')
        )
        .join(DocumentView, Document.id == DocumentView.document_id)
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                DocumentView.viewed_at >= start_date
            )
        )
        .group_by(Document.id, Document.filename)
        .order_by(func.count(DocumentView.id).desc())
        .limit(5)
    )
    
    most_accessed = [
        {
            "document_id": str(row.id),
            "filename": row.filename,
            "views": row.view_count
        }
        for row in top_documents
    ]
    
    return AnalyticsTrends(
        period=period,
        uploads_by_date=uploads_data,
        views_by_date=views_data,
        storage_by_date=storage_data,
        most_accessed_documents=most_accessed,
        total_uploads=sum(uploads_data.values()),
        total_views=sum(views_data.values()),
        total_storage_added=sum(storage_data.values())
    )


@router.get("/insights/ai", response_model=AIInsightsResponse)
async def get_ai_insights(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get AI-powered insights and recommendations
    """
    tenant_uuid = UUID(tenant_id)
    insights: List[AIInsight] = []
    
    # Check for uncategorized documents
    uncategorized = await db.execute(
        select(func.count(Document.id))
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                or_(Document.category == None, Document.category == '')
            )
        )
    )
    uncategorized_count = uncategorized.scalar() or 0
    
    if uncategorized_count > 0:
        insights.append(AIInsight(
            type="categorization",
            priority="medium",
            title=f"{uncategorized_count} documents need categorization",
            description="Organize your recent uploads for better search results",
            action_url=f"/{tenant_id}/documents?filter=uncategorized",
            action_text="Categorize Now"
        ))
    
    # Check for documents that could benefit from AI analysis
    # (PDFs without summaries)
    contract_eligible = await db.execute(
        select(func.count(Document.id))
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.mime_type == 'application/pdf',
                or_(Document.summary == None, Document.summary == '')
            )
        )
    )
    contract_count = contract_eligible.scalar() or 0
    
    if contract_count > 0:
        insights.append(AIInsight(
            type="analysis",
            priority="high",
            title="Contract analysis available",
            description=f"{contract_count} contracts can be analyzed for key terms and dates",
            action_url=f"/{tenant_id}/agents?type=contract_analyzer",
            action_text="Analyze Contracts"
        ))
    
    # Check if AI summaries are enabled
    # This would check user/tenant settings - for now, we'll suggest it if they have long documents
    long_docs = await db.execute(
        select(func.count(Document.id))
        .where(
            and_(
                Document.tenant_id == tenant_uuid,
                Document.file_size > 1024 * 1024,  # Files larger than 1MB
                Document.summary == None
            )
        )
    )
    long_docs_count = long_docs.scalar() or 0
    
    if long_docs_count > 5:
        insights.append(AIInsight(
            type="feature",
            priority="low",
            title="Enable smart summaries",
            description="Get AI-generated summaries for long documents",
            action_url=f"/{tenant_id}/settings/ai",
            action_text="Enable Feature"
        ))
    
    # Check for expiring shared documents
    expiring_shares = await db.execute(
        select(func.count(DocumentShare.id))
        .where(
            and_(
                DocumentShare.tenant_id == tenant_uuid,
                DocumentShare.is_active == True,
                DocumentShare.expires_at != None,
                DocumentShare.expires_at <= datetime.utcnow() + timedelta(days=7),
                DocumentShare.expires_at > datetime.utcnow()
            )
        )
    )
    expiring_count = expiring_shares.scalar() or 0
    
    if expiring_count > 0:
        insights.append(AIInsight(
            type="warning",
            priority="high",
            title=f"{expiring_count} shared links expiring soon",
            description="Review and extend access for important shared documents",
            action_url=f"/{tenant_id}/shared?filter=expiring",
            action_text="Review Shares"
        ))
    
    return AIInsightsResponse(
        insights=insights,
        generated_at=datetime.utcnow()
    )