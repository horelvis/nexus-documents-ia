"""
Core ACL Module - Access Control Layer.

Single provider: JSONBACLProvider uses IndexedDocument JSONB fields.

Usage:
    from core.acl import ACLProvider, ACLProviderFactory, Permission

    provider = ACLProviderFactory.get_provider(tenant_id, user_id)
    allowed = await provider.check_permission(db, doc_id, Permission.VIEW)
    doc_ids = await provider.get_accessible_document_ids(db, Permission.VIEW)
"""

from core.acl.base import (
    ACLProvider,
    ACLProviderType,
    Permission,
    PermissionSet,
    ACLProviderError,
    ProviderNotConfiguredError,
)
from core.acl.factory import ACLProviderFactory

__all__ = [
    "ACLProvider",
    "ACLProviderType",
    "ACLProviderFactory",
    "Permission",
    "PermissionSet",
    "ACLProviderError",
    "ProviderNotConfiguredError",
]
