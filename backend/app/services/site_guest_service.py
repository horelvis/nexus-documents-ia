"""
Site Guest Service - Admin operations for external sharing.

Handles guest management, permissions, and invitation emails.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    SiteGuest, SiteGuestOTP, SiteGuestSession, SiteGuestPermission,
    SiteGuestAccessLog, SiteGuestShare, SiteGuestShareDocument,
    User, Document
)
from app.schemas.site_guest import (
    SiteGuestCreate, SiteGuestUpdate, SiteGuestResponse,
    SiteGuestPermissionResponse, SiteGuestAccessLogResponse,
    TenantSiteSettingsUpdate, SiteGuestStatistics,
    SiteGuestShareResponse
)
from app.services.email_service import EmailService
from app.core.config import settings

logger = logging.getLogger(__name__)


# Single-tenant on-premise: hardcoded site settings
DEFAULT_SITE_NAME = "NouxCube"
DEFAULT_SITE_SLUG = "nouxcube"
DEFAULT_SITE_WELCOME_MESSAGE = "Bienvenido al portal de NouxCube."


@dataclass
class SiteSettings:
    """Hardcoded site settings for single-tenant deployment."""
    id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    name: str = DEFAULT_SITE_NAME
    slug: str = DEFAULT_SITE_SLUG
    site_enabled: bool = True
    site_welcome_message: str = DEFAULT_SITE_WELCOME_MESSAGE
    is_active: bool = True


class SiteGuestService:
    """Service for managing Site Guests (admin operations)."""

    # =====================================
    # GUEST MANAGEMENT
    # =====================================

    @staticmethod
    async def create_guest(
        db: AsyncSession,
        guest_data: SiteGuestCreate,
        invited_by_user_id: UUID
    ) -> SiteGuest:
        """Create a new Site Guest and optionally send invitation email."""
        # Check if guest already exists
        existing = await SiteGuestService.get_guest_by_email(db, guest_data.email)
        if existing:
            raise ValueError(f"Guest with email {guest_data.email} already exists")

        # Create guest
        guest = SiteGuest(
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

        logger.info(f"Created Site Guest: {guest.email}")
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
        email: str
    ) -> Optional[SiteGuest]:
        """Get a Site Guest by email."""
        result = await db.execute(
            select(SiteGuest).where(SiteGuest.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_guests(
        db: AsyncSession,
        include_inactive: bool = False,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[SiteGuest], int]:
        """List all Site Guests with pagination."""
        query = select(SiteGuest)

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
    # SHARE/COLLECTION MANAGEMENT
    # =====================================

    @staticmethod
    async def get_or_create_guest(
        db: AsyncSession,
        email: str,
        name: Optional[str] = None,
        invited_by_user_id: Optional[UUID] = None
    ) -> Tuple[SiteGuest, bool]:
        """
        Get existing guest by email or create new one.
        Returns (guest, is_new) tuple.

        IMPORTANTE: No crear duplicados - un email = un guest.
        """
        # Search for existing guest (case-insensitive)
        existing_guest = await SiteGuestService.get_guest_by_email(db, email)

        if existing_guest:
            # Reactivate if deactivated
            if not existing_guest.is_active:
                existing_guest.is_active = True
                await db.commit()
                await db.refresh(existing_guest)
                logger.info(f"Reactivated existing guest: {email}")
            return (existing_guest, False)  # False = not new

        # Create new guest
        new_guest = SiteGuest(
            email=email.lower(),
            name=name,
            invited_by_user_id=invited_by_user_id,
            is_active=True,
            can_view=True,
            can_download=False,
            can_upload=False
        )
        db.add(new_guest)
        await db.commit()
        await db.refresh(new_guest)

        logger.info(f"Created new guest: {email}")
        return (new_guest, True)  # True = is new

    @staticmethod
    async def create_share(
        db: AsyncSession,
        guest_id: UUID,
        name: str,
        document_ids: List[UUID],
        permission_type: str = "view",
        description: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        created_by_user_id: Optional[UUID] = None
    ) -> SiteGuestShare:
        """
        Create a share/collection with documents for a guest.

        Documents stay in their original location - this is just a reference.
        """
        allowed_permission_types = {"view", "download", "upload"}
        if permission_type not in allowed_permission_types:
            raise ValueError(f"Invalid permission type: {permission_type}")

        # Verify guest exists
        result = await db.execute(
            select(SiteGuest).where(SiteGuest.id == guest_id)
        )
        guest = result.scalar_one_or_none()
        if not guest:
            raise ValueError("Guest not found")

        # Verify documents exist (dedupe IDs)
        unique_document_ids = list(dict.fromkeys(document_ids))
        result = await db.execute(
            select(Document.id).where(Document.id.in_(unique_document_ids))
        )
        valid_doc_ids = list(result.scalars().all())

        missing_doc_ids = set(unique_document_ids) - set(valid_doc_ids)
        if missing_doc_ids:
            logger.warning(
                "Some documents were not found: %s",
                list(missing_doc_ids)
            )

        if not valid_doc_ids:
            raise ValueError("No valid documents found")

        # Create share
        share = SiteGuestShare(
            guest_id=guest_id,
            name=name,
            description=description,
            permission_type=permission_type,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at
        )
        db.add(share)
        await db.flush()  # Get share ID

        # Add documents to share
        for doc_id in valid_doc_ids:
            share_doc = SiteGuestShareDocument(
                share_id=share.id,
                document_id=doc_id
            )
            db.add(share_doc)

        await db.commit()
        await db.refresh(share)

        logger.info(f"Created share '{name}' with {len(valid_doc_ids)} documents for guest {guest_id}")
        return share

    @staticmethod
    async def get_share(db: AsyncSession, share_id: UUID) -> Optional[SiteGuestShare]:
        """Get a share by ID with documents loaded."""
        result = await db.execute(
            select(SiteGuestShare)
            .options(selectinload(SiteGuestShare.documents).selectinload(SiteGuestShareDocument.document))
            .where(SiteGuestShare.id == share_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_guest_shares(
        db: AsyncSession,
        guest_id: UUID
    ) -> List[SiteGuestShare]:
        """List all shares for a guest."""
        result = await db.execute(
            select(SiteGuestShare)
            .options(selectinload(SiteGuestShare.documents))
            .where(SiteGuestShare.guest_id == guest_id)
            .order_by(SiteGuestShare.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def delete_share(db: AsyncSession, share_id: UUID) -> bool:
        """Delete a share (documents are NOT deleted, only the reference)."""
        result = await db.execute(
            select(SiteGuestShare).where(SiteGuestShare.id == share_id)
        )
        share = result.scalar_one_or_none()

        if not share:
            return False

        await db.delete(share)
        await db.commit()

        logger.info(f"Deleted share {share_id}")
        return True

    @staticmethod
    async def send_share_notification(
        db: AsyncSession,
        guest: SiteGuest,
        share: SiteGuestShare,
        is_new_guest: bool = True,
        language: str = "es"
    ) -> bool:
        """
        Send notification email when documents are shared with a guest.

        Different email for new guests vs existing guests with new share.
        """
        site = SiteSettings()

        # Build portal URL
        portal_url = f"{settings.FRONTEND_URL}/portal/{site.slug}"

        # Get document count
        result = await db.execute(
            select(func.count()).where(SiteGuestShareDocument.share_id == share.id)
        )
        document_count = result.scalar() or 0

        try:
            if is_new_guest:
                # New guest - send full invitation
                success = await EmailService.send_guest_invitation(
                    to_email=guest.email,
                    recipient_name=guest.name or guest.email,
                    tenant_name=site.name,
                    portal_url=portal_url,
                    welcome_message=f"Se han compartido {document_count} documento(s) contigo en la colección '{share.name}'.",
                    expires_at=share.expires_at,
                    can_view=share.permission_type in ["view", "download", "upload"],
                    can_download=share.permission_type in ["download", "upload"],
                    language=language
                )
            else:
                # Existing guest - send notification about new share
                success = await EmailService.send_guest_invitation(
                    to_email=guest.email,
                    recipient_name=guest.name or guest.email,
                    tenant_name=site.name,
                    portal_url=portal_url,
                    welcome_message=f"Se han compartido {document_count} documento(s) adicionales contigo en la colección '{share.name}'.",
                    expires_at=share.expires_at,
                    can_view=share.permission_type in ["view", "download", "upload"],
                    can_download=share.permission_type in ["download", "upload"],
                    language=language
                )

            if success:
                logger.info(f"Share notification sent to {guest.email} for share '{share.name}'")
            return success

        except Exception as e:
            logger.error(f"Failed to send share notification: {e}")
            return False

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
    async def send_invitation_email(db: AsyncSession, guest: SiteGuest, language: str = "es") -> bool:
        """Send invitation email to a guest using dedicated invitation template."""
        site = SiteSettings()

        # Build portal URL
        portal_url = f"{settings.FRONTEND_URL}/portal/{site.slug}"

        try:
            # Use dedicated guest invitation template
            success = await EmailService.send_guest_invitation(
                to_email=guest.email,
                recipient_name=guest.name or guest.email,
                tenant_name=site.name,
                portal_url=portal_url,
                welcome_message=site.site_welcome_message,
                expires_at=guest.expires_at,
                can_view=guest.can_view,
                can_download=guest.can_download,
                language=language
            )

            if success:
                logger.info(f"Invitation email sent to {guest.email}")
            return success

        except Exception as e:
            logger.error(f"Failed to send invitation email: {e}")
            return False

    # =====================================
    # SITE SETTINGS (single-tenant: hardcoded)
    # =====================================

    @staticmethod
    async def get_tenant_site_settings(db: AsyncSession) -> SiteSettings:
        """Get site settings (hardcoded for single-tenant on-premise)."""
        return SiteSettings()

    @staticmethod
    async def update_tenant_site_settings(
        db: AsyncSession,
        updates: TenantSiteSettingsUpdate
    ) -> SiteSettings:
        """Update site settings (no-op for single-tenant on-premise)."""
        logger.info("update_tenant_site_settings is a no-op in single-tenant on-premise mode")
        return SiteSettings()

    @staticmethod
    async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Optional[SiteSettings]:
        """
        Get site settings by slug for public portal.

        In single-tenant mode, always returns the hardcoded settings
        when the slug matches or is the org UUID.
        """
        key = (slug or "").strip().lower()
        if not key:
            return None

        site = SiteSettings()
        if key == site.slug.lower() or key == str(site.id):
            return site
        return None

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
    async def get_statistics(db: AsyncSession) -> SiteGuestStatistics:
        """Get statistics for site guests."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        # Total guests
        total_result = await db.execute(
            select(func.count()).select_from(SiteGuest)
        )
        total_guests = total_result.scalar()

        # Active guests
        active_result = await db.execute(
            select(func.count()).select_from(SiteGuest).where(
                SiteGuest.is_active == True
            )
        )
        active_guests = active_result.scalar()

        # Expired guests
        expired_result = await db.execute(
            select(func.count()).select_from(SiteGuest).where(
                SiteGuest.expires_at < now
            )
        )
        expired_guests = expired_result.scalar()

        # Total access count
        access_result = await db.execute(
            select(func.sum(SiteGuest.access_count))
        )
        total_access_count = access_result.scalar() or 0

        # Recent accesses (last 24 hours)
        recent_result = await db.execute(
            select(func.count()).select_from(SiteGuestAccessLog).where(
                SiteGuestAccessLog.created_at >= yesterday
            )
        )
        recent_accesses = recent_result.scalar()

        # Documents shared (unique)
        docs_result = await db.execute(
            select(func.count(func.distinct(SiteGuestPermission.document_id))).where(
                SiteGuestPermission.document_id.isnot(None)
            )
        )
        documents_shared = docs_result.scalar()

        # Folders shared (unique)
        folders_result = await db.execute(
            select(func.count(func.distinct(SiteGuestPermission.folder_path))).where(
                SiteGuestPermission.folder_path.isnot(None)
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
