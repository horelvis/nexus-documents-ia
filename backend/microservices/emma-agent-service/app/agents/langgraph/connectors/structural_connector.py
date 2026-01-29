"""
Apache AGE Structural Connector

Conector para consultas estructurales usando Apache AGE (grafo PostgreSQL).
Maneja consultas de conteo, listado y filtrado de documentos.

Este es el conector por defecto para consultas estructurales.
Se registra automáticamente al importar el módulo.
"""

import logging
import re
from typing import Any, Dict, List

from .base import BaseConnector, ConnectorCapability, ConnectorResult
from .registry import register_connector
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)


# Patterns that indicate structural queries
STRUCTURAL_PATTERNS = [
    # Counting patterns
    r"cuántos?\s+(documentos?|expedientes?|contratos?|facturas?|archivos?|carpetas?)",
    r"cuántas?\s+(facturas?|nóminas?|carpetas?)",
    r"número\s+de\s+(documentos?|expedientes?|contratos?)",
    r"total\s+de\s+(documentos?|expedientes?)",
    # Listing patterns
    r"lista(r|me)?\s+(todos?|las?|los?)\s+(documentos?|expedientes?|contratos?)",
    r"muéstrame\s+(todos?|las?|los?)",
    r"dame\s+(una\s+)?lista",
    # Filtering by date/year
    r"del\s+año\s+\d{4}",
    r"de\s+\d{4}",
    r"entre\s+\d{4}\s+y\s+\d{4}",
    r"del\s+(último|pasado)\s+(mes|año|trimestre)",
    # Existence patterns
    r"tengo\s+(algún|alguna|documentos?|expedientes?)",
    r"existe(n)?\s+(documentos?|expedientes?|contratos?)",
    r"hay\s+(algún|alguna|documentos?)",
]

_STRUCTURAL_REGEX = [re.compile(p, re.IGNORECASE) for p in STRUCTURAL_PATTERNS]


@register_connector("apache_age")
class ApacheAGEConnector(BaseConnector):
    """
    Connector for Apache AGE graph database.

    Handles structural queries like:
    - Counting documents/folders
    - Listing with filters
    - Date range queries
    - Existence checks
    """

    name = "Apache AGE"
    description = "Base de datos de grafos para consultas estructurales (conteo, listado, filtrado)"
    capabilities = [
        ConnectorCapability.COUNT,
        ConnectorCapability.LIST,
        ConnectorCapability.AGGREGATE,
        ConnectorCapability.GRAPH,
    ]
    priority = 100  # High priority for structural queries

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._client = None

    async def initialize(self) -> bool:
        """Initialize connection to weaviate-service (which proxies to AGE)."""
        try:
            from app.clients.weaviate_client import get_weaviate_client
            self._client = get_weaviate_client()
            health = await self._client.health_check()
            self._initialized = health.get("status") == "healthy"
            return self._initialized
        except Exception as e:
            logger.error(f"Failed to initialize Apache AGE connector: {e}")
            return False

    async def can_handle(self, query: str, context: Dict[str, Any]) -> float:
        """
        Determine if this is a structural query.

        Returns high confidence for counting, listing, filtering queries.
        """
        query_lower = query.lower()

        # Check structural patterns
        for pattern in _STRUCTURAL_REGEX:
            if pattern.search(query_lower):
                return 0.95  # High confidence for structural queries

        # Check for hints in context
        if context.get("query_type") == "structural":
            return 1.0

        if context.get("force_graph"):
            return 0.9

        # Low confidence for general queries (can still handle as fallback)
        return 0.1

    async def execute(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> ConnectorResult:
        """
        Execute structural query via Apache AGE.
        """
        tracker = ReasoningTracker.get_current()
        tracker.set_source("apache_age")

        tenant_id = context.get("tenant_id", "")
        max_results = context.get("max_results", 100)

        # Step 1: Connection
        tracker.add_connector_step(
            "Apache AGE",
            "conectando",
            "weaviate-service/structural"
        )

        if not self._client:
            from app.clients.weaviate_client import get_weaviate_client
            self._client = get_weaviate_client()

        try:
            # Step 2: Query execution
            tracker.add_step(
                StepType.SEARCH,
                f"Ejecutando consulta estructural: '{query[:50]}...'"
            )

            result = await self._client.structural_query(
                tenant_id=tenant_id,
                query=query,
                max_results=max_results
            )

            # Step 3: Route info
            route_descriptions = {
                "GRAPH_ONLY": "Solo grafo (rápido)",
                "VECTOR_ONLY": "Búsqueda semántica",
                "HYBRID": "Híbrido (grafo + semántico)",
            }
            tracker.add_step(
                StepType.ROUTING,
                f"Ruta: {result.route} - {route_descriptions.get(result.route, 'N/A')}",
                confidence=result.confidence
            )

            # Step 4: Data extraction
            data = result.data
            entities = []

            if data:
                if "count" in data:
                    entities.append(f"{data['count']} elementos")
                if "documents" in data:
                    entities.append(f"{len(data['documents'])} documentos")
                if "folders" in data:
                    entities.append(f"{len(data['folders'])} carpetas")

            tracker.add_step(
                StepType.DATA_EXTRACTION,
                f"Extraído: {', '.join(entities) if entities else 'sin resultados'}",
                entities=entities,
                confidence=result.confidence
            )

            return ConnectorResult(
                data=data,
                confidence=result.confidence,
                source="apache_age",
                metadata={
                    "route": result.route,
                    "context": result.context,
                }
            )

        except Exception as e:
            logger.error(f"Apache AGE query failed: {e}")
            tracker.add_error_step(str(e), source="apache_age")

            return ConnectorResult(
                data=None,
                confidence=0.0,
                source="apache_age",
                error=str(e)
            )
