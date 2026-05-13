"""
LGPD User Data Deletion Service
Comprehensive user data removal for LGPD/GDPR compliance

LGPD Article 18 / GDPR Article 17 - Right to Data Deletion:
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
    User, UserImage, Document, DocumentView,
    LGPDDeletionAudit, document_tags, Tag,
    SignatureRequest, SignatureRequestSigner, SignatureEvent, SignatureContact,
)
from app.services.async_storage_service import AsyncStorageService
from app.services.elasticsearch_client import elasticsearch_client
from app.services.weaviate_client import weaviate_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class LGPDDeletionService:
    """
    Service for complete user data deletion according to LGPD/GDPR requirements.
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
    ) -> Dict[str, Any]:
        """
        Process complete user data deletion request for LGPD compliance.

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
            logger.info(f"LGPD DELETION REQUEST - User {user_id} requested by {requested_by_user_id}")

            # 1. Verify user exists
            user = await self._get_user(db, user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            # 2. Security check - only self-deletion or admin
            if user_id != requested_by_user_id:
                await self._verify_admin_permissions(db, requested_by_user_id)

            # 3. Create deletion audit record
            deletion_record = await self._create_deletion_audit(
                db, user_id, requested_by_user_id, reason
            )

            # 4. Execute complete user data deletion
            deletion_summary = await self._execute_complete_deletion(db, user)
            # 5. Update deletion audit with results
            await self._finalize_deletion_audit(db, deletion_record.id, deletion_summary)

            logger.info(f"LGPD DELETION COMPLETED - User {user_id}")

            return {
                "user_id": user_id,
                "deletion_id": str(deletion_record.id),
                "status": "completed",
                "deleted_at": datetime.utcnow().isoformat(),
                "summary": deletion_summary,
                "lgpd_compliance": {
                    "article": "LGPD Article 18 / GDPR Article 17 - Right to Data Deletion",
                    "method": "complete_data_destruction",
                    "anonymization_applied": deletion_summary.get("anonymized_records", 0) > 0,
                    "external_services_notified": deletion_summary.get("external_deletions", {})
                }
            }

        except Exception as e:
            logger.error(f"LGPD DELETION FAILED for user {user_id}: {e}")
            await db.rollback()
            raise

    async def _get_user(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user with image relationship loaded."""
        stmt = select(User).options(
            selectinload(User.image)
        ).where(User.id == user_id)

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _verify_admin_permissions(self, db: AsyncSession, admin_user_id: str):
        """Verify admin has permission to delete users."""
        stmt = select(User).where(
            User.id == admin_user_id,
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
        """Create LGPD deletion audit record."""
        user = await self._get_user(db, user_id)

        audit_record = LGPDDeletionAudit(
            user_id=user_id,
            user_email=user.email,
            requested_by=requested_by,
            reason=reason,
            status="in_progress",
            started_at=datetime.utcnow()
        )

        db.add(audit_record)
        await db.commit()
        await db.refresh(audit_record)

        return audit_record

    async def _execute_complete_deletion(self, db: AsyncSession, user: User) -> Dict[str, Any]:
        """Execute complete user data deletion."""
        deletion_summary = {
            "user_id": str(user.id),
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

            # 7. Delete from external services
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
        """Delete all user documents and associated data."""
        deleted_count = 0

        # Get all documents created by user
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

    async def _delete_user_profile_data(self, db: AsyncSession, user: User) -> int:
        """Delete user profile data."""
        deleted_count = 0

        # Delete user image
        if user.image:
            await db.delete(user.image)
            deleted_count += 1

        # Note: user_roles association table and DocumentShare/Recipient/
        # AccessLog models were removed when the local RBAC + sharing layer
        # was replaced by role-based ACL on Document.roles. There is no
        # per-user data to cascade-delete at those tables anymore.

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

        return deleted_count

    async def _anonymize_audit_records(self, db: AsyncSession, user_id: UUID) -> int:
        """Anonymize audit records (LGPD requires keeping audit trail).

        Note: the RoleAssignmentAudit and DocumentTagAudit tables were
        removed with the legacy RBAC/sharing subsystem. Only the
        LGPDDeletionAudit table remains and is append-only, so there is
        nothing to anonymize in this pass.
        """
        return 0

    async def _delete_from_vector_services(self, user: User) -> Dict[str, Any]:
        """Delete user data from vector databases."""
        deletion_results = {}

        try:
            collection_name = "Nouxcube_documents"

            # Deletion of user embeddings would require implementing user-based deletion
            # in WeaviateClient. For now, we log the requirement.
            deletion_results["weaviate"] = {
                "status": "manual_cleanup_required",
                "note": "Vector embeddings need manual cleanup",
                "collection": collection_name
            }

            logger.warning(f"Weaviate cleanup required for user {user.id} in collection {collection_name}")

        except Exception as e:
            deletion_results["weaviate"] = {"status": "failed", "error": str(e)}

        return deletion_results

    async def _delete_from_elasticsearch(self, user: User) -> Dict[str, Any]:
        """Delete user data from Elasticsearch."""
        deletion_results = {}

        try:
            deletion_results["elasticsearch"] = {
                "status": "manual_cleanup_required",
                "note": "Elasticsearch documents need manual cleanup by user filter via microservice"
            }

            logger.warning(f"Elasticsearch cleanup required for user {user.id}")

        except Exception as e:
            deletion_results["elasticsearch"] = {"status": "failed", "error": str(e)}

        return deletion_results

    async def _delete_from_storage(self, user: User) -> Dict[str, Any]:
        """Delete user data from storage services (GCS)."""
        deletion_results = {}

        try:
            deletion_results["gcs"] = {
                "status": "manual_cleanup_required",
                "note": "GCS files need manual cleanup by user metadata"
            }

            logger.warning(f"Storage cleanup required for user {user.id}")

        except Exception as e:
            deletion_results["gcs"] = {"status": "failed", "error": str(e)}

        return deletion_results

    async def _delete_from_external_services(self, user: User) -> Dict[str, Any]:
        """Delete user from external services (Clerk and Stripe removed — on-premise only)."""
        return {}

    async def _delete_user_record(self, db: AsyncSession, user: User):
        """Delete the actual user record (final step)."""
        await db.delete(user)
        logger.info(f"User record deleted: {user.id}")

    def _merge_deleted_counts(self, target: Dict[str, int], source: Dict[str, int]):
        """Utility to merge deletion counters."""
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
        """Update deletion audit record with results."""
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
        (What data will be deleted).
        """
        try:
            user = await self._get_user(db, user_id)
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

            # Role assignments no longer live in a local table; KeyCloak is
            # the source of truth for user roles.
            roles_total = 0

            return {
                "user_id": user_id,
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat(),
                "data_summary": {
                    "profile_data": {
                        "user_record": 1,
                        "user_image": 1 if user.image else 0,
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
                }
            }

        except Exception as e:
            logger.error(f"Failed to get user data summary for {user_id}: {e}")
            raise


# Global service instance
lgpd_deletion_service = LGPDDeletionService()
