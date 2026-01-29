"""
Connector Registry - Dynamic Discovery and Routing

Este registro permite:
1. Auto-registro de conectores via decorador @register_connector
2. Descubrimiento dinámico de conectores disponibles
3. Routing basado en confianza (can_handle score)
4. Integración automática con el grafo de LangGraph

El grafo de decisiones consulta este registro para determinar
qué conectores pueden manejar una consulta específica.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Type
from dataclasses import dataclass

from .base import BaseConnector, ConnectorCapability, ConnectorResult

logger = logging.getLogger(__name__)


@dataclass
class ConnectorMatch:
    """Result of matching a connector to a query."""
    connector: BaseConnector
    confidence: float
    name: str

    def __lt__(self, other: "ConnectorMatch") -> bool:
        """Sort by confidence (descending) then priority (descending)."""
        if self.confidence != other.confidence:
            return self.confidence > other.confidence
        return self.connector.priority > other.connector.priority


class ConnectorRegistry:
    """
    Central registry for all data connectors.

    Supports dynamic registration and query-based routing.

    Example:
        # In your connector file
        from app.agents.langgraph.connectors import register_connector, BaseConnector

        @register_connector("my_database")
        class MyDatabaseConnector(BaseConnector):
            ...

        # In the decision graph
        from app.agents.langgraph.connectors import get_connectors_for_query

        matches = await get_connectors_for_query(
            query="¿Cuántos registros hay en la base de datos?",
            context={"tenant_id": "xxx"}
        )

        # matches is sorted by confidence, execute the best one
        if matches:
            result = await matches[0].connector.execute(query, context)
    """

    _instance: Optional["ConnectorRegistry"] = None
    _connectors: Dict[str, Type[BaseConnector]] = {}
    _instances: Dict[str, BaseConnector] = {}
    _initialized: bool = False

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._connectors = {}
            cls._instances = {}
            cls._initialized = False
        return cls._instance

    @classmethod
    def register(cls, name: str, connector_class: Type[BaseConnector]):
        """
        Register a connector class.

        Args:
            name: Unique identifier for this connector
            connector_class: The connector class to register
        """
        registry = cls()
        if name in registry._connectors:
            logger.warning(f"Connector '{name}' already registered, overwriting")

        registry._connectors[name] = connector_class
        logger.info(f"📦 Registered connector: {name} ({connector_class.__name__})")

    @classmethod
    def get(cls, name: str) -> Optional[BaseConnector]:
        """
        Get a connector instance by name.

        Lazily initializes the connector on first access.
        """
        registry = cls()

        if name not in registry._connectors:
            return None

        # Lazy instantiation
        if name not in registry._instances:
            connector_class = registry._connectors[name]
            registry._instances[name] = connector_class()
            logger.debug(f"Instantiated connector: {name}")

        return registry._instances[name]

    @classmethod
    def get_all(cls) -> Dict[str, BaseConnector]:
        """Get all registered connectors (instantiates if needed)."""
        registry = cls()

        for name in registry._connectors:
            if name not in registry._instances:
                registry._instances[name] = registry._connectors[name]()

        return registry._instances.copy()

    @classmethod
    async def initialize_all(cls) -> Dict[str, bool]:
        """
        Initialize all registered connectors.

        Returns dict of {name: success} for each connector.
        """
        registry = cls()
        results = {}

        for name, connector in cls.get_all().items():
            try:
                results[name] = await connector.initialize()
                logger.info(f"✅ Initialized connector: {name}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize connector {name}: {e}")
                results[name] = False

        registry._initialized = True
        return results

    @classmethod
    async def get_matches(
        cls,
        query: str,
        context: Dict[str, Any],
        min_confidence: float = 0.1,
        capabilities: Optional[List[ConnectorCapability]] = None,
    ) -> List[ConnectorMatch]:
        """
        Find connectors that can handle a query.

        Args:
            query: The user's query
            context: Execution context
            min_confidence: Minimum confidence to include
            capabilities: Filter by required capabilities

        Returns:
            List of ConnectorMatch sorted by confidence (highest first)
        """
        matches = []

        for name, connector in cls.get_all().items():
            # Filter by capabilities if specified
            if capabilities:
                if not any(cap in connector.capabilities for cap in capabilities):
                    continue

            try:
                confidence = await connector.can_handle(query, context)

                if confidence >= min_confidence:
                    matches.append(ConnectorMatch(
                        connector=connector,
                        confidence=confidence,
                        name=name,
                    ))
                    logger.debug(f"Connector {name} matched with confidence {confidence:.2f}")

            except Exception as e:
                logger.warning(f"Error checking connector {name}: {e}")

        # Sort by confidence (descending)
        matches.sort()

        return matches

    @classmethod
    def list_registered(cls) -> List[Dict[str, Any]]:
        """List all registered connectors with their metadata."""
        registry = cls()

        return [
            {
                "name": name,
                "class": conn_class.__name__,
                "description": getattr(conn_class, "description", ""),
                "capabilities": [c.value for c in getattr(conn_class, "capabilities", [])],
                "priority": getattr(conn_class, "priority", 0),
            }
            for name, conn_class in registry._connectors.items()
        ]


# Decorator for easy registration
def register_connector(name: str) -> Callable[[Type[BaseConnector]], Type[BaseConnector]]:
    """
    Decorator to register a connector class.

    Example:
        @register_connector("alfresco")
        class AlfrescoConnector(BaseConnector):
            name = "Alfresco"
            description = "Conector para Alfresco ECM"
            ...
    """
    def decorator(cls: Type[BaseConnector]) -> Type[BaseConnector]:
        ConnectorRegistry.register(name, cls)
        return cls
    return decorator


# Convenience functions
def get_connector(name: str) -> Optional[BaseConnector]:
    """Get a connector by name."""
    return ConnectorRegistry.get(name)


def get_all_connectors() -> Dict[str, BaseConnector]:
    """Get all registered connectors."""
    return ConnectorRegistry.get_all()


async def get_connectors_for_query(
    query: str,
    context: Dict[str, Any],
    min_confidence: float = 0.1,
    capabilities: Optional[List[ConnectorCapability]] = None,
) -> List[ConnectorMatch]:
    """
    Find the best connectors for a query.

    This is the main entry point for dynamic routing.

    Example:
        matches = await get_connectors_for_query(
            query="¿Cuántos expedientes del 2006?",
            context={"tenant_id": "xxx"},
            capabilities=[ConnectorCapability.COUNT]
        )

        if matches:
            best = matches[0]
            print(f"Using {best.name} with confidence {best.confidence}")
            result = await best.connector.execute(query, context)
    """
    return await ConnectorRegistry.get_matches(query, context, min_confidence, capabilities)
