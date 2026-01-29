"""
Dynamic Connector Registry for LangGraph

Este módulo permite registrar conectores dinámicamente que se integran
automáticamente en el grafo de decisiones de Emma.

Cuando añades un nuevo conector (BBDD, Alfresco, SharePoint, etc.),
solo necesitas:

1. Crear el conector implementando BaseConnector
2. Registrarlo con @register_connector

El grafo de LangGraph detectará automáticamente los conectores disponibles
y los incluirá en el routing de decisiones.

Ejemplo:
    from app.agents.langgraph.connectors import BaseConnector, register_connector

    @register_connector("postgresql_external")
    class PostgreSQLConnector(BaseConnector):
        name = "PostgreSQL Externo"
        description = "Búsqueda en base de datos PostgreSQL externa"
        capabilities = ["search", "count", "aggregate"]

        async def can_handle(self, query: str, context: dict) -> float:
            # Retorna confianza 0.0-1.0 de si puede manejar esta consulta
            if "base de datos" in query.lower() or "sql" in query.lower():
                return 0.8
            return 0.0

        async def execute(self, query: str, context: dict) -> ConnectorResult:
            # Ejecuta la consulta y retorna resultados
            tracker = ReasoningTracker.get_current()
            tracker.add_connector_step("PostgreSQL", "conectando", "db_externa:5432")
            # ... lógica de conexión y consulta
            return ConnectorResult(data=results, confidence=0.9)
"""

from .base import BaseConnector, ConnectorResult, ConnectorCapability
from .registry import (
    register_connector,
    get_connector,
    get_all_connectors,
    get_connectors_for_query,
    ConnectorRegistry,
)

__all__ = [
    "BaseConnector",
    "ConnectorResult",
    "ConnectorCapability",
    "register_connector",
    "get_connector",
    "get_all_connectors",
    "get_connectors_for_query",
    "ConnectorRegistry",
]
