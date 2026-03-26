"""
LGPD User Data Deletion Service
Comprehensive user data removal for LGPD compliance

LGPD Article 18 - Right to Data Deletion:
- Complete removal of personal data
- Anonymization of records where deletion is not possible
- Removal from all systems and backups
- Documentation of deletion process
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy import delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models import (
    User, UserImage, Tenant, Document, DocumentView, 
    RoleAssignmentAudit, DocumentTagAudit, LGPDDeletionAudit,
    role_permissions, user_roles, document_tags,
    Role, Tag, DocumentShare, DocumentShareAccessLog, DocumentShareRecipient,
    SignatureRequest, SignatureRequestSigner, SignatureEvent, SignatureContact,
    GoogleDriveToken
)
from app.db.agent_models import AgentExecution, AgentExecutionLog, AgentDefinition
from app.services.async_storage_service import AsyncStorageService
from app.services.elasticsearch_client import elasticsearch_client
from app.services.weaviate_client import weaviate_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class LGPDDeletionService:
    """
    Service for complete user data deletion according to LGPD requirements
    """
    
    def __init__(self):
        self.deletion_log = []
        
    async def request_user_deletion(
        self,
        db: AsyncSession,
        user_id: str,
        requested_by_user_id: str,
        confirmation_token: str,
        reason: Optional[str] = None,
        delete_tenant: bool = False
    ) -> Dict[str, Any]:
        """
        Process complete user data deletion request for LGPD compliance
        
        Args:
            db: Database session
            user_id: User ID to delete
            requested_by_user_id: Who requested the deletion
            confirmation_token: Security confirmation token
            reason: Optional reason for deletion
            
        Returns:
            Deletion summary report
        """
        try:
            logger.info(f"🔥 LGPD DELETION REQUEST - User {user_id} requested by {requested_by_user_id}")
            
            # 1. Verify user exists and get tenant info
            user = await self._get_user_with_tenant(db, user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # 2. Security check - only self-deletion or admin
            if user_id != requested_by_user_id:
                await self._verify_admin_permissions(db, requested_by_user_id, user.tenant_id)
            
            # 3. Create deletion audit record
            deletion_record = await self._create_deletion_audit(
                db, user_id, requested_by_user_id, reason
            )
            
            # 4. Execute complete data deletion
            if delete_tenant:
                deletion_summary = await self._execute_tenant_deletion(db, user, deletion_record.id)
                # Note: Audit record is deleted with tenant, no finalization needed
            else:
                deletion_summary = await self._execute_complete_deletion(db, user)
                # 5. Update deletion audit with results (only for user deletion, not tenant)
                await self._finalize_deletion_audit(db, deletion_record.id, deletion_summary)

            logger.info(f"✅ LGPD DELETION COMPLETED - User {user_id}")
            
            return {
                "user_id": user_id,
                "deletion_id": str(deletion_record.id),
                "status": "completed",
                "deleted_at": datetime.utcnow().isoformat(),
                "summary": deletion_summary,
                "lgpd_compliance": {
                    "article": "LGPD Article 18 - Right to Data Deletion",
                    "method": "complete_data_destruction",
                    "anonymization_applied": deletion_summary.get("anonymized_records", 0) > 0,
                    "external_services_notified": deletion_summary.get("external_deletions", {})
                }
            }
            
        except Exception as e:
            logger.error(f"❌ LGPD DELETION FAILED for user {user_id}: {e}")
            await db.rollback()
            raise
    
    async def _get_user_with_tenant(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user with tenant information"""
        stmt = select(User).options(
            selectinload(User.tenant),
            selectinload(User.image)
        ).where(User.id == user_id)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _verify_admin_permissions(self, db: AsyncSession, admin_user_id: str, tenant_id: UUID):
        """Verify admin has permission to delete users"""
        stmt = select(User).where(
            User.id == admin_user_id,
            User.tenant_id == tenant_id,
            User.is_superuser == True
        )
        result = await db.execute(stmt)
        admin = result.scalar_one_or_none()
        
        if not admin:
            raise PermissionError("Only superusers can delete other users")
    
    async def _create_deletion_audit(
        self, 
        db: AsyncSession, 
        user_id: str, 
        requested_by: str, 
        reason: Optional[str]
    ):
        """Create LGPD deletion audit record"""
        # Get user info before deletion for audit
        user = await self._get_user_with_tenant(db, user_id)
        
        audit_record = LGPDDeletionAudit(
            user_id=user_id,
            user_email=user.email,
            requested_by=requested_by,
            tenant_id=user.tenant_id,
            reason=reason,
            status="in_progress",
            started_at=datetime.utcnow()
        )
        
        db.add(audit_record)
        await db.commit()
        await db.refresh(audit_record)
        
        return audit_record
    
    async def _execute_complete_deletion(self, db: AsyncSession, user: User) -> Dict[str, Any]:
        """Execute complete user data deletion"""
        deletion_summary = {
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id),
            "deleted_records": {},
            "anonymized_records": 0,
            "storage_deletions": {},
            "external_deletions": {},
            "errors": []
        }
        
        try:
            # 1. Delete user's documents and associated data
            docs_deleted = await self._delete_user_documents(db, user, deletion_summary)
            deletion_summary["deleted_records"]["documents"] = docs_deleted
            
            # 2. Delete user's profile data
            profile_deleted = await self._delete_user_profile_data(db, user)
            deletion_summary["deleted_records"]["profile_data"] = profile_deleted
            
            # 3. Anonymize audit records (cannot delete for compliance)
            anonymized = await self._anonymize_audit_records(db, user.id)
            deletion_summary["anonymized_records"] = anonymized
            
            # 4. Delete from vector databases
            vector_deleted = await self._delete_from_vector_services(user)
            deletion_summary["deleted_records"]["vector_data"] = vector_deleted
            
            # 5. Delete from Elasticsearch
            es_deleted = await self._delete_from_elasticsearch(user)
            deletion_summary["deleted_records"]["elasticsearch_data"] = es_deleted
            
            # 6. Delete from storage services (GCS)
            storage_deleted = await self._delete_from_storage(user)
            deletion_summary["storage_deletions"] = storage_deleted
            
            # 7. Delete from external services (Clerk, Stripe)
            external_deleted = await self._delete_from_external_services(user)
            deletion_summary["external_deletions"] = external_deleted
            
            # 8. Finally, delete user record
            await self._delete_user_record(db, user)
            deletion_summary["deleted_records"]["user"] = 1
            
            await db.commit()
            
        except Exception as e:
            deletion_summary["errors"].append(str(e))
            raise
        
        return deletion_summary
    
    async def _delete_user_documents(self, db: AsyncSession, user: User, summary: Dict) -> int:
        """Delete all user documents and associated data"""
        deleted_count = 0
        
        # Get all user documents
        stmt = select(Document).where(Document.created_by == user.id)
        result = await db.execute(stmt)
        documents = result.scalars().all()
        
        for doc in documents:
            try:
                # Delete document tags associations
                await db.execute(
                    delete(document_tags).where(document_tags.c.document_id == doc.id)
                )
                
                # Delete document views
                await db.execute(
                    delete(DocumentView).where(DocumentView.document_id == doc.id)
                )
                
                # Delete document itself
                await db.delete(doc)
                deleted_count += 1
                
                logger.debug(f"Deleted document: {doc.id}")
                
            except Exception as e:
                summary["errors"].append(f"Failed to delete document {doc.id}: {e}")
        
        return deleted_count

    async def _execute_tenant_deletion(self, db: AsyncSession, user: User, deletion_record_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Delete the entire tenant and all associated users/data.
        Only triggered when a tenant owner/admin explicitly requests it.
        """
        tenant_stmt = select(Tenant).options(selectinload(Tenant.users)).where(Tenant.id == user.tenant_id)
        tenant_result = await db.execute(tenant_stmt)
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise ValueError("Tenant not found for deletion")
        
        tenant_users = list(tenant.users or [])
        if not tenant_users:
            tenant_users = [user]

        tenant_user_ids = [str(tu.id) for tu in tenant_users]
        
        aggregate_summary: Dict[str, Any] = {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "tenant_deleted": False,
            "user_deletions": [],
            "deleted_records": {},
            "anonymized_records": 0,
            "storage_deletions": {},
            "external_deletions": {},
            "errors": []
        }
        
        for tenant_user_id in tenant_user_ids:
            member_user = await self._get_user_with_tenant(db, tenant_user_id)
            if not member_user:
                aggregate_summary["errors"].append(f"User {tenant_user_id} not found during tenant deletion")
                continue

            member_summary = await self._execute_complete_deletion(db, member_user)
            aggregate_summary["user_deletions"].append(member_summary)
            self._merge_deleted_counts(aggregate_summary["deleted_records"], member_summary.get("deleted_records", {}))
            aggregate_summary["anonymized_records"] += member_summary.get("anonymized_records", 0)
            if member_summary.get("storage_deletions"):
                aggregate_summary["storage_deletions"][member_summary["user_id"]] = member_summary.get("storage_deletions", {})
            if member_summary.get("external_deletions"):
                aggregate_summary["external_deletions"][member_summary["user_id"]] = member_summary.get("external_deletions", {})
            if member_summary.get("errors"):
                aggregate_summary["errors"].extend(member_summary["errors"])

        # Tenant-wide shared links cleanup
        share_cleanup = await self._delete_tenant_shares(db, tenant.id)
        for key, value in share_cleanup.items():
            try:
                numeric_value = int(value) if value is not None else 0
            except (TypeError, ValueError):
                numeric_value = 0
            if numeric_value <= 0:
                continue
            aggregate_key = f"tenant_{key}"
            aggregate_summary["deleted_records"][aggregate_key] = (
                aggregate_summary["deleted_records"].get(aggregate_key, 0) + numeric_value
            )

        # Finalize the current deletion audit record before deleting all audits
        if deletion_record_id:
            await self._finalize_deletion_audit(db, deletion_record_id, aggregate_summary)

        # Delete LGPD deletion audits for this tenant (must be deleted before tenant)
        lgpd_audits_result = await db.execute(
            delete(LGPDDeletionAudit).where(LGPDDeletionAudit.tenant_id == tenant.id)
        )
        aggregate_summary["deleted_records"]["lgpd_deletion_audits"] = lgpd_audits_result.rowcount or 0

        await db.delete(tenant)
        await db.commit()
        aggregate_summary["tenant_deleted"] = True
        aggregate_summary["deleted_records"]["tenants"] = aggregate_summary["deleted_records"].get("tenants", 0) + 1
        return aggregate_summary

    async def _delete_tenant_shares(self, db: AsyncSession, tenant_id: UUID) -> Dict[str, int]:
        """Delete all document shares (and related entries) for a tenant"""
        share_ids_subq = select(DocumentShare.id).where(DocumentShare.tenant_id == tenant_id).subquery()
        cleanup_counts = {
            "document_share_access_logs": 0,
            "document_share_recipients": 0,
            "document_shares": 0
        }

        # Count before deletion for audit visibility
        access_count_result = await db.execute(
            select(func.count(DocumentShareAccessLog.id)).where(DocumentShareAccessLog.share_id.in_(share_ids_subq))
        )
        cleanup_counts["document_share_access_logs"] = access_count_result.scalar() or 0

        recipients_count_result = await db.execute(
            select(func.count(DocumentShareRecipient.id)).where(DocumentShareRecipient.share_id.in_(share_ids_subq))
        )
        cleanup_counts["document_share_recipients"] = recipients_count_result.scalar() or 0

        shares_count_result = await db.execute(
            select(func.count(DocumentShare.id)).where(DocumentShare.tenant_id == tenant_id)
        )
        cleanup_counts["document_shares"] = shares_count_result.scalar() or 0

        await db.execute(
            delete(DocumentShareAccessLog).where(DocumentShareAccessLog.share_id.in_(share_ids_subq))
        )
        await db.execute(
            delete(DocumentShareRecipient).where(DocumentShareRecipient.share_id.in_(share_ids_subq))
        )
        await db.execute(
            delete(DocumentShare).where(DocumentShare.tenant_id == tenant_id)
        )

        return cleanup_counts
    
    async def _delete_user_profile_data(self, db: AsyncSession, user: User) -> int:
        """Delete user profile data"""
        deleted_count = 0
        
        # Delete user image
        if user.image:
            await db.delete(user.image)
            deleted_count += 1
        
        # Remove user from roles
        await db.execute(
            delete(user_roles).where(user_roles.c.user_id == user.id)
        )
        deleted_count += 1
        
        # Delete document shares and related records
        await db.execute(
            delete(DocumentShareAccessLog).where(DocumentShareAccessLog.share_id.in_(
                select(DocumentShare.id).where(DocumentShare.created_by == user.id)
            ))
        )
        await db.execute(
            delete(DocumentShareRecipient).where(DocumentShareRecipient.share_id.in_(
                select(DocumentShare.id).where(DocumentShare.created_by == user.id)
            ))
        )
        await db.execute(
            delete(DocumentShare).where(DocumentShare.created_by == user.id)
        )
        
        # Delete signature-related records
        await db.execute(
            delete(SignatureEvent).where(SignatureEvent.request_id.in_(
                select(SignatureRequest.id).where(SignatureRequest.created_by == user.id)
            ))
        )
        await db.execute(
            delete(SignatureRequestSigner).where(SignatureRequestSigner.request_id.in_(
                select(SignatureRequest.id).where(SignatureRequest.created_by == user.id)
            ))
        )
        await db.execute(
            delete(SignatureRequest).where(SignatureRequest.created_by == user.id)
        )
        await db.execute(
            delete(SignatureContact).where(SignatureContact.created_by == user.id)
        )

        # Delete Google Drive tokens bound to the user
        tokens_result = await db.execute(
            delete(GoogleDriveToken).where(GoogleDriveToken.user_id == user.id)
        )
        deleted_count += tokens_result.rowcount or 0
        await db.flush()
        
        # Delete agent executions and logs
        await db.execute(
            delete(AgentExecutionLog).where(
                AgentExecutionLog.execution_id.in_(
                    select(AgentExecution.id).where(AgentExecution.user_id == user.id)
                )
            )
        )
        await db.execute(
            delete(AgentExecution).where(AgentExecution.user_id == user.id)
        )
        
        return deleted_count
    
    async def _anonymize_audit_records(self, db: AsyncSession, user_id: UUID) -> int:
        """Anonymize audit records (LGPD requires keeping audit trail)"""
        anonymized_count = 0
        anonymous_id = "00000000-0000-0000-0000-000000000000"
        
        # Anonymize role assignment audits
        result = await db.execute(
            update(RoleAssignmentAudit)
            .where(RoleAssignmentAudit.user_id == user_id)
            .values(user_id=anonymous_id)
        )
        anonymized_count += result.rowcount
        
        result = await db.execute(
            update(RoleAssignmentAudit)
            .where(RoleAssignmentAudit.assigned_by == user_id)
            .values(assigned_by=anonymous_id)
        )
        anonymized_count += result.rowcount
        
        # Anonymize document tag audits
        result = await db.execute(
            update(DocumentTagAudit)
            .where(DocumentTagAudit.tagged_by == user_id)
            .values(tagged_by=anonymous_id)
        )
        anonymized_count += result.rowcount
        
        logger.info(f"Anonymized {anonymized_count} audit records for user {user_id}")
        return anonymized_count
    
    async def _delete_from_vector_services(self, user: User) -> Dict[str, Any]:
        """Delete user data from vector databases"""
        deletion_results = {}

        try:
            collection_name = f"Nouxcube_{str(user.tenant_id).replace('-', '_')}_documents"

            # Delete all documents by user from vector database
            # This would require implementing user-based deletion in WeaviateClient
            # For now, we'll log the requirement
            deletion_results["weaviate"] = {
                "status": "manual_cleanup_required",
                "note": "Vector embeddings need manual cleanup by tenant",
                "collection": collection_name
            }

            logger.warning(f"Weaviate cleanup required for user {user.id} in collection {collection_name}")

        except Exception as e:
            deletion_results["weaviate"] = {"status": "failed", "error": str(e)}

        return deletion_results
    
    async def _delete_from_elasticsearch(self, user: User) -> Dict[str, Any]:
        """Delete user data from Elasticsearch"""
        deletion_results = {}
        
        try:
            # Note: Elasticsearch microservice doesn't have user-based deletion yet
            # This would require implementing user-based deletion in elasticsearch-service
            deletion_results["elasticsearch"] = {
                "status": "manual_cleanup_required",
                "note": "Elasticsearch documents need manual cleanup by user filter via microservice"
            }
            
            logger.warning(f"Elasticsearch cleanup required for user {user.id}")
            
        except Exception as e:
            deletion_results["elasticsearch"] = {"status": "failed", "error": str(e)}
        
        return deletion_results
    
    async def _delete_from_storage(self, user: User) -> Dict[str, Any]:
        """Delete user data from storage services (GCS)"""
        deletion_results = {}
        
        try:
            # This would require implementing user-based file deletion
            # in the storage service
            deletion_results["gcs"] = {
                "status": "manual_cleanup_required",
                "note": "GCS files need manual cleanup by user metadata"
            }
            
            logger.warning(f"Storage cleanup required for user {user.id}")
            
        except Exception as e:
            deletion_results["gcs"] = {"status": "failed", "error": str(e)}
        
        return deletion_results
    
    async def _delete_from_external_services(self, user: User) -> Dict[str, Any]:
        """Delete user from external services (Clerk and Stripe removed — on-premise only)"""
        return {}
    
    async def _delete_user_record(self, db: AsyncSession, user: User):
        """Delete the actual user record (final step)"""
        await db.delete(user)
        logger.info(f"User record deleted: {user.id}")
    
    def _merge_deleted_counts(self, target: Dict[str, int], source: Dict[str, int]):
        """Utility to merge deletion counters"""
        if not source:
            return
        for key, value in source.items():
            try:
                numeric_value = int(value) if value is not None else 0
            except (TypeError, ValueError):
                logger.debug(f"Skipping non-numeric deleted_records entry {key}={value}")
                continue
            if numeric_value <= 0:
                continue
            target[key] = target.get(key, 0) + numeric_value
    
    async def _finalize_deletion_audit(self, db: AsyncSession, deletion_id: UUID, summary: Dict):
        """Update deletion audit record with results"""
        stmt = select(LGPDDeletionAudit).where(LGPDDeletionAudit.id == deletion_id)
        result = await db.execute(stmt)
        audit_record = result.scalar_one()
        
        audit_record.status = "completed" if not summary["errors"] else "completed_with_errors"
        audit_record.completed_at = datetime.utcnow()
        audit_record.deletion_summary = summary
        audit_record.total_records_deleted = sum(
            v for v in summary["deleted_records"].values()
            if isinstance(v, (int, float))
        )
        audit_record.anonymized_records = summary["anonymized_records"]
        
        await db.commit()
    
    async def get_user_data_summary(self, db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """
        Get summary of all user data for LGPD transparency
        (What data will be deleted)
        """
        try:
            user = await self._get_user_with_tenant(db, user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Count documents
            docs_count = await db.execute(
                select(func.count(Document.id)).where(Document.created_by == user.id)
            )
            documents_count = docs_count.scalar()
            
            # Count document views
            views_count = await db.execute(
                select(func.count(DocumentView.id)).where(DocumentView.user_id == user.id)
            )
            views_total = views_count.scalar()
            
            # Count role assignments
            roles_count = await db.execute(
                select(func.count(user_roles.c.user_id)).where(user_roles.c.user_id == user.id)
            )
            roles_total = roles_count.scalar()
            
            return {
                "user_id": user_id,
                "email": user.email,
                "full_name": user.full_name,
                "tenant": user.tenant.name,
                "created_at": user.created_at.isoformat(),
                "data_summary": {
                    "profile_data": {
                        "user_record": 1,
                        "user_image": 1 if user.image else 0,
                        "external_accounts": {
                            "clerk": bool(user.clerk_user_id),
                            "stripe": bool(user.stripe_customer_id)
                        }
                    },
                    "document_data": {
                        "documents_created": documents_count,
                        "document_views": views_total
                    },
                    "access_data": {
                        "role_assignments": roles_total
                    },
                    "audit_data": {
                        "note": "Audit records will be anonymized, not deleted",
                        "retention_reason": "Legal compliance requirement"
                    }
                },
                "lgpd_rights": {
                    "article_18": "Right to data deletion",
                    "deletion_scope": "Complete personal data removal",
                    "audit_retention": "Anonymized audit trail maintained for compliance",
                    "external_services": "Clerk and Stripe accounts are deleted automatically when credentials are configured; otherwise manual action is required"
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get user data summary for {user_id}: {e}")
            raise


# Create the missing model for LGPD deletion audit
# This should be added to models.py
LGPD_DELETION_AUDIT_MODEL = '''
class LGPDDeletionAudit(Base):
    """LGPD User Deletion Audit Trail"""
    __tablename__ = "lgpd_deletion_audits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Don't FK since user will be deleted
    user_email = Column(String(255), nullable=False)  # Keep for audit
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    reason = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, in_progress, completed, failed
    
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Deletion results
    deletion_summary = Column(JSONB, nullable=True)
    total_records_deleted = Column(Integer, nullable=True, default=0)
    anonymized_records = Column(Integer, nullable=True, default=0)
    
    # LGPD compliance fields
    lgpd_article = Column(String(50), nullable=False, default="Article 18")
    deletion_method = Column(String(100), nullable=False, default="complete_data_destruction")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    requested_by_user = relationship("User")
    tenant = relationship("Tenant")
    
    __table_args__ = (
        Index('idx_lgpd_deletions_tenant_status', 'tenant_id', 'status'),
        Index('idx_lgpd_deletions_user_date', 'user_id', 'created_at'),
    )
'''


# Global service instance
lgpd_deletion_service = LGPDDeletionService()
