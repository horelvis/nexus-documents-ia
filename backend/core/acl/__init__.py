"""
Core ACL Module - Abstract Access Control Layer.

This module defines the abstract interface for ACL providers, allowing
pluggable ACL backends for different deployment modes:
    - SaaS: TableACLProvider (uses DocumentACL table)
    - On-Premise: JSONBACLProvider (uses IndexedDocument JSONB fields)

Usage:
    from core.acl import ACLProvider, ACLProviderFactory, Permission

    # Get provider for current tenant
    provider = ACLProviderFactory.get_provider(tenant_id, user_id)

    # Check permission
    allowed = await provider.check_permission(db, doc_id, Permission.VIEW)

    # Get accessible documents
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
