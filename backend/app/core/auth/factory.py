"""
Authentication Provider Factory.

Manages provider instances based on deployment mode.

Single-tenant deployment: there is one auth provider configured via env
vars (OIDC for on-premise, Clerk for the deprecated SaaS mode). The
previous multi-tenant `get_for_tenant()` and the `TenantAuthConfig`
table-backed loader were removed during the multi-tenancy refactor.

Usage:
    from app.core.auth.factory import AuthProviderFactory

    provider = await AuthProviderFactory.get_default()
"""

import logging
from typing import Dict, Type, Optional, Any

from app.core.features import Feature, FeatureFlags, is_on_premise_mode
from app.core.auth.base import (
    AuthProvider,
    AuthProviderType,
    ProviderNotConfiguredError,
)

logger = logging.getLogger(__name__)


class AuthProviderFactory:
    """
    Factory for creating and managing the deployment's auth provider.

    There is exactly one provider per deployment, cached as
    _default_instance.
    """

    # Registry of provider classes
    _providers: Dict[AuthProviderType, Type[AuthProvider]] = {}

    # Default provider instance (single-tenant deployment)
    _default_instance: Optional[AuthProvider] = None

    @classmethod
    def register(cls, provider_type: AuthProviderType, provider_class: Type[AuthProvider]):
        """
        Register a provider implementation.

        Args:
            provider_type: The type of provider
            provider_class: The provider class to instantiate
        """
        cls._providers[provider_type] = provider_class
        logger.info(f"Registered auth provider: {provider_type.value}")

    @classmethod
    async def get_default(cls) -> AuthProvider:
        """
        Get the default authentication provider based on deployment mode.

        Returns:
            Default AuthProvider instance
        """
        if cls._default_instance:
            return cls._default_instance

        # Determine provider type based on deployment mode
        if is_on_premise_mode():
            # On-premise defaults to OIDC (most common enterprise SSO)
            provider_type = AuthProviderType.OIDC
            config = cls._get_default_oidc_config()
        else:
            # SaaS mode uses Clerk
            provider_type = AuthProviderType.CLERK
            config = cls._get_default_clerk_config()

        cls._default_instance = await cls._create_provider(provider_type, config)
        logger.info(f"Created default {provider_type.value} provider")

        return cls._default_instance

    @classmethod
    async def _create_provider(
        cls,
        provider_type: AuthProviderType,
        config: Dict[str, Any],
    ) -> AuthProvider:
        """
        Create a provider instance.

        Args:
            provider_type: Type of provider to create
            config: Provider configuration

        Returns:
            Initialized AuthProvider
        """
        provider_class = cls._providers.get(provider_type)

        if not provider_class:
            raise ProviderNotConfiguredError(
                f"No implementation registered for {provider_type.value}"
            )

        provider = provider_class(config)
        await provider.initialize()

        return provider

    @classmethod
    def _get_default_clerk_config(cls) -> Dict[str, Any]:
        """Get default Clerk configuration from environment."""
        from app.core.config import settings

        return {
            "provider": "clerk",
            "secret_key": settings.CLERK_SECRET_KEY,
            "publishable_key": getattr(settings, "CLERK_PUBLISHABLE_KEY", None),
        }

    @classmethod
    def _get_default_oidc_config(cls) -> Dict[str, Any]:
        """Get default OIDC configuration from environment."""
        import os

        return {
            "provider": "oidc",
            "issuer": os.getenv("OIDC_ISSUER", ""),
            # Internal issuer for fetching JWKS (Docker internal DNS)
            # Use this when issuer hostname differs from internal service name
            # Example: issuer=http://localhost:8080/realms/x, internal=http://keycloak:8080/realms/x
            "internal_issuer": os.getenv("OIDC_INTERNAL_ISSUER", ""),
            "client_id": os.getenv("OIDC_CLIENT_ID", ""),
            "client_secret": os.getenv("OIDC_CLIENT_SECRET", ""),
            "scopes": os.getenv("OIDC_SCOPES", "openid profile email").split(),
            "auto_provision_users": os.getenv("OIDC_AUTO_PROVISION", "true").lower() == "true",
        }

    @classmethod
    def clear_cache(cls):
        """Clear the cached default provider instance."""
        cls._default_instance = None

    @classmethod
    def get_registered_providers(cls) -> list[str]:
        """Get list of registered provider types."""
        return [p.value for p in cls._providers.keys()]


# Auto-register providers on import
def _register_default_providers():
    """Register the default provider implementations."""
    try:
        from app.core.auth.providers.clerk import ClerkAuthProvider
        AuthProviderFactory.register(AuthProviderType.CLERK, ClerkAuthProvider)
    except ImportError:
        logger.debug("Clerk provider not available")

    try:
        from app.core.auth.providers.oidc import OIDCAuthProvider
        AuthProviderFactory.register(AuthProviderType.OIDC, OIDCAuthProvider)
    except ImportError:
        logger.debug("OIDC provider not available")

    try:
        from app.core.auth.providers.saml import SAMLAuthProvider
        AuthProviderFactory.register(AuthProviderType.SAML, SAMLAuthProvider)
    except ImportError:
        logger.debug("SAML provider not available")

    try:
        from app.core.auth.providers.ldap import LDAPAuthProvider
        AuthProviderFactory.register(AuthProviderType.LDAP, LDAPAuthProvider)
    except ImportError:
        logger.debug("LDAP provider not available")


# Register providers when module loads
_register_default_providers()
