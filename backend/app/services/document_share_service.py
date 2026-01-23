import secrets
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_, func, desc, select

from app.db.models import (
    Document, IndexedDocument, DocumentShare, DocumentShareAccessLog,
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
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
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
            # First try Document table (SaaS uploads)
            result = await self.db.execute(
                select(Document).filter(
                    and_(
                        Document.id == document_id,
                        Document.tenant_id == self.tenant_id
                    )
                )
            )
            document = result.scalar_one_or_none()

            # If not found, try IndexedDocument table (connector documents)
            if not document:
                indexed_result = await self.db.execute(
                    select(IndexedDocument).filter(
                        and_(
                            IndexedDocument.id == document_id,
                            IndexedDocument.tenant_id == self.tenant_id
                        )
                    )
                )
                indexed_doc = indexed_result.scalar_one_or_none()
                if indexed_doc:
                    # Use IndexedDocument as the source
                    document = indexed_doc

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

            self.db.add(share)
            await self.db.flush()  # Get the share ID

            # Create recipient records if provided
            if recipients:
                for email in recipients:
                    recipient = DocumentShareRecipient(
                        share_id=share.id,
                        tenant_id=self.tenant_id,
                        email=email,
                        verification_code=secrets.token_urlsafe(16)
                    )
                    self.db.add(recipient)
            elif recipient_email:
                # Single recipient
                recipient = DocumentShareRecipient(
                    share_id=share.id,
                    tenant_id=self.tenant_id,
                    email=recipient_email,
                    name=recipient_name,
                    verification_code=secrets.token_urlsafe(16)
                )
                self.db.add(recipient)

            # Update document metrics
            if document.metrics:
                document.metrics.share_count += 1
            else:
                metrics = DocumentMetrics(
                    document_id=document_id,
                    tenant_id=self.tenant_id,
                    share_count=1
                )
                self.db.add(metrics)

            await self.db.commit()
            await self.db.refresh(share)
            
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
            await self.db.rollback()
            logger.error(f"Error creating share: {str(e)}")
            raise

    async def create_bulk_shares(
        self,
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
        document_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[DocumentShareResponse], int]:
        """List document shares with filters"""
        query = select(DocumentShare).options(
            joinedload(DocumentShare.document)
        ).filter(
            DocumentShare.tenant_id == self.tenant_id
        )

        if document_id:
            query = query.filter(DocumentShare.document_id == document_id)

        if is_active is not None:
            query = query.filter(DocumentShare.is_active == is_active)

        # Get total count
        count_query = select(func.count()).select_from(DocumentShare).filter(
            DocumentShare.tenant_id == self.tenant_id
        )
        if document_id:
            count_query = count_query.filter(DocumentShare.document_id == document_id)
        if is_active is not None:
            count_query = count_query.filter(DocumentShare.is_active == is_active)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * per_page
        result = await self.db.execute(
            query.order_by(
                desc(DocumentShare.created_at)
            ).offset(offset).limit(per_page)
        )
        shares = result.scalars().all()
        
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
        share_id: UUID
    ) -> Optional[DocumentShareResponse]:
        """Get a specific share by ID"""
        result = await self.db.execute(
            select(DocumentShare).options(
                joinedload(DocumentShare.document)
            ).filter(
                and_(
                    DocumentShare.id == share_id,
                    DocumentShare.tenant_id == self.tenant_id
                )
            )
        )
        share = result.scalar_one_or_none()
        
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
        share_id: UUID,
        update_data: Dict[str, Any]
    ) -> Optional[DocumentShareResponse]:
        """Update share settings"""
        result = await self.db.execute(
            select(DocumentShare).filter(
                and_(
                    DocumentShare.id == share_id,
                    DocumentShare.tenant_id == self.tenant_id
                )
            )
        )
        share = result.scalar_one_or_none()

        if not share:
            return None

        # Update fields
        for field, value in update_data.dict(exclude_unset=True).items():
            setattr(share, field, value)

        share.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(share)

        return await self.get_share(share_id)
    
    async def revoke_share(
        self,
        share_id: UUID,
        revoked_by: UUID
    ) -> bool:
        """Revoke a share link"""
        result = await self.db.execute(
            select(DocumentShare).filter(
                and_(
                    DocumentShare.id == share_id,
                    DocumentShare.tenant_id == self.tenant_id
                )
            )
        )
        share = result.scalar_one_or_none()

        if not share:
            return False

        share.is_active = False
        share.revoked_at = datetime.now(timezone.utc)
        share.revoked_by = revoked_by

        await self.db.commit()
        return True
    
    async def get_access_logs(
        self,
        share_id: UUID,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[ShareAccessLogResponse], int]:
        """Get access logs for a share"""
        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(DocumentShareAccessLog).filter(
                DocumentShareAccessLog.share_id == share_id
            )
        )
        total = count_result.scalar() or 0

        # Get logs with pagination
        offset = (page - 1) * per_page
        logs_result = await self.db.execute(
            select(DocumentShareAccessLog).filter(
                DocumentShareAccessLog.share_id == share_id
            ).order_by(
                desc(DocumentShareAccessLog.accessed_at)
            ).offset(offset).limit(per_page)
        )
        logs = logs_result.scalars().all()
        
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
        document_id: Optional[UUID] = None
    ) -> ShareStatistics:
        """Get sharing statistics"""
        base_filters = [DocumentShare.tenant_id == self.tenant_id]
        if document_id:
            base_filters.append(DocumentShare.document_id == document_id)

        # Get counts
        total_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(*base_filters)
        )
        total_shares = total_result.scalar() or 0

        active_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                *base_filters,
                DocumentShare.is_active == True
            )
        )
        active_shares = active_result.scalar() or 0

        expired_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                *base_filters,
                DocumentShare.expires_at != None,
                DocumentShare.expires_at < datetime.now(timezone.utc)
            )
        )
        expired_shares = expired_result.scalar() or 0

        revoked_result = await self.db.execute(
            select(func.count()).select_from(DocumentShare).filter(
                *base_filters,
                DocumentShare.revoked_at != None
            )
        )
        revoked_shares = revoked_result.scalar() or 0

        # Get total access count
        access_result = await self.db.execute(
            select(func.sum(DocumentShare.current_access_count)).filter(
                *base_filters
            )
        )
        total_access_count = access_result.scalar() or 0

        # Get unique recipients
        recipients_result = await self.db.execute(
            select(func.count(func.distinct(DocumentShare.recipient_email))).filter(
                DocumentShare.tenant_id == self.tenant_id,
                DocumentShare.recipient_email != None
            )
        )
        unique_recipients = recipients_result.scalar() or 0

        # Get most accessed documents
        most_accessed_result = await self.db.execute(
            select(
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
            ).limit(10)
        )
        most_accessed = most_accessed_result.all()

        most_accessed_documents = [
            {
                "document_id": str(doc.id),
                "title": doc.title,
                "total_accesses": doc.total_accesses or 0
            }
            for doc in most_accessed
        ]

        # Get recent shares
        recent_query = select(DocumentShare).filter(*base_filters).order_by(
            desc(DocumentShare.created_at)
        ).limit(10)
        recent_result = await self.db.execute(recent_query)
        recent_shares_list = recent_result.scalars().all()

        recent_shares = []
        for share in recent_shares_list:
            recent_shares.append(await self.get_share(share.id))

        # Get access by date (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        access_by_date_result = await self.db.execute(
            select(
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
            )
        )
        access_by_date_query = access_by_date_result.all()

        access_by_date = {
            str(row.date): row.count
            for row in access_by_date_query
        }

        # Get access by hour
        access_by_hour_result = await self.db.execute(
            select(
                func.extract('hour', DocumentShareAccessLog.accessed_at).label('hour'),
                func.count(DocumentShareAccessLog.id).label('count')
            ).join(
                DocumentShare, DocumentShareAccessLog.share_id == DocumentShare.id
            ).filter(
                DocumentShare.tenant_id == self.tenant_id
            ).group_by(
                func.extract('hour', DocumentShareAccessLog.accessed_at)
            )
        )
        access_by_hour_query = access_by_hour_result.all()
        
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

            # Get creator info via explicit query (avoid lazy-loading)
            creator_result = await self.db.execute(
                select(User).filter(User.id == self.user_id)
            )
            creator = creator_result.scalar_one_or_none()
            creator_name = "Someone"
            if creator:
                creator_name = creator.full_name or creator.email or "Someone"

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

            # Mark recipient as notified via explicit query (avoid lazy-loading share.recipients)
            recipient_result = await self.db.execute(
                select(DocumentShareRecipient).filter(
                    and_(
                        DocumentShareRecipient.share_id == share.id,
                        DocumentShareRecipient.email == recipient_email
                    )
                )
            )
            recipient = recipient_result.scalar_one_or_none()
            if recipient:
                recipient.notified_at = datetime.now(timezone.utc)
                await self.db.commit()

        except Exception as e:
            logger.error(f"Failed to send share notification: {str(e)}")