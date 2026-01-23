"""
On-Premise ACL Module.

Provides JSONB-based access control using IndexedDocument fields:
    - owner_id: Document owner (full access)
    - is_tenant_public: All tenant users can view
    - shared_with_users: List of user IDs with access
    - shared_with_groups: List of SSO groups with access
"""

from modules.on_premise.acl.provider import JSONBACLProvider

__all__ = ["JSONBACLProvider"]
