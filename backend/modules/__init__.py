"""
Modules - Deployment-specific code modules.

Modules are loaded based on DEPLOYMENT_MODE:
    - saas: SaaS-specific code (Clerk, Stripe, DocumentACL table)
    - on_premise: On-premise code (OIDC, connectors, JSONB ACL)
"""
