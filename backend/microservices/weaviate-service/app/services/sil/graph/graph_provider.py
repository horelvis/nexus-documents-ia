"""
Graph Provider Abstract Interface

This abstraction allows SIL to work with different graph databases:
- Apache AGE (current)
- Neo4j (future)
- Amazon Neptune (future)
- Others

The interface is designed around Cypher-like semantics but implementations
can translate to native query languages.

Usage:
    from app.services.sil.graph import get_graph_provider

    provider = await get_graph_provider()
    await provider.add_node("Document", {"id": "doc-123", "title": "Contract"})
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class NodeLabel(str, Enum):
    """Standard node labels in the structural graph."""
    DOCUMENT = "structural_document"
    FOLDER = "structural_folder"
    SITE = "structural_site"
    # Legal Knowledge Graph extensions
    LAW = "legal_law"
    ARTICLE = "legal_article"
    JURISDICTION = "legal_jurisdiction"
    OBLIGATION = "legal_obligation"


class EdgeLabel(str, Enum):
    """Standard edge labels in the structural graph."""
    CONTAINS = "contains"
    VERSION_OF = "version_of"
    RELATES_TO = "relates_to"
    SIBLING_OF = "sibling_of"
    CHILD_OF = "child_of"
    # Legal Knowledge Graph extensions
    GOVERNED_BY = "governed_by"
    REFERENCES = "references"
    CONTAINS_ARTICLE = "contains_article"
    CREATES_OBLIGATION = "creates_obligation"
    AMENDS = "amends"


@dataclass
class GraphNode:
    """
    Represents a node in the graph.

    Attributes:
        node_id: Unique identifier for the node
        label: Node type/label (e.g., "structural_document")
        tenant_id: Tenant isolation key
        properties: Additional node properties
    """
    node_id: str
    label: Union[NodeLabel, str]
    tenant_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def label_value(self) -> str:
        """Get the string value of the label."""
        if isinstance(self.label, Enum):
            return self.label.value
        return self.label

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "node_id": self.node_id,
            "label": self.label_value,
            "tenant_id": self.tenant_id,
            **self.properties,
        }


@dataclass
class GraphEdge:
    """
    Represents an edge/relationship in the graph.

    Attributes:
        source_id: Source node ID
        target_id: Target node ID
        label: Edge type/label (e.g., "contains")
        tenant_id: Tenant isolation key
        properties: Additional edge properties
    """
    source_id: str
    target_id: str
    label: Union[EdgeLabel, str]
    tenant_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def label_value(self) -> str:
        """Get the string value of the label."""
        if isinstance(self.label, Enum):
            return self.label.value
        return self.label

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "label": self.label_value,
            "tenant_id": self.tenant_id,
            **self.properties,
        }


@dataclass
class QueryResult:
    """
    Represents the result of a graph query.

    Attributes:
        rows: List of result rows as dictionaries
        columns: Column names in the result
        execution_time_ms: Query execution time
        query: The query that was executed (for debugging)
    """
    rows: List[Dict[str, Any]]
    columns: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    query: str = ""

    @property
    def is_empty(self) -> bool:
        """Check if the result is empty."""
        return len(self.rows) == 0

    @property
    def first(self) -> Optional[Dict[str, Any]]:
        """Get the first row or None."""
        return self.rows[0] if self.rows else None

    def scalar(self, column: str = None) -> Any:
        """Get a single scalar value from the first row."""
        if not self.rows:
            return None
        row = self.rows[0]
        if column:
            return row.get(column)
        # Return first value
        return next(iter(row.values()), None)


# =============================================================================
# Abstract Provider Interface
# =============================================================================

class GraphProvider(ABC):
    """
    Abstract base class for graph database providers.

    This interface abstracts the graph database operations so that
    SIL can work with different backends (Apache AGE, Neo4j, etc.)

    All methods are async to support non-blocking I/O.
    """

    # Provider identification
    provider_name: str = "abstract"

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the provider and establish connections.

        This should be called before any other operations.
        Should be idempotent (safe to call multiple times).
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close connections and clean up resources.
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the graph database is available and connected.

        Returns:
            True if the database is reachable, False otherwise
        """
        pass

    # =========================================================================
    # Schema Operations
    # =========================================================================

    @abstractmethod
    async def ensure_node_label(self, label: Union[NodeLabel, str]) -> bool:
        """
        Ensure a node label/type exists in the schema.

        Args:
            label: The node label to create if not exists

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def ensure_edge_label(self, label: Union[EdgeLabel, str]) -> bool:
        """
        Ensure an edge label/type exists in the schema.

        Args:
            label: The edge label to create if not exists

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def ensure_schema(self,
                           node_labels: List[Union[NodeLabel, str]],
                           edge_labels: List[Union[EdgeLabel, str]]) -> bool:
        """
        Ensure all required labels exist in the schema.

        Args:
            node_labels: List of node labels to ensure
            edge_labels: List of edge labels to ensure

        Returns:
            True if all labels exist/created successfully
        """
        pass

    # =========================================================================
    # Node Operations
    # =========================================================================

    @abstractmethod
    async def add_node(self, node: GraphNode) -> Optional[str]:
        """
        Add a node to the graph.

        Uses MERGE semantics - creates if not exists, updates if exists.

        Args:
            node: The node to add

        Returns:
            The node ID if successful, None otherwise
        """
        pass

    @abstractmethod
    async def get_node(self,
                       node_id: str,
                       label: Union[NodeLabel, str],
                       tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a node by ID.

        Args:
            node_id: The node identifier
            label: The node label
            tenant_id: Tenant isolation key

        Returns:
            Node properties as dict, or None if not found
        """
        pass

    @abstractmethod
    async def update_node(self,
                          node_id: str,
                          label: Union[NodeLabel, str],
                          tenant_id: str,
                          properties: Dict[str, Any]) -> bool:
        """
        Update node properties.

        Args:
            node_id: The node identifier
            label: The node label
            tenant_id: Tenant isolation key
            properties: Properties to update (merged with existing)

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_node(self,
                          node_id: str,
                          label: Union[NodeLabel, str],
                          tenant_id: str,
                          soft_delete: bool = True) -> bool:
        """
        Delete a node from the graph.

        Args:
            node_id: The node identifier
            label: The node label
            tenant_id: Tenant isolation key
            soft_delete: If True, set valid_to instead of deleting

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def node_exists(self,
                          node_id: str,
                          label: Union[NodeLabel, str],
                          tenant_id: str) -> bool:
        """
        Check if a node exists.

        Args:
            node_id: The node identifier
            label: The node label
            tenant_id: Tenant isolation key

        Returns:
            True if node exists, False otherwise
        """
        pass

    # =========================================================================
    # Edge Operations
    # =========================================================================

    @abstractmethod
    async def add_edge(self, edge: GraphEdge,
                       source_label: Union[NodeLabel, str],
                       target_label: Union[NodeLabel, str]) -> bool:
        """
        Add an edge between two nodes.

        Uses MERGE semantics - creates if not exists.

        Args:
            edge: The edge to add
            source_label: Label of the source node
            target_label: Label of the target node

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_edge(self,
                          source_id: str,
                          target_id: str,
                          label: Union[EdgeLabel, str],
                          tenant_id: str) -> bool:
        """
        Delete an edge between two nodes.

        Args:
            source_id: Source node identifier
            target_id: Target node identifier
            label: Edge label
            tenant_id: Tenant isolation key

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_edges(self,
                        node_id: str,
                        label: Union[NodeLabel, str],
                        tenant_id: str,
                        edge_label: Optional[Union[EdgeLabel, str]] = None,
                        direction: str = "both") -> List[Dict[str, Any]]:
        """
        Get edges connected to a node.

        Args:
            node_id: The node identifier
            label: The node label
            tenant_id: Tenant isolation key
            edge_label: Filter by edge type (optional)
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of edges as dictionaries
        """
        pass

    # =========================================================================
    # Query Operations
    # =========================================================================

    @abstractmethod
    async def execute_query(self,
                           query: str,
                           parameters: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        Execute a raw query against the graph.

        The query language depends on the provider:
        - Apache AGE: Cypher
        - Neo4j: Cypher
        - Neptune: Gremlin/SPARQL

        Args:
            query: The query string
            parameters: Query parameters (if supported)

        Returns:
            QueryResult with rows and metadata
        """
        pass

    @abstractmethod
    async def count_nodes(self,
                          label: Union[NodeLabel, str],
                          tenant_id: str,
                          filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count nodes matching criteria.

        Args:
            label: Node label to count
            tenant_id: Tenant isolation key
            filters: Additional property filters

        Returns:
            Number of matching nodes
        """
        pass

    @abstractmethod
    async def find_nodes(self,
                         label: Union[NodeLabel, str],
                         tenant_id: str,
                         filters: Optional[Dict[str, Any]] = None,
                         limit: int = 100,
                         order_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find nodes matching criteria.

        Args:
            label: Node label to search
            tenant_id: Tenant isolation key
            filters: Property filters
            limit: Maximum results
            order_by: Property to order by

        Returns:
            List of matching nodes
        """
        pass

    @abstractmethod
    async def traverse(self,
                       start_node_id: str,
                       start_label: Union[NodeLabel, str],
                       tenant_id: str,
                       edge_labels: Optional[List[Union[EdgeLabel, str]]] = None,
                       max_depth: int = 2,
                       direction: str = "both") -> List[Dict[str, Any]]:
        """
        Traverse the graph from a starting node.

        Args:
            start_node_id: Starting node identifier
            start_label: Label of starting node
            tenant_id: Tenant isolation key
            edge_labels: Filter by edge types (optional)
            max_depth: Maximum traversal depth
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of reached nodes with path information
        """
        pass

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    @abstractmethod
    async def clear_tenant_data(self, tenant_id: str) -> bool:
        """
        Clear all graph data for a tenant.

        Args:
            tenant_id: Tenant to clear data for

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get statistics about the graph for a tenant.

        Args:
            tenant_id: Tenant to get stats for

        Returns:
            Dictionary with stats (node counts, edge counts, etc.)
        """
        pass

    # =========================================================================
    # Utility Methods (with default implementations)
    # =========================================================================

    def escape_string(self, value: str) -> str:
        """
        Escape a string value for use in queries.

        Default implementation escapes single quotes and backslashes.
        Providers may override for specific escaping rules.
        """
        if not value:
            return ""
        return value.replace("\\", "\\\\").replace("'", "''")

    def format_datetime(self, dt: datetime) -> str:
        """
        Format a datetime for storage in the graph.

        Default uses ISO8601 format.
        """
        if dt is None:
            return ""
        return dt.isoformat()

    def parse_datetime(self, value: str) -> Optional[datetime]:
        """
        Parse a datetime string from the graph.
        """
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
