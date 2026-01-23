"""
Authentication Provider Factory.

Manages provider instances and selects the appropriate provider
based on tenant configuration or deployment mode.

Usage:
    from app.core.auth.factory import AuthProviderFactory

    # Get provider for a specific tenant
    provider = await AuthProviderFactory.get_for_tenant(tenant_id, db)

    # Get the default provider (based on deployment mode)
    provider = await AuthProviderFactory.get_default()
"""

import logging
from typing import Dict, Type, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.features import Feature, FeatureFlags, is_on_premise_mode
from app.core.auth.base import (
    AuthProvider,
    AuthProviderType,
    ProviderNotConfiguredError,
)

logger = logging.getLogger(__name__)


class AuthProviderFactory:
    """
    Factory for creating and managing authentication providers.

    Providers are cached per-tenant for efficiency.
    """

    # Registry of provider classes
    _providers: Dict[AuthProviderType, Type[AuthProvider]] = {}

    # Cache of provider instances (tenant_id -> provider)
    _instances: Dict[str, AuthProvider] = {}

    # Default provider instance (for non-tenant requests)
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
    async def get_for_tenant(
        cls,
        tenant_id: str,
        db: AsyncSession,
    ) -> AuthProvider:
        """
        Get the authentication provider configured for a tenant.

        Args:
            tenant_id: The tenant identifier
            db: Database session for loading config

        Returns:
            Configured AuthProvider instance

        Raises:
            ProviderNotConfiguredError: If provider cannot be created
        """
        # Check cache first
        cache_key = tenant_id
        if cache_key in cls._instances:
            return cls._instances[cache_key]

        # Load tenant auth config from database
        config = await cls._load_tenant_auth_config(tenant_id, db)

        if not config:
            # No tenant-specific config, use default
            tenant_display = tenant_id[:8] if tenant_id else "None"
            logger.debug(f"No auth config for tenant {tenant_display}..., using default")
            return await cls.get_default()

        # Create provider based on config
        provider_type = AuthProviderType(config.get("provider", "clerk"))
        provider = await cls._create_provider(provider_type, config)

        # Cache it
        cls._instances[cache_key] = provider
        tenant_display = tenant_id[:8] if tenant_id else "None"
        logger.info(f"Created {provider_type.value} provider for tenant {tenant_display}...")

        return provider

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
    async def _load_tenant_auth_config(
        cls,
        tenant_id: str,
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        Load authentication configuration for a tenant.

        Args:
            tenant_id: Tenant identifier
            db: Database session

        Returns:
            Configuration dictionary or None if not configured
        """
        try:
            # Try to load TenantAuthConfig if it exists
            from app.db.models import TenantAuthConfig

            result = await db.execute(
                select(TenantAuthConfig).where(
                    TenantAuthConfig.tenant_id == tenant_id
                )
            )
            auth_config = result.scalar_one_or_none()

            if not auth_config:
                return None

            # Build config dict from model
            config = {
                "provider": auth_config.provider,
                "auto_provision_users": auth_config.auto_provision_users,
                "group_role_mapping": auth_config.group_role_mapping or {},
            }

            # Add provider-specific config
            if auth_config.provider == "oidc" and auth_config.oidc_config:
                config.update(auth_config.oidc_config)
            elif auth_config.provider == "saml" and auth_config.saml_config:
                config.update(auth_config.saml_config)
            elif auth_config.provider == "ldap" and auth_config.ldap_config:
                config.update(auth_config.ldap_config)

            return config

        except Exception as e:
            # TenantAuthConfig might not exist yet (migration not run)
            # Rollback to clear the failed transaction state
            await db.rollback()
            logger.debug(f"Could not load tenant auth config: {e}")
            return None

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
    def clear_cache(cls, tenant_id: Optional[str] = None):
        """
        Clear cached provider instances.

        Args:
            tenant_id: Specific tenant to clear, or None for all
        """
        if tenant_id:
            cls._instances.pop(tenant_id, None)
        else:
            cls._instances.clear()
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
