"""
On-Premise Module - Code specific to on-premise deployments.

This module includes:
    - JSONB ACL provider (uses IndexedDocument fields for access control)
    - Connector APIs (Alfresco, SharePoint, etc.)
    - OIDC/SAML authentication integration

Activated when: DEPLOYMENT_MODE=on_premise
"""

from modules.on_premise.module import OnPremiseModule

__all__ = ["OnPremiseModule"]
