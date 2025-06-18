import secrets
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, desc

from app.db.models import (
    Document, DocumentShare, DocumentShareAccessLog, 
    DocumentShareRecipient, User, DocumentMetrics
)
from app.schemas.document_share import (
    DocumentShareResponse, ShareAccessLogResponse,
    BulkShareResult, ShareStatistics
)
from app.core.security import get_password_hash
from app.core.config import settings
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class DocumentShareService:
    def __init__(self, tenant_id: str, user_id: str):
        self.tenant_id = UUID(tenant_id)
        self.user_id = UUID(user_id)
        self.email_service = EmailService()
    
    def _generate_share_token(self) -> str:
        """Generate a secure, unique share token"""
        return secrets.token_urlsafe(32)
    
    def _get_share_url(self, token: str) -> str:
        """Generate the full share URL"""
        base_url = settings.FRONTEND_URL or "http://localhost:3000"
        return f"{base_url}/shared/{token}"
    
    async def create_share(
        self,
        db: Session,
        document_id: UUID,
        share_type: str = "view",
        expires_at: Optional[datetime] = None,
        max_access_count: Optional[int] = None,
        password: Optional[str] = None,
        recipient_email: Optional[str] = None,
        recipient_name: Optional[str] = None,
        share_message: Optional[str] = None,
        permissions: Optional[Dict[str, Any]] = None,
        recipients: Optional[List[str]] = None
    ) -> DocumentShareResponse:
        """Create a new document share"""
        try:
            # Verify document exists and belongs to tenant
            document = db.query(Document).filter(
                and_(
                    Document.id == document_id,
                    Document.tenant_id == self.tenant_id
                )
            ).first()
            
            if not document:
                raise ValueError("Document not found or access denied")
            
            # Generate unique token
            share_token = self._generate_share_token()
            
            # Hash password if provided
            password_hash = None
            if password:
                password_hash = get_password_hash(password)
            
            # Create share
            share = DocumentShare(
                document_id=document_id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
                share_token=share_token,
                share_type=share_type,
                expires_at=expires_at,
                max_access_count=max_access_count,
                password_hash=password_hash,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                share_message=share_message,
                permissions=permissions or {}
            )
            
            db.add(share)
            db.flush()  # Get the share ID
            
            # Create recipient records if provided
            if recipients:
                for email in recipients:
                    recipient = DocumentShareRecipient(
                        share_id=share.id,
                        tenant_id=self.tenant_id,
                        email=email,
                        verification_code=secrets.token_urlsafe(16)
                    )
                    db.add(recipient)
            elif recipient_email:
                # Single recipient
                recipient = DocumentShareRecipient(
                    share_id=share.id,
                    tenant_id=self.tenant_id,
                    email=recipient_email,
                    name=recipient_name,
                    verification_code=secrets.token_urlsafe(16)
                )
                db.add(recipient)
            
            # Update document metrics
            if document.metrics:
                document.metrics.share_count += 1
            else:
                metrics = DocumentMetrics(
                    document_id=document_id,
                    tenant_id=self.tenant_id,
                    share_count=1
                )
                db.add(metrics)
            
            db.commit()
            db.refresh(share)
            
            # Send email notification if recipient email provided
            if recipient_email:
                await self._send_share_notification(
                    share=share,
                    document=document,
                    recipient_email=recipient_email,
                    recipient_name=recipient_name
                )
            
            # Prepare response
            response = DocumentShareResponse(
                id=share.id,
                document_id=share.document_id,
                tenant_id=share.tenant_id,
                created_by=share.created_by,
                share_token=share.share_token,
                share_url=self._get_share_url(share.share_token),
                share_type=share.share_type,
                expires_at=share.expires_at,
                max_access_count=share.max_access_count,
                current_access_count=share.current_access_count,
                is_active=share.is_active,
                recipient_email=share.recipient_email,
                recipient_name=share.recipient_name,
                share_message=share.share_message,
                permissions=share.permissions,
                first_accessed_at=share.first_accessed_at,
                last_accessed_at=share.last_accessed_at,
                created_at=share.created_at,
                updated_at=share.updated_at,
                document_title=document.title,
                document_filename=document.filename
            )
            
            return response
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating share: {str(e)}")
            raise
    
    async def create_bulk_shares(
        self,
        db: Session,
        document_id: UUID,
        recipients: List[str],
        **kwargs
    ) -> BulkShareResult:
        """Create multiple shares for different recipients"""
        result = BulkShareResult(
            total_requested=len(recipients),
            total_successful=0,
            total_failed=0
        )
        
        for email in recipients:
            try:
                share = await self.create_share(
                    db=db,
                    document_id=document_id,
                    recipient_email=email,
                    **kwargs
                )
                result.successful.append(share)
                result.total_successful += 1
            except Exception as e:
                result.failed.append({
                    "email": email,
                    "error": str(e)
                })
                result.total_failed += 1
                logger.error(f"Failed to create share for {email}: {str(e)}")
        
        return result
    
    async def list_shares(
        self,
        db: Session,
        document_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[DocumentShareResponse], int]:
        """List document shares with filters"""
        query = db.query(DocumentShare).options(
            joinedload(DocumentShare.document)
        ).filter(
            DocumentShare.tenant_id == self.tenant_id
        )
        
        if document_id:
            query = query.filter(DocumentShare.document_id == document_id)
        
        if is_active is not None:
            query = query.filter(DocumentShare.is_active == is_active)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        shares = query.order_by(
            desc(DocumentShare.created_at)
        ).offset(offset).limit(per_page).all()
        
        # Convert to response models
        share_responses = []
        for share in shares:
            response = DocumentShareResponse(
                id=share.id,
                document_id=share.document_id,
                tenant_id=share.tenant_id,
                created_by=share.created_by,
                share_token=share.share_token,
                share_url=self._get_share_url(share.share_token),
                share_type=share.share_type,
                expires_at=share.expires_at,
                max_access_count=share.max_access_count,
                current_access_count=share.current_access_count,
                is_active=share.is_active,
                recipient_email=share.recipient_email,
                recipient_name=share.recipient_name,
                share_message=share.share_message,
                permissions=share.permissions,
                first_accessed_at=share.first_accessed_at,
                last_accessed_at=share.last_accessed_at,
                created_at=share.created_at,
                updated_at=share.updated_at,
                revoked_at=share.revoked_at,
                revoked_by=share.revoked_by,
                document_title=share.document.title if share.document else None,
                document_filename=share.document.filename if share.document else None
            )
            share_responses.append(response)
        
        return share_responses, total
    
    async def get_share(
        self,
        db: Session,
        share_id: UUID
    ) -> Optional[DocumentShareResponse]:
        """Get a specific share by ID"""
        share = db.query(DocumentShare).options(
            joinedload(DocumentShare.document)
        ).filter(
            and_(
                DocumentShare.id == share_id,
                DocumentShare.tenant_id == self.tenant_id
            )
        ).first()
        
        if not share:
            return None
        
        return DocumentShareResponse(
            id=share.id,
            document_id=share.document_id,
            tenant_id=share.tenant_id,
            created_by=share.created_by,
            share_token=share.share_token,
            share_url=self._get_share_url(share.share_token),
            share_type=share.share_type,
            expires_at=share.expires_at,
            max_access_count=share.max_access_count,
            current_access_count=share.current_access_count,
            is_active=share.is_active,
            recipient_email=share.recipient_email,
            recipient_name=share.recipient_name,
            share_message=share.share_message,
            permissions=share.permissions,
            first_accessed_at=share.first_accessed_at,
            last_accessed_at=share.last_accessed_at,
            created_at=share.created_at,
            updated_at=share.updated_at,
            revoked_at=share.revoked_at,
            revoked_by=share.revoked_by,
            document_title=share.document.title if share.document else None,
            document_filename=share.document.filename if share.document else None
        )
    
    async def update_share(
        self,
        db: Session,
        share_id: UUID,
        update_data: Dict[str, Any]
    ) -> Optional[DocumentShareResponse]:
        """Update share settings"""
        share = db.query(DocumentShare).filter(
            and_(
                DocumentShare.id == share_id,
                DocumentShare.tenant_id == self.tenant_id
            )
        ).first()
        
        if not share:
            return None
        
        # Update fields
        for field, value in update_data.dict(exclude_unset=True).items():
            setattr(share, field, value)
        
        share.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(share)
        
        return await self.get_share(db, share_id)
    
    async def revoke_share(
        self,
        db: Session,
        share_id: UUID,
        revoked_by: UUID
    ) -> bool:
        """Revoke a share link"""
        share = db.query(DocumentShare).filter(
            and_(
                DocumentShare.id == share_id,
                DocumentShare.tenant_id == self.tenant_id
            )
        ).first()
        
        if not share:
            return False
        
        share.is_active = False
        share.revoked_at = datetime.now(timezone.utc)
        share.revoked_by = revoked_by
        
        db.commit()
        return True
    
    async def get_access_logs(
        self,
        db: Session,
        share_id: UUID,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[ShareAccessLogResponse], int]:
        """Get access logs for a share"""
        query = db.query(DocumentShareAccessLog).filter(
            DocumentShareAccessLog.share_id == share_id
        )
        
        total = query.count()
        
        offset = (page - 1) * per_page
        logs = query.order_by(
            desc(DocumentShareAccessLog.accessed_at)
        ).offset(offset).limit(per_page).all()
        
        log_responses = []
        for log in logs:
            response = ShareAccessLogResponse(
                id=log.id,
                share_id=log.share_id,
                document_id=log.document_id,
                accessed_at=log.accessed_at,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                action=log.action,
                success=log.success,
                error_message=log.error_message,
                country_code=log.country_code,
                city=log.city,
                device_type=log.device_type,
                browser=log.browser,
                os=log.os,
                user_id=log.user_id
            )
            log_responses.append(response)
        
        return log_responses, total
    
    async def get_statistics(
        self,
        db: Session,
        document_id: Optional[UUID] = None
    ) -> ShareStatistics:
        """Get sharing statistics"""
        query = db.query(DocumentShare).filter(
            DocumentShare.tenant_id == self.tenant_id
        )
        
        if document_id:
            query = query.filter(DocumentShare.document_id == document_id)
        
        # Get counts
        total_shares = query.count()
        active_shares = query.filter(DocumentShare.is_active == True).count()
        expired_shares = query.filter(
            and_(
                DocumentShare.expires_at != None,
                DocumentShare.expires_at < datetime.now(timezone.utc)
            )
        ).count()
        revoked_shares = query.filter(DocumentShare.revoked_at != None).count()
        
        # Get total access count
        total_access_count = db.query(
            func.sum(DocumentShare.current_access_count)
        ).filter(
            DocumentShare.tenant_id == self.tenant_id
        ).scalar() or 0
        
        # Get unique recipients
        unique_recipients = db.query(
            func.count(func.distinct(DocumentShare.recipient_email))
        ).filter(
            and_(
                DocumentShare.tenant_id == self.tenant_id,
                DocumentShare.recipient_email != None
            )
        ).scalar() or 0
        
        # Get most accessed documents
        most_accessed = db.query(
            Document.id,
            Document.title,
            func.sum(DocumentShare.current_access_count).label('total_accesses')
        ).join(
            DocumentShare, Document.id == DocumentShare.document_id
        ).filter(
            DocumentShare.tenant_id == self.tenant_id
        ).group_by(
            Document.id, Document.title
        ).order_by(
            desc('total_accesses')
        ).limit(10).all()
        
        most_accessed_documents = [
            {
                "document_id": str(doc.id),
                "title": doc.title,
                "total_accesses": doc.total_accesses or 0
            }
            for doc in most_accessed
        ]
        
        # Get recent shares
        recent_shares_query = query.order_by(
            desc(DocumentShare.created_at)
        ).limit(10).all()
        
        recent_shares = []
        for share in recent_shares_query:
            recent_shares.append(await self.get_share(db, share.id))
        
        # Get access by date (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        access_by_date_query = db.query(
            func.date(DocumentShareAccessLog.accessed_at).label('date'),
            func.count(DocumentShareAccessLog.id).label('count')
        ).join(
            DocumentShare, DocumentShareAccessLog.share_id == DocumentShare.id
        ).filter(
            and_(
                DocumentShare.tenant_id == self.tenant_id,
                DocumentShareAccessLog.accessed_at >= thirty_days_ago
            )
        ).group_by(
            func.date(DocumentShareAccessLog.accessed_at)
        ).all()
        
        access_by_date = {
            str(row.date): row.count
            for row in access_by_date_query
        }
        
        # Get access by hour
        access_by_hour_query = db.query(
            func.extract('hour', DocumentShareAccessLog.accessed_at).label('hour'),
            func.count(DocumentShareAccessLog.id).label('count')
        ).join(
            DocumentShare, DocumentShareAccessLog.share_id == DocumentShare.id
        ).filter(
            DocumentShare.tenant_id == self.tenant_id
        ).group_by(
            func.extract('hour', DocumentShareAccessLog.accessed_at)
        ).all()
        
        access_by_hour = {
            int(row.hour): row.count
            for row in access_by_hour_query
        }
        
        return ShareStatistics(
            total_shares=total_shares,
            active_shares=active_shares,
            expired_shares=expired_shares,
            revoked_shares=revoked_shares,
            total_access_count=int(total_access_count),
            unique_recipients=unique_recipients,
            most_accessed_documents=most_accessed_documents,
            recent_shares=recent_shares,
            access_by_date=access_by_date,
            access_by_hour=access_by_hour
        )
    
    async def _send_share_notification(
        self,
        share: DocumentShare,
        document: Document,
        recipient_email: str,
        recipient_name: Optional[str] = None
    ):
        """Send email notification to share recipient"""
        try:
            share_url = self._get_share_url(share.share_token)
            
            # Get creator info
            creator = share.creator
            creator_name = creator.full_name if creator and creator.full_name else creator.email if creator else "Someone"
            
            # Prepare email data
            subject = f"{creator_name} shared a document with you: {document.title}"
            
            template_data = {
                "recipient_name": recipient_name or "there",
                "creator_name": creator_name,
                "document_title": document.title,
                "share_message": share.share_message,
                "share_url": share_url,
                "expires_at": share.expires_at,
                "share_type": share.share_type,
                "has_password": bool(share.password_hash)
            }
            
            # Send email
            await self.email_service.send_share_notification(
                to_email=recipient_email,
                subject=subject,
                template_data=template_data
            )
            
            # Mark recipient as notified
            if share.recipients:
                recipient = next(
                    (r for r in share.recipients if r.email == recipient_email),
                    None
                )
                if recipient:
                    recipient.notified_at = datetime.now(timezone.utc)
                    
        except Exception as e:
            logger.error(f"Failed to send share notification: {str(e)}")