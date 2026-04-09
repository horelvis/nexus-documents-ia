"""
Site Guest Authentication Service - OTP and session management.

Handles OTP generation, verification, and session management for guest access.
"""
import logging
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import (
    SiteGuest, SiteGuestOTP, SiteGuestSession, SiteGuestPermission,
    SiteGuestAccessLog, Document, SiteGuestShare, SiteGuestShareDocument
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
    MAX_OTP_REQUESTS_PER_HOUR = 10  # Increased for development

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
        email: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Request an OTP code for guest authentication.

        Returns: {success, message, expires_in_seconds}
        """
        # Find guest by email
        guest = await SiteGuestService.get_guest_by_email(db, email)

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
    async def _send_otp_email(db: AsyncSession, guest: SiteGuest, otp_code: str, language: str = "es") -> bool:
        """Send OTP code via email using dedicated OTP template."""
        # Single-tenant: use the deployment's organization name.
        tenant_name = getattr(settings, "DEFAULT_TENANT_NAME", "NouxCube")

        try:
            success = await EmailService.send_guest_otp(
                to_email=guest.email,
                recipient_name=guest.name or guest.email,
                otp_code=otp_code,
                expiry_minutes=SiteGuestAuthService.OTP_EXPIRY_MINUTES,
                tenant_name=tenant_name,
                language=language
            )
            return success
        except Exception as e:
            logger.error(f"Failed to send OTP email: {e}")
            return False

    @staticmethod
    async def verify_otp(
        db: AsyncSession,
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
        guest = await SiteGuestService.get_guest_by_email(db, email)

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

        Includes documents from:
        1. Explicit document permissions (SiteGuestPermission)
        2. Folder permissions (SiteGuestPermission)
        3. Shares/Collections (SiteGuestShare) - NEW
        """
        documents: List[Document] = []
        doc_permission_map: Dict[UUID, Dict[str, Any]] = {}
        existing_doc_ids: set[UUID] = set()

        # =====================================
        # 1. Get shares/collections summary (NEW)
        # =====================================
        shares_result = await db.execute(
            select(SiteGuestShare).where(
                and_(
                    SiteGuestShare.guest_id == guest.id,
                    or_(
                        SiteGuestShare.expires_at.is_(None),
                        SiteGuestShare.expires_at > datetime.now(timezone.utc)
                    )
                )
            )
        )
        shares = shares_result.scalars().all()

        share_ids = [s.id for s in shares]
        share_counts: Dict[UUID, int] = {}
        if share_ids:
            counts_result = await db.execute(
                select(
                    SiteGuestShareDocument.share_id,
                    func.count(SiteGuestShareDocument.document_id)
                )
                .where(SiteGuestShareDocument.share_id.in_(share_ids))
                .group_by(SiteGuestShareDocument.share_id)
            )
            share_counts = {share_id: count for share_id, count in counts_result.all()}

        formatted_shares = [
            {
                "id": share.id,
                "name": share.name,
                "description": share.description,
                "permission_type": share.permission_type,
                "document_count": share_counts.get(share.id, 0),
                "created_at": share.created_at,
                "expires_at": share.expires_at,
            }
            for share in shares
        ]

        # =====================================
        # 2. Get explicit document permissions (Legacy)
        # =====================================
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
        legacy_doc_ids = [p.document_id for p in doc_permissions if p.document_id and p.document_id not in existing_doc_ids]

        if legacy_doc_ids:
            result = await db.execute(
                select(Document).where(Document.id.in_(legacy_doc_ids))
            )
            legacy_docs = result.scalars().all()
            for doc in legacy_docs:
                if doc.id not in existing_doc_ids:
                    documents.append(doc)
                    existing_doc_ids.add(doc.id)

        # =====================================
        # 3. Get documents from folder permissions (Legacy)
        # =====================================
        folder_paths = [p.folder_path for p in folder_permissions if p.folder_path]

        for folder_path in folder_paths:
            result = await db.execute(
                select(Document).where(Document.folder_path.startswith(folder_path))
            )
            folder_docs = result.scalars().all()
            for d in folder_docs:
                if d.id not in existing_doc_ids:
                    documents.append(d)
                    existing_doc_ids.add(d.id)

        # Build permission map for legacy permissions
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

        # Format folders (legacy only)
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
            "shares": formatted_shares,
            "total_shares": len(formatted_shares),
            "documents": formatted_docs,
            "folders": formatted_folders,
            "total_documents": len(formatted_docs),
            "total_folders": len(formatted_folders)
        }

    @staticmethod
    async def get_share_documents(
        db: AsyncSession,
        guest: SiteGuest,
        share_id: UUID
    ) -> Tuple[SiteGuestShare, List[Document]]:
        """
        Get documents for a specific share/collection visible to the current guest.

        The share must belong to the guest, be within the same tenant, and not be expired.
        """
        share_result = await db.execute(
            select(SiteGuestShare)
            .where(
                and_(
                    SiteGuestShare.id == share_id,
                    SiteGuestShare.guest_id == guest.id,
                    or_(
                        SiteGuestShare.expires_at.is_(None),
                        SiteGuestShare.expires_at > datetime.now(timezone.utc)
                    )
                )
            )
        )
        share = share_result.scalar_one_or_none()
        if not share:
            raise ValueError("Share not found")

        docs_result = await db.execute(
            select(Document)
            .join(SiteGuestShareDocument, SiteGuestShareDocument.document_id == Document.id)
            .where(SiteGuestShareDocument.share_id == share_id)
            .order_by(Document.updated_at.desc())
        )
        documents = docs_result.scalars().all()
        return share, documents

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

        Checks permissions from:
        1. SiteGuestShares (collections) - NEW
        2. Explicit document permissions (SiteGuestPermission)
        3. Folder permissions (SiteGuestPermission)
        """
        # =====================================
        # 1. Check SiteGuestShares (NEW - Collections)
        # =====================================
        share_doc_result = await db.execute(
            select(SiteGuestShare).join(
                SiteGuestShareDocument,
                SiteGuestShareDocument.share_id == SiteGuestShare.id
            ).where(
                and_(
                    SiteGuestShare.guest_id == guest.id,
                    SiteGuestShareDocument.document_id == document_id,
                    or_(
                        SiteGuestShare.expires_at.is_(None),
                        SiteGuestShare.expires_at > datetime.now(timezone.utc)
                    )
                )
            )
        )
        share = share_doc_result.scalar_one_or_none()

        if share:
            # Document is in a share - check permission type
            if permission_type == "view":
                return True  # All shares allow view
            elif permission_type == "download":
                return share.permission_type in ["download", "upload"]
            elif permission_type == "upload":
                return share.permission_type == "upload"

        # =====================================
        # 2. Check explicit document permission (Legacy)
        # =====================================
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

        # =====================================
        # 3. Check folder permission (Legacy)
        # =====================================
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

        return False


# Singleton instance
site_guest_auth_service = SiteGuestAuthService()
