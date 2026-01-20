"""
Knowledge Graph Service

Implements a persistent knowledge graph using NetworkX + Redis:
- NetworkX DiGraph for fast in-memory graph operations
- Redis for persistence (survives container restarts)
- Per-tenant graph isolation
- Lazy loading with TTL-based eviction

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    KnowledgeGraphService                     │
├─────────────────────────────────────────────────────────────┤
│  In-Memory (NetworkX)           │  Persistent (Redis)        │
│  ├─ DiGraph per tenant          │  ├─ kg:{tenant}:nodes      │
│  ├─ Fast traversal O(1)         │  ├─ kg:{tenant}:edges      │
│  └─ TTL eviction (1h)           │  └─ kg:{tenant}:index      │
├─────────────────────────────────────────────────────────────┤
│  Operations:                                                 │
│  • add_entity() - Add node to graph                          │
│  • add_relationship() - Add edge between nodes               │
│  • get_neighbors() - BFS traversal for query expansion       │
│  • find_entity_by_value() - Lookup entity by normalized val  │
└─────────────────────────────────────────────────────────────┘

Usage:
    from app.services.knowledge.graph_service import knowledge_graph_service

    # Add entities during indexing
    await knowledge_graph_service.add_entity(
        tenant_id="tenant-123",
        entity_id="ent-abc",
        entity_type="PERSON",
        entity_value="Juan García",
        document_id="doc-456"
    )

    # Get neighbors for query expansion
    neighbors = await knowledge_graph_service.get_neighbors(
        tenant_id="tenant-123",
        entity_id="ent-abc",
        max_depth=2
    )
"""

import logging
import json
import time
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import deque

import redis.asyncio as redis

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None

from ...core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the knowledge graph."""
    entity_id: str
    entity_type: str
    entity_value: str
    normalized_value: str
    document_ids: Set[str] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_value": self.entity_value,
            "normalized_value": self.normalized_value,
            "document_ids": list(self.document_ids),
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        return cls(
            entity_id=data["entity_id"],
            entity_type=data["entity_type"],
            entity_value=data["entity_value"],
            normalized_value=data["normalized_value"],
            document_ids=set(data.get("document_ids", [])),
            attributes=data.get("attributes", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
        )


@dataclass
class GraphEdge:
    """An edge (relationship) in the knowledge graph."""
    source_id: str
    target_id: str
    relationship_type: str
    strength: float
    document_ids: Set[str] = field(default_factory=set)
    context_snippet: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type,
            "strength": self.strength,
            "document_ids": list(self.document_ids),
            "context_snippet": self.context_snippet,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            relationship_type=data["relationship_type"],
            strength=data.get("strength", 0.5),
            document_ids=set(data.get("document_ids", [])),
            context_snippet=data.get("context_snippet"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
        )


@dataclass
class TenantGraph:
    """Container for a tenant's graph and metadata."""
    tenant_id: str
    graph: Any  # nx.DiGraph
    last_accessed: datetime = field(default_factory=datetime.now)
    dirty: bool = False  # Has unsaved changes
    node_count: int = 0
    edge_count: int = 0


class KnowledgeGraphService:
    """
    Knowledge Graph Service with NetworkX + Redis.

    Features:
    - Per-tenant graph isolation
    - In-memory NetworkX for fast operations
    - Redis persistence for durability
    - Lazy loading with TTL eviction
    - BFS traversal for query expansion
    """

    def __init__(self):
        self._graphs: Dict[str, TenantGraph] = {}  # tenant_id -> TenantGraph
        self._redis: Optional[redis.Redis] = None
        self._redis_prefix = settings.rag_graph_redis_prefix
        self._cache_ttl = settings.rag_graph_cache_ttl
        self._max_neighbors = settings.rag_graph_max_neighbors
        self._traversal_depth = settings.rag_graph_traversal_depth
        self._min_strength = settings.rag_graph_min_relationship_strength
        self._initialized = False
        self._persist_batch_size = 100  # Persist after N changes
        self._pending_changes: Dict[str, int] = {}  # tenant_id -> pending change count

    async def initialize(self) -> None:
        """Initialize the service and Redis connection."""
        if self._initialized:
            return

        if not NETWORKX_AVAILABLE:
            logger.warning("⚠️ NetworkX not available, knowledge graph disabled")
            return

        if not settings.rag_knowledge_graph_enabled:
            logger.info("ℹ️ Knowledge graph disabled by configuration")
            return

        try:
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
            # Test connection
            await self._redis.ping()
            self._initialized = True
            logger.info("✅ KnowledgeGraphService initialized")

        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed, using in-memory only: {e}")
            self._redis = None
            self._initialized = True

    async def _get_or_create_graph(self, tenant_id: str) -> TenantGraph:
        """Get or create a graph for a tenant, loading from Redis if needed."""
        if not NETWORKX_AVAILABLE:
            raise RuntimeError("NetworkX not available")

        # Check if graph exists in memory
        if tenant_id in self._graphs:
            tenant_graph = self._graphs[tenant_id]
            tenant_graph.last_accessed = datetime.now()
            return tenant_graph

        # Try to load from Redis
        graph = await self._load_from_redis(tenant_id)
        if graph is None:
            graph = nx.DiGraph()

        tenant_graph = TenantGraph(
            tenant_id=tenant_id,
            graph=graph,
            node_count=graph.number_of_nodes(),
            edge_count=graph.number_of_edges(),
        )
        self._graphs[tenant_id] = tenant_graph

        logger.info(
            f"📊 Loaded graph for {tenant_id}: "
            f"{tenant_graph.node_count} nodes, {tenant_graph.edge_count} edges"
        )

        return tenant_graph

    async def add_entity(
        self,
        tenant_id: str,
        entity_id: str,
        entity_type: str,
        entity_value: str,
        document_id: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add an entity node to the knowledge graph.

        If the entity already exists (by normalized value), updates the existing
        node with the new document_id.

        Args:
            tenant_id: Tenant identifier
            entity_id: Unique entity identifier
            entity_type: Type of entity (PERSON, ORGANIZATION, etc.)
            entity_value: Display value of the entity
            document_id: Source document ID
            attributes: Optional additional attributes

        Returns:
            True if entity was added/updated, False on error
        """
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return False

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            # Normalize value for deduplication
            normalized = self._normalize_value(entity_value)

            # Check if entity with same normalized value exists
            existing_id = None
            for node_id in graph.nodes():
                node_data = graph.nodes[node_id]
                if node_data.get("normalized_value") == normalized:
                    existing_id = node_id
                    break

            if existing_id:
                # Update existing node with new document
                node_data = graph.nodes[existing_id]
                doc_ids = set(node_data.get("document_ids", []))
                doc_ids.add(document_id)
                graph.nodes[existing_id]["document_ids"] = list(doc_ids)
                logger.debug(f"Updated existing entity {existing_id} with document {document_id}")
            else:
                # Add new node
                node = GraphNode(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    entity_value=entity_value,
                    normalized_value=normalized,
                    document_ids={document_id},
                    attributes=attributes or {},
                )
                graph.add_node(entity_id, **node.to_dict())
                tenant_graph.node_count = graph.number_of_nodes()
                logger.debug(f"Added entity {entity_id}: {entity_value}")

            # Mark dirty and schedule persist
            tenant_graph.dirty = True
            await self._schedule_persist(tenant_id)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to add entity: {e}")
            return False

    async def add_relationship(
        self,
        tenant_id: str,
        source_id: str,
        target_id: str,
        relationship_type: str,
        strength: float,
        document_id: str,
        context_snippet: Optional[str] = None,
    ) -> bool:
        """
        Add a relationship edge between two entities.

        If the relationship already exists, updates the strength (max of old/new)
        and adds the document_id.

        Args:
            tenant_id: Tenant identifier
            source_id: Source entity ID
            target_id: Target entity ID
            relationship_type: Type of relationship (BELONGS_TO, REFERENCES, etc.)
            strength: Relationship strength (0.0-1.0)
            document_id: Source document ID
            context_snippet: Optional context text

        Returns:
            True if relationship was added/updated, False on error
        """
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return False

        # Filter weak relationships
        if strength < self._min_strength:
            return False

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            # Check both nodes exist
            if source_id not in graph.nodes or target_id not in graph.nodes:
                logger.debug(f"Skipping relationship - nodes not found: {source_id} -> {target_id}")
                return False

            # Check if edge exists
            if graph.has_edge(source_id, target_id):
                # Update existing edge
                edge_data = graph.edges[source_id, target_id]
                doc_ids = set(edge_data.get("document_ids", []))
                doc_ids.add(document_id)
                graph.edges[source_id, target_id]["document_ids"] = list(doc_ids)
                # Keep max strength
                graph.edges[source_id, target_id]["strength"] = max(
                    edge_data.get("strength", 0),
                    strength
                )
            else:
                # Add new edge
                edge = GraphEdge(
                    source_id=source_id,
                    target_id=target_id,
                    relationship_type=relationship_type,
                    strength=strength,
                    document_ids={document_id},
                    context_snippet=context_snippet,
                )
                graph.add_edge(source_id, target_id, **edge.to_dict())
                tenant_graph.edge_count = graph.number_of_edges()

            tenant_graph.dirty = True
            await self._schedule_persist(tenant_id)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to add relationship: {e}")
            return False

    async def get_neighbors(
        self,
        tenant_id: str,
        entity_id: str,
        max_depth: Optional[int] = None,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring entities using BFS traversal.

        Used for query expansion - finds related entities that might be
        relevant to a query about the starting entity.

        Args:
            tenant_id: Tenant identifier
            entity_id: Starting entity ID
            max_depth: Maximum BFS depth (default from config)
            relationship_types: Filter by relationship types (optional)

        Returns:
            List of neighbor entities with relationship info
        """
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return []

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            if entity_id not in graph.nodes:
                return []

            depth = max_depth or self._traversal_depth
            max_results = self._max_neighbors

            # BFS traversal
            visited = {entity_id}
            queue = deque([(entity_id, 0)])  # (node_id, depth)
            neighbors = []

            while queue and len(neighbors) < max_results:
                current_id, current_depth = queue.popleft()

                if current_depth >= depth:
                    continue

                # Get outgoing edges
                for _, neighbor_id, edge_data in graph.out_edges(current_id, data=True):
                    if neighbor_id in visited:
                        continue

                    # Filter by relationship type if specified
                    rel_type = edge_data.get("relationship_type", "")
                    if relationship_types and rel_type not in relationship_types:
                        continue

                    visited.add(neighbor_id)
                    queue.append((neighbor_id, current_depth + 1))

                    # Add to results
                    node_data = graph.nodes[neighbor_id]
                    neighbors.append({
                        "entity_id": neighbor_id,
                        "entity_type": node_data.get("entity_type"),
                        "entity_value": node_data.get("entity_value"),
                        "relationship_type": rel_type,
                        "relationship_strength": edge_data.get("strength", 0.5),
                        "depth": current_depth + 1,
                    })

                # Also check incoming edges (bidirectional traversal)
                for source_id, _, edge_data in graph.in_edges(current_id, data=True):
                    if source_id in visited:
                        continue

                    rel_type = edge_data.get("relationship_type", "")
                    if relationship_types and rel_type not in relationship_types:
                        continue

                    visited.add(source_id)
                    queue.append((source_id, current_depth + 1))

                    node_data = graph.nodes[source_id]
                    neighbors.append({
                        "entity_id": source_id,
                        "entity_type": node_data.get("entity_type"),
                        "entity_value": node_data.get("entity_value"),
                        "relationship_type": f"inverse_{rel_type}",
                        "relationship_strength": edge_data.get("strength", 0.5),
                        "depth": current_depth + 1,
                    })

            # Sort by strength (descending) and depth (ascending)
            neighbors.sort(key=lambda x: (-x["relationship_strength"], x["depth"]))

            return neighbors[:max_results]

        except Exception as e:
            logger.error(f"❌ Failed to get neighbors: {e}")
            return []

    async def find_entity_by_value(
        self,
        tenant_id: str,
        value: str,
        entity_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find an entity by its value (normalized).

        Args:
            tenant_id: Tenant identifier
            value: Entity value to search for
            entity_type: Optional type filter

        Returns:
            Entity data dict or None if not found
        """
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return None

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            normalized = self._normalize_value(value)

            for node_id in graph.nodes():
                node_data = graph.nodes[node_id]
                if node_data.get("normalized_value") == normalized:
                    if entity_type and node_data.get("entity_type") != entity_type:
                        continue
                    return {
                        "entity_id": node_id,
                        **node_data,
                    }

            return None

        except Exception as e:
            logger.error(f"❌ Failed to find entity: {e}")
            return None

    async def find_entities_in_text(
        self,
        tenant_id: str,
        text: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find entities that appear in given text.

        Used for detecting entities in a query for graph-based expansion.

        Args:
            tenant_id: Tenant identifier
            text: Text to search for entities
            limit: Maximum entities to return

        Returns:
            List of matching entity data dicts
        """
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return []

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            text_lower = text.lower()
            found = []

            for node_id in graph.nodes():
                node_data = graph.nodes[node_id]
                entity_value = node_data.get("entity_value", "")
                normalized = node_data.get("normalized_value", "")

                # Check if entity value appears in text
                if normalized and len(normalized) > 2 and normalized in text_lower:
                    found.append({
                        "entity_id": node_id,
                        **node_data,
                        "match_position": text_lower.find(normalized),
                    })

            # Sort by match position and limit
            found.sort(key=lambda x: x["match_position"])
            return found[:limit]

        except Exception as e:
            logger.error(f"❌ Failed to find entities in text: {e}")
            return []

    async def delete_document_entities(
        self,
        tenant_id: str,
        document_id: str,
    ) -> int:
        """
        Remove a document from all entities and relationships.

        Entities that only belonged to this document are deleted entirely.

        Args:
            tenant_id: Tenant identifier
            document_id: Document ID to remove

        Returns:
            Number of entities affected
        """
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return 0

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            nodes_to_remove = []
            affected_count = 0

            # Update nodes
            for node_id in list(graph.nodes()):
                node_data = graph.nodes[node_id]
                doc_ids = set(node_data.get("document_ids", []))

                if document_id in doc_ids:
                    doc_ids.discard(document_id)
                    affected_count += 1

                    if not doc_ids:
                        # No more documents reference this entity
                        nodes_to_remove.append(node_id)
                    else:
                        graph.nodes[node_id]["document_ids"] = list(doc_ids)

            # Remove orphaned nodes
            for node_id in nodes_to_remove:
                graph.remove_node(node_id)

            # Update edges
            edges_to_remove = []
            for source, target, edge_data in list(graph.edges(data=True)):
                doc_ids = set(edge_data.get("document_ids", []))
                if document_id in doc_ids:
                    doc_ids.discard(document_id)
                    if not doc_ids:
                        edges_to_remove.append((source, target))
                    else:
                        graph.edges[source, target]["document_ids"] = list(doc_ids)

            for source, target in edges_to_remove:
                graph.remove_edge(source, target)

            tenant_graph.node_count = graph.number_of_nodes()
            tenant_graph.edge_count = graph.number_of_edges()
            tenant_graph.dirty = True

            await self._persist_to_redis(tenant_id)

            logger.info(
                f"🗑️ Removed document {document_id} from graph: "
                f"{affected_count} entities affected, {len(nodes_to_remove)} removed"
            )

            return affected_count

        except Exception as e:
            logger.error(f"❌ Failed to delete document entities: {e}")
            return 0

    async def get_graph_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get statistics about a tenant's knowledge graph."""
        if not settings.rag_knowledge_graph_enabled or not NETWORKX_AVAILABLE:
            return {"enabled": False}

        await self.initialize()

        try:
            tenant_graph = await self._get_or_create_graph(tenant_id)
            graph = tenant_graph.graph

            # Count entity types
            type_counts = {}
            for node_id in graph.nodes():
                entity_type = graph.nodes[node_id].get("entity_type", "unknown")
                type_counts[entity_type] = type_counts.get(entity_type, 0) + 1

            return {
                "enabled": True,
                "tenant_id": tenant_id,
                "node_count": graph.number_of_nodes(),
                "edge_count": graph.number_of_edges(),
                "entity_types": type_counts,
                "last_accessed": tenant_graph.last_accessed.isoformat(),
                "dirty": tenant_graph.dirty,
            }

        except Exception as e:
            logger.error(f"❌ Failed to get graph stats: {e}")
            return {"enabled": True, "error": str(e)}

    # =========================================================================
    # PERSISTENCE METHODS
    # =========================================================================

    async def _schedule_persist(self, tenant_id: str) -> None:
        """Schedule persistence after batch threshold is reached."""
        count = self._pending_changes.get(tenant_id, 0) + 1
        self._pending_changes[tenant_id] = count

        if count >= self._persist_batch_size:
            await self._persist_to_redis(tenant_id)
            self._pending_changes[tenant_id] = 0

    async def _persist_to_redis(self, tenant_id: str) -> bool:
        """Persist a tenant's graph to Redis."""
        if not self._redis:
            return False

        try:
            tenant_graph = self._graphs.get(tenant_id)
            if not tenant_graph or not tenant_graph.dirty:
                return True

            graph = tenant_graph.graph

            # Serialize nodes
            nodes_data = {}
            for node_id in graph.nodes():
                nodes_data[node_id] = json.dumps(graph.nodes[node_id])

            # Serialize edges
            edges_data = {}
            for source, target, edge_data in graph.edges(data=True):
                edge_key = f"{source}|{target}"
                edges_data[edge_key] = json.dumps(edge_data)

            # Build index (normalized_value -> entity_id)
            index_data = {}
            for node_id in graph.nodes():
                normalized = graph.nodes[node_id].get("normalized_value", "")
                if normalized:
                    index_data[normalized] = node_id

            # Store in Redis
            nodes_key = f"{self._redis_prefix}{tenant_id}:nodes"
            edges_key = f"{self._redis_prefix}{tenant_id}:edges"
            index_key = f"{self._redis_prefix}{tenant_id}:index"

            async with self._redis.pipeline() as pipe:
                # Delete old data
                await pipe.delete(nodes_key, edges_key, index_key)

                # Store new data
                if nodes_data:
                    await pipe.hset(nodes_key, mapping=nodes_data)
                if edges_data:
                    await pipe.hset(edges_key, mapping=edges_data)
                if index_data:
                    await pipe.hset(index_key, mapping=index_data)

                # Set TTL
                await pipe.expire(nodes_key, self._cache_ttl * 24)  # 24x longer than memory cache
                await pipe.expire(edges_key, self._cache_ttl * 24)
                await pipe.expire(index_key, self._cache_ttl * 24)

                await pipe.execute()

            tenant_graph.dirty = False
            logger.debug(
                f"📦 Persisted graph for {tenant_id}: "
                f"{len(nodes_data)} nodes, {len(edges_data)} edges"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Failed to persist graph: {e}")
            return False

    async def _load_from_redis(self, tenant_id: str) -> Optional[Any]:
        """Load a tenant's graph from Redis."""
        if not self._redis or not NETWORKX_AVAILABLE:
            return None

        try:
            nodes_key = f"{self._redis_prefix}{tenant_id}:nodes"
            edges_key = f"{self._redis_prefix}{tenant_id}:edges"

            # Load nodes
            nodes_data = await self._redis.hgetall(nodes_key)
            if not nodes_data:
                return None

            graph = nx.DiGraph()

            # Add nodes
            for node_id, node_json in nodes_data.items():
                node_attrs = json.loads(node_json)
                graph.add_node(node_id, **node_attrs)

            # Add edges
            edges_data = await self._redis.hgetall(edges_key)
            for edge_key, edge_json in edges_data.items():
                source, target = edge_key.split("|")
                edge_attrs = json.loads(edge_json)
                graph.add_edge(source, target, **edge_attrs)

            logger.info(
                f"📂 Loaded graph from Redis for {tenant_id}: "
                f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
            )
            return graph

        except Exception as e:
            logger.warning(f"⚠️ Failed to load graph from Redis: {e}")
            return None

    async def flush_all(self) -> None:
        """Persist all dirty graphs to Redis."""
        for tenant_id, tenant_graph in self._graphs.items():
            if tenant_graph.dirty:
                await self._persist_to_redis(tenant_id)

    async def evict_stale_graphs(self) -> int:
        """Evict graphs that haven't been accessed within TTL."""
        if not self._graphs:
            return 0

        now = datetime.now()
        evicted = 0
        tenants_to_evict = []

        for tenant_id, tenant_graph in self._graphs.items():
            age_seconds = (now - tenant_graph.last_accessed).total_seconds()
            if age_seconds > self._cache_ttl:
                # Persist before evicting
                if tenant_graph.dirty:
                    await self._persist_to_redis(tenant_id)
                tenants_to_evict.append(tenant_id)

        for tenant_id in tenants_to_evict:
            del self._graphs[tenant_id]
            evicted += 1

        if evicted:
            logger.info(f"🧹 Evicted {evicted} stale graphs from memory")

        return evicted

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _normalize_value(self, value: str) -> str:
        """Normalize an entity value for deduplication and lookup."""
        import unicodedata

        # Lowercase and strip
        normalized = value.lower().strip()

        # Remove accents
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        return normalized


# Global singleton instance
knowledge_graph_service = KnowledgeGraphService()
