"""
Base Connector Interface for Dynamic Integration

Define la interfaz que todos los conectores deben implementar para
integrarse automáticamente en el grafo de decisiones de LangGraph.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConnectorCapability(str, Enum):
    """Capabilities a connector can provide."""
    SEARCH = "search"           # Búsqueda de documentos/datos
    COUNT = "count"             # Conteo de elementos
    AGGREGATE = "aggregate"     # Agregaciones (sum, avg, etc.)
    LIST = "list"               # Listado con filtros
    READ = "read"               # Lectura de contenido
    GRAPH = "graph"             # Consultas de grafo/relaciones
    METADATA = "metadata"       # Consulta de metadatos
    TIMELINE = "timeline"       # Consultas temporales


@dataclass
class ConnectorResult:
    """Result from a connector execution."""
    data: Any
    confidence: float = 1.0
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": self.metadata,
            "error": self.error,
            "success": self.success,
        }


class BaseConnector(ABC):
    """
    Base class for all data connectors.

    Implementa esta clase para añadir un nuevo conector que se integre
    automáticamente en el grafo de decisiones de Emma.

    El método `can_handle()` determina si este conector puede manejar
    una consulta específica, permitiendo routing dinámico.

    Attributes:
        name: Nombre legible del conector
        description: Descripción para el LLM
        capabilities: Lista de capacidades que ofrece
        priority: Prioridad en caso de empate (mayor = más prioridad)

    Example:
        class AlfrescoConnector(BaseConnector):
            name = "Alfresco"
            description = "Sistema de gestión documental Alfresco"
            capabilities = [ConnectorCapability.SEARCH, ConnectorCapability.READ]
            priority = 10

            async def can_handle(self, query: str, context: dict) -> float:
                if context.get("source_hint") == "alfresco":
                    return 1.0
                if "alfresco" in query.lower():
                    return 0.9
                return 0.3  # Puede manejar consultas generales

            async def execute(self, query: str, context: dict) -> ConnectorResult:
                tracker = ReasoningTracker.get_current()
                tracker.add_connector_step("Alfresco", "buscando", query[:30])
                # ... implementación
    """

    # Override these in subclasses
    name: str = "Base Connector"
    description: str = "Base connector interface"
    capabilities: List[ConnectorCapability] = []
    priority: int = 0

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize connector with optional configuration.

        Args:
            config: Connector-specific configuration
        """
        self.config = config or {}
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize the connector (connect to services, validate credentials, etc.)

        Override this to perform async initialization.
        Returns True if initialization was successful.
        """
        self._initialized = True
        return True

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the connector is healthy and available.

        Returns:
            Dict with 'healthy' bool and optional 'message'
        """
        return {"healthy": self._initialized, "message": "OK" if self._initialized else "Not initialized"}

    @abstractmethod
    async def can_handle(self, query: str, context: Dict[str, Any]) -> float:
        """
        Determine if this connector can handle the given query.

        This is the key method for dynamic routing. The connector registry
        calls this on all connectors and routes to the one with highest confidence.

        Args:
            query: The user's natural language query
            context: Additional context (tenant_id, user_id, hints, etc.)

        Returns:
            Confidence score from 0.0 (cannot handle) to 1.0 (perfect match)

        Example implementation:
            async def can_handle(self, query: str, context: dict) -> float:
                query_lower = query.lower()

                # High confidence if explicitly mentioned
                if "base de datos" in query_lower:
                    return 0.95

                # Medium confidence if structural query
                if any(kw in query_lower for kw in ["cuántos", "lista", "filtrar"]):
                    return 0.6

                # Low confidence as fallback
                return 0.2
        """
        pass

    @abstractmethod
    async def execute(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> ConnectorResult:
        """
        Execute the query and return results.

        Use ReasoningTracker to register steps for UI visibility:

            from app.agents.langgraph.reasoning_tracker import ReasoningTracker

            tracker = ReasoningTracker.get_current()
            tracker.add_connector_step(self.name, "conectando", "servidor:puerto")
            # ... do work
            tracker.add_step("data_extraction", f"Encontrados {len(results)} registros")

        Args:
            query: The user's query
            context: Execution context (tenant_id, user_id, max_results, etc.)

        Returns:
            ConnectorResult with data and metadata
        """
        pass

    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Get OpenAI-compatible tool schema for this connector.

        This allows the connector to be used as a LangChain tool.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name.lower().replace(" ", "_"),
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 20
                        }
                    },
                    "required": ["query"]
                }
            }
        }

    def __repr__(self) -> str:
        caps = ", ".join(c.value for c in self.capabilities)
        return f"<{self.__class__.__name__}(name='{self.name}', capabilities=[{caps}])>"
