"""
Schemas for dashboard endpoints
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel


class DashboardStats(BaseModel):
    """Main dashboard statistics"""
    total_documents: int
    processed_documents: int
    processing_documents: int
    error_documents: int
    total_storage_bytes: int
    active_users: int
    recent_uploads: int
    trends: Dict[str, float]  # Percentage changes
    
    class Config:
        from_attributes = True


class ActivityLog(BaseModel):
    """Individual activity log entry"""
    id: str
    type: str  # document_upload, document_view, agent_execution, etc.
    title: str
    description: str
    user_name: str
    user_email: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class RecentActivityResponse(BaseModel):
    """Response for recent activity endpoint"""
    activities: List[ActivityLog]
    total: int
    
    class Config:
        from_attributes = True


class DocumentTrend(BaseModel):
    """Document statistics over time"""
    date: str
    uploads: int
    views: int
    shares: int
    
    class Config:
        from_attributes = True


class AnalyticsTrends(BaseModel):
    """Analytics trends over a period"""
    period: str  # 7d, 30d, 90d
    uploads_by_date: Dict[str, int]
    views_by_date: Dict[str, int]
    storage_by_date: Dict[str, int]
    most_accessed_documents: List[Dict[str, Any]]
    total_uploads: int
    total_views: int
    total_storage_added: int
    
    class Config:
        from_attributes = True


class AIInsight(BaseModel):
    """Individual AI-generated insight"""
    type: str  # categorization, analysis, feature, warning
    priority: str  # high, medium, low
    title: str
    description: str
    action_url: Optional[str] = None
    action_text: Optional[str] = None
    
    class Config:
        from_attributes = True


class AIInsightsResponse(BaseModel):
    """Response for AI insights endpoint"""
    insights: List[AIInsight]
    generated_at: datetime
    
    class Config:
        from_attributes = True