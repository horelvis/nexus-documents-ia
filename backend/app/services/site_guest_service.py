"""
Site Guest Service - Admin operations for external sharing.

Handles guest management, permissions, and invitation emails.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    SiteGuest, SiteGuestOTP, SiteGuestSession, SiteGuestPermission,
    SiteGuestAccessLog, Tenant, User, Document
)
from app.schemas.site_guest import (
    SiteGuestCreate, SiteGuestUpdate, SiteGuestResponse,
    SiteGuestPermissionResponse, SiteGuestAccessLogResponse,
    TenantSiteSettingsUpdate, SiteGuestStatistics
)
from app.services.email_service import EmailService
from app.core.config import settings

logger = logging.getLogger(__name__)


class SiteGuestService:
    """Service for managing Site Guests (admin operations)."""

    # =====================================
    # GUEST MANAGEMENT
    # =====================================

    @staticmethod
    async def create_guest(
        db: AsyncSession,
        tenant_id: UUID,
        guest_data: SiteGuestCreate,
        invited_by_user_id: UUID
    ) -> SiteGuest:
        """Create a new Site Guest and optionally send invitation email."""
        # Check if guest already exists
        existing = await SiteGuestService.get_guest_by_email(db, tenant_id, guest_data.email)
        if existing:
            raise ValueError(f"Guest with email {guest_data.email} already exists")

        # Create guest
        guest = SiteGuest(
            tenant_id=tenant_id,
            email=guest_data.email,
            name=guest_data.name,
            can_view=guest_data.can_view,
            can_download=guest_data.can_download,
            can_upload=guest_data.can_upload,
            expires_at=guest_data.expires_at,
            invited_by_user_id=invited_by_user_id,
            is_active=True
        )
        db.add(guest)
        await db.commit()
        await db.refresh(guest)

        # Send invitation if requested
        if guest_data.send_invitation:
            await SiteGuestService.send_invitation_email(db, guest)

        logger.info(f"Created Site Guest: {guest.email} for tenant {tenant_id}")
        return guest

    @staticmethod
    async def get_guest(db: AsyncSession, guest_id: UUID) -> Optional[SiteGuest]:
        """Get a Site Guest by ID."""
        result = await db.execute(
            select(SiteGuest).where(SiteGuest.id == guest_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_guest_by_email(
        db: AsyncSession,
        tenant_id: UUID,
        email: str
    ) -> Optional[SiteGuest]:
        """Get a Site Guest by email within a tenant."""
        result = await db.execute(
            select(SiteGuest).where(
                and_(
                    SiteGuest.tenant_id == tenant_id,
                    SiteGuest.email == email.lower()
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_guests(
        db: AsyncSession,
        tenant_id: UUID,
        include_inactive: bool = False,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[SiteGuest], int]:
        """List all Site Guests for a tenant with pagination."""
        query = select(SiteGuest).where(SiteGuest.tenant_id == tenant_id)

        if not include_inactive:
            query = query.where(SiteGuest.is_active == True)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar()

        # Apply pagination
        query = query.order_by(SiteGuest.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await db.execute(query)
        guests = result.scalars().all()

        return guests, total

    @staticmethod
    async def update_guest(
        db: AsyncSession,
        guest_id: UUID,
        updates: SiteGuestUpdate
    ) -> SiteGuest:
        """Update a Site Guest."""
        guest = await SiteGuestService.get_guest(db, guest_id)
        if not guest:
            raise ValueError("Guest not found")

        update_data = updates.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(guest, field, value)

        await db.commit()
        await db.refresh(guest)

        logger.info(f"Updated Site Guest: {guest.email}")
        return guest

    @staticmethod
    async def deactivate_guest(db: AsyncSession, guest_id: UUID) -> SiteGuest:
        """Deactivate a Site Guest (soft delete)."""
        guest = await SiteGuestService.get_guest(db, guest_id)
        if not guest:
            raise ValueError("Guest not found")

        guest.is_active = False

        # Revoke all active sessions
        await db.execute(
            select(SiteGuestSession)
            .where(
                and_(
                    SiteGuestSession.guest_id == guest_id,
                    SiteGuestSession.is_active == True
                )
            )
        )
        sessions = (await db.execute(
            select(SiteGuestSession).where(
                and_(
                    SiteGuestSession.guest_id == guest_id,
                    SiteGuestSession.is_active == True
                )
            )
        )).scalars().all()

        for session in sessions:
            session.is_active = False
            session.revoked_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(guest)

        logger.info(f"Deactivated Site Guest: {guest.email}")
        return guest

    # =====================================
    # PERMISSION MANAGEMENT
    # =====================================

    @staticmethod
    async def grant_document_permission(
        db: AsyncSession,
        guest_id: UUID,
        document_id: UUID,
        permission_type: str,
        granted_by_user_id: UUID,
        expires_at: Optional[datetime] = None
    ) -> SiteGuestPermission:
        """Grant document permission to a guest."""
        # Verify guest exists
        guest = await SiteGuestService.get_guest(db, guest_id)
        if not guest:
            raise ValueError("Guest not found")

        # Check if permission already exists
        existing = await db.execute(
            select(SiteGuestPermission).where(
                and_(
                    SiteGuestPermission.guest_id == guest_id,
                    SiteGuestPermission.document_id == document_id,
                    SiteGuestPermission.permission_type == permission_type
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Permission already exists")

        permission = SiteGuestPermission(
            guest_id=guest_id,
            document_id=document_id,
            folder_path=None,
            permission_type=permission_type,
            granted_by_user_id=granted_by_user_id,
            expires_at=expires_at
        )
        db.add(permission)
        await db.commit()
        await db.refresh(permission)

        logger.info(f"Granted {permission_type} permission for document {document_id} to guest {guest_id}")
        return permission

    @staticmethod
    async def grant_folder_permission(
        db: AsyncSession,
        guest_id: UUID,
        folder_path: str,
        permission_type: str,
        granted_by_user_id: UUID,
        expires_at: Optional[datetime] = None
    ) -> SiteGuestPermission:
        """Grant folder permission to a guest."""
        # Verify guest exists
        guest = await SiteGuestService.get_guest(db, guest_id)
        if not guest:
            raise ValueError("Guest not found")

        # Check if permission already exists
        existing = await db.execute(
            select(SiteGuestPermission).where(
                and_(
                    SiteGuestPermission.guest_id == guest_id,
                    SiteGuestPermission.folder_path == folder_path,
                    SiteGuestPermission.permission_type == permission_type
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Permission already exists")

        permission = SiteGuestPermission(
            guest_id=guest_id,
            document_id=None,
            folder_path=folder_path,
            permission_type=permission_type,
            granted_by_user_id=granted_by_user_id,
            expires_at=expires_at
        )
        db.add(permission)
        await db.commit()
        await db.refresh(permission)

        logger.info(f"Granted {permission_type} permission for folder {folder_path} to guest {guest_id}")
        return permission

    @staticmethod
    async def revoke_permission(db: AsyncSession, permission_id: UUID) -> bool:
        """Revoke a permission."""
        result = await db.execute(
            select(SiteGuestPermission).where(SiteGuestPermission.id == permission_id)
        )
        permission = result.scalar_one_or_none()

        if not permission:
            return False

        await db.delete(permission)
        await db.commit()

        logger.info(f"Revoked permission {permission_id}")
        return True

    @staticmethod
    async def list_guest_permissions(
        db: AsyncSession,
        guest_id: UUID
    ) -> List[SiteGuestPermission]:
        """List all permissions for a guest."""
        result = await db.execute(
            select(SiteGuestPermission)
            .where(SiteGuestPermission.guest_id == guest_id)
            .order_by(SiteGuestPermission.created_at.desc())
        )
        return result.scalars().all()

    # =====================================
    # ACCESS LOGS
    # =====================================

    @staticmethod
    async def get_guest_access_logs(
        db: AsyncSession,
        guest_id: UUID,
        page: int = 1,
        per_page: int = 50
    ) -> Tuple[List[SiteGuestAccessLog], int]:
        """Get access logs for a guest with pagination."""
        query = (
            select(SiteGuestAccessLog)
            .where(SiteGuestAccessLog.guest_id == guest_id)
            .order_by(SiteGuestAccessLog.created_at.desc())
        )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar()

        # Apply pagination
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await db.execute(query)
        logs = result.scalars().all()

        return logs, total

    @staticmethod
    async def log_guest_action(
        db: AsyncSession,
        guest_id: UUID,
        action: str,
        session_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        folder_path: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SiteGuestAccessLog:
        """Log a guest action for auditing."""
        log = SiteGuestAccessLog(
            guest_id=guest_id,
            session_id=session_id,
            action=action,
            success=success,
            error_message=error_message,
            document_id=document_id,
            folder_path=folder_path,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
        db.add(log)
        await db.commit()
        return log

    # =====================================
    # INVITATION EMAILS
    # =====================================

    @staticmethod
    async def send_invitation_email(db: AsyncSession, guest: SiteGuest) -> bool:
        """Send invitation email to a guest."""
        # Get tenant info
        tenant = await db.execute(
            select(Tenant).where(Tenant.id == guest.tenant_id)
        )
        tenant = tenant.scalar_one_or_none()
        if not tenant:
            logger.error(f"Tenant not found for guest {guest.id}")
            return False

        # Build portal URL
        portal_url = f"{settings.FRONTEND_URL}/{tenant.slug or tenant.id}"

        try:
            # Use email service with custom template
            success = await EmailService.send_share_notification(
                to_email=guest.email,
                subject=f"You've been invited to access {tenant.name}",
                template_data={
                    "recipient_name": guest.name or guest.email,
                    "sender_name": tenant.name,
                    "document_name": "Site Portal",
                    "share_link": portal_url,
                    "message": tenant.site_welcome_message or f"You have been invited to access documents from {tenant.name}. Click the link below to access the portal.",
                    "expires_at": guest.expires_at
                }
            )

            if success:
                logger.info(f"Invitation email sent to {guest.email}")
            return success

        except Exception as e:
            logger.error(f"Failed to send invitation email: {e}")
            return False

    # =====================================
    # TENANT SITE SETTINGS
    # =====================================

    @staticmethod
    async def get_tenant_site_settings(db: AsyncSession, tenant_id: UUID) -> Optional[Tenant]:
        """Get tenant site settings."""
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_tenant_site_settings(
        db: AsyncSession,
        tenant_id: UUID,
        updates: TenantSiteSettingsUpdate
    ) -> Tenant:
        """Update tenant site settings."""
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise ValueError("Tenant not found")

        update_data = updates.model_dump(exclude_unset=True)

        # Validate slug uniqueness if being updated
        if "slug" in update_data and update_data["slug"]:
            existing = await db.execute(
                select(Tenant).where(
                    and_(
                        Tenant.slug == update_data["slug"],
                        Tenant.id != tenant_id
                    )
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("Slug already in use by another tenant")

        for field, value in update_data.items():
            setattr(tenant, field, value)

        await db.commit()
        await db.refresh(tenant)

        logger.info(f"Updated site settings for tenant {tenant_id}")
        return tenant

    @staticmethod
    async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Optional[Tenant]:
        """Get tenant by slug for public portal."""
        result = await db.execute(
            select(Tenant).where(
                and_(
                    Tenant.slug == slug.lower(),
                    Tenant.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def generate_slug(name: str) -> str:
        """Generate a URL-friendly slug from a name."""
        # Convert to lowercase
        slug = name.lower()
        # Replace spaces and special chars with hyphens
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        # Limit length
        return slug[:100]

    # =====================================
    # STATISTICS
    # =====================================

    @staticmethod
    async def get_statistics(db: AsyncSession, tenant_id: UUID) -> SiteGuestStatistics:
        """Get statistics for site guests."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        # Total guests
        total_result = await db.execute(
            select(func.count()).where(SiteGuest.tenant_id == tenant_id)
        )
        total_guests = total_result.scalar()

        # Active guests
        active_result = await db.execute(
            select(func.count()).where(
                and_(
                    SiteGuest.tenant_id == tenant_id,
                    SiteGuest.is_active == True
                )
            )
        )
        active_guests = active_result.scalar()

        # Expired guests
        expired_result = await db.execute(
            select(func.count()).where(
                and_(
                    SiteGuest.tenant_id == tenant_id,
                    SiteGuest.expires_at < now
                )
            )
        )
        expired_guests = expired_result.scalar()

        # Total access count
        access_result = await db.execute(
            select(func.sum(SiteGuest.access_count)).where(
                SiteGuest.tenant_id == tenant_id
            )
        )
        total_access_count = access_result.scalar() or 0

        # Recent accesses (last 24 hours)
        recent_result = await db.execute(
            select(func.count()).select_from(SiteGuestAccessLog).join(
                SiteGuest, SiteGuestAccessLog.guest_id == SiteGuest.id
            ).where(
                and_(
                    SiteGuest.tenant_id == tenant_id,
                    SiteGuestAccessLog.created_at >= yesterday
                )
            )
        )
        recent_accesses = recent_result.scalar()

        # Documents shared (unique)
        docs_result = await db.execute(
            select(func.count(func.distinct(SiteGuestPermission.document_id))).join(
                SiteGuest, SiteGuestPermission.guest_id == SiteGuest.id
            ).where(
                and_(
                    SiteGuest.tenant_id == tenant_id,
                    SiteGuestPermission.document_id.isnot(None)
                )
            )
        )
        documents_shared = docs_result.scalar()

        # Folders shared (unique)
        folders_result = await db.execute(
            select(func.count(func.distinct(SiteGuestPermission.folder_path))).join(
                SiteGuest, SiteGuestPermission.guest_id == SiteGuest.id
            ).where(
                and_(
                    SiteGuest.tenant_id == tenant_id,
                    SiteGuestPermission.folder_path.isnot(None)
                )
            )
        )
        folders_shared = folders_result.scalar()

        return SiteGuestStatistics(
            total_guests=total_guests,
            active_guests=active_guests,
            inactive_guests=total_guests - active_guests,
            expired_guests=expired_guests,
            total_access_count=total_access_count,
            recent_accesses=recent_accesses,
            documents_shared=documents_shared,
            folders_shared=folders_shared,
            access_by_action={},  # TODO: Implement action breakdown
            access_by_date={}  # TODO: Implement date breakdown
        )


# Singleton instance
site_guest_service = SiteGuestService()
