"""
JSONB ACL Provider for On-Premise deployments.

Uses JSONB fields in IndexedDocument for simple, efficient ACL:
    - owner_id: Document owner (full access)
    - is_tenant_public: All tenant users can view
    - shared_with_users: List of user IDs with view access
    - shared_with_groups: List of SSO groups with view access

This provider is optimized for on-premise deployments where:
    1. Documents come from external connectors (Alfresco, SharePoint)
    2. Access control mirrors source system permissions
    3. SSO groups are synced from enterprise IdP
"""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.acl.base import (
    ACLProvider,
    ACLProviderType,
    Permission,
    PermissionSet,
    DocumentNotFoundError,
)

logger = logging.getLogger(__name__)


class JSONBACLProvider(ACLProvider):
    """
    ACL provider using JSONB fields in IndexedDocument.

    Access hierarchy:
        1. Owner → full access (view, edit, delete, share)
        2. Tenant admin → full access
        3. Tenant public → view only
        4. Shared with user → view only
        5. Shared with group → view only
        6. Default → no access
    """

    @property
    def provider_type(self) -> ACLProviderType:
        return ACLProviderType.JSONB

    async def initialize(self, db: AsyncSession) -> None:
        """
        Initialize provider by loading user context.

        Loads:
            - User's SSO groups (for group-based access)
            - Admin status
            - Roles (for future role-based permissions)
        """
        if self._initialized:
            return

        try:
            from app.db.models import User

            result = await db.execute(
                select(User).where(User.id == self.user_id)
            )
            user = result.scalar_one_or_none()

            if user:
                # Load SSO groups for group-based access
                self._user_groups = user.sso_groups or []

                # Load application roles
                self._user_roles = [role.name for role in user.roles] if user.roles else []

                # Check admin status
                self._is_admin = user.is_superuser

                logger.debug(
                    f"Initialized JSONB ACL provider: user={self.user_id[:8]}..., "
                    f"groups={len(self._user_groups)}, is_admin={self._is_admin}"
                )
            else:
                logger.warning(f"User {self.user_id} not found during ACL initialization")

        except Exception as e:
            logger.error(f"Error initializing JSONB ACL provider: {e}")
            # Don't fail - just proceed with empty groups
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

        Args:
            db: Database session
            document_id: The document to check
            permission: The permission to check
            user_id: Optional user ID override

        Returns:
            True if user has the permission
        """
        effective_user = user_id or self.user_id
        permissions = await self.get_effective_permissions(db, document_id, effective_user)
        return permissions.has_permission(permission)

    async def get_effective_permissions(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: Optional[str] = None,
    ) -> PermissionSet:
        """
        Get all effective permissions for a user on a document.

        Permission hierarchy (highest to lowest):
            1. Owner → full access
            2. Tenant admin → full access
            3. Tenant public → view only
            4. Shared with user → view only
            5. Shared with group → view only
        """
        effective_user = user_id or self.user_id

        try:
            from app.db.models import IndexedDocument

            result = await db.execute(
                select(IndexedDocument).where(
                    and_(
                        IndexedDocument.id == document_id,
                        IndexedDocument.tenant_id == self.tenant_id,
                    )
                )
            )
            doc = result.scalar_one_or_none()

            if not doc:
                raise DocumentNotFoundError(f"Document {document_id} not found")

            # Check owner (full access)
            if str(doc.owner_id) == str(effective_user):
                return PermissionSet.full_access(is_owner=True)

            # Check tenant admin (full access)
            if self._is_admin:
                return PermissionSet.full_access(is_admin=True)

            # For non-owners/non-admins, only view permission is available
            # Edit/Delete/Share are owner-only in on-premise mode

            # Check tenant public
            if doc.is_tenant_public:
                return PermissionSet.view_only(source="everyone")

            # Check shared with user
            shared_users = doc.shared_with_users or []
            if str(effective_user) in [str(u) for u in shared_users]:
                return PermissionSet.view_only(source="user")

            # Check shared with groups
            shared_groups = doc.shared_with_groups or []
            for group in self._user_groups:
                if group in shared_groups:
                    return PermissionSet.view_only(source="group")

            # No access
            return PermissionSet.no_access()

        except DocumentNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error checking permissions for document {document_id}: {e}")
            return PermissionSet.no_access()

    async def get_accessible_document_ids(
        self,
        db: AsyncSession,
        permission: Permission = Permission.VIEW,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[UUID]:
        """
        Get list of document IDs the user can access.

        For JSONB ACL, this builds a query that checks:
            - User is owner
            - Document is tenant public
            - User ID is in shared_with_users
            - User's groups intersect with shared_with_groups
        """
        try:
            from app.db.models import IndexedDocument
            from sqlalchemy import cast, String
            from sqlalchemy.dialects.postgresql import JSONB, array

            # Build access conditions
            conditions = [
                # User is owner
                IndexedDocument.owner_id == self.user_id,
                # Document is tenant public
                IndexedDocument.is_tenant_public == True,
            ]

            # For non-view permissions, only owner/admin has access
            if permission != Permission.VIEW:
                if self._is_admin:
                    # Admin can access all documents for edit/delete/share
                    query = (
                        select(IndexedDocument.id)
                        .where(IndexedDocument.tenant_id == self.tenant_id)
                        .order_by(IndexedDocument.created_at.desc())
                    )
                else:
                    # Non-admin can only edit/delete/share own documents
                    query = (
                        select(IndexedDocument.id)
                        .where(
                            and_(
                                IndexedDocument.tenant_id == self.tenant_id,
                                IndexedDocument.owner_id == self.user_id,
                            )
                        )
                        .order_by(IndexedDocument.created_at.desc())
                    )

                if limit:
                    query = query.limit(limit).offset(offset)

                result = await db.execute(query)
                return [row[0] for row in result.fetchall()]

            # For VIEW permission, use all access conditions

            # User ID in shared_with_users array
            # PostgreSQL: shared_with_users ? 'user_id'
            conditions.append(
                IndexedDocument.shared_with_users.op("?")(str(self.user_id))
            )

            # User's groups intersect with shared_with_groups
            if self._user_groups:
                for group in self._user_groups:
                    conditions.append(
                        IndexedDocument.shared_with_groups.op("?")(group)
                    )

            # Build query with OR conditions (any match grants access)
            query = (
                select(IndexedDocument.id)
                .where(
                    and_(
                        IndexedDocument.tenant_id == self.tenant_id,
                        or_(*conditions),
                    )
                )
                .order_by(IndexedDocument.created_at.desc())
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

        More efficient than checking each document individually.
        """
        if not document_ids:
            return []

        try:
            from app.db.models import IndexedDocument

            # Build access conditions (same as get_accessible_document_ids)
            conditions = [
                IndexedDocument.owner_id == self.user_id,
                IndexedDocument.is_tenant_public == True,
                IndexedDocument.shared_with_users.op("?")(str(self.user_id)),
            ]

            for group in self._user_groups:
                conditions.append(
                    IndexedDocument.shared_with_groups.op("?")(group)
                )

            # For non-view permissions, only owner/admin
            if permission != Permission.VIEW:
                if self._is_admin:
                    query = (
                        select(IndexedDocument.id)
                        .where(
                            and_(
                                IndexedDocument.tenant_id == self.tenant_id,
                                IndexedDocument.id.in_(document_ids),
                            )
                        )
                    )
                else:
                    query = (
                        select(IndexedDocument.id)
                        .where(
                            and_(
                                IndexedDocument.tenant_id == self.tenant_id,
                                IndexedDocument.id.in_(document_ids),
                                IndexedDocument.owner_id == self.user_id,
                            )
                        )
                    )
            else:
                query = (
                    select(IndexedDocument.id)
                    .where(
                        and_(
                            IndexedDocument.tenant_id == self.tenant_id,
                            IndexedDocument.id.in_(document_ids),
                            or_(*conditions),
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

        Updates the Weaviate object's metadata to include ACL info
        for efficient filtering during semantic search.
        """
        try:
            from app.db.models import IndexedDocument

            result = await db.execute(
                select(IndexedDocument).where(IndexedDocument.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc or not doc.weaviate_id:
                logger.debug(f"Document {document_id} not indexed in Weaviate")
                return

            # Prepare ACL metadata for Weaviate
            acl_metadata = {
                "owner_id": str(doc.owner_id),
                "is_tenant_public": doc.is_tenant_public,
                "shared_with_users": [str(u) for u in (doc.shared_with_users or [])],
                "shared_with_groups": doc.shared_with_groups or [],
            }

            # Call Weaviate service to update metadata
            # This is done via HTTP to the weaviate-service
            import httpx
            import os

            weaviate_service_url = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")

            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{weaviate_service_url}/api/v1/weaviate/objects/{doc.weaviate_id}/acl",
                    json=acl_metadata,
                    timeout=10.0,
                )

                if response.status_code not in (200, 204):
                    logger.warning(
                        f"Failed to sync ACL to Weaviate for {document_id}: "
                        f"{response.status_code}"
                    )

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
            from app.db.models import IndexedDocument

            result = await db.execute(
                select(IndexedDocument.owner_id).where(
                    and_(
                        IndexedDocument.id == document_id,
                        IndexedDocument.tenant_id == self.tenant_id,
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

    async def grant_access(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_ids: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        make_public: bool = False,
    ) -> bool:
        """
        Grant access to a document (owner/admin only).

        Args:
            db: Database session
            document_id: Document to update
            user_ids: User IDs to add to shared_with_users
            groups: Groups to add to shared_with_groups
            make_public: Set is_tenant_public to True

        Returns:
            True if successful
        """
        # Verify caller has share permission
        permissions = await self.get_effective_permissions(db, document_id)
        if not permissions.can_share and not permissions.is_owner and not self._is_admin:
            logger.warning(
                f"User {self.user_id} denied share access to document {document_id}"
            )
            return False

        try:
            from app.db.models import IndexedDocument

            result = await db.execute(
                select(IndexedDocument).where(
                    and_(
                        IndexedDocument.id == document_id,
                        IndexedDocument.tenant_id == self.tenant_id,
                    )
                )
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return False

            # Update sharing
            if user_ids:
                current_users = set(doc.shared_with_users or [])
                current_users.update(user_ids)
                doc.shared_with_users = list(current_users)

            if groups:
                current_groups = set(doc.shared_with_groups or [])
                current_groups.update(groups)
                doc.shared_with_groups = list(current_groups)

            if make_public:
                doc.is_tenant_public = True

            await db.commit()

            # Sync to Weaviate
            await self.sync_to_vector_db(db, document_id)

            return True

        except Exception as e:
            logger.error(f"Error granting access to document {document_id}: {e}")
            await db.rollback()
            return False

    async def revoke_access(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_ids: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        make_private: bool = False,
    ) -> bool:
        """
        Revoke access from a document (owner/admin only).

        Args:
            db: Database session
            document_id: Document to update
            user_ids: User IDs to remove from shared_with_users
            groups: Groups to remove from shared_with_groups
            make_private: Set is_tenant_public to False

        Returns:
            True if successful
        """
        # Verify caller has share permission
        permissions = await self.get_effective_permissions(db, document_id)
        if not permissions.can_share and not permissions.is_owner and not self._is_admin:
            logger.warning(
                f"User {self.user_id} denied share revoke access to document {document_id}"
            )
            return False

        try:
            from app.db.models import IndexedDocument

            result = await db.execute(
                select(IndexedDocument).where(
                    and_(
                        IndexedDocument.id == document_id,
                        IndexedDocument.tenant_id == self.tenant_id,
                    )
                )
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return False

            # Update sharing
            if user_ids:
                current_users = set(doc.shared_with_users or [])
                for uid in user_ids:
                    current_users.discard(uid)
                doc.shared_with_users = list(current_users)

            if groups:
                current_groups = set(doc.shared_with_groups or [])
                for group in groups:
                    current_groups.discard(group)
                doc.shared_with_groups = list(current_groups)

            if make_private:
                doc.is_tenant_public = False

            await db.commit()

            # Sync to Weaviate
            await self.sync_to_vector_db(db, document_id)

            return True

        except Exception as e:
            logger.error(f"Error revoking access from document {document_id}: {e}")
            await db.rollback()
            return False
