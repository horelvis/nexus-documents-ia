"""
SaaS Module - Code specific to SaaS deployments.

This module includes:
    - Table ACL provider (uses DocumentACL table for fine-grained permissions)
    - Clerk authentication integration
    - Stripe billing integration
    - Digital signatures
    - Site portal

Activated when: DEPLOYMENT_MODE=saas
"""

from modules.saas.module import SaaSModule

__all__ = ["SaaSModule"]
