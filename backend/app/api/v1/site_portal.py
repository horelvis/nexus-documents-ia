"""
Site Portal API - Public endpoints for guest access.

Provides OTP authentication, content access, and document operations for Site Guests.
These endpoints are PUBLIC (no Clerk auth) - authentication is via session token.
"""
import logging
import os
import shutil
import tempfile
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_database import get_async_db
from app.db.models import SiteGuest, Document
from app.services.document_preview_service import DocumentPreviewService
from app.services.site_guest_service import SiteGuestService
from app.services.site_guest_auth_service import SiteGuestAuthService
from app.schemas.site_guest import (
    OTPRequestPayload, OTPRequestResponse,
    OTPVerifyPayload, OTPVerifyResponse,
    SiteGuestResponse,
    TenantSiteInfo, GuestMeResponse,
    PortalContentResponse, PortalDocumentInfo,
    PortalShareInfo, PortalShareDocumentsResponse,
)
from app.schemas.general import SuccessResponse
from app.services.async_storage_client import AsyncStorageClient
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================
# DEPENDENCY: Get current guest from session token
# =====================================

async def get_current_guest(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_async_db)
) -> SiteGuest:
    """
    Dependency to validate session token and return the authenticated guest.

    Expects: Authorization: Bearer <session_token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.replace("Bearer ", "")
    guest = await SiteGuestAuthService.validate_session(db, token)

    if not guest:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return guest


async def get_optional_guest(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_async_db)
) -> Optional[SiteGuest]:
    """
    Optional dependency - returns guest if authenticated, None otherwise.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.replace("Bearer ", "")
    return await SiteGuestAuthService.validate_session(db, token)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    # Check for proxy headers
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# =====================================
# TENANT RESOLUTION (PUBLIC)
# =====================================

@router.get("/t/{tenant_slug}", response_model=TenantSiteInfo)
async def get_tenant_by_slug(
    tenant_slug: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get tenant site info by slug.

    This is a PUBLIC endpoint used by the portal frontend to resolve tenant by URL.
    Returns basic tenant info if the site is enabled.
    """
    tenant = await SiteGuestService.get_tenant_by_slug(db, tenant_slug)

    if not tenant:
        raise HTTPException(status_code=404, detail="Site not found")

    if not tenant.site_enabled:
        raise HTTPException(status_code=404, detail="Site not available")

    return TenantSiteInfo(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        slug=tenant.slug or str(tenant.id),
        site_enabled=tenant.site_enabled,
        logo_url=tenant.site_logo_url,
        welcome_message=tenant.site_welcome_message
    )


# =====================================
# OTP AUTHENTICATION (PUBLIC)
# =====================================

@router.post("/t/{tenant_slug}/request-otp", response_model=OTPRequestResponse)
async def request_otp(
    tenant_slug: str,
    payload: OTPRequestPayload,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Request an OTP code for guest authentication.

    Sends a 6-digit code to the guest's email if they are registered and active.
    For security, always returns success message even if email not found.
    """
    # Resolve tenant
    tenant = await SiteGuestService.get_tenant_by_slug(db, tenant_slug)
    if not tenant or not tenant.site_enabled:
        raise HTTPException(status_code=404, detail="Site not found")

    ip_address = get_client_ip(request)

    result = await SiteGuestAuthService.request_otp(
        db,
        tenant.id,
        payload.email,
        ip_address
    )

    return OTPRequestResponse(
        success=result["success"],
        message=result["message"],
        expires_in_seconds=result["expires_in_seconds"]
    )


@router.post("/t/{tenant_slug}/verify-otp", response_model=OTPVerifyResponse)
async def verify_otp(
    tenant_slug: str,
    payload: OTPVerifyPayload,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verify OTP code and create session.

    Returns a session token if successful, which should be used for subsequent requests.
    Session expires after 8 hours.
    """
    # Resolve tenant
    tenant = await SiteGuestService.get_tenant_by_slug(db, tenant_slug)
    if not tenant or not tenant.site_enabled:
        raise HTTPException(status_code=404, detail="Site not found")

    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    result = await SiteGuestAuthService.verify_otp(
        db,
        tenant.id,
        payload.email,
        payload.otp_code,
        ip_address,
        user_agent
    )

    if not result["success"]:
        return OTPVerifyResponse(
            success=False,
            session_token=None,
            expires_at=None,
            guest=None,
            error=result["error"]
        )

    return OTPVerifyResponse(
        success=True,
        session_token=result["session_token"],
        expires_at=result["expires_at"],
        guest=_guest_to_response(result["guest"]) if result["guest"] else None,
        error=None
    )


# =====================================
# SESSION MANAGEMENT
# =====================================

@router.post("/logout", response_model=SuccessResponse)
async def logout(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Logout and revoke the current session.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No session token provided")

    token = authorization.replace("Bearer ", "")
    ip_address = get_client_ip(request)

    success = await SiteGuestAuthService.logout(db, token, ip_address)

    if success:
        return SuccessResponse(message="Logged out successfully")
    else:
        raise HTTPException(status_code=400, detail="Invalid session")


@router.get("/me", response_model=GuestMeResponse)
async def get_current_guest_info(
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest)
):
    """
    Get the currently authenticated guest's info.

    Returns guest details and session information.
    """
    # Get tenant info
    tenant = await SiteGuestService.get_tenant_site_settings(db, guest.tenant_id)
    if not tenant:
        raise HTTPException(status_code=500, detail="Tenant not found")

    # Get session info
    from app.services.site_guest_auth_service import SiteGuestAuthService
    # Session info is already validated in dependency

    return GuestMeResponse(
        guest=_guest_to_response(guest),
        tenant_name=tenant.name,
        tenant_logo_url=tenant.site_logo_url,
        session_expires_at=guest.last_access_at  # Approximate; actual is in session
    )


# =====================================
# CONTENT ACCESS
# =====================================

@router.get("/content", response_model=PortalContentResponse)
async def get_accessible_content(
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest)
):
    """
    Get all documents and folders accessible to the current guest.

    Returns content based on explicit permissions granted by admin.
    """
    content = await SiteGuestAuthService.get_accessible_content(db, guest)

    shares = [
        PortalShareInfo(
            id=s["id"],
            name=s["name"],
            description=s.get("description"),
            permission_type=s["permission_type"],
            document_count=s["document_count"],
            created_at=s["created_at"],
            expires_at=s.get("expires_at"),
        )
        for s in content.get("shares", [])
    ]

    documents = [
        PortalDocumentInfo(
            id=doc["id"],
            title=doc["title"],
            filename=doc["filename"],
            file_type=doc["file_type"],
            file_size=doc["file_size"],
            mime_type=doc["mime_type"],
            folder_path=doc["folder_path"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            can_view=doc["can_view"],
            can_download=doc["can_download"]
        )
        for doc in content["documents"]
    ]

    from app.schemas.site_guest import PortalFolderInfo
    folders = [
        PortalFolderInfo(
            path=folder["path"],
            name=folder["name"],
            document_count=folder["document_count"],
            can_view=folder["can_view"],
            can_download=folder["can_download"],
            can_upload=folder["can_upload"]
        )
        for folder in content["folders"]
    ]

    return PortalContentResponse(
        shares=shares,
        total_shares=content.get("total_shares", len(shares)),
        documents=documents,
        folders=folders,
        total_documents=content["total_documents"],
        total_folders=content["total_folders"]
    )


@router.get("/shares/{share_id}/documents", response_model=PortalShareDocumentsResponse)
async def get_share_documents(
    share_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest)
):
    """
    Get documents for a specific share/collection.

    Used by the portal UI to load share contents on demand.
    """
    try:
        share, documents = await SiteGuestAuthService.get_share_documents(db, guest, share_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    can_download = share.permission_type in ["download", "upload"]
    formatted_docs = [
        PortalDocumentInfo(
            id=doc.id,
            title=doc.title,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            mime_type=doc.mime_type,
            folder_path=doc.folder_path,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            can_view=True,
            can_download=can_download,
        )
        for doc in documents
    ]

    return PortalShareDocumentsResponse(
        share=PortalShareInfo(
            id=share.id,
            name=share.name,
            description=share.description,
            permission_type=share.permission_type,
            document_count=len(formatted_docs),
            created_at=share.created_at,
            expires_at=share.expires_at,
        ),
        documents=formatted_docs,
        total_documents=len(formatted_docs),
    )


@router.get("/documents/{document_id}", response_model=PortalDocumentInfo)
async def get_document_info(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest)
):
    """
    Get metadata for a specific document.

    Requires view permission for the document.
    """
    # Check permission
    has_permission = await SiteGuestAuthService.check_document_permission(
        db, guest, document_id, "view"
    )

    if not has_permission:
        raise HTTPException(status_code=403, detail="Access denied to this document")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Log access
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    await SiteGuestService.log_guest_action(
        db, guest.id, "view_document",
        document_id=document_id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    # Check download permission
    can_download = await SiteGuestAuthService.check_document_permission(
        db, guest, document_id, "download"
    )

    return PortalDocumentInfo(
        id=document.id,
        title=document.title,
        filename=document.filename,
        file_type=document.file_type,
        file_size=document.file_size,
        mime_type=document.mime_type,
        folder_path=document.folder_path,
        created_at=document.created_at,
        updated_at=document.updated_at,
        can_view=True,
        can_download=can_download
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest)
):
    """
    Download a document.

    Requires download permission for the document.
    Returns a signed URL or streams the file content.
    """
    # Check permission
    has_permission = await SiteGuestAuthService.check_document_permission(
        db, guest, document_id, "download"
    )

    if not has_permission:
        raise HTTPException(status_code=403, detail="Download not permitted for this document")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Log download
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    await SiteGuestService.log_guest_action(
        db, guest.id, "download_document",
        document_id=document_id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    # Generate signed URL for download
    try:
        # Get tenant for bucket name
        tenant = await SiteGuestService.get_tenant_site_settings(db, guest.tenant_id)
        if not tenant:
            raise HTTPException(status_code=500, detail="Tenant not found")

        storage_client = AsyncStorageClient(
            tenant_id=str(guest.tenant_id),
            user_id=str(document.created_by),
            bucket_name=tenant.bucket_name
        )
        signed_url, expires_at = await storage_client.generate_download_signed_url(
            document.file_path,
            expiration=3600  # 1 hour
        )

        # Return redirect to signed URL
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=signed_url, status_code=302)

    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download link")


@router.get("/documents/{document_id}/view")
async def view_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest)
):
    """
    Get a view URL for a document.

    Requires view permission. Returns a URL to a PDF preview rendered in the frontend (not a direct download of the original file).
    """
    # Check permission
    has_permission = await SiteGuestAuthService.check_document_permission(
        db, guest, document_id, "view"
    )

    if not has_permission:
        raise HTTPException(status_code=403, detail="View not permitted for this document")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Log view
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    await SiteGuestService.log_guest_action(
        db, guest.id, "view_document_content",
        document_id=document_id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    try:
        # Get tenant for bucket name
        tenant = await SiteGuestService.get_tenant_site_settings(db, guest.tenant_id)
        if not tenant:
            raise HTTPException(status_code=500, detail="Tenant not found")

        return {
            "view_url": f"/api/v1/site-portal/documents/{document_id}/preview-pdf",
            "content_type": "application/pdf",
        }

    except Exception as e:
        logger.error(f"Failed to generate view URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate view link")


@router.get("/documents/{document_id}/preview-pdf")
async def view_document_preview_pdf(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    guest: SiteGuest = Depends(get_current_guest),
):
    """
    Stream a PDF preview for a document (Portal).

    Requires view permission. Uses the existing preview pipeline (Gotenberg) and caches the generated PDF in storage.
    """
    has_permission = await SiteGuestAuthService.check_document_permission(
        db, guest, document_id, "view"
    )
    if not has_permission:
        raise HTTPException(status_code=403, detail="View not permitted for this document")

    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    tenant = await SiteGuestService.get_tenant_site_settings(db, guest.tenant_id)
    if not tenant:
        raise HTTPException(status_code=500, detail="Tenant not found")

    storage_client = AsyncStorageClient(
        tenant_id=str(guest.tenant_id),
        user_id=str(document.created_by),
        bucket_name=tenant.bucket_name,
    )

    preview_key = f"previews/{guest.tenant_id}/{document_id}/{document_id}_preview.pdf"

    # Generate preview if missing
    if not await storage_client.get_file_info(preview_key):
        temp_dir = tempfile.mkdtemp()
        try:
            temp_file_path = os.path.join(temp_dir, document.filename or "document")
            file_content = await storage_client.download_file(document.file_path or "")
            if not file_content:
                raise HTTPException(status_code=500, detail="Could not download document for preview")

            with open(temp_file_path, "wb") as f:
                f.write(file_content)

            preview_service = DocumentPreviewService(
                tenant_id=str(guest.tenant_id),
                user_id=str(document.created_by),
            )
            try:
                preview_result = await preview_service.generate_preview(
                    document_id=str(document_id),
                    file_path=temp_file_path,
                    filename=document.filename or "document",
                    force_regenerate=False,
                )
                if not preview_result.get("pdf_available"):
                    raise HTTPException(status_code=415, detail="Preview not available for this document type")

                pdf_local_path = preview_result.get("pdf_local_path")
                if not pdf_local_path or not os.path.exists(pdf_local_path):
                    raise HTTPException(status_code=500, detail="Preview generation failed")

                with open(pdf_local_path, "rb") as f:
                    pdf_bytes = f.read()

                await storage_client.upload_file(
                    file=pdf_bytes,
                    filename=preview_key,
                    metadata={
                        "document_id": str(document_id),
                        "type": "site_portal_preview_pdf",
                        "original_filename": document.filename,
                    },
                )
            finally:
                await preview_service.cleanup()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    pdf_bytes = await storage_client.download_file(preview_key)
    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="Could not retrieve preview PDF")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{document.filename or "preview.pdf"}"',
            "Cache-Control": "private, max-age=300",
        },
    )


# =====================================
# HELPER FUNCTIONS
# =====================================

def _guest_to_response(guest) -> SiteGuestResponse:
    """Convert SiteGuest model to response schema."""
    return SiteGuestResponse(
        id=guest.id,
        tenant_id=guest.tenant_id,
        email=guest.email,
        name=guest.name,
        is_active=guest.is_active,
        can_view=guest.can_view,
        can_download=guest.can_download,
        can_upload=guest.can_upload,
        expires_at=guest.expires_at,
        invited_by_user_id=guest.invited_by_user_id,
        invited_at=guest.invited_at,
        last_access_at=guest.last_access_at,
        access_count=guest.access_count,
        created_at=guest.created_at,
        updated_at=guest.updated_at,
        is_expired=guest.is_expired(),
        is_valid=guest.is_valid()
    )
