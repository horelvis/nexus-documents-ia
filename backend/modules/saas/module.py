"""
SaaS Module Registration.

This module configures the application for SaaS deployment:
    - Registers TableACLProvider as default ACL provider
    - Includes SaaS-specific routers (Stripe, signatures, site portal)
    - Configures Clerk as default auth provider

Usage:
    from modules.saas import SaaSModule

    # In app/main.py
    if is_saas_mode():
        SaaSModule.register(app)
"""

import logging
from fastapi import FastAPI

from core.acl.factory import ACLProviderFactory
from core.acl.base import ACLProviderType

logger = logging.getLogger(__name__)


class SaaSModule:
    """
    SaaS deployment module.

    Configures the application for SaaS (multi-tenant cloud) environments:
        - Uses Document model for uploaded documents
        - Uses DocumentACL table for fine-grained permissions
        - Uses Clerk for authentication
        - Includes Stripe billing integration
        - Includes digital signatures
        - Includes site portal for external sharing
    """

    _registered = False

    @classmethod
    def register(cls, app: FastAPI) -> None:
        """
        Register the SaaS module with the FastAPI application.

        Args:
            app: The FastAPI application instance
        """
        if cls._registered:
            logger.warning("SaaS module already registered")
            return

        logger.info("Registering SaaS module...")

        # Register ACL provider
        cls._register_acl_provider()

        # Include SaaS-specific routers
        cls._include_routers(app)

        # Configure middleware (if any SaaS specific)
        cls._configure_middleware(app)

        cls._registered = True
        logger.info("SaaS module registered successfully")

    @classmethod
    def _register_acl_provider(cls) -> None:
        """Register the Table ACL provider as default."""
        try:
            from modules.saas.acl.provider import TableACLProvider

            ACLProviderFactory.register(ACLProviderType.TABLE, TableACLProvider)
            ACLProviderFactory.set_default(ACLProviderType.TABLE)

            logger.info("Registered Table ACL provider as default")
        except ImportError as e:
            logger.warning(f"TableACLProvider not available: {e}")
            # SaaS mode can fall back to existing DocumentACLService
            # which is already integrated in the codebase

    @classmethod
    def _include_routers(cls, app: FastAPI) -> None:
        """
        Include SaaS-specific routers.

        Note: Currently SaaS routers (stripe, signatures, etc.) are in
        app/api/v1/ and conditionally included via feature flags.
        This method serves as a placeholder for future migration.
        """
        # SaaS-specific endpoints are currently managed via feature flags
        # in app/api/api.py

        # Future: Move SaaS routes here
        # from modules.saas.api import stripe, signatures, site_portal
        # app.include_router(stripe.router, prefix="/api/v1/stripe")
        # app.include_router(signatures.router, prefix="/api/v1/signatures")

        logger.debug("SaaS routers included (using main api.py for now)")

    @classmethod
    def _configure_middleware(cls, app: FastAPI) -> None:
        """Configure SaaS-specific middleware."""
        # Add any SaaS specific middleware here
        # For example: Rate limiting, usage tracking, etc.
        pass

    @classmethod
    def get_required_features(cls) -> list[str]:
        """
        Get list of features that must be enabled in SaaS mode.

        Returns:
            List of feature names that must be enabled
        """
        return [
            "CLERK_AUTH",
            "STRIPE_BILLING",
            "DIGITAL_SIGNATURES",
            "SITE_PORTAL",
            "DASHBOARD_ANALYTICS",
        ]

    @classmethod
    def get_excluded_features(cls) -> list[str]:
        """
        Get list of features that should be disabled in SaaS mode.

        Returns:
            List of feature names to disable
        """
        return [
            "SSO_MULTI_PROTOCOL",  # Use Clerk instead
            # Connectors are available but not the primary use case
        ]

    @classmethod
    def is_registered(cls) -> bool:
        """Check if the module has been registered."""
        return cls._registered


def get_module_info() -> dict:
    """
    Get information about the SaaS module.

    Returns:
        Dictionary with module metadata
    """
    return {
        "name": "saas",
        "description": "SaaS deployment module with Table ACL and Clerk/Stripe integration",
        "version": "1.0.0",
        "acl_provider": "TableACLProvider",
        "auth_provider": "Clerk",
        "required_features": SaaSModule.get_required_features(),
        "excluded_features": SaaSModule.get_excluded_features(),
    }
