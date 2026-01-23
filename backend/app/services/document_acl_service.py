"""
Document ACL Service

Manages document-level Access Control Lists for granular permissions.
Handles permission checks, grants, revocations, and syncs to Weaviate.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_, func, select, delete

from app.db.models import (
    Document, DocumentACL, DocumentACLAudit,
    User, Role
)
from app.schemas.document_acl import (
    GranteeType, ACLAction, ACLSource, Permission,
    PermissionSet,
    DocumentACLResponse, DocumentACLListResponse,
    GrantPermissionRequest, RevokePermissionRequest,
    EffectivePermissions,
    DocumentACLAuditResponse, DocumentACLAuditListResponse,
    BulkACLUpdateRequest, BulkACLUpdateResponse,
)

logger = logging.getLogger(__name__)


class DocumentACLService:
    """
    Service for managing document-level ACLs.

    Provides:
    - Permission checking (view, edit, delete, share)
    - Granting/revoking permissions
    - Bulk operations
    - Audit logging
    - Weaviate synchronization
    """

    def __init__(self, tenant_id: str, user_id: str):
        self.tenant_id = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        self.user_id = UUID(user_id) if isinstance(user_id, str) else user_id

    # ========================================
    # PERMISSION CHECKING
    # ========================================

    async def check_permission(
        self,
        db: AsyncSession,
        document_id: UUID,
        permission: Permission,
        user: Optional[User] = None,
    ) -> bool:
        """
        Check if current user has a specific permission on a document.

        Permission hierarchy:
        1. Document owner → always has all permissions
        2. Tenant admin → always has all permissions
        3. Explicit user ACL
        4. Role-based ACL (any matching role)
        5. 'everyone' ACL
        6. Default → deny

        Args:
            db: Database session
            document_id: Document to check
            permission: Permission type (view, edit, delete, share)
            user: User object (if None, fetched from self.user_id)

        Returns:
            True if permission is granted, False otherwise
        """
        effective = await self.get_effective_permissions(db, document_id, user)
        permission_map = {
            Permission.VIEW: effective.can_view,
            Permission.EDIT: effective.can_edit,
            Permission.DELETE: effective.can_delete,
            Permission.SHARE: effective.can_share,
        }
        return permission_map.get(permission, False)

    async def get_effective_permissions(
        self,
        db: AsyncSession,
        document_id: UUID,
        user: Optional[User] = None,
    ) -> EffectivePermissions:
        """
        Get the user's effective permissions on a document.

        Combines all applicable ACL entries with implicit permissions
        (owner, admin) to determine what the user can actually do.

        Args:
            db: Database session
            document_id: Document to check
            user: User object (if None, fetched from self.user_id)

        Returns:
            EffectivePermissions with all computed permissions
        """
        result = EffectivePermissions()

        # Get user if not provided
        if user is None:
            user_result = await db.execute(
                select(User).options(
                    joinedload(User.roles)
                ).filter(User.id == self.user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                return result  # No user, no permissions

        # Get document with creator info
        doc_result = await db.execute(
            select(Document).filter(
                and_(
                    Document.id == document_id,
                    Document.tenant_id == self.tenant_id
                )
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            return result  # Document doesn't exist or wrong tenant

        # Check 1: Is user the owner?
        if document.created_by == self.user_id:
            result.is_owner = True
            result.can_view = True
            result.can_edit = True
            result.can_delete = True
            result.can_share = True
            return result

        # Check 2: Is user a tenant admin?
        if user.is_admin:
            result.is_admin = True
            result.can_view = True
            result.can_edit = True
            result.can_delete = True
            result.can_share = True
            return result

        # Check 3-5: Get applicable ACLs
        user_role_ids = [role.id for role in (user.roles or [])]
        now = datetime.now(timezone.utc)

        # Build query for all applicable ACLs
        acl_filters = [
            DocumentACL.document_id == document_id,
            DocumentACL.tenant_id == self.tenant_id,
            DocumentACL.can_view == True,  # Only consider ACLs that grant view
            or_(
                DocumentACL.expires_at.is_(None),
                DocumentACL.expires_at > now
            )
        ]

        # Grantee conditions: user, roles, or everyone
        grantee_conditions = [
            # Direct user grant
            and_(
                DocumentACL.grantee_type == GranteeType.USER.value,
                DocumentACL.grantee_id == self.user_id
            ),
            # Everyone grant
            DocumentACL.grantee_type == GranteeType.EVERYONE.value,
        ]

        # Add role conditions if user has roles
        if user_role_ids:
            grantee_conditions.append(
                and_(
                    DocumentACL.grantee_type == GranteeType.ROLE.value,
                    DocumentACL.grantee_id.in_(user_role_ids)
                )
            )

        acl_query = select(DocumentACL).filter(
            and_(*acl_filters, or_(*grantee_conditions))
        )

        acl_result = await db.execute(acl_query)
        acls = acl_result.scalars().all()

        if not acls:
            return result  # No applicable ACLs

        # Combine permissions from all applicable ACLs
        for acl in acls:
            result.applicable_acl_ids.append(acl.id)

            # Track source of permissions
            if acl.grantee_type == GranteeType.USER.value:
                result.from_user_acl = True
            elif acl.grantee_type == GranteeType.ROLE.value:
                result.from_role_acl = True
            elif acl.grantee_type == GranteeType.EVERYONE.value:
                result.from_everyone_acl = True

            # Combine permissions (OR logic - any grant wins)
            if acl.can_view:
                result.can_view = True
            if acl.can_edit:
                result.can_edit = True
            if acl.can_delete:
                result.can_delete = True
            if acl.can_share:
                result.can_share = True

        return result

    # ========================================
    # GRANT/REVOKE PERMISSIONS
    # ========================================

    async def grant_permission(
        self,
        db: AsyncSession,
        document_id: UUID,
        request: GrantPermissionRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> DocumentACLResponse:
        """
        Grant permissions to a user, role, or everyone.

        Security: Caller must have 'share' permission on the document.

        Args:
            db: Database session
            document_id: Document to grant access to
            request: Grant request with grantee and permissions
            ip_address: Requestor's IP for audit
            user_agent: Requestor's user agent for audit

        Returns:
            Created or updated ACL entry
        """
        try:
            # Check if ACL already exists
            existing_query = select(DocumentACL).filter(
                and_(
                    DocumentACL.document_id == document_id,
                    DocumentACL.tenant_id == self.tenant_id,
                    DocumentACL.grantee_type == request.grantee_type.value,
                    DocumentACL.grantee_id == request.grantee_id if request.grantee_id else DocumentACL.grantee_id.is_(None)
                )
            )
            existing_result = await db.execute(existing_query)
            existing_acl = existing_result.scalar_one_or_none()

            permissions_before = None
            action = ACLAction.GRANTED

            if existing_acl:
                # Update existing ACL
                permissions_before = existing_acl.to_permissions_dict()
                action = ACLAction.MODIFIED

                existing_acl.can_view = request.permissions.can_view
                existing_acl.can_edit = request.permissions.can_edit
                existing_acl.can_delete = request.permissions.can_delete
                existing_acl.can_share = request.permissions.can_share
                existing_acl.expires_at = request.expires_at
                existing_acl.updated_at = datetime.now(timezone.utc)

                acl = existing_acl
            else:
                # Create new ACL
                acl = DocumentACL(
                    document_id=document_id,
                    tenant_id=self.tenant_id,
                    grantee_type=request.grantee_type.value,
                    grantee_id=request.grantee_id,
                    can_view=request.permissions.can_view,
                    can_edit=request.permissions.can_edit,
                    can_delete=request.permissions.can_delete,
                    can_share=request.permissions.can_share,
                    granted_by=self.user_id,
                    expires_at=request.expires_at,
                    source=request.source.value,
                )
                db.add(acl)

            await db.flush()

            # Create audit log
            audit = DocumentACLAudit(
                document_id=document_id,
                tenant_id=self.tenant_id,
                acl_id=acl.id,
                action=action.value,
                grantee_type=request.grantee_type.value,
                grantee_id=request.grantee_id,
                permissions_before=permissions_before,
                permissions_after=acl.to_permissions_dict(),
                performed_by=self.user_id,
                source=request.source.value,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(audit)

            await db.commit()
            await db.refresh(acl)

            # Sync to Weaviate (async, don't block)
            await self._sync_document_acl_to_weaviate(document_id)

            # Resolve names for response
            return await self._acl_to_response(db, acl)

        except Exception as e:
            await db.rollback()
            logger.error(f"Error granting permission: {e}")
            raise

    async def revoke_permission(
        self,
        db: AsyncSession,
        document_id: UUID,
        request: RevokePermissionRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Revoke permissions from a user, role, or everyone.

        Security: Caller must have 'share' permission on the document.

        Args:
            db: Database session
            document_id: Document to revoke access from
            request: Revoke request with grantee info
            ip_address: Requestor's IP for audit
            user_agent: Requestor's user agent for audit

        Returns:
            True if ACL was found and revoked
        """
        try:
            # Find the ACL
            acl_query = select(DocumentACL).filter(
                and_(
                    DocumentACL.document_id == document_id,
                    DocumentACL.tenant_id == self.tenant_id,
                    DocumentACL.grantee_type == request.grantee_type.value,
                    DocumentACL.grantee_id == request.grantee_id if request.grantee_id else DocumentACL.grantee_id.is_(None)
                )
            )
            acl_result = await db.execute(acl_query)
            acl = acl_result.scalar_one_or_none()

            if not acl:
                return False

            permissions_before = acl.to_permissions_dict()

            # Create audit log before deletion
            audit = DocumentACLAudit(
                document_id=document_id,
                tenant_id=self.tenant_id,
                acl_id=acl.id,
                action=ACLAction.REVOKED.value,
                grantee_type=request.grantee_type.value,
                grantee_id=request.grantee_id,
                permissions_before=permissions_before,
                permissions_after=None,
                performed_by=self.user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(audit)

            # Delete the ACL
            await db.delete(acl)
            await db.commit()

            # Sync to Weaviate
            await self._sync_document_acl_to_weaviate(document_id)

            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error revoking permission: {e}")
            raise

    async def revoke_by_acl_id(
        self,
        db: AsyncSession,
        document_id: UUID,
        acl_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """Revoke a specific ACL entry by its ID."""
        try:
            acl_result = await db.execute(
                select(DocumentACL).filter(
                    and_(
                        DocumentACL.id == acl_id,
                        DocumentACL.document_id == document_id,
                        DocumentACL.tenant_id == self.tenant_id
                    )
                )
            )
            acl = acl_result.scalar_one_or_none()

            if not acl:
                return False

            permissions_before = acl.to_permissions_dict()

            # Create audit log
            audit = DocumentACLAudit(
                document_id=document_id,
                tenant_id=self.tenant_id,
                acl_id=acl_id,
                action=ACLAction.REVOKED.value,
                grantee_type=acl.grantee_type,
                grantee_id=acl.grantee_id,
                permissions_before=permissions_before,
                performed_by=self.user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(audit)

            await db.delete(acl)
            await db.commit()

            await self._sync_document_acl_to_weaviate(document_id)

            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error revoking ACL by ID: {e}")
            raise

    # ========================================
    # LIST/GET OPERATIONS
    # ========================================

    async def list_document_acls(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> DocumentACLListResponse:
        """
        List all ACL entries for a document.

        Args:
            db: Database session
            document_id: Document to list ACLs for

        Returns:
            List of ACL entries with resolved names
        """
        # Get document info
        doc_result = await db.execute(
            select(Document).options(
                joinedload(Document.creator)
            ).filter(
                and_(
                    Document.id == document_id,
                    Document.tenant_id == self.tenant_id
                )
            )
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            raise ValueError("Document not found")

        # Get all ACLs for document
        acl_result = await db.execute(
            select(DocumentACL).filter(
                and_(
                    DocumentACL.document_id == document_id,
                    DocumentACL.tenant_id == self.tenant_id
                )
            ).order_by(DocumentACL.created_at)
        )
        acls = acl_result.scalars().all()

        # Convert to responses with resolved names
        acl_responses = []
        for acl in acls:
            response = await self._acl_to_response(db, acl)
            acl_responses.append(response)

        return DocumentACLListResponse(
            document_id=document_id,
            document_title=document.title,
            owner_id=document.created_by,
            owner_name=document.creator.full_name if document.creator else None,
            acls=acl_responses,
            total=len(acl_responses)
        )

    async def get_acl(
        self,
        db: AsyncSession,
        acl_id: UUID,
    ) -> Optional[DocumentACLResponse]:
        """Get a specific ACL entry by ID."""
        acl_result = await db.execute(
            select(DocumentACL).filter(
                and_(
                    DocumentACL.id == acl_id,
                    DocumentACL.tenant_id == self.tenant_id
                )
            )
        )
        acl = acl_result.scalar_one_or_none()

        if not acl:
            return None

        return await self._acl_to_response(db, acl)

    # ========================================
    # BULK OPERATIONS
    # ========================================

    async def bulk_update_acls(
        self,
        db: AsyncSession,
        request: BulkACLUpdateRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> BulkACLUpdateResponse:
        """
        Update ACLs on multiple documents at once.

        Args:
            db: Database session
            request: Bulk update request
            ip_address: Requestor's IP for audit
            user_agent: Requestor's user agent for audit

        Returns:
            Summary of successes and failures
        """
        result = BulkACLUpdateResponse(success_count=0, failure_count=0)

        for doc_id in request.document_ids:
            try:
                # Grant permissions
                if request.grant_permissions:
                    for grant in request.grant_permissions:
                        await self.grant_permission(
                            db, doc_id, grant, ip_address, user_agent
                        )

                # Revoke permissions
                if request.revoke_permissions:
                    for revoke in request.revoke_permissions:
                        await self.revoke_permission(
                            db, doc_id, revoke, ip_address, user_agent
                        )

                result.success_count += 1

            except Exception as e:
                result.failure_count += 1
                result.failures.append({
                    "document_id": str(doc_id),
                    "error": str(e)
                })
                logger.error(f"Bulk ACL update failed for {doc_id}: {e}")

        return result

    # ========================================
    # AUDIT LOG
    # ========================================

    async def get_audit_log(
        self,
        db: AsyncSession,
        document_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> DocumentACLAuditListResponse:
        """
        Get ACL audit log for a document or entire tenant.

        Args:
            db: Database session
            document_id: Optional document filter
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Paginated audit log entries
        """
        filters = [DocumentACLAudit.tenant_id == self.tenant_id]
        if document_id:
            filters.append(DocumentACLAudit.document_id == document_id)

        # Get total count
        count_result = await db.execute(
            select(func.count()).select_from(DocumentACLAudit).filter(*filters)
        )
        total = count_result.scalar() or 0

        # Get paginated results
        offset = (page - 1) * page_size
        audit_result = await db.execute(
            select(DocumentACLAudit)
            .filter(*filters)
            .order_by(DocumentACLAudit.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        audits = audit_result.scalars().all()

        # Convert to responses
        audit_responses = []
        for audit in audits:
            response = await self._audit_to_response(db, audit)
            audit_responses.append(response)

        return DocumentACLAuditListResponse(
            document_id=document_id,
            tenant_id=self.tenant_id,
            audits=audit_responses,
            total=total,
            page=page,
            page_size=page_size
        )

    # ========================================
    # WEAVIATE SYNCHRONIZATION
    # ========================================

    async def _sync_document_acl_to_weaviate(self, document_id: UUID, db: AsyncSession = None):
        """
        Sync ACL state to Weaviate and Elasticsearch document properties.

        Updates acl_user_ids, acl_role_ids, acl_everyone in both systems
        for efficient filtering during searches.

        Args:
            document_id: Document to sync
            db: Database session (optional, will create if not provided)
        """
        import httpx
        from app.core.config import settings

        try:
            # Get database session if not provided
            if db is None:
                from app.db.async_database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    return await self._sync_document_acl_to_weaviate_impl(document_id, db)
            else:
                return await self._sync_document_acl_to_weaviate_impl(document_id, db)

        except Exception as e:
            logger.error(f"Failed to sync ACL to Weaviate/Elasticsearch: {e}")
            # Don't raise - ACL is source of truth, sync is async

    async def _sync_document_acl_to_weaviate_impl(self, document_id: UUID, db: AsyncSession):
        """
        Internal implementation of ACL sync to Weaviate, Elasticsearch, and cache invalidation.

        SECURITY: When document ACL changes, we must:
        1. Update Weaviate document properties for vector search filtering
        2. Update Elasticsearch document for full-text search filtering
        3. Invalidate semantic cache entries that reference this document

        Step 3 is critical: cached RAG responses may contain this document's content.
        If a user loses access to the document, they should not receive cached responses
        that include information from that document.
        """
        import httpx
        from app.core.config import settings

        now = datetime.now(timezone.utc)

        # Get all valid ACLs with can_view=True for this document
        acl_result = await db.execute(
            select(DocumentACL).filter(
                and_(
                    DocumentACL.document_id == document_id,
                    DocumentACL.tenant_id == self.tenant_id,
                    DocumentACL.can_view == True,
                    or_(
                        DocumentACL.expires_at.is_(None),
                        DocumentACL.expires_at > now
                    )
                )
            )
        )
        acls = acl_result.scalars().all()

        # Extract user_ids, role_ids, and everyone flag
        acl_user_ids = []
        acl_role_ids = []
        acl_everyone = False

        for acl in acls:
            if acl.grantee_type == GranteeType.USER.value and acl.grantee_id:
                acl_user_ids.append(str(acl.grantee_id))
            elif acl.grantee_type == GranteeType.ROLE.value and acl.grantee_id:
                acl_role_ids.append(str(acl.grantee_id))
            elif acl.grantee_type == GranteeType.EVERYONE.value:
                acl_everyone = True

        # Get document owner for created_by field
        doc_result = await db.execute(
            select(Document.created_by).filter(Document.id == document_id)
        )
        doc_row = doc_result.first()
        created_by = str(doc_row[0]) if doc_row and doc_row[0] else None

        # Get tenant collection name
        collection_name = f"Nouxcube_{str(self.tenant_id).replace('-', '_')}_documents"

        # 1. Sync to Weaviate (vector search filter)
        await self._sync_acl_to_weaviate(
            document_id, collection_name, acl_user_ids, acl_role_ids, acl_everyone
        )

        # 2. Sync to Elasticsearch (full-text search filter)
        await self._sync_acl_to_elasticsearch(
            document_id, collection_name, acl_user_ids, acl_role_ids, acl_everyone, created_by
        )

        # 3. SECURITY: Invalidate semantic cache entries referencing this document
        # This prevents stale cached responses from being returned to users who lost access
        await self._invalidate_cache_for_document(document_id)

    async def _sync_acl_to_weaviate(
        self,
        document_id: UUID,
        collection_name: str,
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool
    ):
        """Sync ACL to Weaviate service."""
        import httpx
        from app.core.config import settings

        weaviate_url = f"{settings.WEAVIATE_SERVICE_URL}/api/v1/weaviate/documents/{document_id}/acl"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(
                    weaviate_url,
                    json={
                        "collection_name": collection_name,
                        "acl_user_ids": acl_user_ids,
                        "acl_role_ids": acl_role_ids,
                        "acl_everyone": acl_everyone
                    },
                    headers={
                        "X-API-Key": settings.MICROSERVICES_API_KEY,
                        "X-Tenant-ID": str(self.tenant_id)
                    }
                )

                if response.status_code == 200:
                    logger.info(
                        f"✅ Synced ACL to Weaviate for document {document_id}: "
                        f"users={len(acl_user_ids)}, roles={len(acl_role_ids)}, everyone={acl_everyone}"
                    )
                elif response.status_code == 404:
                    logger.warning(f"Document {document_id} not found in Weaviate (may not be indexed yet)")
                else:
                    logger.error(f"Weaviate ACL sync failed: {response.status_code} - {response.text}")

        except httpx.ConnectError:
            logger.warning(f"Could not connect to Weaviate service for ACL sync (document {document_id})")
        except Exception as e:
            logger.error(f"Error calling Weaviate service for ACL sync: {e}")

    async def _sync_acl_to_elasticsearch(
        self,
        document_id: UUID,
        collection_name: str,
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool,
        created_by: str = None
    ):
        """Sync ACL to Elasticsearch service."""
        from app.services.elasticsearch_client import elasticsearch_client

        try:
            success = await elasticsearch_client.sync_document_acl(
                document_id=str(document_id),
                collection_name=collection_name,
                acl_user_ids=acl_user_ids,
                acl_role_ids=acl_role_ids,
                acl_everyone=acl_everyone,
                created_by=created_by
            )

            if success:
                logger.info(
                    f"✅ Synced ACL to Elasticsearch for document {document_id}: "
                    f"users={len(acl_user_ids)}, roles={len(acl_role_ids)}, everyone={acl_everyone}"
                )
            else:
                logger.warning(f"Elasticsearch ACL sync returned False for document {document_id}")

        except Exception as e:
            logger.error(f"Error syncing ACL to Elasticsearch: {e}")

    async def _invalidate_cache_for_document(self, document_id: UUID):
        """
        Invalidate semantic cache entries that reference this document.

        SECURITY: When a document's ACL changes, any cached RAG response that
        used this document as a source must be invalidated. This prevents:
        - Users who lost access from seeing cached responses with that document's content
        - Stale permission data from being returned via cached responses

        This is an O(n) operation on the cache, but it's necessary for security
        and only runs when ACL changes (infrequent operation).
        """
        from app.services.weaviate_client import weaviate_client

        try:
            result = await weaviate_client.invalidate_cache_by_document(
                tenant_id=str(self.tenant_id),
                document_id=str(document_id)
            )

            entries_invalidated = result.get("entries_invalidated", 0)
            if entries_invalidated > 0:
                logger.info(
                    f"🔄 Invalidated {entries_invalidated} cache entries for document {document_id}"
                )

        except Exception as e:
            # Log but don't raise - cache invalidation failure shouldn't block ACL updates
            logger.warning(f"Failed to invalidate cache for document {document_id}: {e}")

    async def sync_all_documents_to_weaviate(self, db: AsyncSession):
        """
        Sync all document ACLs to Weaviate.

        Used for migration or recovery.
        """
        doc_result = await db.execute(
            select(Document.id).filter(Document.tenant_id == self.tenant_id)
        )
        doc_ids = [row[0] for row in doc_result.fetchall()]

        for doc_id in doc_ids:
            await self._sync_document_acl_to_weaviate(doc_id)

        logger.info(f"Synced {len(doc_ids)} documents to Weaviate")

    # ========================================
    # HELPER METHODS
    # ========================================

    async def _acl_to_response(
        self,
        db: AsyncSession,
        acl: DocumentACL
    ) -> DocumentACLResponse:
        """Convert ACL model to response with resolved names."""
        grantee_name = None

        if acl.grantee_type == GranteeType.USER.value and acl.grantee_id:
            user_result = await db.execute(
                select(User.full_name, User.email).filter(User.id == acl.grantee_id)
            )
            user = user_result.first()
            if user:
                grantee_name = user.full_name or user.email

        elif acl.grantee_type == GranteeType.ROLE.value and acl.grantee_id:
            role_result = await db.execute(
                select(Role.name).filter(Role.id == acl.grantee_id)
            )
            role = role_result.first()
            if role:
                grantee_name = role.name

        elif acl.grantee_type == GranteeType.EVERYONE.value:
            grantee_name = "Everyone in tenant"

        granter_name = None
        if acl.granted_by:
            granter_result = await db.execute(
                select(User.full_name, User.email).filter(User.id == acl.granted_by)
            )
            granter = granter_result.first()
            if granter:
                granter_name = granter.full_name or granter.email

        return DocumentACLResponse(
            id=acl.id,
            document_id=acl.document_id,
            tenant_id=acl.tenant_id,
            grantee_type=GranteeType(acl.grantee_type),
            grantee_id=acl.grantee_id,
            can_view=acl.can_view,
            can_edit=acl.can_edit,
            can_delete=acl.can_delete,
            can_share=acl.can_share,
            granted_by=acl.granted_by,
            granted_at=acl.granted_at,
            expires_at=acl.expires_at,
            source=ACLSource(acl.source),
            created_at=acl.created_at,
            updated_at=acl.updated_at,
            grantee_name=grantee_name,
            granter_name=granter_name,
            is_expired=acl.is_expired(),
        )

    async def _audit_to_response(
        self,
        db: AsyncSession,
        audit: DocumentACLAudit
    ) -> DocumentACLAuditResponse:
        """Convert audit model to response with resolved names."""
        grantee_name = None
        if audit.grantee_type == GranteeType.USER.value and audit.grantee_id:
            user_result = await db.execute(
                select(User.full_name, User.email).filter(User.id == audit.grantee_id)
            )
            user = user_result.first()
            if user:
                grantee_name = user.full_name or user.email
        elif audit.grantee_type == GranteeType.ROLE.value and audit.grantee_id:
            role_result = await db.execute(
                select(Role.name).filter(Role.id == audit.grantee_id)
            )
            role = role_result.first()
            if role:
                grantee_name = role.name
        elif audit.grantee_type == GranteeType.EVERYONE.value:
            grantee_name = "Everyone in tenant"

        performer_name = None
        if audit.performed_by:
            performer_result = await db.execute(
                select(User.full_name, User.email).filter(User.id == audit.performed_by)
            )
            performer = performer_result.first()
            if performer:
                performer_name = performer.full_name or performer.email

        document_title = None
        doc_result = await db.execute(
            select(Document.title).filter(Document.id == audit.document_id)
        )
        doc = doc_result.first()
        if doc:
            document_title = doc.title

        return DocumentACLAuditResponse(
            id=audit.id,
            document_id=audit.document_id,
            tenant_id=audit.tenant_id,
            acl_id=audit.acl_id,
            action=ACLAction(audit.action),
            grantee_type=GranteeType(audit.grantee_type),
            grantee_id=audit.grantee_id,
            permissions_before=audit.permissions_before,
            permissions_after=audit.permissions_after,
            performed_by=audit.performed_by,
            source=audit.source,
            ip_address=audit.ip_address,
            user_agent=audit.user_agent,
            created_at=audit.created_at,
            grantee_name=grantee_name,
            performer_name=performer_name,
            document_title=document_title,
        )

    # ========================================
    # UTILITY METHODS
    # ========================================

    async def get_documents_user_can_access(
        self,
        db: AsyncSession,
        permission: Permission = Permission.VIEW,
        user: Optional[User] = None,
    ) -> List[UUID]:
        """
        Get list of document IDs the user can access.

        Used for filtering document lists.
        """
        if user is None:
            user_result = await db.execute(
                select(User).options(joinedload(User.roles)).filter(User.id == self.user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                return []

        # If admin, return all documents
        if user.is_admin:
            doc_result = await db.execute(
                select(Document.id).filter(Document.tenant_id == self.tenant_id)
            )
            return [row[0] for row in doc_result.fetchall()]

        user_role_ids = [role.id for role in (user.roles or [])]
        now = datetime.now(timezone.utc)

        permission_column = {
            Permission.VIEW: DocumentACL.can_view,
            Permission.EDIT: DocumentACL.can_edit,
            Permission.DELETE: DocumentACL.can_delete,
            Permission.SHARE: DocumentACL.can_share,
        }.get(permission, DocumentACL.can_view)

        # Documents where user is owner
        owned_docs = select(Document.id).filter(
            and_(
                Document.tenant_id == self.tenant_id,
                Document.created_by == self.user_id
            )
        )

        # Documents with applicable ACL
        grantee_conditions = [
            and_(
                DocumentACL.grantee_type == GranteeType.USER.value,
                DocumentACL.grantee_id == self.user_id
            ),
            DocumentACL.grantee_type == GranteeType.EVERYONE.value,
        ]
        if user_role_ids:
            grantee_conditions.append(
                and_(
                    DocumentACL.grantee_type == GranteeType.ROLE.value,
                    DocumentACL.grantee_id.in_(user_role_ids)
                )
            )

        acl_docs = select(DocumentACL.document_id).filter(
            and_(
                DocumentACL.tenant_id == self.tenant_id,
                permission_column == True,
                or_(
                    DocumentACL.expires_at.is_(None),
                    DocumentACL.expires_at > now
                ),
                or_(*grantee_conditions)
            )
        ).distinct()

        # Combine: owned OR has ACL
        combined = owned_docs.union(acl_docs)
        result = await db.execute(combined)

        return [row[0] for row in result.fetchall()]
