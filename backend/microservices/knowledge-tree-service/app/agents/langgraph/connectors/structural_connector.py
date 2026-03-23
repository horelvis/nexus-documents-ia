"""
FalkorDB Structural Connector

Conector para consultas estructurales usando FalkorDB (grafo).
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
    Connector for FalkorDB graph database.

    Handles structural queries like:
    - Counting documents/folders
    - Listing with filters
    - Date range queries
    - Existence checks
    """

    name = "FalkorDB"
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
        """Initialize connection to FalkorDB via tenant_knowledge_service."""
        try:
            from app.services.tenant_knowledge_service import tenant_knowledge_service
            await tenant_knowledge_service.initialize()
            self._knowledge_service = tenant_knowledge_service
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize FalkorDB connector: {e}")
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
        Execute structural query via FalkorDB.
        """
        tracker = ReasoningTracker.get_current()
        tracker.set_source("apache_age")

        tenant_id = context.get("tenant_id", "")
        max_results = context.get("max_results", 100)

        # Step 1: Connection
        tracker.add_connector_step(
            "FalkorDB",
            "conectando",
            "base de datos de grafos"
        )

        if not hasattr(self, '_knowledge_service') or not self._knowledge_service:
            from app.services.tenant_knowledge_service import tenant_knowledge_service
            await tenant_knowledge_service.initialize()
            self._knowledge_service = tenant_knowledge_service

        try:
            # Step 2: Query execution
            tracker.add_step(
                StepType.SEARCH,
                f"Ejecutando consulta estructural: '{query[:50]}...'"
            )

            # Gather data from AGE graph directly
            totals = await self._knowledge_service.get_totals(tenant_id)
            type_counts = await self._knowledge_service.get_document_type_counts(tenant_id)
            top_folders = await self._knowledge_service.get_top_folders(tenant_id, limit=max_results)
            toon_context = await self._knowledge_service.build_toon_context(tenant_id)

            # Step 3: Route info
            tracker.add_step(
                StepType.ROUTING,
                "Ruta: GRAPH_ONLY - Solo grafo (rápido)",
                confidence=0.95
            )

            # Step 4: Data extraction
            data = {
                "count": totals.get("documents", 0),
                "folders": top_folders,
                "type_counts": type_counts,
                "totals": totals,
            }
            entities = []
            if totals.get("documents", 0) > 0:
                entities.append(f"{totals['documents']} documentos")
            if totals.get("folders", 0) > 0:
                entities.append(f"{totals['folders']} carpetas")

            tracker.add_step(
                StepType.DATA_EXTRACTION,
                f"Extraído: {', '.join(entities) if entities else 'sin resultados'}",
                entities=entities,
                confidence=0.95
            )

            return ConnectorResult(
                data=data,
                confidence=0.95,
                source="apache_age",
                metadata={
                    "route": "GRAPH_ONLY",
                    "context": toon_context.get("context_for_llm", ""),
                }
            )

        except Exception as e:
            logger.error(f"FalkorDB query failed: {e}")
            tracker.add_error_step(str(e), source="apache_age")

            return ConnectorResult(
                data=None,
                confidence=0.0,
                source="apache_age",
                error=str(e)
            )
