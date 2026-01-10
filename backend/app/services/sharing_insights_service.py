"""
Sharing Insights Service

Provides read-only queries for document sharing and site guest analytics.
Used by Emma AI to answer questions about sharing activity.

All queries are tenant-isolated and read-only.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_, func, desc, select, case

from app.db.models import (
    Document, DocumentShare, DocumentShareAccessLog, DocumentShareRecipient,
    SiteGuest, SiteGuestShare, SiteGuestShareDocument, SiteGuestAccessLog,
    User
)
from app.schemas.sharing_insights import (
    RecentShareItem, RecentSharesResponse,
    SharesByRecipientResponse, ShareStatisticsResponse,
    SiteGuestItem, SiteGuestsResponse,
    GuestDocumentItem, GuestDocumentsResponse,
    GuestActivityItem, GuestActivityResponse,
    GuestStatisticsResponse, SharingOverviewResponse
)

logger = logging.getLogger(__name__)


class SharingInsightsService:
    """
    Read-only service for sharing insights queries.

    All methods require tenant_id for data isolation.
    """

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = UUID(tenant_id)

    # =========================================================================
    # Document Shares Queries
    # =========================================================================

    async def get_recent_shares(
        self,
        days: int = 7,
        limit: int = 50
    ) -> RecentSharesResponse:
        """
        Get documents shared within the last N days from BOTH sharing systems:
        1. DocumentShare - Direct share links (like Google Drive links)
        2. SiteGuestShare - Portal sharing with external guests

        Args:
            days: Number of days to look back (default 7)
            limit: Maximum results (default 50)

        Returns:
            RecentSharesResponse with share details from both systems
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        items = []

        # =================================================================
        # 1. Query DocumentShare (direct share links)
        # =================================================================
        doc_share_query = (
            select(DocumentShare)
            .options(
                joinedload(DocumentShare.document),
                joinedload(DocumentShare.creator)
            )
            .filter(
                and_(
                    DocumentShare.tenant_id == self.tenant_id,
                    DocumentShare.created_at >= since_date
                )
            )
            .order_by(desc(DocumentShare.created_at))
            .limit(limit)
        )

        doc_result = await self.db.execute(doc_share_query)
        doc_shares = doc_result.scalars().unique().all()

        for share in doc_shares:
            item = RecentShareItem(
                share_id=share.id,
                document_id=share.document_id,
                document_title=share.document.title if share.document else "Unknown",
                document_filename=share.document.filename if share.document else "unknown",
                recipient_email=share.recipient_email,
                recipient_name=share.recipient_name,
                share_type=share.share_type,
                is_active=share.is_active,
                access_count=share.current_access_count,
                created_at=share.created_at,
                expires_at=share.expires_at,
                last_accessed_at=share.last_accessed_at,
                created_by_email=share.creator.email if share.creator else None,
                created_by_name=share.creator.full_name if share.creator else None,
                share_source="document_share",
                share_collection_name=None
            )
            items.append(item)

        # =================================================================
        # 2. Query SiteGuestShare + SiteGuestShareDocument (portal sharing)
        # =================================================================
        guest_share_query = (
            select(
                SiteGuestShareDocument,
                SiteGuestShare,
                SiteGuest,
                Document,
                User
            )
            .select_from(SiteGuestShareDocument)
            .join(SiteGuestShare, SiteGuestShareDocument.share_id == SiteGuestShare.id)
            .join(SiteGuest, SiteGuestShare.guest_id == SiteGuest.id)
            .join(Document, SiteGuestShareDocument.document_id == Document.id)
            .outerjoin(User, SiteGuestShare.created_by_user_id == User.id)
            .filter(
                and_(
                    SiteGuestShare.tenant_id == self.tenant_id,
                    SiteGuestShareDocument.created_at >= since_date
                )
            )
            .order_by(desc(SiteGuestShareDocument.created_at))
            .limit(limit)
        )

        guest_result = await self.db.execute(guest_share_query)
        guest_rows = guest_result.all()

        for row in guest_rows:
            share_doc = row[0]  # SiteGuestShareDocument
            share = row[1]      # SiteGuestShare
            guest = row[2]      # SiteGuest
            doc = row[3]        # Document
            creator = row[4]    # User (may be None)

            # Check if share is still active (not expired)
            is_active = not share.is_expired() if hasattr(share, 'is_expired') else True

            item = RecentShareItem(
                share_id=share.id,
                document_id=doc.id,
                document_title=doc.title,
                document_filename=doc.filename,
                recipient_email=guest.email,
                recipient_name=guest.name,
                share_type=share.permission_type,
                is_active=is_active and guest.is_active,
                access_count=guest.access_count,
                created_at=share_doc.created_at,
                expires_at=share.expires_at,
                last_accessed_at=guest.last_access_at,
                created_by_email=creator.email if creator else None,
                created_by_name=creator.full_name if creator else None,
                share_source="site_guest_share",
                share_collection_name=share.name
            )
            items.append(item)

        # =================================================================
        # 3. Sort combined results by created_at and apply limit
        # =================================================================
        items.sort(key=lambda x: x.created_at, reverse=True)
        items = items[:limit]

        # Get total counts from both systems
        doc_count_query = select(func.count()).select_from(DocumentShare).filter(
            and_(
                DocumentShare.tenant_id == self.tenant_id,
                DocumentShare.created_at >= since_date
            )
        )
        doc_count_result = await self.db.execute(doc_count_query)
        doc_count = doc_count_result.scalar() or 0

        guest_count_query = (
            select(func.count())
            .select_from(SiteGuestShareDocument)
            .join(SiteGuestShare, SiteGuestShareDocument.share_id == SiteGuestShare.id)
            .filter(
                and_(
                    SiteGuestShare.tenant_id == self.tenant_id,
                    SiteGuestShareDocument.created_at >= since_date
                )
            )
        )
        guest_count_result = await self.db.execute(guest_count_query)
        guest_count = guest_count_result.scalar() or 0

        total_count = doc_count + guest_count

        return RecentSharesResponse(
            shares=items,
            total_count=total_count,
            days_queried=days
        )

    async def get_shares_by_recipient(
        self,
        email: str,
        limit: int = 50
    ) -> SharesByRecipientResponse:
        """
        Get all shares sent to a specific recipient email from BOTH systems:
        1. DocumentShare - Direct share links
        2. SiteGuestShare - Portal sharing with external guests

        Args:
            email: Recipient email to filter by
            limit: Maximum results

        Returns:
            SharesByRecipientResponse with shares for that recipient
        """
        items = []

        # =================================================================
        # 1. Search in DocumentShare (direct share links)
        # =================================================================
        doc_query = (
            select(DocumentShare)
            .options(
                joinedload(DocumentShare.document),
                joinedload(DocumentShare.creator)
            )
            .outerjoin(DocumentShareRecipient)
            .filter(
                and_(
                    DocumentShare.tenant_id == self.tenant_id,
                    or_(
                        DocumentShare.recipient_email.ilike(f"%{email}%"),
                        DocumentShareRecipient.email.ilike(f"%{email}%")
                    )
                )
            )
            .order_by(desc(DocumentShare.created_at))
            .limit(limit)
        )

        doc_result = await self.db.execute(doc_query)
        doc_shares = doc_result.scalars().unique().all()

        for share in doc_shares:
            item = RecentShareItem(
                share_id=share.id,
                document_id=share.document_id,
                document_title=share.document.title if share.document else "Unknown",
                document_filename=share.document.filename if share.document else "unknown",
                recipient_email=share.recipient_email,
                recipient_name=share.recipient_name,
                share_type=share.share_type,
                is_active=share.is_active,
                access_count=share.current_access_count,
                created_at=share.created_at,
                expires_at=share.expires_at,
                last_accessed_at=share.last_accessed_at,
                created_by_email=share.creator.email if share.creator else None,
                created_by_name=share.creator.full_name if share.creator else None,
                share_source="document_share",
                share_collection_name=None
            )
            items.append(item)

        # =================================================================
        # 2. Search in SiteGuestShare (portal sharing)
        # =================================================================
        guest_query = (
            select(
                SiteGuestShareDocument,
                SiteGuestShare,
                SiteGuest,
                Document,
                User
            )
            .select_from(SiteGuestShareDocument)
            .join(SiteGuestShare, SiteGuestShareDocument.share_id == SiteGuestShare.id)
            .join(SiteGuest, SiteGuestShare.guest_id == SiteGuest.id)
            .join(Document, SiteGuestShareDocument.document_id == Document.id)
            .outerjoin(User, SiteGuestShare.created_by_user_id == User.id)
            .filter(
                and_(
                    SiteGuestShare.tenant_id == self.tenant_id,
                    SiteGuest.email.ilike(f"%{email}%")
                )
            )
            .order_by(desc(SiteGuestShareDocument.created_at))
            .limit(limit)
        )

        guest_result = await self.db.execute(guest_query)
        guest_rows = guest_result.all()

        for row in guest_rows:
            share_doc = row[0]  # SiteGuestShareDocument
            share = row[1]      # SiteGuestShare
            guest = row[2]      # SiteGuest
            doc = row[3]        # Document
            creator = row[4]    # User (may be None)

            is_active = not share.is_expired() if hasattr(share, 'is_expired') else True

            item = RecentShareItem(
                share_id=share.id,
                document_id=doc.id,
                document_title=doc.title,
                document_filename=doc.filename,
                recipient_email=guest.email,
                recipient_name=guest.name,
                share_type=share.permission_type,
                is_active=is_active and guest.is_active,
                access_count=guest.access_count,
                created_at=share_doc.created_at,
                expires_at=share.expires_at,
                last_accessed_at=guest.last_access_at,
                created_by_email=creator.email if creator else None,
                created_by_name=creator.full_name if creator else None,
                share_source="site_guest_share",
                share_collection_name=share.name
            )
            items.append(item)

        # Sort by created_at and apply limit
        items.sort(key=lambda x: x.created_at, reverse=True)
        items = items[:limit]

        return SharesByRecipientResponse(
            recipient_email=email,
            shares=items,
            total_count=len(items)
        )

    async def get_share_statistics(
        self,
        days: int = 30
    ) -> ShareStatisticsResponse:
        """
        Get aggregated sharing statistics for the tenant.

        Args:
            days: Period to analyze (default 30)

        Returns:
            ShareStatisticsResponse with aggregated stats
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        now = datetime.now(timezone.utc)

        # Base filter
        base_filter = DocumentShare.tenant_id == self.tenant_id

        # Total shares
        total_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(base_filter)
        )
        total_shares = total_result.scalar() or 0

        # Active shares
        active_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                and_(base_filter, DocumentShare.is_active == True)
            )
        )
        active_shares = active_result.scalar() or 0

        # Expired shares
        expired_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                and_(
                    base_filter,
                    DocumentShare.expires_at != None,
                    DocumentShare.expires_at < now
                )
            )
        )
        expired_shares = expired_result.scalar() or 0

        # Revoked shares
        revoked_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                and_(base_filter, DocumentShare.revoked_at != None)
            )
        )
        revoked_shares = revoked_result.scalar() or 0

        # Total access count
        access_result = await self.db.execute(
            select(func.sum(DocumentShare.current_access_count)).filter(base_filter)
        )
        total_access_count = access_result.scalar() or 0

        # Unique recipients
        recipients_result = await self.db.execute(
            select(func.count(func.distinct(DocumentShare.recipient_email))).filter(
                and_(base_filter, DocumentShare.recipient_email != None)
            )
        )
        unique_recipients = recipients_result.scalar() or 0

        # Most shared documents
        most_shared_result = await self.db.execute(
            select(
                Document.id,
                Document.title,
                func.count(DocumentShare.id).label('share_count')
            )
            .join(DocumentShare, Document.id == DocumentShare.document_id)
            .filter(DocumentShare.tenant_id == self.tenant_id)
            .group_by(Document.id, Document.title)
            .order_by(desc('share_count'))
            .limit(10)
        )
        most_shared = [
            {"document_id": str(r.id), "title": r.title, "share_count": r.share_count}
            for r in most_shared_result.all()
        ]

        # Shares by type
        type_result = await self.db.execute(
            select(
                DocumentShare.share_type,
                func.count(DocumentShare.id).label('count')
            )
            .filter(base_filter)
            .group_by(DocumentShare.share_type)
        )
        shares_by_type = {r.share_type: r.count for r in type_result.all()}

        return ShareStatisticsResponse(
            total_shares=total_shares,
            active_shares=active_shares,
            expired_shares=expired_shares,
            revoked_shares=revoked_shares,
            total_access_count=int(total_access_count),
            unique_recipients=unique_recipients,
            most_shared_documents=most_shared,
            shares_by_type=shares_by_type,
            period_days=days
        )

    # =========================================================================
    # Site Guests Queries
    # =========================================================================

    async def get_site_guests(
        self,
        active_only: bool = False,
        limit: int = 100
    ) -> SiteGuestsResponse:
        """
        Get list of site guests for the tenant.

        Args:
            active_only: If True, only return active guests
            limit: Maximum results

        Returns:
            SiteGuestsResponse with guest list
        """
        query = (
            select(SiteGuest)
            .options(joinedload(SiteGuest.inviter))
            .filter(SiteGuest.tenant_id == self.tenant_id)
        )

        if active_only:
            query = query.filter(SiteGuest.is_active == True)

        query = query.order_by(desc(SiteGuest.invited_at)).limit(limit)

        result = await self.db.execute(query)
        guests = result.scalars().unique().all()

        # Count active guests
        active_count_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuest.is_active == True
                )
            )
        )
        active_count = active_count_result.scalar() or 0

        # Total count
        total_count_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                SiteGuest.tenant_id == self.tenant_id
            )
        )
        total_count = total_count_result.scalar() or 0

        # Get shares count per guest
        shares_count_query = (
            select(
                SiteGuestShare.guest_id,
                func.count(SiteGuestShare.id).label('shares_count')
            )
            .filter(SiteGuestShare.tenant_id == self.tenant_id)
            .group_by(SiteGuestShare.guest_id)
        )
        shares_result = await self.db.execute(shares_count_query)
        shares_by_guest = {r.guest_id: r.shares_count for r in shares_result.all()}

        items = []
        for guest in guests:
            item = SiteGuestItem(
                guest_id=guest.id,
                email=guest.email,
                name=guest.name,
                is_active=guest.is_active,
                can_view=guest.can_view,
                can_download=guest.can_download,
                can_upload=guest.can_upload,
                invited_at=guest.invited_at,
                invited_by_email=guest.inviter.email if guest.inviter else None,
                invited_by_name=guest.inviter.full_name if guest.inviter else None,
                last_access_at=guest.last_access_at,
                access_count=guest.access_count,
                expires_at=guest.expires_at,
                shares_count=shares_by_guest.get(guest.id, 0)
            )
            items.append(item)

        return SiteGuestsResponse(
            guests=items,
            total_count=total_count,
            active_count=active_count
        )

    async def get_guest_documents(
        self,
        email: str
    ) -> GuestDocumentsResponse:
        """
        Get all documents accessible by a specific guest.

        Args:
            email: Guest email

        Returns:
            GuestDocumentsResponse with accessible documents
        """
        # First find the guest
        guest_query = select(SiteGuest).filter(
            and_(
                SiteGuest.tenant_id == self.tenant_id,
                SiteGuest.email.ilike(email)
            )
        )
        guest_result = await self.db.execute(guest_query)
        guest = guest_result.scalar_one_or_none()

        if not guest:
            return GuestDocumentsResponse(
                guest_email=email,
                guest_name=None,
                documents=[],
                total_count=0
            )

        # Get documents via SiteGuestShare -> SiteGuestShareDocument
        docs_query = (
            select(
                Document,
                SiteGuestShare.name.label('share_name'),
                SiteGuestShare.permission_type,
                SiteGuestShare.created_at.label('shared_at'),
                User.email.label('shared_by_email'),
                User.full_name.label('shared_by_name')
            )
            .select_from(SiteGuestShareDocument)
            .join(SiteGuestShare, SiteGuestShareDocument.share_id == SiteGuestShare.id)
            .join(Document, SiteGuestShareDocument.document_id == Document.id)
            .outerjoin(User, SiteGuestShare.created_by_user_id == User.id)
            .filter(SiteGuestShare.guest_id == guest.id)
            .order_by(desc(SiteGuestShare.created_at))
        )

        docs_result = await self.db.execute(docs_query)
        rows = docs_result.all()

        items = []
        for row in rows:
            doc = row[0]
            item = GuestDocumentItem(
                document_id=doc.id,
                document_title=doc.title,
                document_filename=doc.filename,
                share_name=row.share_name,
                permission_type=row.permission_type,
                shared_at=row.shared_at,
                shared_by_email=row.shared_by_email,
                shared_by_name=row.shared_by_name
            )
            items.append(item)

        return GuestDocumentsResponse(
            guest_email=guest.email,
            guest_name=guest.name,
            documents=items,
            total_count=len(items)
        )

    async def get_guest_activity(
        self,
        email: str,
        days: int = 30,
        limit: int = 100
    ) -> GuestActivityResponse:
        """
        Get activity logs for a specific guest.

        Args:
            email: Guest email
            days: Number of days to look back
            limit: Maximum results

        Returns:
            GuestActivityResponse with activity logs
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Find guest
        guest_query = select(SiteGuest).filter(
            and_(
                SiteGuest.tenant_id == self.tenant_id,
                SiteGuest.email.ilike(email)
            )
        )
        guest_result = await self.db.execute(guest_query)
        guest = guest_result.scalar_one_or_none()

        if not guest:
            return GuestActivityResponse(
                guest_email=email,
                guest_name=None,
                activities=[],
                total_count=0,
                days_queried=days
            )

        # Get activity logs
        logs_query = (
            select(SiteGuestAccessLog)
            .options(joinedload(SiteGuestAccessLog.document))
            .filter(
                and_(
                    SiteGuestAccessLog.guest_id == guest.id,
                    SiteGuestAccessLog.created_at >= since_date
                )
            )
            .order_by(desc(SiteGuestAccessLog.created_at))
            .limit(limit)
        )

        logs_result = await self.db.execute(logs_query)
        logs = logs_result.scalars().unique().all()

        # Total count
        count_query = select(func.count()).select_from(SiteGuestAccessLog).filter(
            and_(
                SiteGuestAccessLog.guest_id == guest.id,
                SiteGuestAccessLog.created_at >= since_date
            )
        )
        count_result = await self.db.execute(count_query)
        total_count = count_result.scalar() or 0

        items = []
        for log in logs:
            item = GuestActivityItem(
                log_id=log.id,
                action=log.action,
                success=log.success,
                document_id=log.document_id,
                document_title=log.document.title if log.document else None,
                ip_address=log.ip_address,
                created_at=log.created_at,
                details=log.details
            )
            items.append(item)

        return GuestActivityResponse(
            guest_email=guest.email,
            guest_name=guest.name,
            activities=items,
            total_count=total_count,
            days_queried=days
        )

    async def get_guest_statistics(self) -> GuestStatisticsResponse:
        """
        Get aggregated statistics about site guests.

        Returns:
            GuestStatisticsResponse with aggregated stats
        """
        base_filter = SiteGuest.tenant_id == self.tenant_id
        now = datetime.now(timezone.utc)

        # Total guests
        total_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(base_filter)
        )
        total_guests = total_result.scalar() or 0

        # Active guests
        active_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(base_filter, SiteGuest.is_active == True)
            )
        )
        active_guests = active_result.scalar() or 0

        # Inactive guests
        inactive_guests = total_guests - active_guests

        # Expired guests
        expired_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(
                    base_filter,
                    SiteGuest.expires_at != None,
                    SiteGuest.expires_at < now
                )
            )
        )
        expired_guests = expired_result.scalar() or 0

        # Activity counts from logs
        # Total logins
        logins_result = await self.db.execute(
            select(func.count()).select_from(SiteGuestAccessLog)
            .join(SiteGuest, SiteGuestAccessLog.guest_id == SiteGuest.id)
            .filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuestAccessLog.action == 'login',
                    SiteGuestAccessLog.success == True
                )
            )
        )
        total_logins = logins_result.scalar() or 0

        # Total document views
        views_result = await self.db.execute(
            select(func.count()).select_from(SiteGuestAccessLog)
            .join(SiteGuest, SiteGuestAccessLog.guest_id == SiteGuest.id)
            .filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuestAccessLog.action == 'view',
                    SiteGuestAccessLog.success == True
                )
            )
        )
        total_document_views = views_result.scalar() or 0

        # Total downloads
        downloads_result = await self.db.execute(
            select(func.count()).select_from(SiteGuestAccessLog)
            .join(SiteGuest, SiteGuestAccessLog.guest_id == SiteGuest.id)
            .filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuestAccessLog.action == 'download',
                    SiteGuestAccessLog.success == True
                )
            )
        )
        total_downloads = downloads_result.scalar() or 0

        # Most active guests
        most_active_result = await self.db.execute(
            select(
                SiteGuest.id,
                SiteGuest.email,
                SiteGuest.name,
                SiteGuest.access_count
            )
            .filter(base_filter)
            .order_by(desc(SiteGuest.access_count))
            .limit(10)
        )
        most_active_guests = [
            {
                "guest_id": str(r.id),
                "email": r.email,
                "name": r.name,
                "access_count": r.access_count
            }
            for r in most_active_result.all()
        ]

        # Recent invitations (last 30 days)
        thirty_days_ago = now - timedelta(days=30)
        recent_result = await self.db.execute(
            select(
                SiteGuest.email,
                SiteGuest.name,
                SiteGuest.invited_at
            )
            .filter(
                and_(
                    base_filter,
                    SiteGuest.invited_at >= thirty_days_ago
                )
            )
            .order_by(desc(SiteGuest.invited_at))
            .limit(10)
        )
        recent_invitations = [
            {
                "email": r.email,
                "name": r.name,
                "invited_at": r.invited_at.isoformat()
            }
            for r in recent_result.all()
        ]

        # Guests by permission type
        # Count guests with each permission combination
        view_only = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(
                    base_filter,
                    SiteGuest.can_view == True,
                    SiteGuest.can_download == False,
                    SiteGuest.can_upload == False
                )
            )
        )
        can_download = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(base_filter, SiteGuest.can_download == True)
            )
        )
        can_upload = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(base_filter, SiteGuest.can_upload == True)
            )
        )

        guests_by_permission = {
            "view_only": view_only.scalar() or 0,
            "can_download": can_download.scalar() or 0,
            "can_upload": can_upload.scalar() or 0
        }

        return GuestStatisticsResponse(
            total_guests=total_guests,
            active_guests=active_guests,
            inactive_guests=inactive_guests,
            expired_guests=expired_guests,
            total_logins=total_logins,
            total_document_views=total_document_views,
            total_downloads=total_downloads,
            most_active_guests=most_active_guests,
            recent_invitations=recent_invitations,
            guests_by_permission=guests_by_permission
        )

    # =========================================================================
    # Combined Overview
    # =========================================================================

    async def get_sharing_overview(self) -> SharingOverviewResponse:
        """
        Get a high-level overview of all sharing activity.

        Returns:
            SharingOverviewResponse with summary stats
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        # Document shares counts
        total_shares_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                DocumentShare.tenant_id == self.tenant_id
            )
        )
        total_document_shares = total_shares_result.scalar() or 0

        active_shares_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                and_(
                    DocumentShare.tenant_id == self.tenant_id,
                    DocumentShare.is_active == True
                )
            )
        )
        active_document_shares = active_shares_result.scalar() or 0

        access_count_result = await self.db.execute(
            select(func.sum(DocumentShare.current_access_count)).filter(
                DocumentShare.tenant_id == self.tenant_id
            )
        )
        total_share_accesses = access_count_result.scalar() or 0

        # Site guests counts
        total_guests_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                SiteGuest.tenant_id == self.tenant_id
            )
        )
        total_site_guests = total_guests_result.scalar() or 0

        active_guests_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuest.is_active == True
                )
            )
        )
        active_site_guests = active_guests_result.scalar() or 0

        # Guest logins
        logins_result = await self.db.execute(
            select(func.count()).select_from(SiteGuestAccessLog)
            .join(SiteGuest, SiteGuestAccessLog.guest_id == SiteGuest.id)
            .filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuestAccessLog.action == 'login',
                    SiteGuestAccessLog.success == True
                )
            )
        )
        total_guest_logins = logins_result.scalar() or 0

        # Last 7 days activity
        shares_7d_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                and_(
                    DocumentShare.tenant_id == self.tenant_id,
                    DocumentShare.created_at >= seven_days_ago
                )
            )
        )
        shares_last_7_days = shares_7d_result.scalar() or 0

        invitations_7d_result = await self.db.execute(
            select(func.count()).select_from(SiteGuest).filter(
                and_(
                    SiteGuest.tenant_id == self.tenant_id,
                    SiteGuest.invited_at >= seven_days_ago
                )
            )
        )
        guest_invitations_last_7_days = invitations_7d_result.scalar() or 0

        accesses_7d_result = await self.db.execute(
            select(func.count()).select_from(DocumentShareAccessLog).filter(
                and_(
                    DocumentShareAccessLog.tenant_id == self.tenant_id,
                    DocumentShareAccessLog.accessed_at >= seven_days_ago
                )
            )
        )
        accesses_last_7_days = accesses_7d_result.scalar() or 0

        return SharingOverviewResponse(
            total_document_shares=total_document_shares,
            active_document_shares=active_document_shares,
            total_share_accesses=int(total_share_accesses),
            total_site_guests=total_site_guests,
            active_site_guests=active_site_guests,
            total_guest_logins=total_guest_logins,
            shares_last_7_days=shares_last_7_days,
            guest_invitations_last_7_days=guest_invitations_last_7_days,
            accesses_last_7_days=accesses_last_7_days
        )
