"""
Graph Provider Factory

Creates and manages graph provider instances based on configuration.

The factory pattern allows switching between graph databases (Apache AGE,
Neo4j, etc.) without changing application code.

Usage:
    from app.services.sil.graph import get_graph_provider

    # Get configured provider (singleton)
    provider = await get_graph_provider()

    # Or get a specific provider
    provider = await get_graph_provider("apache_age")

Configuration:
    Set GRAPH_PROVIDER environment variable:
    - "apache_age" (default)
    - "neo4j" (future)
"""

import logging
from typing import Optional

from .graph_provider import GraphProvider
from .age_provider import AGEProvider

logger = logging.getLogger(__name__)


class GraphProviderFactory:
    """
    Factory for creating graph provider instances.

    Supports multiple provider types and maintains singletons
    for efficient resource usage.
    """

    _instances: dict = {}

    @classmethod
    async def get_provider(
        cls,
        provider_type: Optional[str] = None,
        **kwargs,
    ) -> GraphProvider:
        """
        Get a graph provider instance.

        Args:
            provider_type: Type of provider ("apache_age", "neo4j")
                          If None, uses configuration default
            **kwargs: Provider-specific configuration

        Returns:
            Initialized GraphProvider instance

        Raises:
            ValueError: If provider_type is unknown
        """
        # Determine provider type from config if not specified
        if provider_type is None:
            provider_type = cls._get_default_provider_type()

        # Return cached instance if available
        cache_key = f"{provider_type}:{hash(frozenset(kwargs.items()))}"
        if cache_key in cls._instances:
            provider = cls._instances[cache_key]
            if await provider.is_available():
                return provider

        # Create new instance
        provider = cls._create_provider(provider_type, **kwargs)
        await provider.initialize()

        # Cache the instance
        cls._instances[cache_key] = provider

        logger.info(f"✅ Created graph provider: {provider_type}")
        return provider

    @classmethod
    def _get_default_provider_type(cls) -> str:
        """Get default provider type from configuration."""
        try:
            from app.core.config import settings

            # Check for explicit setting
            if hasattr(settings, "graph_provider"):
                return settings.graph_provider

            # Default to Apache AGE
            return "apache_age"

        except ImportError:
            return "apache_age"

    @classmethod
    def _create_provider(cls, provider_type: str, **kwargs) -> GraphProvider:
        """Create a new provider instance."""
        if provider_type == "apache_age":
            return cls._create_age_provider(**kwargs)

        elif provider_type == "neo4j":
            return cls._create_neo4j_provider(**kwargs)

        else:
            raise ValueError(f"Unknown graph provider type: {provider_type}")

    @classmethod
    def _create_age_provider(cls, **kwargs) -> AGEProvider:
        """Create an AGE provider with configuration."""
        try:
            from app.core.config import settings

            return AGEProvider(
                host=kwargs.get("host", getattr(settings, "postgres_host", "localhost")),
                port=kwargs.get("port", getattr(settings, "postgres_port", 5432)),
                database=kwargs.get("database", getattr(settings, "postgres_db", "nexus")),
                user=kwargs.get("user", getattr(settings, "postgres_user", "postgres")),
                password=kwargs.get("password", getattr(settings, "postgres_password", "")),
                graph_name=kwargs.get("graph_name", getattr(settings, "age_graph_name", "knowledge_graph")),
                pool_size=kwargs.get("pool_size", 10),
            )

        except ImportError:
            # Fallback for testing without full app context
            return AGEProvider(
                host=kwargs.get("host", "localhost"),
                port=kwargs.get("port", 5432),
                database=kwargs.get("database", "nexus"),
                user=kwargs.get("user", "postgres"),
                password=kwargs.get("password", ""),
                graph_name=kwargs.get("graph_name", "knowledge_graph"),
                pool_size=kwargs.get("pool_size", 10),
            )

    @classmethod
    def _create_neo4j_provider(cls, **kwargs) -> GraphProvider:
        """Create a Neo4j provider with configuration."""
        from .neo4j_provider import Neo4jProvider

        try:
            from app.core.config import settings

            return Neo4jProvider(
                uri=kwargs.get("uri", getattr(settings, "neo4j_uri", "bolt://localhost:7687")),
                user=kwargs.get("user", getattr(settings, "neo4j_user", "neo4j")),
                password=kwargs.get("password", getattr(settings, "neo4j_password", "")),
                database=kwargs.get("database", getattr(settings, "neo4j_database", "neo4j")),
            )

        except ImportError:
            return Neo4jProvider(
                uri=kwargs.get("uri", "bolt://localhost:7687"),
                user=kwargs.get("user", "neo4j"),
                password=kwargs.get("password", ""),
                database=kwargs.get("database", "neo4j"),
            )

    @classmethod
    async def close_all(cls) -> None:
        """Close all cached provider instances."""
        for key, provider in list(cls._instances.items()):
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider {key}: {e}")

        cls._instances.clear()
        logger.info("✅ All graph providers closed")

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the provider cache (for testing)."""
        cls._instances.clear()


# =============================================================================
# Convenience Functions
# =============================================================================

# Global provider instance (lazy initialized)
_default_provider: Optional[GraphProvider] = None


async def get_graph_provider(provider_type: Optional[str] = None, **kwargs) -> GraphProvider:
    """
    Get the graph provider instance.

    This is the primary entry point for accessing the graph database.

    Args:
        provider_type: Optional provider type override
        **kwargs: Provider-specific configuration

    Returns:
        Initialized GraphProvider instance

    Example:
        provider = await get_graph_provider()
        await provider.add_node(GraphNode(...))
    """
    global _default_provider

    if provider_type is None and not kwargs and _default_provider is not None:
        if await _default_provider.is_available():
            return _default_provider

    provider = await GraphProviderFactory.get_provider(provider_type, **kwargs)

    if provider_type is None and not kwargs:
        _default_provider = provider

    return provider


async def close_graph_provider() -> None:
    """Close the default graph provider."""
    global _default_provider

    if _default_provider is not None:
        await _default_provider.close()
        _default_provider = None

    await GraphProviderFactory.close_all()
