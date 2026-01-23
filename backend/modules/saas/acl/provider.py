"""
Table ACL Provider for SaaS deployments.

Uses dedicated DocumentACL table for fine-grained permissions.
Wraps the existing DocumentACLService for compatibility.

This provider is optimized for SaaS deployments where:
    1. Documents are uploaded directly by users
    2. Fine-grained sharing with other users/roles is needed
    3. Audit trail of all permission changes is required
    4. Temporary access with expiration is needed
"""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from core.acl.base import (
    ACLProvider,
    ACLProviderType,
    Permission,
    PermissionSet,
    DocumentNotFoundError,
)

logger = logging.getLogger(__name__)


class TableACLProvider(ACLProvider):
    """
    ACL provider using dedicated DocumentACL table.

    Wraps the existing DocumentACLService for backward compatibility
    while implementing the ACLProvider interface.
    """

    def __init__(self, tenant_id: str, user_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(tenant_id, user_id, config)
        self._acl_service = None

    @property
    def provider_type(self) -> ACLProviderType:
        return ACLProviderType.TABLE

    def _get_acl_service(self):
        """Lazy-load the DocumentACLService."""
        if self._acl_service is None:
            from app.services.document_acl_service import DocumentACLService
            self._acl_service = DocumentACLService(self.tenant_id, self.user_id)
        return self._acl_service

    async def initialize(self, db: AsyncSession) -> None:
        """
        Initialize provider by loading user context.

        Loads:
            - User's roles (for role-based ACL)
            - Admin status
        """
        if self._initialized:
            return

        try:
            from app.db.models import User

            result = await db.execute(
                select(User).options(
                    joinedload(User.roles)
                ).where(User.id == self.user_id)
            )
            user = result.scalar_one_or_none()

            if user:
                # Load application roles
                self._user_roles = [str(role.id) for role in user.roles] if user.roles else []

                # Check admin status
                self._is_admin = getattr(user, 'is_admin', False) or user.is_superuser

                logger.debug(
                    f"Initialized Table ACL provider: user={self.user_id[:8] if self.user_id else 'None'}..., "
                    f"roles={len(self._user_roles)}, is_admin={self._is_admin}"
                )
            else:
                logger.warning(f"User {self.user_id} not found during ACL initialization")

        except Exception as e:
            logger.error(f"Error initializing Table ACL provider: {e}")
            pass

        self._initialized = True

    async def check_permission(
        self,
        db: AsyncSession,
        document_id: UUID,
        permission: Permission,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Check if user has a specific permission on a document.

        Delegates to DocumentACLService for compatibility.
        """
        service = self._get_acl_service()

        # Map core.acl.Permission to app.schemas.document_acl.Permission
        from app.schemas.document_acl import Permission as SchemaPermission

        permission_map = {
            Permission.VIEW: SchemaPermission.VIEW,
            Permission.EDIT: SchemaPermission.EDIT,
            Permission.DELETE: SchemaPermission.DELETE,
            Permission.SHARE: SchemaPermission.SHARE,
        }

        return await service.check_permission(
            db,
            document_id,
            permission_map[permission],
        )

    async def get_effective_permissions(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: Optional[str] = None,
    ) -> PermissionSet:
        """
        Get all effective permissions for a user on a document.

        Delegates to DocumentACLService and converts response.
        """
        service = self._get_acl_service()
        effective = await service.get_effective_permissions(db, document_id)

        return PermissionSet(
            can_view=effective.can_view,
            can_edit=effective.can_edit,
            can_delete=effective.can_delete,
            can_share=effective.can_share,
            is_owner=effective.is_owner,
            is_admin=effective.is_admin,
            from_user_acl=effective.from_user_acl,
            from_role_acl=effective.from_role_acl,
            from_everyone_acl=effective.from_everyone_acl,
        )

    async def get_accessible_document_ids(
        self,
        db: AsyncSession,
        permission: Permission = Permission.VIEW,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[UUID]:
        """
        Get list of document IDs the user can access.

        For Table ACL, this queries:
            - Documents owned by user
            - Documents with explicit user ACL
            - Documents with matching role ACL
            - Documents with 'everyone' ACL
        """
        try:
            from app.db.models import Document, DocumentACL
            from app.schemas.document_acl import GranteeType

            # Build subquery for ACL-accessible documents
            acl_conditions = [
                # Explicit user ACL
                and_(
                    DocumentACL.grantee_type == GranteeType.USER.value,
                    DocumentACL.grantee_id == self.user_id,
                ),
                # Everyone ACL
                DocumentACL.grantee_type == GranteeType.EVERYONE.value,
            ]

            # Add role conditions
            for role_id in self._user_roles:
                acl_conditions.append(
                    and_(
                        DocumentACL.grantee_type == GranteeType.ROLE.value,
                        DocumentACL.grantee_id == role_id,
                    )
                )

            # Permission column mapping
            permission_column = {
                Permission.VIEW: DocumentACL.can_view,
                Permission.EDIT: DocumentACL.can_edit,
                Permission.DELETE: DocumentACL.can_delete,
                Permission.SHARE: DocumentACL.can_share,
            }[permission]

            # Documents with matching ACL
            acl_subquery = (
                select(DocumentACL.document_id)
                .where(
                    and_(
                        DocumentACL.tenant_id == self.tenant_id,
                        permission_column == True,
                        or_(*acl_conditions),
                    )
                )
            )

            # Main query: owned documents OR ACL-accessible
            query = (
                select(Document.id)
                .where(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        or_(
                            Document.created_by == self.user_id,  # Owner
                            Document.id.in_(acl_subquery),  # ACL access
                        ),
                    )
                )
                .order_by(Document.created_at.desc())
            )

            # Admin can see all
            if self._is_admin:
                query = (
                    select(Document.id)
                    .where(Document.tenant_id == self.tenant_id)
                    .order_by(Document.created_at.desc())
                )

            if limit:
                query = query.limit(limit).offset(offset)

            result = await db.execute(query)
            return [row[0] for row in result.fetchall()]

        except Exception as e:
            logger.error(f"Error getting accessible document IDs: {e}")
            return []

    async def filter_accessible_documents(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        permission: Permission = Permission.VIEW,
    ) -> List[UUID]:
        """
        Filter a list of document IDs to only those the user can access.
        """
        if not document_ids:
            return []

        try:
            from app.db.models import Document, DocumentACL
            from app.schemas.document_acl import GranteeType

            # Admin can access all
            if self._is_admin:
                query = (
                    select(Document.id)
                    .where(
                        and_(
                            Document.tenant_id == self.tenant_id,
                            Document.id.in_(document_ids),
                        )
                    )
                )
                result = await db.execute(query)
                return [row[0] for row in result.fetchall()]

            # Build ACL conditions
            acl_conditions = [
                and_(
                    DocumentACL.grantee_type == GranteeType.USER.value,
                    DocumentACL.grantee_id == self.user_id,
                ),
                DocumentACL.grantee_type == GranteeType.EVERYONE.value,
            ]

            for role_id in self._user_roles:
                acl_conditions.append(
                    and_(
                        DocumentACL.grantee_type == GranteeType.ROLE.value,
                        DocumentACL.grantee_id == role_id,
                    )
                )

            permission_column = {
                Permission.VIEW: DocumentACL.can_view,
                Permission.EDIT: DocumentACL.can_edit,
                Permission.DELETE: DocumentACL.can_delete,
                Permission.SHARE: DocumentACL.can_share,
            }[permission]

            acl_subquery = (
                select(DocumentACL.document_id)
                .where(
                    and_(
                        DocumentACL.tenant_id == self.tenant_id,
                        DocumentACL.document_id.in_(document_ids),
                        permission_column == True,
                        or_(*acl_conditions),
                    )
                )
            )

            query = (
                select(Document.id)
                .where(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.id.in_(document_ids),
                        or_(
                            Document.created_by == self.user_id,
                            Document.id.in_(acl_subquery),
                        ),
                    )
                )
            )

            result = await db.execute(query)
            accessible_ids = {row[0] for row in result.fetchall()}

            # Preserve original order
            return [doc_id for doc_id in document_ids if doc_id in accessible_ids]

        except Exception as e:
            logger.error(f"Error filtering accessible documents: {e}")
            return []

    async def sync_to_vector_db(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> None:
        """
        Sync ACL changes to Weaviate.

        Delegates to DocumentACLService's sync method.
        """
        service = self._get_acl_service()

        try:
            await service.sync_acl_to_weaviate(db, document_id)
        except Exception as e:
            logger.error(f"Error syncing ACL to Weaviate for {document_id}: {e}")

    async def is_document_owner(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: Optional[str] = None,
    ) -> bool:
        """Check if user is the document owner."""
        effective_user = user_id or self.user_id

        try:
            from app.db.models import Document

            result = await db.execute(
                select(Document.created_by).where(
                    and_(
                        Document.id == document_id,
                        Document.tenant_id == self.tenant_id,
                    )
                )
            )
            row = result.one_or_none()

            if not row:
                return False

            return str(row[0]) == str(effective_user)

        except Exception as e:
            logger.error(f"Error checking document ownership: {e}")
            return False
