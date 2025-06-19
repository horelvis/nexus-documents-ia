from typing import List, Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4
import secrets
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import (
    get_current_user_async,
    get_current_tenant_id_async
)
from app.db.async_database import get_async_db
from app.db.models import User, Document, DocumentShare, DocumentShareAccessLog, DocumentShareRecipient
from app.schemas.document_share import (
    DocumentShareCreate,
    DocumentShareUpdate,
    DocumentShareResponse,
    DocumentShareListResponse,
    DocumentShareAccessRequest,
    DocumentShareAccessResponse,
    ShareAccessLogListResponse,
    BulkShareResult,
    ShareStatistics
)
from app.services.document_share_service import DocumentShareService
from app.core.security import get_password_hash, verify_password
from app.core.config import settings
from sqlalchemy import select, func

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=DocumentShareResponse)
async def create_document_share(
    share_data: DocumentShareCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Create a new share link for a document.
    
    Features:
    - Generate unique, secure share token
    - Optional password protection
    - Optional expiration date
    - Optional access count limit
    - Optional recipient email notification
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        
        # Verify document exists and user has access
        result = await db.execute(
            select(Document).filter(
                and_(
                    Document.id == share_data.document_id,
                    Document.tenant_id == UUID(tenant_id)
                )
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Create share
        share = await share_service.create_share(
            db=db,
            document_id=share_data.document_id,
            share_type=share_data.share_type,
            expires_at=share_data.expires_at,
            max_access_count=share_data.max_access_count,
            password=share_data.password,
            recipient_email=share_data.recipient_email,
            recipient_name=share_data.recipient_name,
            share_message=share_data.share_message,
            permissions=share_data.permissions,
            recipients=share_data.recipients
        )
        
        return share
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating document share: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create share link")


@router.post("/bulk", response_model=BulkShareResult)
async def create_bulk_shares(
    share_data: DocumentShareCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Create multiple share links for a document with different recipients.
    """
    if not share_data.recipients:
        raise HTTPException(status_code=400, detail="Recipients list is required for bulk sharing")
    
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        
        # Verify document exists
        result = await db.execute(
            select(Document).filter(
                and_(
                    Document.id == share_data.document_id,
                    Document.tenant_id == UUID(tenant_id)
                )
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Create shares for each recipient
        result = await share_service.create_bulk_shares(
            db=db,
            document_id=share_data.document_id,
            recipients=share_data.recipients,
            share_type=share_data.share_type,
            expires_at=share_data.expires_at,
            max_access_count=share_data.max_access_count,
            password=share_data.password,
            share_message=share_data.share_message,
            permissions=share_data.permissions
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error creating bulk shares: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create bulk shares")


@router.get("", response_model=DocumentShareListResponse)
async def list_document_shares(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_id: Optional[UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    """
    List all document shares for the current tenant.
    
    Filters:
    - document_id: Filter by specific document
    - is_active: Filter by active/inactive shares
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        
        shares, total = await share_service.list_shares(
            db=db,
            document_id=document_id,
            is_active=is_active,
            page=page,
            per_page=per_page
        )
        
        return DocumentShareListResponse(
            shares=shares,
            total=total,
            page=page,
            per_page=per_page
        )
        
    except Exception as e:
        logger.error(f"Error listing shares: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list shares")


@router.get("/statistics", response_model=ShareStatistics)
async def get_share_statistics(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_id: Optional[UUID] = Query(None)
):
    """
    Get sharing statistics for the tenant or a specific document.
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        stats = await share_service.get_statistics(db=db, document_id=document_id)
        return stats
        
    except Exception as e:
        logger.error(f"Error getting share statistics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@router.get("/{share_id}", response_model=DocumentShareResponse)
async def get_document_share(
    share_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get details of a specific document share.
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        share = await share_service.get_share(db=db, share_id=share_id)
        
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        
        return share
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting share: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get share")


@router.patch("/{share_id}", response_model=DocumentShareResponse)
async def update_document_share(
    share_id: UUID,
    update_data: DocumentShareUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Update a document share's settings.
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        share = await share_service.update_share(
            db=db,
            share_id=share_id,
            update_data=update_data
        )
        
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        
        return share
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating share: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update share")


@router.delete("/{share_id}")
async def revoke_document_share(
    share_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Revoke a document share link.
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        success = await share_service.revoke_share(
            db=db,
            share_id=share_id,
            revoked_by=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Share not found")
        
        return {"message": "Share revoked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking share: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to revoke share")


@router.get("/{share_id}/logs", response_model=ShareAccessLogListResponse)
async def get_share_access_logs(
    share_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    """
    Get access logs for a specific share.
    """
    try:
        share_service = DocumentShareService(tenant_id=tenant_id, user_id=str(current_user.id))
        
        # Verify share belongs to tenant
        result = await db.execute(
            select(DocumentShare).filter(
                and_(
                    DocumentShare.id == share_id,
                    DocumentShare.tenant_id == UUID(tenant_id)
                )
            )
        )
        share = result.scalar_one_or_none()
        
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        
        logs, total = await share_service.get_access_logs(
            db=db,
            share_id=share_id,
            page=page,
            per_page=per_page
        )
        
        return ShareAccessLogListResponse(
            logs=logs,
            total=total,
            page=page,
            per_page=per_page
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting access logs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get access logs")


# Public endpoints for accessing shared documents (no authentication required)

@router.get("/access/{share_token}", response_model=DocumentShareAccessResponse)
async def access_shared_document(
    share_token: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    password: Optional[str] = Query(None)
):
    """
    Access a shared document using a share token.
    This endpoint is public and doesn't require authentication.
    """
    try:
        # Find share by token
        result = await db.execute(
            select(DocumentShare).options(selectinload(DocumentShare.document)).filter(
                DocumentShare.share_token == share_token
            )
        )
        share = result.scalar_one_or_none()
        
        if not share:
            raise HTTPException(status_code=404, detail="Invalid share link")
        
        # Check if share is valid
        if not share.is_valid():
            raise HTTPException(status_code=403, detail="Share link has expired or is no longer valid")
        
        # Check password if required
        if share.password_hash:
            if not password:
                return DocumentShareAccessResponse(
                    success=False,
                    requires_password=True,
                    error="Password required"
                )
            
            if not verify_password(password, share.password_hash):
                return DocumentShareAccessResponse(
                    success=False,
                    requires_password=True,
                    error="Invalid password"
                )
        
        # Get document info
        document = share.document
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Log access
        access_log = DocumentShareAccessLog(
            share_id=share.id,
            document_id=document.id,
            tenant_id=share.tenant_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referrer=request.headers.get("referer"),
            action="view",
            success=True
        )
        db.add(access_log)
        
        # Increment access count
        share.increment_access_count()
        
        # Update recipient access if email matches
        if share.recipient_email:
            result = await db.execute(
                select(DocumentShareRecipient).filter(
                    and_(
                        DocumentShareRecipient.share_id == share.id,
                        DocumentShareRecipient.email == share.recipient_email
                    )
                )
            )
            recipient = result.scalar_one_or_none()
            
            if recipient:
                if not recipient.first_accessed_at:
                    recipient.first_accessed_at = datetime.now(timezone.utc)
                recipient.last_accessed_at = datetime.now(timezone.utc)
                recipient.access_count += 1
        
        await await db.commit()
        
        # Generate temporary access URL
        from app.services.storage_service import StorageService
        storage_service = StorageService(str(share.tenant_id), str(share.created_by))
        
        # Get signed URL for document access
        if share.share_type == "download":
            signed_url = storage_service.generate_download_url(document.file_path, expiration_minutes=60)
        else:  # view
            signed_url = f"/api/v1/shares/view/{share_token}?token={secrets.token_urlsafe(32)}"
        
        return DocumentShareAccessResponse(
            success=True,
            document_url=signed_url,
            document_info={
                "title": document.title,
                "filename": document.filename,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "description": document.description,
                "share_type": share.share_type,
                "mime_type": document.mime_type
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accessing shared document: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to access document")


@router.get("/view/{share_token}")
async def view_shared_document(
    share_token: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    token: str = Query(...)  # Temporary access token
):
    """
    Stream a shared document for viewing.
    This endpoint is public but requires a valid temporary token.
    """
    try:
        # Find share by token
        result = await db.execute(
            select(DocumentShare).options(selectinload(DocumentShare.document)).filter(
                DocumentShare.share_token == share_token
            )
        )
        share = result.scalar_one_or_none()
        
        if not share or not share.is_valid():
            raise HTTPException(status_code=404, detail="Invalid or expired share link")
        
        # TODO: Validate temporary access token
        # For now, we'll allow access if the share is valid
        
        document = share.document
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Stream document through storage service
        from app.services.storage_service import StorageService
        storage_service = StorageService(str(share.tenant_id), str(share.created_by))
        
        file_content = storage_service.download_file(document.file_path)
        if not file_content:
            raise HTTPException(status_code=500, detail="Could not retrieve document")
        
        # Determine content type
        content_type = document.mime_type or "application/octet-stream"
        
        # Create response
        headers = {
            "Content-Type": content_type,
            "Content-Disposition": f'inline; filename="{document.filename}"'
        }
        
        return Response(
            content=file_content,
            headers=headers,
            media_type=content_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing shared document: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to view document")