"""
Graph Provider Abstraction Layer for SIL

This module provides a database-agnostic interface for graph operations,
allowing SIL to work with different graph databases without code changes.

Supported Providers:
- Apache AGE (current) - PostgreSQL extension for graph queries
- Neo4j (future) - Native graph database

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                   SIL Components                            │
    │  (structural_graph, cypher_builder, pre_llm_reasoning)      │
    └────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                  GraphProvider (Abstract)                   │
    │                                                             │
    │  • add_node(node)           • execute_query(cypher)         │
    │  • get_node(id)             • count_nodes(label)            │
    │  • add_edge(edge)           • find_nodes(label, filters)    │
    │  • traverse(start, depth)   • get_stats(tenant_id)          │
    └────────────────────────┬────────────────────────────────────┘
                             │
             ┌───────────────┴───────────────┐
             │                               │
             ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   AGEProvider   │             │  Neo4jProvider  │
    │  (PostgreSQL)   │             │    (future)     │
    └─────────────────┘             └─────────────────┘

Usage:
    # Get the configured provider
    from app.services.sil.graph import get_graph_provider

    provider = await get_graph_provider()

    # Add a document node
    node = GraphNode(
        node_id="doc-123",
        label=NodeLabel.DOCUMENT,
        tenant_id="tenant-456",
        properties={"title": "Contract", "client": "ACME"}
    )
    await provider.add_node(node)

    # Query the graph
    result = await provider.execute_query(
        "MATCH (d:structural_document) WHERE d.tenant_id = $tenant RETURN d",
        parameters={"tenant": "tenant-456"}
    )

Configuration:
    Set GRAPH_PROVIDER environment variable:
    - "apache_age" (default) - Use Apache AGE on PostgreSQL
    - "neo4j" - Use Neo4j (requires implementation)

    For Apache AGE, configure PostgreSQL connection:
    - POSTGRES_HOST
    - POSTGRES_PORT
    - POSTGRES_DB
    - POSTGRES_USER
    - POSTGRES_PASSWORD
    - AGE_GRAPH_NAME (default: "knowledge_graph")
"""

# Data models
from .graph_provider import (
    GraphNode,
    GraphEdge,
    QueryResult,
    NodeLabel,
    EdgeLabel,
)

# Abstract interface
from .graph_provider import GraphProvider

# Concrete implementations
from .age_provider import AGEProvider
from .neo4j_provider import Neo4jProvider

# Factory and convenience functions
from .provider_factory import (
    GraphProviderFactory,
    get_graph_provider,
    close_graph_provider,
)

__all__ = [
    # Data models
    "GraphNode",
    "GraphEdge",
    "QueryResult",
    "NodeLabel",
    "EdgeLabel",
    # Abstract interface
    "GraphProvider",
    # Implementations
    "AGEProvider",
    "Neo4jProvider",
    # Factory
    "GraphProviderFactory",
    "get_graph_provider",
    "close_graph_provider",
]
