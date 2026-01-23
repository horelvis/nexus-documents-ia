"""
SaaS ACL Module.

Provides Table-based access control using dedicated DocumentACL table:
    - Fine-grained permissions per document
    - Supports user, role, and 'everyone' grantees
    - Audit trail for all ACL changes
    - Expiration support for temporary access
"""

from modules.saas.acl.provider import TableACLProvider

__all__ = ["TableACLProvider"]
