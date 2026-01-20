"""
Apache AGE Knowledge Graph Service

Implements a persistent knowledge graph using Apache AGE (PostgreSQL extension):
- Native graph storage in PostgreSQL (ACID transactions)
- Cypher query language for graph traversal
- Multi-tenant isolation via vertex/edge properties
- No in-memory state - all data persisted in database

Architecture:
┌─────────────────────────────────────────────────────────────────────────┐
│                    AGE Knowledge Graph Service                           │
├─────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL + Apache AGE                                                 │
│  ├─ Graph: knowledge_graph (shared, tenant-isolated via properties)     │
│  ├─ Vertices: Entity, Document, Chunk                                   │
│  ├─ Edges: APPEARS_IN, RELATED_TO, REFERENCES, DEPENDS_ON               │
│  └─ Indexes: kg_entity_index, kg_document_index (for fast lookups)      │
├─────────────────────────────────────────────────────────────────────────┤
│  Operations:                                                            │
│  • add_entity() - Create vertex in graph                                │
│  • add_relationship() - Create edge between vertices                    │
│  • get_neighbors() - Cypher BFS traversal                               │
│  • find_entity_by_value() - Lookup entity by normalized value           │
└─────────────────────────────────────────────────────────────────────────┘

Cypher Query Examples:

  -- Find related entities (for query expansion):
  MATCH (e:Entity {value: 'Juan García', tenant_id: 'tenant-123'})
        -[:RELATED_TO*1..2]-(related)
  RETURN related.value, related.type

  -- Find all entities in a document:
  MATCH (e:Entity)-[:APPEARS_IN]->(d:Document {id: 'doc-456'})
  RETURN e.value, e.type

Usage:
    from app.services.knowledge.age_graph_service import age_knowledge_graph

    # Add entity during indexing
    vertex_id = await age_knowledge_graph.add_entity(
        tenant_id="tenant-123",
        entity_type="PERSON",
        entity_value="Juan García",
        document_id="doc-456"
    )

    # Get neighbors for query expansion
    neighbors = await age_knowledge_graph.get_neighbors(
        tenant_id="tenant-123",
        entity_value="Juan García",
        max_depth=2
    )
"""

import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import asynccontextmanager

import asyncpg

from ...core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node (vertex) in the knowledge graph."""

    entity_id: str
    entity_type: str
    entity_value: str
    normalized_value: str
    tenant_id: str
    document_ids: Set[str] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    vertex_id: Optional[int] = None  # AGE internal vertex ID

    def to_cypher_props(self) -> str:
        """Convert to Cypher property map for CREATE/MERGE."""
        props = {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_value": self.entity_value,
            "normalized_value": self.normalized_value,
            "tenant_id": self.tenant_id,
            "document_ids": list(self.document_ids),
        }
        # Escape single quotes in values
        parts = []
        for k, v in props.items():
            if isinstance(v, str):
                escaped = v.replace("'", "''")
                parts.append(f"{k}: '{escaped}'")
            elif isinstance(v, list):
                escaped_list = [s.replace("'", "''") if isinstance(s, str) else str(s) for s in v]
                parts.append(f"{k}: {escaped_list}")
            else:
                parts.append(f"{k}: {v}")
        return "{" + ", ".join(parts) + "}"


@dataclass
class GraphEdge:
    """An edge (relationship) in the knowledge graph."""

    source_id: str
    target_id: str
    relationship_type: str
    strength: float
    tenant_id: str
    document_ids: Set[str] = field(default_factory=set)
    context_snippet: Optional[str] = None

    def to_cypher_props(self) -> str:
        """Convert to Cypher property map for CREATE/MERGE."""
        props = {
            "relationship_type": self.relationship_type,
            "strength": self.strength,
            "tenant_id": self.tenant_id,
            "document_ids": list(self.document_ids),
        }
        if self.context_snippet:
            props["context_snippet"] = self.context_snippet[:500]  # Limit length

        parts = []
        for k, v in props.items():
            if isinstance(v, str):
                escaped = v.replace("'", "''")
                parts.append(f"{k}: '{escaped}'")
            elif isinstance(v, list):
                escaped_list = [s.replace("'", "''") if isinstance(s, str) else str(s) for s in v]
                parts.append(f"{k}: {escaped_list}")
            elif isinstance(v, float):
                parts.append(f"{k}: {v}")
            else:
                parts.append(f"{k}: {v}")
        return "{" + ", ".join(parts) + "}"


class AGEKnowledgeGraphService:
    """
    Apache AGE Knowledge Graph Service.

    Uses PostgreSQL + AGE extension for persistent graph storage with
    Cypher query language support.
    """

    GRAPH_NAME = "knowledge_graph"

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._min_strength = settings.rag_graph_min_relationship_strength
        self._max_neighbors = settings.rag_graph_max_neighbors
        self._traversal_depth = settings.rag_graph_traversal_depth

    async def initialize(self) -> None:
        """Initialize the service and database connection pool."""
        if self._initialized:
            return

        if not settings.rag_knowledge_graph_enabled:
            logger.info("ℹ️ Knowledge graph disabled by configuration")
            return

        try:
            # Parse database URL for asyncpg
            db_url = settings.database_url
            # Convert postgresql+asyncpg:// to postgresql://
            if "+asyncpg" in db_url:
                db_url = db_url.replace("+asyncpg", "")

            self._pool = await asyncpg.create_pool(
                db_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )

            # Verify AGE is available and graph exists
            async with self._pool.acquire() as conn:
                # Load AGE extension
                await conn.execute("LOAD 'age';")
                await conn.execute(
                    "SET search_path = ag_catalog, \"$user\", public;"
                )

                # Check if graph exists
                result = await conn.fetchval(
                    "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1",
                    self.GRAPH_NAME,
                )

                if result == 0:
                    # Create graph if not exists (should be created by init script)
                    await conn.execute(
                        f"SELECT create_graph('{self.GRAPH_NAME}');"
                    )
                    logger.info(f"✅ Created graph: {self.GRAPH_NAME}")

            self._initialized = True
            logger.info("✅ AGE Knowledge Graph Service initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize AGE Knowledge Graph: {e}")
            # Don't raise - service can operate without graph
            self._initialized = True  # Prevent retries

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection with AGE loaded and search path set."""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute(
                "SET search_path = ag_catalog, \"$user\", public;"
            )
            yield conn

    async def _execute_cypher(
        self,
        conn: asyncpg.Connection,
        cypher_query: str,
        return_columns: List[Tuple[str, str]],
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.

        Args:
            conn: Database connection
            cypher_query: Cypher query string
            return_columns: List of (column_name, type) tuples for result parsing

        Returns:
            List of result dictionaries
        """
        # Build the column specification for the AS clause
        col_specs = ", ".join([f"{name} agtype" for name, _ in return_columns])

        sql = f"""
            SELECT * FROM cypher('{self.GRAPH_NAME}', $$
                {cypher_query}
            $$) AS ({col_specs});
        """

        try:
            rows = await conn.fetch(sql)
            results = []

            for row in rows:
                result = {}
                for i, (col_name, col_type) in enumerate(return_columns):
                    value = row[i]
                    if value is not None:
                        # Parse agtype JSON
                        if isinstance(value, str):
                            try:
                                parsed = json.loads(value)
                                result[col_name] = parsed
                            except json.JSONDecodeError:
                                result[col_name] = value
                        else:
                            result[col_name] = value
                    else:
                        result[col_name] = None
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Cypher query failed: {e}\nQuery: {cypher_query}")
            raise

    async def add_entity(
        self,
        tenant_id: str,
        entity_type: str,
        entity_value: str,
        document_id: str,
        entity_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Add an entity node to the knowledge graph.

        If an entity with the same normalized value exists for this tenant,
        updates it by adding the new document_id.

        Args:
            tenant_id: Tenant identifier
            entity_type: Type of entity (PERSON, ORGANIZATION, etc.)
            entity_value: Display value of the entity
            document_id: Source document ID
            entity_id: Optional unique entity identifier (generated if not provided)
            attributes: Optional additional attributes

        Returns:
            Entity ID if successful, None on error
        """
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return None

        await self.initialize()

        if not self._pool:
            return None

        try:
            normalized = self._normalize_value(entity_value)

            if not entity_id:
                import uuid
                entity_id = f"ent-{uuid.uuid4().hex[:12]}"

            async with self._get_connection() as conn:
                # Check if entity exists in index
                existing = await conn.fetchrow(
                    """
                    SELECT vertex_id FROM kg_entity_index
                    WHERE normalized_value = $1 AND entity_type = $2 AND tenant_id = $3
                    """,
                    normalized,
                    entity_type,
                    tenant_id,
                )

                if existing:
                    # Update existing entity - add document_id
                    # Cypher MATCH and SET to update document_ids array
                    cypher = f"""
                        MATCH (e:Entity {{normalized_value: '{normalized}', tenant_id: '{tenant_id}'}})
                        SET e.document_ids = e.document_ids + ['{document_id}']
                        RETURN id(e)
                    """
                    await self._execute_cypher(conn, cypher, [("id", "bigint")])
                    logger.debug(f"Updated existing entity: {entity_value}")
                    return entity_id

                # Create new entity
                node = GraphNode(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    entity_value=entity_value,
                    normalized_value=normalized,
                    tenant_id=tenant_id,
                    document_ids={document_id},
                    attributes=attributes or {},
                )

                cypher = f"""
                    CREATE (e:Entity {node.to_cypher_props()})
                    RETURN id(e)
                """
                results = await self._execute_cypher(conn, cypher, [("id", "bigint")])

                if results:
                    vertex_id = results[0].get("id")

                    # Add to index for fast lookups
                    await conn.execute(
                        """
                        INSERT INTO kg_entity_index
                            (normalized_value, entity_type, tenant_id, vertex_id)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (normalized_value, entity_type, tenant_id)
                        DO UPDATE SET vertex_id = $4
                        """,
                        normalized,
                        entity_type,
                        tenant_id,
                        vertex_id,
                    )

                    logger.debug(f"Created entity: {entity_value} (vertex_id={vertex_id})")
                    return entity_id

            return None

        except Exception as e:
            logger.error(f"❌ Failed to add entity: {e}")
            return None

    async def add_relationship(
        self,
        tenant_id: str,
        source_value: str,
        target_value: str,
        relationship_type: str,
        strength: float,
        document_id: str,
        context_snippet: Optional[str] = None,
    ) -> bool:
        """
        Add a relationship edge between two entities.

        Args:
            tenant_id: Tenant identifier
            source_value: Source entity value (normalized for lookup)
            target_value: Target entity value (normalized for lookup)
            relationship_type: Type of relationship
            strength: Relationship strength (0.0-1.0)
            document_id: Source document ID
            context_snippet: Optional context text

        Returns:
            True if successful, False on error
        """
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return False

        # Filter weak relationships
        if strength < self._min_strength:
            return False

        await self.initialize()

        if not self._pool:
            return False

        try:
            source_normalized = self._normalize_value(source_value)
            target_normalized = self._normalize_value(target_value)

            async with self._get_connection() as conn:
                # Build edge properties
                edge = GraphEdge(
                    source_id=source_normalized,
                    target_id=target_normalized,
                    relationship_type=relationship_type,
                    strength=strength,
                    tenant_id=tenant_id,
                    document_ids={document_id},
                    context_snippet=context_snippet,
                )

                # MERGE edge - create if not exists, update if exists
                cypher = f"""
                    MATCH (s:Entity {{normalized_value: '{source_normalized}', tenant_id: '{tenant_id}'}})
                    MATCH (t:Entity {{normalized_value: '{target_normalized}', tenant_id: '{tenant_id}'}})
                    MERGE (s)-[r:RELATED_TO]->(t)
                    ON CREATE SET r = {edge.to_cypher_props()}
                    ON MATCH SET r.strength = CASE WHEN r.strength > {strength} THEN r.strength ELSE {strength} END,
                                 r.document_ids = r.document_ids + ['{document_id}']
                    RETURN id(r)
                """

                results = await self._execute_cypher(conn, cypher, [("id", "bigint")])

                if results:
                    logger.debug(
                        f"Created/updated relationship: {source_value} -[{relationship_type}]-> {target_value}"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Failed to add relationship: {e}")
            return False

    async def get_neighbors(
        self,
        tenant_id: str,
        entity_value: str,
        max_depth: Optional[int] = None,
        relationship_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring entities using Cypher path traversal.

        Args:
            tenant_id: Tenant identifier
            entity_value: Starting entity value
            max_depth: Maximum traversal depth
            relationship_types: Filter by relationship types

        Returns:
            List of neighbor entities with relationship info
        """
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return []

        await self.initialize()

        if not self._pool:
            return []

        try:
            normalized = self._normalize_value(entity_value)
            depth = max_depth or self._traversal_depth
            max_results = self._max_neighbors

            async with self._get_connection() as conn:
                # Build Cypher query for variable-length path
                # This finds all entities connected within depth hops
                cypher = f"""
                    MATCH (start:Entity {{normalized_value: '{normalized}', tenant_id: '{tenant_id}'}})
                          -[r:RELATED_TO*1..{depth}]-(neighbor:Entity)
                    WHERE neighbor.tenant_id = '{tenant_id}'
                    RETURN DISTINCT
                        neighbor.entity_value AS value,
                        neighbor.entity_type AS type,
                        neighbor.normalized_value AS normalized,
                        r[0].relationship_type AS rel_type,
                        r[0].strength AS strength,
                        length(r) AS depth
                    ORDER BY r[0].strength DESC
                    LIMIT {max_results}
                """

                results = await self._execute_cypher(
                    conn,
                    cypher,
                    [
                        ("value", "text"),
                        ("type", "text"),
                        ("normalized", "text"),
                        ("rel_type", "text"),
                        ("strength", "float"),
                        ("depth", "int"),
                    ],
                )

                neighbors = []
                for row in results:
                    neighbors.append({
                        "entity_value": row.get("value"),
                        "entity_type": row.get("type"),
                        "normalized_value": row.get("normalized"),
                        "relationship_type": row.get("rel_type"),
                        "relationship_strength": row.get("strength", 0.5),
                        "depth": row.get("depth", 1),
                    })

                logger.debug(
                    f"Found {len(neighbors)} neighbors for '{entity_value}' "
                    f"(depth={depth})"
                )

                return neighbors

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
        Find an entity by its value.

        Args:
            tenant_id: Tenant identifier
            value: Entity value to search for
            entity_type: Optional type filter

        Returns:
            Entity data dict or None if not found
        """
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return None

        await self.initialize()

        if not self._pool:
            return None

        try:
            normalized = self._normalize_value(value)

            async with self._get_connection() as conn:
                type_filter = ""
                if entity_type:
                    type_filter = f", entity_type: '{entity_type}'"

                cypher = f"""
                    MATCH (e:Entity {{normalized_value: '{normalized}', tenant_id: '{tenant_id}'{type_filter}}})
                    RETURN
                        e.entity_id AS entity_id,
                        e.entity_type AS entity_type,
                        e.entity_value AS entity_value,
                        e.normalized_value AS normalized_value,
                        e.document_ids AS document_ids
                    LIMIT 1
                """

                results = await self._execute_cypher(
                    conn,
                    cypher,
                    [
                        ("entity_id", "text"),
                        ("entity_type", "text"),
                        ("entity_value", "text"),
                        ("normalized_value", "text"),
                        ("document_ids", "text[]"),
                    ],
                )

                if results:
                    return results[0]

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

        Uses the entity index for fast substring matching.

        Args:
            tenant_id: Tenant identifier
            text: Text to search for entities
            limit: Maximum entities to return

        Returns:
            List of matching entity data dicts
        """
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return []

        await self.initialize()

        if not self._pool:
            return []

        try:
            text_lower = text.lower()

            async with self._get_connection() as conn:
                # Query the index for entities whose normalized values appear in text
                # This is more efficient than scanning all vertices
                rows = await conn.fetch(
                    """
                    SELECT
                        normalized_value,
                        entity_type,
                        vertex_id
                    FROM kg_entity_index
                    WHERE tenant_id = $1
                      AND length(normalized_value) > 2
                      AND position(normalized_value IN $2) > 0
                    LIMIT $3
                    """,
                    tenant_id,
                    text_lower,
                    limit,
                )

                entities = []
                for row in rows:
                    # Get full entity data from graph
                    cypher = f"""
                        MATCH (e:Entity)
                        WHERE id(e) = {row['vertex_id']}
                        RETURN
                            e.entity_id AS entity_id,
                            e.entity_type AS entity_type,
                            e.entity_value AS entity_value,
                            e.normalized_value AS normalized_value
                    """

                    results = await self._execute_cypher(
                        conn,
                        cypher,
                        [
                            ("entity_id", "text"),
                            ("entity_type", "text"),
                            ("entity_value", "text"),
                            ("normalized_value", "text"),
                        ],
                    )

                    if results:
                        entity = results[0]
                        entity["match_position"] = text_lower.find(
                            row["normalized_value"]
                        )
                        entities.append(entity)

                # Sort by match position
                entities.sort(key=lambda x: x.get("match_position", 999))

                return entities

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

        Entities that only belonged to this document are deleted.

        Args:
            tenant_id: Tenant identifier
            document_id: Document ID to remove

        Returns:
            Number of entities affected
        """
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return 0

        await self.initialize()

        if not self._pool:
            return 0

        try:
            async with self._get_connection() as conn:
                # First, remove document_id from all entities' document_ids arrays
                # and count affected entities
                cypher_update = f"""
                    MATCH (e:Entity {{tenant_id: '{tenant_id}'}})
                    WHERE '{document_id}' IN e.document_ids
                    SET e.document_ids = [x IN e.document_ids WHERE x <> '{document_id}']
                    RETURN count(e) AS affected
                """

                results = await self._execute_cypher(
                    conn, cypher_update, [("affected", "int")]
                )
                affected = results[0].get("affected", 0) if results else 0

                # Delete orphaned entities (no document_ids left)
                cypher_delete = f"""
                    MATCH (e:Entity {{tenant_id: '{tenant_id}'}})
                    WHERE size(e.document_ids) = 0
                    DETACH DELETE e
                    RETURN count(e) AS deleted
                """

                delete_results = await self._execute_cypher(
                    conn, cypher_delete, [("deleted", "int")]
                )
                deleted = delete_results[0].get("deleted", 0) if delete_results else 0

                # Clean up index
                await conn.execute(
                    """
                    DELETE FROM kg_entity_index
                    WHERE tenant_id = $1
                      AND vertex_id NOT IN (
                          SELECT DISTINCT vertex_id
                          FROM kg_entity_index ei
                          WHERE EXISTS (
                              SELECT 1 FROM ag_catalog.ag_graph g
                              -- This is a simplified check
                          )
                      )
                    """,
                    tenant_id,
                )

                logger.info(
                    f"🗑️ Removed document {document_id}: "
                    f"{affected} entities affected, {deleted} deleted"
                )

                return affected

        except Exception as e:
            logger.error(f"❌ Failed to delete document entities: {e}")
            return 0

    async def get_graph_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get statistics about a tenant's knowledge graph."""
        if not settings.rag_knowledge_graph_enabled or not self._pool:
            return {"enabled": False}

        await self.initialize()

        if not self._pool:
            return {"enabled": False, "error": "Database not connected"}

        try:
            async with self._get_connection() as conn:
                # Count entities by type
                cypher_entities = f"""
                    MATCH (e:Entity {{tenant_id: '{tenant_id}'}})
                    RETURN e.entity_type AS type, count(e) AS count
                """

                entity_results = await self._execute_cypher(
                    conn, cypher_entities, [("type", "text"), ("count", "int")]
                )

                type_counts = {r["type"]: r["count"] for r in entity_results}
                total_entities = sum(type_counts.values())

                # Count relationships
                cypher_edges = f"""
                    MATCH (s:Entity {{tenant_id: '{tenant_id}'}})-[r:RELATED_TO]->(t)
                    RETURN count(r) AS count
                """

                edge_results = await self._execute_cypher(
                    conn, cypher_edges, [("count", "int")]
                )
                total_edges = edge_results[0].get("count", 0) if edge_results else 0

                return {
                    "enabled": True,
                    "backend": "apache_age",
                    "graph_name": self.GRAPH_NAME,
                    "tenant_id": tenant_id,
                    "node_count": total_entities,
                    "edge_count": total_edges,
                    "entity_types": type_counts,
                }

        except Exception as e:
            logger.error(f"❌ Failed to get graph stats: {e}")
            return {"enabled": True, "backend": "apache_age", "error": str(e)}

    async def close(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info("AGE Knowledge Graph Service closed")

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

        # Escape for Cypher (single quotes)
        normalized = normalized.replace("'", "")

        return normalized


# Global singleton instance
age_knowledge_graph = AGEKnowledgeGraphService()
