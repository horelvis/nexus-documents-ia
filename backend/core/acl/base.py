"""
Base classes for ACL (Access Control List) providers.

This module defines the abstract interface for ACL providers,
allowing pluggable ACL backends (Table-based for SaaS, JSONB for On-Premise).

Usage:
    from core.acl.base import ACLProvider, Permission

    class MyACLProvider(ACLProvider):
        async def check_permission(self, db, doc_id, permission) -> bool:
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class ACLProviderType(Enum):
    """Supported ACL provider types."""
    JSONB = "jsonb"      # Uses JSONB fields in IndexedDocument (On-Premise)


class Permission(str, Enum):
    """Individual permission types."""
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"
    SHARE = "share"


@dataclass
class PermissionSet:
    """
    Set of permissions for a document.

    Represents the combined permissions a user has on a document.
    """
    can_view: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False

    # Source tracking (for debugging/UI)
    is_owner: bool = False
    is_admin: bool = False
    from_user_acl: bool = False
    from_role_acl: bool = False
    from_group_acl: bool = False
    from_everyone_acl: bool = False

    @classmethod
    def full_access(cls, is_owner: bool = False, is_admin: bool = False) -> "PermissionSet":
        """Create a permission set with full access."""
        return cls(
            can_view=True,
            can_edit=True,
            can_delete=True,
            can_share=True,
            is_owner=is_owner,
            is_admin=is_admin,
        )

    @classmethod
    def view_only(cls, source: str = "user") -> "PermissionSet":
        """Create a permission set with view-only access."""
        ps = cls(can_view=True)
        if source == "user":
            ps.from_user_acl = True
        elif source == "role":
            ps.from_role_acl = True
        elif source == "group":
            ps.from_group_acl = True
        elif source == "everyone":
            ps.from_everyone_acl = True
        return ps

    @classmethod
    def no_access(cls) -> "PermissionSet":
        """Create a permission set with no access."""
        return cls()

    def has_permission(self, permission: Permission) -> bool:
        """Check if this set includes a specific permission."""
        mapping = {
            Permission.VIEW: self.can_view,
            Permission.EDIT: self.can_edit,
            Permission.DELETE: self.can_delete,
            Permission.SHARE: self.can_share,
        }
        return mapping.get(permission, False)

    def merge(self, other: "PermissionSet") -> "PermissionSet":
        """Merge with another permission set (union of permissions)."""
        return PermissionSet(
            can_view=self.can_view or other.can_view,
            can_edit=self.can_edit or other.can_edit,
            can_delete=self.can_delete or other.can_delete,
            can_share=self.can_share or other.can_share,
            is_owner=self.is_owner or other.is_owner,
            is_admin=self.is_admin or other.is_admin,
            from_user_acl=self.from_user_acl or other.from_user_acl,
            from_role_acl=self.from_role_acl or other.from_role_acl,
            from_group_acl=self.from_group_acl or other.from_group_acl,
            from_everyone_acl=self.from_everyone_acl or other.from_everyone_acl,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "can_view": self.can_view,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_share": self.can_share,
            "is_owner": self.is_owner,
            "is_admin": self.is_admin,
            "from_user_acl": self.from_user_acl,
            "from_role_acl": self.from_role_acl,
            "from_group_acl": self.from_group_acl,
            "from_everyone_acl": self.from_everyone_acl,
        }


class ACLProvider(ABC):
    """
    Abstract base class for ACL providers.

    All ACL providers (Table-based, JSONB) must implement this interface
    to be usable with the ACL factory.

    Providers handle permission checking and document access filtering
    based on their storage mechanism (dedicated table vs JSONB fields).
    """

    def __init__(self, tenant_id: str, user_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize provider with tenant and user context.

        Args:
            tenant_id: The tenant ID for scoping queries
            user_id: The user ID for permission checks
            config: Optional provider-specific configuration
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.config = config or {}
        self._initialized = False
        self._user_roles: List[str] = []
        self._user_groups: List[str] = []
        self._is_admin: bool = False

    @property
    @abstractmethod
    def provider_type(self) -> ACLProviderType:
        """Return the provider type."""
        pass

    @abstractmethod
    async def initialize(self, db: AsyncSession) -> None:
        """
        Initialize the provider (load user roles, groups, admin status).

        Called once when the provider is first used. Should load
        user's roles, groups, and admin status from the database.

        Args:
            db: Database session for queries
        """
        pass

    @abstractmethod
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
            user_id: Optional user ID override (default: self.user_id)

        Returns:
            True if user has the permission, False otherwise
        """
        pass

    @abstractmethod
    async def get_effective_permissions(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: Optional[str] = None,
    ) -> PermissionSet:
        """
        Get all effective permissions for a user on a document.

        Args:
            db: Database session
            document_id: The document to check
            user_id: Optional user ID override (default: self.user_id)

        Returns:
            PermissionSet with all effective permissions
        """
        pass

    @abstractmethod
    async def get_accessible_document_ids(
        self,
        db: AsyncSession,
        permission: Permission = Permission.VIEW,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[UUID]:
        """
        Get list of document IDs the user can access with given permission.

        This is used for filtering search results and document lists.

        Args:
            db: Database session
            permission: The permission to filter by
            limit: Maximum number of IDs to return
            offset: Offset for pagination

        Returns:
            List of document IDs user can access
        """
        pass

    @abstractmethod
    async def filter_accessible_documents(
        self,
        db: AsyncSession,
        document_ids: List[UUID],
        permission: Permission = Permission.VIEW,
    ) -> List[UUID]:
        """
        Filter a list of document IDs to only those the user can access.

        More efficient than checking each document individually.

        Args:
            db: Database session
            document_ids: List of document IDs to filter
            permission: The permission to filter by

        Returns:
            Filtered list of accessible document IDs
        """
        pass

    @abstractmethod
    async def sync_to_vector_db(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> None:
        """
        Sync ACL changes to the vector database (Weaviate).

        Called after ACL changes to update vector DB metadata
        for proper filtering during semantic search.

        Args:
            db: Database session
            document_id: The document whose ACL changed
        """
        pass

    async def is_document_owner(
        self,
        db: AsyncSession,
        document_id: UUID,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Check if user is the document owner.

        Default implementation - can be overridden by providers.

        Args:
            db: Database session
            document_id: The document to check
            user_id: Optional user ID override

        Returns:
            True if user owns the document
        """
        # Subclasses should implement based on their document model
        return False

    def set_user_context(
        self,
        roles: List[str],
        groups: List[str],
        is_admin: bool = False,
    ) -> None:
        """
        Set user's roles and groups for permission checks.

        Args:
            roles: List of role names/IDs
            groups: List of group names/IDs
            is_admin: Whether user is tenant admin
        """
        self._user_roles = roles
        self._user_groups = groups
        self._is_admin = is_admin


class ACLProviderError(Exception):
    """Base exception for ACL provider errors."""
    pass


class ProviderNotConfiguredError(ACLProviderError):
    """Provider is not properly configured."""
    pass


class DocumentNotFoundError(ACLProviderError):
    """Document not found."""
    pass


class PermissionDeniedError(ACLProviderError):
    """User does not have required permission."""
    pass
