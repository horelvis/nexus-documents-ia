"""
Site Guest Authentication Service - OTP and session management.

Handles OTP generation, verification, and session management for guest access.
"""
import logging
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    SiteGuest, SiteGuestOTP, SiteGuestSession, SiteGuestPermission,
    SiteGuestAccessLog, Tenant, Document
)
from app.services.email_service import EmailService
from app.services.site_guest_service import SiteGuestService
from app.core.config import settings

logger = logging.getLogger(__name__)


class SiteGuestAuthService:
    """Service for guest authentication via OTP."""

    # Configuration
    OTP_EXPIRY_MINUTES = 10
    OTP_LENGTH = 6
    SESSION_EXPIRY_HOURS = 8
    MAX_OTP_ATTEMPTS = 5
    MAX_OTP_REQUESTS_PER_HOUR = 3

    # =====================================
    # OTP MANAGEMENT
    # =====================================

    @staticmethod
    def _generate_otp() -> str:
        """Generate a 6-digit OTP code."""
        return ''.join([str(secrets.randbelow(10)) for _ in range(SiteGuestAuthService.OTP_LENGTH)])

    @staticmethod
    def _hash_otp(otp: str) -> str:
        """Hash OTP code with SHA256."""
        return hashlib.sha256(otp.encode()).hexdigest()

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash session token with SHA256."""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    async def request_otp(
        db: AsyncSession,
        tenant_id: UUID,
        email: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Request an OTP code for guest authentication.

        Returns: {success, message, expires_in_seconds}
        """
        # Find guest by email
        guest = await SiteGuestService.get_guest_by_email(db, tenant_id, email)

        if not guest:
            # Don't reveal if email exists or not (security)
            logger.warning(f"OTP requested for non-existent guest: {email}")
            return {
                "success": True,
                "message": "If the email is registered, you will receive an OTP code shortly.",
                "expires_in_seconds": SiteGuestAuthService.OTP_EXPIRY_MINUTES * 60
            }

        if not guest.is_valid():
            logger.warning(f"OTP requested for invalid/expired guest: {email}")
            return {
                "success": False,
                "message": "Your access has expired or been revoked.",
                "expires_in_seconds": 0
            }

        # Rate limiting: check OTP requests in last hour
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_otps = await db.execute(
            select(func.count()).where(
                and_(
                    SiteGuestOTP.guest_id == guest.id,
                    SiteGuestOTP.created_at >= one_hour_ago
                )
            )
        )
        if recent_otps.scalar() >= SiteGuestAuthService.MAX_OTP_REQUESTS_PER_HOUR:
            logger.warning(f"OTP rate limit exceeded for guest: {email}")
            return {
                "success": False,
                "message": "Too many OTP requests. Please try again later.",
                "expires_in_seconds": 0
            }

        # Invalidate any existing unused OTPs
        existing_otps = await db.execute(
            select(SiteGuestOTP).where(
                and_(
                    SiteGuestOTP.guest_id == guest.id,
                    SiteGuestOTP.used_at.is_(None)
                )
            )
        )
        for otp in existing_otps.scalars():
            otp.used_at = datetime.now(timezone.utc)  # Mark as used

        # Generate new OTP
        otp_code = SiteGuestAuthService._generate_otp()
        otp_hash = SiteGuestAuthService._hash_otp(otp_code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=SiteGuestAuthService.OTP_EXPIRY_MINUTES)

        otp = SiteGuestOTP(
            guest_id=guest.id,
            otp_hash=otp_hash,
            expires_at=expires_at,
            ip_address=ip_address
        )
        db.add(otp)
        await db.commit()

        # Log the action
        await SiteGuestService.log_guest_action(
            db, guest.id, "otp_request",
            ip_address=ip_address,
            details={"email": email}
        )

        # Send OTP via email
        await SiteGuestAuthService._send_otp_email(db, guest, otp_code)

        logger.info(f"OTP generated for guest: {email}")
        return {
            "success": True,
            "message": "OTP code sent to your email.",
            "expires_in_seconds": SiteGuestAuthService.OTP_EXPIRY_MINUTES * 60
        }

    @staticmethod
    async def _send_otp_email(db: AsyncSession, guest: SiteGuest, otp_code: str) -> bool:
        """Send OTP code via email."""
        # Get tenant info
        tenant = await db.execute(
            select(Tenant).where(Tenant.id == guest.tenant_id)
        )
        tenant = tenant.scalar_one_or_none()

        try:
            success = await EmailService.send_share_notification(
                to_email=guest.email,
                subject=f"Your access code for {tenant.name if tenant else 'Site Portal'}",
                template_data={
                    "recipient_name": guest.name or guest.email,
                    "sender_name": tenant.name if tenant else "Site Portal",
                    "document_name": "Access Code",
                    "share_link": "",  # No link, just the code
                    "message": f"Your access code is: <strong style='font-size: 24px; letter-spacing: 5px;'>{otp_code}</strong><br><br>This code expires in {SiteGuestAuthService.OTP_EXPIRY_MINUTES} minutes.",
                    "expires_at": None
                }
            )
            return success
        except Exception as e:
            logger.error(f"Failed to send OTP email: {e}")
            return False

    @staticmethod
    async def verify_otp(
        db: AsyncSession,
        tenant_id: UUID,
        email: str,
        otp_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify OTP code and create session.

        Returns: {success, session_token, expires_at, guest, error}
        """
        # Find guest
        guest = await SiteGuestService.get_guest_by_email(db, tenant_id, email)

        if not guest:
            return {
                "success": False,
                "session_token": None,
                "expires_at": None,
                "guest": None,
                "error": "Invalid email or OTP code"
            }

        if not guest.is_valid():
            return {
                "success": False,
                "session_token": None,
                "expires_at": None,
                "guest": None,
                "error": "Your access has expired or been revoked"
            }

        # Find valid OTP
        now = datetime.now(timezone.utc)
        otp_hash = SiteGuestAuthService._hash_otp(otp_code)

        result = await db.execute(
            select(SiteGuestOTP).where(
                and_(
                    SiteGuestOTP.guest_id == guest.id,
                    SiteGuestOTP.otp_hash == otp_hash,
                    SiteGuestOTP.expires_at > now,
                    SiteGuestOTP.used_at.is_(None),
                    SiteGuestOTP.attempts < SiteGuestAuthService.MAX_OTP_ATTEMPTS
                )
            )
        )
        otp = result.scalar_one_or_none()

        if not otp:
            # Check if there's an OTP with attempts to increment
            result = await db.execute(
                select(SiteGuestOTP).where(
                    and_(
                        SiteGuestOTP.guest_id == guest.id,
                        SiteGuestOTP.expires_at > now,
                        SiteGuestOTP.used_at.is_(None)
                    )
                ).order_by(SiteGuestOTP.created_at.desc()).limit(1)
            )
            latest_otp = result.scalar_one_or_none()
            if latest_otp:
                latest_otp.attempts += 1
                await db.commit()

            await SiteGuestService.log_guest_action(
                db, guest.id, "otp_verify_failed",
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                error_message="Invalid or expired OTP"
            )

            return {
                "success": False,
                "session_token": None,
                "expires_at": None,
                "guest": None,
                "error": "Invalid or expired OTP code"
            }

        # Mark OTP as used
        otp.used_at = now

        # Create session
        session_token = secrets.token_urlsafe(32)
        session_token_hash = SiteGuestAuthService._hash_token(session_token)
        session_expires_at = now + timedelta(hours=SiteGuestAuthService.SESSION_EXPIRY_HOURS)

        session = SiteGuestSession(
            guest_id=guest.id,
            session_token_hash=session_token_hash,
            expires_at=session_expires_at,
            last_activity_at=now,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(session)

        # Update guest access tracking
        guest.last_access_at = now
        guest.access_count += 1

        await db.commit()
        await db.refresh(guest)

        # Log successful login
        await SiteGuestService.log_guest_action(
            db, guest.id, "login",
            session_id=session.id,
            ip_address=ip_address,
            user_agent=user_agent
        )

        logger.info(f"OTP verified for guest: {email}, session created")
        return {
            "success": True,
            "session_token": session_token,
            "expires_at": session_expires_at,
            "guest": guest,
            "error": None
        }

    # =====================================
    # SESSION MANAGEMENT
    # =====================================

    @staticmethod
    async def validate_session(
        db: AsyncSession,
        session_token: str
    ) -> Optional[SiteGuest]:
        """
        Validate a session token and return the associated guest.

        Returns: SiteGuest or None if invalid
        """
        session_token_hash = SiteGuestAuthService._hash_token(session_token)
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(SiteGuestSession).where(
                and_(
                    SiteGuestSession.session_token_hash == session_token_hash,
                    SiteGuestSession.is_active == True,
                    SiteGuestSession.expires_at > now,
                    SiteGuestSession.revoked_at.is_(None)
                )
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        # Get guest
        guest = await SiteGuestService.get_guest(db, session.guest_id)
        if not guest or not guest.is_valid():
            return None

        # Update last activity
        session.last_activity_at = now
        await db.commit()

        return guest

    @staticmethod
    async def get_session_by_token(
        db: AsyncSession,
        session_token: str
    ) -> Optional[SiteGuestSession]:
        """Get session by token."""
        session_token_hash = SiteGuestAuthService._hash_token(session_token)

        result = await db.execute(
            select(SiteGuestSession).where(
                SiteGuestSession.session_token_hash == session_token_hash
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def logout(
        db: AsyncSession,
        session_token: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """Logout and revoke session."""
        session = await SiteGuestAuthService.get_session_by_token(db, session_token)

        if not session:
            return False

        session.is_active = False
        session.revoked_at = datetime.now(timezone.utc)

        # Log logout
        await SiteGuestService.log_guest_action(
            db, session.guest_id, "logout",
            session_id=session.id,
            ip_address=ip_address
        )

        await db.commit()
        logger.info(f"Guest session logged out: {session.id}")
        return True

    # =====================================
    # CONTENT ACCESS
    # =====================================

    @staticmethod
    async def get_accessible_content(
        db: AsyncSession,
        guest: SiteGuest
    ) -> Dict[str, Any]:
        """
        Get all content accessible to a guest.

        Returns: {documents: [], folders: [], total_documents, total_folders}
        """
        # Get explicit document permissions
        doc_perms = await db.execute(
            select(SiteGuestPermission).where(
                and_(
                    SiteGuestPermission.guest_id == guest.id,
                    SiteGuestPermission.document_id.isnot(None)
                )
            )
        )
        doc_permissions = doc_perms.scalars().all()

        # Get folder permissions
        folder_perms = await db.execute(
            select(SiteGuestPermission).where(
                and_(
                    SiteGuestPermission.guest_id == guest.id,
                    SiteGuestPermission.folder_path.isnot(None)
                )
            )
        )
        folder_permissions = folder_perms.scalars().all()

        # Get documents from explicit permissions
        document_ids = [p.document_id for p in doc_permissions if p.document_id]
        documents = []

        if document_ids:
            result = await db.execute(
                select(Document).where(Document.id.in_(document_ids))
            )
            documents = result.scalars().all()

        # Get documents from folder permissions
        folder_paths = [p.folder_path for p in folder_permissions if p.folder_path]

        for folder_path in folder_paths:
            result = await db.execute(
                select(Document).where(
                    and_(
                        Document.tenant_id == guest.tenant_id,
                        Document.folder_path.startswith(folder_path)
                    )
                )
            )
            folder_docs = result.scalars().all()
            documents.extend([d for d in folder_docs if d.id not in [doc.id for doc in documents]])

        # Build permission map for documents
        doc_permission_map = {}
        for perm in doc_permissions:
            if perm.document_id not in doc_permission_map:
                doc_permission_map[perm.document_id] = {"can_view": False, "can_download": False}
            if perm.permission_type == "view":
                doc_permission_map[perm.document_id]["can_view"] = True
            elif perm.permission_type == "download":
                doc_permission_map[perm.document_id]["can_download"] = True

        # Format documents with permissions
        formatted_docs = []
        for doc in documents:
            perms = doc_permission_map.get(doc.id, {"can_view": guest.can_view, "can_download": guest.can_download})
            formatted_docs.append({
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "folder_path": doc.folder_path,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "can_view": perms.get("can_view", guest.can_view),
                "can_download": perms.get("can_download", guest.can_download)
            })

        # Format folders
        formatted_folders = []
        for perm in folder_permissions:
            folder_name = perm.folder_path.split("/")[-1] if perm.folder_path else "Root"
            formatted_folders.append({
                "path": perm.folder_path,
                "name": folder_name,
                "document_count": sum(1 for d in documents if d.folder_path and d.folder_path.startswith(perm.folder_path)),
                "can_view": perm.permission_type in ["view", "download", "upload"],
                "can_download": perm.permission_type in ["download", "upload"],
                "can_upload": perm.permission_type == "upload"
            })

        return {
            "documents": formatted_docs,
            "folders": formatted_folders,
            "total_documents": len(formatted_docs),
            "total_folders": len(formatted_folders)
        }

    @staticmethod
    async def check_document_permission(
        db: AsyncSession,
        guest: SiteGuest,
        document_id: UUID,
        permission_type: str
    ) -> bool:
        """
        Check if guest has specific permission for a document.

        permission_type: "view", "download", "upload"
        """
        # Check explicit document permission
        result = await db.execute(
            select(SiteGuestPermission).where(
                and_(
                    SiteGuestPermission.guest_id == guest.id,
                    SiteGuestPermission.document_id == document_id,
                    SiteGuestPermission.permission_type == permission_type
                )
            )
        )
        if result.scalar_one_or_none():
            return True

        # Check folder permission
        doc_result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()

        if document and document.folder_path:
            # Check if any folder permission covers this document
            folder_perms = await db.execute(
                select(SiteGuestPermission).where(
                    and_(
                        SiteGuestPermission.guest_id == guest.id,
                        SiteGuestPermission.folder_path.isnot(None),
                        SiteGuestPermission.permission_type == permission_type
                    )
                )
            )
            for perm in folder_perms.scalars():
                if document.folder_path.startswith(perm.folder_path):
                    return True

        # Check default guest permissions
        if permission_type == "view" and guest.can_view:
            # Only if document is in an allowed folder
            pass  # Need explicit permission
        elif permission_type == "download" and guest.can_download:
            pass  # Need explicit permission

        return False


# Singleton instance
site_guest_auth_service = SiteGuestAuthService()
