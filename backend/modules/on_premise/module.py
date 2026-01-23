"""
On-Premise Module Registration.

This module configures the application for on-premise deployment:
    - Registers JSONBACLProvider as default ACL provider
    - Includes on-premise-specific routers (connectors, user_sync)
    - Configures OIDC as default auth provider

Usage:
    from modules.on_premise import OnPremiseModule

    # In app/main.py
    if is_on_premise_mode():
        OnPremiseModule.register(app)
"""

import logging
from fastapi import FastAPI

from core.acl.factory import ACLProviderFactory
from core.acl.base import ACLProviderType

logger = logging.getLogger(__name__)


class OnPremiseModule:
    """
    On-Premise deployment module.

    Configures the application for on-premise environments:
        - Uses IndexedDocument for connector-sourced documents
        - Uses JSONB fields for ACL (not separate table)
        - Uses OIDC/SAML for authentication (not Clerk)
        - No Stripe billing integration
        - No digital signatures
    """

    _registered = False

    @classmethod
    def register(cls, app: FastAPI) -> None:
        """
        Register the on-premise module with the FastAPI application.

        Args:
            app: The FastAPI application instance
        """
        if cls._registered:
            logger.warning("On-premise module already registered")
            return

        logger.info("Registering On-Premise module...")

        # Register ACL provider
        cls._register_acl_provider()

        # Include on-premise-specific routers
        cls._include_routers(app)

        # Configure middleware (if any on-premise specific)
        cls._configure_middleware(app)

        cls._registered = True
        logger.info("On-Premise module registered successfully")

    @classmethod
    def _register_acl_provider(cls) -> None:
        """Register the JSONB ACL provider as default."""
        try:
            from modules.on_premise.acl.provider import JSONBACLProvider

            ACLProviderFactory.register(ACLProviderType.JSONB, JSONBACLProvider)
            ACLProviderFactory.set_default(ACLProviderType.JSONB)

            logger.info("Registered JSONB ACL provider as default")
        except ImportError as e:
            logger.error(f"Failed to import JSONBACLProvider: {e}")
            raise

    @classmethod
    def _include_routers(cls, app: FastAPI) -> None:
        """
        Include on-premise-specific routers.

        Note: Connector routers are currently in app/api/v1/connectors.py
        and are always included. In the future, we may move them here
        for cleaner separation.
        """
        # On-premise-specific endpoints will be added here
        # For now, connectors and user_sync are in the main api.py
        # and conditionally enabled via feature flags

        # Future: Move connector routes here
        # from modules.on_premise.api import connectors, user_sync
        # app.include_router(connectors.router, prefix="/api/v1/connectors")
        # app.include_router(user_sync.router, prefix="/api/v1/user-sync")

        logger.debug("On-premise routers included (using main api.py for now)")

    @classmethod
    def _configure_middleware(cls, app: FastAPI) -> None:
        """Configure on-premise-specific middleware."""
        # Add any on-premise specific middleware here
        # For example: IP whitelist, internal network checks, etc.
        pass

    @classmethod
    def get_excluded_features(cls) -> list[str]:
        """
        Get list of features that should be disabled in on-premise mode.

        Returns:
            List of feature names to disable
        """
        return [
            "STRIPE_BILLING",
            "DIGITAL_SIGNATURES",
            "SITE_PORTAL",
            "CLERK_AUTH",  # Use OIDC instead
        ]

    @classmethod
    def get_required_features(cls) -> list[str]:
        """
        Get list of features that must be enabled in on-premise mode.

        Returns:
            List of feature names that must be enabled
        """
        return [
            "SSO_MULTI_PROTOCOL",
            "SHAREPOINT_CONNECTOR",
            "ONEDRIVE_CONNECTOR",
            # "ALFRESCO_CONNECTOR",  # Add when implemented
        ]

    @classmethod
    def is_registered(cls) -> bool:
        """Check if the module has been registered."""
        return cls._registered


def get_module_info() -> dict:
    """
    Get information about the on-premise module.

    Returns:
        Dictionary with module metadata
    """
    return {
        "name": "on_premise",
        "description": "On-premise deployment module with JSONB ACL and connector support",
        "version": "1.0.0",
        "acl_provider": "JSONBACLProvider",
        "auth_provider": "OIDC",
        "excluded_features": OnPremiseModule.get_excluded_features(),
        "required_features": OnPremiseModule.get_required_features(),
    }
