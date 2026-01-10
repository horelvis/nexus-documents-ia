"""
Sharing Insights Schemas

Pydantic models for sharing insights API responses.
Used by Emma AI to query document sharing and site guest information.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID


# =============================================================================
# Document Shares Insights
# =============================================================================

class RecentShareItem(BaseModel):
    """A single document share record (from either system)."""
    share_id: UUID
    document_id: UUID
    document_title: str
    document_filename: str
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    share_type: str  # view, download, edit
    is_active: bool
    access_count: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    created_by_email: Optional[str] = None
    created_by_name: Optional[str] = None
    # Source of the share - helps Emma understand the context
    share_source: str = "document_share"  # "document_share" (link) or "site_guest_share" (portal)
    share_collection_name: Optional[str] = None  # For site_guest_share: name of the collection


class RecentSharesResponse(BaseModel):
    """Response for recent shares query."""
    shares: List[RecentShareItem]
    total_count: int
    days_queried: int


class SharesByRecipientResponse(BaseModel):
    """Response for shares filtered by recipient email."""
    recipient_email: str
    shares: List[RecentShareItem]
    total_count: int


class ShareStatisticsResponse(BaseModel):
    """Aggregated sharing statistics."""
    total_shares: int
    active_shares: int
    expired_shares: int
    revoked_shares: int
    total_access_count: int
    unique_recipients: int
    most_shared_documents: List[Dict[str, Any]]
    shares_by_type: Dict[str, int]  # view: 10, download: 5, edit: 2
    period_days: int


# =============================================================================
# Site Guests Insights
# =============================================================================

class SiteGuestItem(BaseModel):
    """A single site guest record."""
    guest_id: UUID
    email: str
    name: Optional[str] = None
    is_active: bool
    can_view: bool
    can_download: bool
    can_upload: bool
    invited_at: datetime
    invited_by_email: Optional[str] = None
    invited_by_name: Optional[str] = None
    last_access_at: Optional[datetime] = None
    access_count: int
    expires_at: Optional[datetime] = None
    shares_count: int = 0  # Number of share collections


class SiteGuestsResponse(BaseModel):
    """Response for site guests list."""
    guests: List[SiteGuestItem]
    total_count: int
    active_count: int


class GuestDocumentItem(BaseModel):
    """A document accessible by a guest."""
    document_id: UUID
    document_title: str
    document_filename: str
    share_name: str  # Name of the share collection
    permission_type: str  # view, download, upload
    shared_at: datetime
    shared_by_email: Optional[str] = None
    shared_by_name: Optional[str] = None


class GuestDocumentsResponse(BaseModel):
    """Response for documents accessible by a specific guest."""
    guest_email: str
    guest_name: Optional[str] = None
    documents: List[GuestDocumentItem]
    total_count: int


class GuestActivityItem(BaseModel):
    """A single activity log entry for a guest."""
    log_id: UUID
    action: str  # login, logout, view, download, upload
    success: bool
    document_id: Optional[UUID] = None
    document_title: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    details: Optional[Dict[str, Any]] = None


class GuestActivityResponse(BaseModel):
    """Response for guest activity logs."""
    guest_email: str
    guest_name: Optional[str] = None
    activities: List[GuestActivityItem]
    total_count: int
    days_queried: int


class GuestStatisticsResponse(BaseModel):
    """Aggregated site guest statistics."""
    total_guests: int
    active_guests: int
    inactive_guests: int
    expired_guests: int
    total_logins: int
    total_document_views: int
    total_downloads: int
    most_active_guests: List[Dict[str, Any]]
    recent_invitations: List[Dict[str, Any]]
    guests_by_permission: Dict[str, int]  # view_only: 5, can_download: 3, can_upload: 1


# =============================================================================
# Combined/Summary Response
# =============================================================================

class SharingOverviewResponse(BaseModel):
    """High-level overview of all sharing activity."""
    # Document shares
    total_document_shares: int
    active_document_shares: int
    total_share_accesses: int

    # Site guests
    total_site_guests: int
    active_site_guests: int
    total_guest_logins: int

    # Recent activity summary
    shares_last_7_days: int
    guest_invitations_last_7_days: int
    accesses_last_7_days: int
