"""
ACL Provider Factory.

Manages ACL provider instances and selects the appropriate provider
based on deployment mode (SaaS vs On-Premise).

Usage:
    from core.acl.factory import ACLProviderFactory

    # Get provider for current context
    provider = await ACLProviderFactory.get_provider(tenant_id, user_id, db)

    # Check permission
    allowed = await provider.check_permission(db, doc_id, Permission.VIEW)
"""

import logging
from typing import Dict, Type, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.acl.base import (
    ACLProvider,
    ACLProviderType,
    ProviderNotConfiguredError,
)

logger = logging.getLogger(__name__)


class ACLProviderFactory:
    """
    Factory for creating and managing ACL providers.

    Providers are cached per (tenant_id, user_id) for efficiency.
    The active provider type is determined by deployment mode.
    """

    # Registry of provider classes
    _providers: Dict[ACLProviderType, Type[ACLProvider]] = {}

    # Cache of provider instances ((tenant_id, user_id) -> provider)
    _instances: Dict[str, ACLProvider] = {}

    # Default provider type (set based on deployment mode)
    _default_type: Optional[ACLProviderType] = None

    @classmethod
    def register(cls, provider_type: ACLProviderType, provider_class: Type[ACLProvider]):
        """
        Register a provider implementation.

        Args:
            provider_type: The type of provider (TABLE or JSONB)
            provider_class: The provider class to instantiate
        """
        cls._providers[provider_type] = provider_class
        logger.info(f"Registered ACL provider: {provider_type.value}")

    @classmethod
    def set_default(cls, provider_type: ACLProviderType):
        """
        Set the default provider type.

        Called by module registration to set which provider to use.

        Args:
            provider_type: The default provider type
        """
        cls._default_type = provider_type
        logger.info(f"Set default ACL provider: {provider_type.value}")

    @classmethod
    async def get_provider(
        cls,
        tenant_id: str,
        user_id: str,
        db: AsyncSession,
        provider_type: Optional[ACLProviderType] = None,
    ) -> ACLProvider:
        """
        Get an ACL provider for the given tenant and user.

        Args:
            tenant_id: The tenant identifier
            user_id: The user identifier
            db: Database session for initialization
            provider_type: Optional override (default: use default type)

        Returns:
            Initialized ACLProvider instance

        Raises:
            ProviderNotConfiguredError: If no provider is registered
        """
        # Determine provider type
        target_type = provider_type or cls._default_type

        if not target_type:
            # Auto-detect based on deployment mode
            target_type = cls._detect_provider_type()

        # Check cache
        cache_key = f"{tenant_id}:{user_id}:{target_type.value}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]

        # Create provider
        provider = await cls._create_provider(
            provider_type=target_type,
            tenant_id=tenant_id,
            user_id=user_id,
            db=db,
        )

        # Cache it
        cls._instances[cache_key] = provider
        logger.debug(
            f"Created {target_type.value} ACL provider for "
            f"tenant={tenant_id[:8]}..., user={user_id[:8]}..."
        )

        return provider

    @classmethod
    async def _create_provider(
        cls,
        provider_type: ACLProviderType,
        tenant_id: str,
        user_id: str,
        db: AsyncSession,
    ) -> ACLProvider:
        """
        Create a provider instance.

        Args:
            provider_type: Type of provider to create
            tenant_id: Tenant identifier
            user_id: User identifier
            db: Database session

        Returns:
            Initialized ACLProvider
        """
        provider_class = cls._providers.get(provider_type)

        if not provider_class:
            raise ProviderNotConfiguredError(
                f"No ACL implementation registered for {provider_type.value}. "
                f"Available: {[p.value for p in cls._providers.keys()]}"
            )

        # Create provider
        provider = provider_class(tenant_id=tenant_id, user_id=user_id)

        # Initialize (loads user roles, groups, admin status)
        await provider.initialize(db)

        return provider

    @classmethod
    def _detect_provider_type(cls) -> ACLProviderType:
        """Always return JSONB — this app is on-premise only."""
        return ACLProviderType.JSONB

    @classmethod
    def clear_cache(
        cls,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        Clear cached provider instances.

        Args:
            tenant_id: Specific tenant to clear (None for all)
            user_id: Specific user to clear (None for all)
        """
        if tenant_id and user_id:
            # Clear specific user
            keys_to_remove = [
                k for k in cls._instances.keys()
                if k.startswith(f"{tenant_id}:{user_id}:")
            ]
        elif tenant_id:
            # Clear all users for tenant
            keys_to_remove = [
                k for k in cls._instances.keys()
                if k.startswith(f"{tenant_id}:")
            ]
        else:
            # Clear all
            keys_to_remove = list(cls._instances.keys())

        for key in keys_to_remove:
            cls._instances.pop(key, None)

        if keys_to_remove:
            logger.debug(f"Cleared {len(keys_to_remove)} ACL provider cache entries")

    @classmethod
    def get_registered_providers(cls) -> list[str]:
        """Get list of registered provider types."""
        return [p.value for p in cls._providers.keys()]

    @classmethod
    def get_default_type(cls) -> Optional[str]:
        """Get the current default provider type."""
        return cls._default_type.value if cls._default_type else None


def _register_default_providers():
    """
    Auto-register providers based on availability.

    This is called at module import to register available providers.
    Modules override the default via set_default().
    """
    try:
        from modules.on_premise.acl.provider import JSONBACLProvider
        ACLProviderFactory.register(ACLProviderType.JSONB, JSONBACLProvider)
    except ImportError:
        logger.debug("JSONB ACL provider not available (on-premise module not loaded)")


# Register providers when module loads
# Note: This will fail silently if modules aren't installed yet
# The modules themselves will register their providers on load
try:
    _register_default_providers()
except Exception as e:
    logger.debug(f"Could not auto-register ACL providers: {e}")
