"""
Connector Adapters Package

Unified interface for external data source connectors.
Provides the ConnectorAdapterFactory for creating appropriate adapter instances.

Usage:
    from app.services.connectors import ConnectorAdapterFactory

    # Get adapter for a connector
    adapter = ConnectorAdapterFactory.get_adapter(connector)

    # List documents
    docs, has_more = await adapter.list_documents()

    # Download content
    content = await adapter.download_content(doc)

    # Health check
    health = await adapter.health_check()
"""
import logging
from typing import Type, Dict

from app.db.models import Connector
from app.schemas.connector import (
    ConnectorType,
    AlfrescoConfig,
    SharePointConfig,
    OneDriveConfig,
    GoogleWorkspaceConfig,
    S3Config,
    AzureBlobConfig,
)

from .base import (
    ConnectorAdapter,
    ConnectorError,
    ConnectorConnectionError,
    ConnectorAuthError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
)
from .alfresco import AlfrescoAdapter

logger = logging.getLogger(__name__)


# Registry of adapter classes by connector type
_ADAPTER_REGISTRY: Dict[str, Type[ConnectorAdapter]] = {
    "alfresco": AlfrescoAdapter,
    # Future adapters:
    # "sharepoint": SharePointAdapter,
    # "onedrive": OneDriveAdapter,
    # "google_drive": GoogleDriveAdapter,
    # "s3": S3Adapter,
    # "azure_blob": AzureBlobAdapter,
}


class ConnectorAdapterFactory:
    """
    Factory for creating connector adapter instances.

    Uses the connector_type to determine which adapter class to instantiate.
    Validates configuration before creating the adapter.

    Thread-safe and stateless - can be called from any context.
    """

    @classmethod
    def get_adapter(cls, connector: Connector) -> ConnectorAdapter:
        """
        Create an adapter instance for the given connector.

        Args:
            connector: Connector model from database

        Returns:
            ConnectorAdapter instance

        Raises:
            ValueError: If connector type is not supported
            ValidationError: If config is invalid
        """
        connector_type = connector.connector_type

        if connector_type not in _ADAPTER_REGISTRY:
            raise ValueError(
                f"Unsupported connector type: {connector_type}. "
                f"Supported types: {list(_ADAPTER_REGISTRY.keys())}"
            )

        adapter_class = _ADAPTER_REGISTRY[connector_type]
        config = connector.config or {}

        logger.info(
            f"Creating {connector_type} adapter for connector {connector.id} "
            f"(tenant: {connector.tenant_id})"
        )

        return adapter_class(connector=connector, config=config)

    @classmethod
    def is_supported(cls, connector_type: str) -> bool:
        """
        Check if a connector type is supported.

        Args:
            connector_type: Type string (e.g., "alfresco", "sharepoint")

        Returns:
            True if adapter exists for this type
        """
        return connector_type in _ADAPTER_REGISTRY

    @classmethod
    def get_supported_types(cls) -> list:
        """
        Get list of supported connector types.

        Returns:
            List of connector type strings
        """
        return list(_ADAPTER_REGISTRY.keys())

    @classmethod
    def register_adapter(
        cls,
        connector_type: str,
        adapter_class: Type[ConnectorAdapter],
    ) -> None:
        """
        Register a new adapter type (for plugins/extensions).

        Args:
            connector_type: Type string
            adapter_class: Adapter class implementing ConnectorAdapter
        """
        if not issubclass(adapter_class, ConnectorAdapter):
            raise TypeError(
                f"Adapter class must inherit from ConnectorAdapter"
            )
        _ADAPTER_REGISTRY[connector_type] = adapter_class
        logger.info(f"Registered adapter for connector type: {connector_type}")


# Convenience function
def get_adapter(connector: Connector) -> ConnectorAdapter:
    """
    Shortcut for ConnectorAdapterFactory.get_adapter().

    Args:
        connector: Connector model

    Returns:
        ConnectorAdapter instance
    """
    return ConnectorAdapterFactory.get_adapter(connector)


# Export public interface
__all__ = [
    # Factory
    "ConnectorAdapterFactory",
    "get_adapter",
    # Base classes
    "ConnectorAdapter",
    # Exceptions
    "ConnectorError",
    "ConnectorConnectionError",
    "ConnectorAuthError",
    "ConnectorPermissionError",
    "ConnectorRateLimitError",
    # Adapters
    "AlfrescoAdapter",
]
