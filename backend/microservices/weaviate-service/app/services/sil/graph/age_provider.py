"""
Apache AGE Graph Provider

Implementation of GraphProvider for Apache AGE (PostgreSQL extension).

Apache AGE provides Cypher query support on top of PostgreSQL,
allowing graph operations while leveraging PostgreSQL's ACID guarantees.

Limitations:
- No parameterized Cypher queries (must use string interpolation)
- No multi-statement transactions in asyncpg
- agtype parsing required for results

Usage:
    from app.services.sil.graph import AGEProvider

    provider = AGEProvider(
        host="localhost",
        database="nexus",
        graph_name="knowledge_graph"
    )
    await provider.initialize()
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .graph_provider import (
    EdgeLabel,
    GraphEdge,
    GraphNode,
    GraphProvider,
    NodeLabel,
    QueryResult,
)

logger = logging.getLogger(__name__)


class AGEProvider(GraphProvider):
    """
    Apache AGE implementation of GraphProvider.

    This provider translates the abstract graph operations into
    Cypher queries executed against Apache AGE.
    """

    provider_name = "apache_age"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "nexus",
        user: str = "postgres",
        password: str = "",
        graph_name: str = "knowledge_graph",
        pool_size: int = 10,
    ):
        """
        Initialize the AGE provider.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            graph_name: Name of the AGE graph
            pool_size: Connection pool size
        """
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._graph_name = graph_name
        self._pool_size = pool_size

        self._pool = None
        self._initialized = False
        self._schema_cache: set = set()

    async def initialize(self) -> None:
        """Initialize the connection pool and ensure graph exists."""
        if self._initialized:
            return

        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                database=self._database,
                user=self._user,
                password=self._password,
                min_size=2,
                max_size=self._pool_size,
            )

            # Ensure graph exists
            async with self._get_connection() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS age;")
                await conn.execute("LOAD 'age';")
                await conn.execute(
                    "SET search_path = ag_catalog, \"$user\", public;"
                )

                # Check if graph exists
                exists = await conn.fetchval(
                    "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1",
                    self._graph_name,
                )

                if exists == 0:
                    await conn.execute(f"SELECT create_graph('{self._graph_name}');")
                    logger.info(f"✅ Created graph: {self._graph_name}")

            self._initialized = True
            logger.info(f"✅ AGEProvider initialized (graph: {self._graph_name})")

        except ImportError:
            logger.error("asyncpg not installed. Run: pip install asyncpg")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AGEProvider: {e}")
            raise

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info("✅ AGEProvider closed")

    async def is_available(self) -> bool:
        """Check if the database is available."""
        if not self._pool:
            return False

        try:
            async with self._get_connection() as conn:
                await conn.fetchval("SELECT 1")
                return True
        except Exception:
            return False

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool with AGE setup."""
        async with self._pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute(
                "SET search_path = ag_catalog, \"$user\", public;"
            )
            yield conn

    # =========================================================================
    # Schema Operations
    # =========================================================================

    async def ensure_node_label(self, label: Union[NodeLabel, str]) -> bool:
        """Ensure a vertex label exists."""
        label_str = label.value if isinstance(label, Enum) else label

        if label_str in self._schema_cache:
            return True

        try:
            async with self._get_connection() as conn:
                exists = await conn.fetchval(
                    """
                    SELECT count(*) FROM ag_catalog.ag_label
                    WHERE name = $1 AND graph = (
                        SELECT graphid FROM ag_catalog.ag_graph WHERE name = $2
                    )
                    """,
                    label_str,
                    self._graph_name,
                )

                if exists == 0:
                    await conn.execute(
                        f"SELECT create_vlabel('{self._graph_name}', '{label_str}');"
                    )
                    logger.info(f"✅ Created vertex label: {label_str}")

                self._schema_cache.add(label_str)
                return True

        except Exception as e:
            logger.error(f"Failed to ensure node label {label_str}: {e}")
            return False

    async def ensure_edge_label(self, label: Union[EdgeLabel, str]) -> bool:
        """Ensure an edge label exists."""
        label_str = label.value if isinstance(label, Enum) else label

        if label_str in self._schema_cache:
            return True

        try:
            async with self._get_connection() as conn:
                exists = await conn.fetchval(
                    """
                    SELECT count(*) FROM ag_catalog.ag_label
                    WHERE name = $1 AND graph = (
                        SELECT graphid FROM ag_catalog.ag_graph WHERE name = $2
                    )
                    """,
                    label_str,
                    self._graph_name,
                )

                if exists == 0:
                    await conn.execute(
                        f"SELECT create_elabel('{self._graph_name}', '{label_str}');"
                    )
                    logger.info(f"✅ Created edge label: {label_str}")

                self._schema_cache.add(label_str)
                return True

        except Exception as e:
            logger.error(f"Failed to ensure edge label {label_str}: {e}")
            return False

    async def ensure_schema(
        self,
        node_labels: List[Union[NodeLabel, str]],
        edge_labels: List[Union[EdgeLabel, str]],
    ) -> bool:
        """Ensure all labels exist."""
        success = True

        for label in node_labels:
            if not await self.ensure_node_label(label):
                success = False

        for label in edge_labels:
            if not await self.ensure_edge_label(label):
                success = False

        return success

    # =========================================================================
    # Node Operations
    # =========================================================================

    async def add_node(self, node: GraphNode) -> Optional[str]:
        """Add or update a node using MERGE."""
        if not self._pool:
            return None

        label = node.label_value
        await self.ensure_node_label(label)

        try:
            props = self._build_properties(node.to_dict())

            async with self._get_connection() as conn:
                # Use MERGE for idempotent upsert
                cypher = f"""
                    MERGE (n:{label} {{node_id: '{self.escape_string(node.node_id)}', tenant_id: '{self.escape_string(node.tenant_id)}'}})
                    SET n = {props}
                    RETURN id(n) as internal_id
                """
                result = await self._execute_cypher(
                    conn, cypher, [("internal_id", "agtype")]
                )

                if result:
                    logger.debug(f"Added/updated node: {node.node_id}")
                    return node.node_id

                return None

        except Exception as e:
            logger.error(f"Failed to add node {node.node_id}: {e}")
            return None

    async def get_node(
        self,
        node_id: str,
        label: Union[NodeLabel, str],
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a node by ID."""
        if not self._pool:
            return None

        label_str = label.value if isinstance(label, Enum) else label

        try:
            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (n:{label_str} {{node_id: '{self.escape_string(node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})
                    RETURN n
                """
                result = await self._execute_cypher(conn, cypher, [("n", "agtype")])

                if result and result[0].get("n"):
                    return self._parse_agtype_node(result[0]["n"])

                return None

        except Exception as e:
            logger.error(f"Failed to get node {node_id}: {e}")
            return None

    async def update_node(
        self,
        node_id: str,
        label: Union[NodeLabel, str],
        tenant_id: str,
        properties: Dict[str, Any],
    ) -> bool:
        """Update node properties."""
        if not self._pool:
            return False

        label_str = label.value if isinstance(label, Enum) else label

        try:
            # Build SET clauses for each property
            set_clauses = []
            for key, value in properties.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    set_clauses.append(f"n.{key} = '{self.escape_string(value)}'")
                elif isinstance(value, bool):
                    set_clauses.append(f"n.{key} = {str(value).lower()}")
                elif isinstance(value, (int, float)):
                    set_clauses.append(f"n.{key} = {value}")
                elif isinstance(value, datetime):
                    set_clauses.append(f"n.{key} = '{value.isoformat()}'")

            if not set_clauses:
                return True

            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (n:{label_str} {{node_id: '{self.escape_string(node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})
                    SET {', '.join(set_clauses)}
                    RETURN id(n) as internal_id
                """
                result = await self._execute_cypher(
                    conn, cypher, [("internal_id", "agtype")]
                )

                return bool(result)

        except Exception as e:
            logger.error(f"Failed to update node {node_id}: {e}")
            return False

    async def delete_node(
        self,
        node_id: str,
        label: Union[NodeLabel, str],
        tenant_id: str,
        soft_delete: bool = True,
    ) -> bool:
        """Delete a node (soft or hard delete)."""
        if not self._pool:
            return False

        label_str = label.value if isinstance(label, Enum) else label

        try:
            async with self._get_connection() as conn:
                if soft_delete:
                    # Soft delete: set valid_to
                    now = datetime.utcnow().isoformat()
                    cypher = f"""
                        MATCH (n:{label_str} {{node_id: '{self.escape_string(node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})
                        SET n.valid_to = '{now}'
                        RETURN id(n) as internal_id
                    """
                else:
                    # Hard delete: remove node and edges
                    cypher = f"""
                        MATCH (n:{label_str} {{node_id: '{self.escape_string(node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})
                        DETACH DELETE n
                        RETURN count(*) as deleted
                    """

                result = await self._execute_cypher(
                    conn,
                    cypher,
                    [("internal_id", "agtype")] if soft_delete else [("deleted", "agtype")],
                )

                return bool(result)

        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            return False

    async def node_exists(
        self,
        node_id: str,
        label: Union[NodeLabel, str],
        tenant_id: str,
    ) -> bool:
        """Check if a node exists."""
        if not self._pool:
            return False

        label_str = label.value if isinstance(label, Enum) else label

        try:
            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (n:{label_str} {{node_id: '{self.escape_string(node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})
                    RETURN count(n) as total
                """
                result = await self._execute_cypher(conn, cypher, [("total", "agtype")])

                return bool(result and result[0].get("total", 0) > 0)

        except Exception as e:
            logger.error(f"Failed to check node exists {node_id}: {e}")
            return False

    # =========================================================================
    # Edge Operations
    # =========================================================================

    async def add_edge(
        self,
        edge: GraphEdge,
        source_label: Union[NodeLabel, str],
        target_label: Union[NodeLabel, str],
    ) -> bool:
        """Add an edge between two nodes."""
        if not self._pool:
            return False

        edge_label = edge.label_value
        source_label_str = source_label.value if isinstance(source_label, Enum) else source_label
        target_label_str = target_label.value if isinstance(target_label, Enum) else target_label

        await self.ensure_edge_label(edge_label)

        try:
            props = self._build_properties({"tenant_id": edge.tenant_id, **edge.properties})

            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (s:{source_label_str} {{node_id: '{self.escape_string(edge.source_id)}', tenant_id: '{self.escape_string(edge.tenant_id)}'}})
                    MATCH (t:{target_label_str} {{node_id: '{self.escape_string(edge.target_id)}', tenant_id: '{self.escape_string(edge.tenant_id)}'}})
                    MERGE (s)-[r:{edge_label} {props}]->(t)
                    RETURN id(r) as edge_id
                """
                result = await self._execute_cypher(
                    conn, cypher, [("edge_id", "agtype")]
                )

                if result:
                    logger.debug(
                        f"Added edge: {edge.source_id} -[{edge_label}]-> {edge.target_id}"
                    )
                    return True

                return False

        except Exception as e:
            logger.error(f"Failed to add edge: {e}")
            return False

    async def delete_edge(
        self,
        source_id: str,
        target_id: str,
        label: Union[EdgeLabel, str],
        tenant_id: str,
    ) -> bool:
        """Delete an edge."""
        if not self._pool:
            return False

        label_str = label.value if isinstance(label, Enum) else label

        try:
            async with self._get_connection() as conn:
                # Match and delete edge (need to know source/target labels)
                cypher = f"""
                    MATCH (s {{node_id: '{self.escape_string(source_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})-[r:{label_str}]->(t {{node_id: '{self.escape_string(target_id)}', tenant_id: '{self.escape_string(tenant_id)}'}})
                    DELETE r
                    RETURN count(*) as deleted
                """
                result = await self._execute_cypher(
                    conn, cypher, [("deleted", "agtype")]
                )

                return bool(result)

        except Exception as e:
            logger.error(f"Failed to delete edge: {e}")
            return False

    async def get_edges(
        self,
        node_id: str,
        label: Union[NodeLabel, str],
        tenant_id: str,
        edge_label: Optional[Union[EdgeLabel, str]] = None,
        direction: str = "both",
    ) -> List[Dict[str, Any]]:
        """Get edges connected to a node."""
        if not self._pool:
            return []

        label_str = label.value if isinstance(label, Enum) else label
        edge_label_str = edge_label.value if isinstance(edge_label, Enum) else edge_label

        try:
            # Build relationship pattern
            if edge_label_str:
                rel_type = f":{edge_label_str}"
            else:
                rel_type = ""

            if direction == "outgoing":
                pattern = f"-[r{rel_type}]->"
            elif direction == "incoming":
                pattern = f"<-[r{rel_type}]-"
            else:
                pattern = f"-[r{rel_type}]-"

            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (n:{label_str} {{node_id: '{self.escape_string(node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}}){pattern}(other)
                    RETURN type(r) as edge_type, other.node_id as other_id, r as edge
                """
                result = await self._execute_cypher(
                    conn,
                    cypher,
                    [("edge_type", "agtype"), ("other_id", "agtype"), ("edge", "agtype")],
                )

                edges = []
                for row in result:
                    edges.append({
                        "type": self._clean_agtype_value(row.get("edge_type")),
                        "other_id": self._clean_agtype_value(row.get("other_id")),
                    })

                return edges

        except Exception as e:
            logger.error(f"Failed to get edges for {node_id}: {e}")
            return []

    # =========================================================================
    # Query Operations
    # =========================================================================

    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """Execute a raw Cypher query."""
        if not self._pool:
            return QueryResult(rows=[], query=query)

        start_time = time.time()

        try:
            # Note: Apache AGE doesn't support parameterized Cypher
            # Parameters should be interpolated into the query string
            # This is a security consideration!
            if parameters:
                for key, value in parameters.items():
                    if isinstance(value, str):
                        query = query.replace(f"${key}", f"'{self.escape_string(value)}'")
                    else:
                        query = query.replace(f"${key}", str(value))

            async with self._get_connection() as conn:
                # Determine columns from query (basic parsing)
                columns = self._extract_columns_from_query(query)

                result = await self._execute_cypher(
                    conn,
                    query,
                    [(col, "agtype") for col in columns],
                )

                execution_time = (time.time() - start_time) * 1000

                return QueryResult(
                    rows=result,
                    columns=columns,
                    execution_time_ms=execution_time,
                    query=query,
                )

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return QueryResult(rows=[], query=query)

    async def count_nodes(
        self,
        label: Union[NodeLabel, str],
        tenant_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count nodes matching criteria."""
        if not self._pool:
            return 0

        label_str = label.value if isinstance(label, Enum) else label

        try:
            where_clauses = [
                f"n.tenant_id = '{self.escape_string(tenant_id)}'",
                "(n.valid_to = '' OR n.valid_to IS NULL)",
            ]

            if filters:
                for key, value in filters.items():
                    if isinstance(value, str):
                        where_clauses.append(
                            f"n.{key} = '{self.escape_string(value)}'"
                        )
                    elif isinstance(value, (int, float)):
                        where_clauses.append(f"n.{key} = {value}")
                    elif isinstance(value, list):
                        values_str = ", ".join(
                            f"'{self.escape_string(v)}'" if isinstance(v, str) else str(v)
                            for v in value
                        )
                        where_clauses.append(f"n.{key} IN [{values_str}]")

            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (n:{label_str})
                    WHERE {' AND '.join(where_clauses)}
                    RETURN count(n) as total
                """
                result = await self._execute_cypher(conn, cypher, [("total", "agtype")])

                if result:
                    return int(result[0].get("total", 0))
                return 0

        except Exception as e:
            logger.error(f"Failed to count nodes: {e}")
            return 0

    async def find_nodes(
        self,
        label: Union[NodeLabel, str],
        tenant_id: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find nodes matching criteria."""
        if not self._pool:
            return []

        label_str = label.value if isinstance(label, Enum) else label

        try:
            where_clauses = [
                f"n.tenant_id = '{self.escape_string(tenant_id)}'",
                "(n.valid_to = '' OR n.valid_to IS NULL)",
            ]

            if filters:
                for key, value in filters.items():
                    if isinstance(value, str):
                        where_clauses.append(
                            f"n.{key} = '{self.escape_string(value)}'"
                        )
                    elif isinstance(value, (int, float)):
                        where_clauses.append(f"n.{key} = {value}")

            order_clause = f"ORDER BY n.{order_by} DESC" if order_by else ""

            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (n:{label_str})
                    WHERE {' AND '.join(where_clauses)}
                    RETURN n
                    {order_clause}
                    LIMIT {limit}
                """
                result = await self._execute_cypher(conn, cypher, [("n", "agtype")])

                nodes = []
                for row in result:
                    if row.get("n"):
                        nodes.append(self._parse_agtype_node(row["n"]))

                return nodes

        except Exception as e:
            logger.error(f"Failed to find nodes: {e}")
            return []

    async def traverse(
        self,
        start_node_id: str,
        start_label: Union[NodeLabel, str],
        tenant_id: str,
        edge_labels: Optional[List[Union[EdgeLabel, str]]] = None,
        max_depth: int = 2,
        direction: str = "both",
    ) -> List[Dict[str, Any]]:
        """Traverse the graph from a starting node."""
        if not self._pool:
            return []

        start_label_str = start_label.value if isinstance(start_label, Enum) else start_label

        try:
            # Build relationship pattern
            if edge_labels:
                labels_str = "|".join(
                    e.value if isinstance(e, Enum) else e
                    for e in edge_labels
                )
                rel_type = f":{labels_str}"
            else:
                rel_type = ""

            if direction == "outgoing":
                pattern = f"-[r{rel_type}*1..{max_depth}]->"
            elif direction == "incoming":
                pattern = f"<-[r{rel_type}*1..{max_depth}]-"
            else:
                pattern = f"-[r{rel_type}*1..{max_depth}]-"

            async with self._get_connection() as conn:
                cypher = f"""
                    MATCH (start:{start_label_str} {{node_id: '{self.escape_string(start_node_id)}', tenant_id: '{self.escape_string(tenant_id)}'}}){pattern}(reached)
                    WHERE reached.tenant_id = '{self.escape_string(tenant_id)}'
                      AND reached.node_id <> '{self.escape_string(start_node_id)}'
                      AND (reached.valid_to = '' OR reached.valid_to IS NULL)
                    RETURN DISTINCT reached
                    LIMIT 50
                """
                result = await self._execute_cypher(conn, cypher, [("reached", "agtype")])

                nodes = []
                for row in result:
                    if row.get("reached"):
                        nodes.append(self._parse_agtype_node(row["reached"]))

                return nodes

        except Exception as e:
            logger.error(f"Failed to traverse from {start_node_id}: {e}")
            return []

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    async def clear_tenant_data(self, tenant_id: str) -> bool:
        """Clear all graph data for a tenant."""
        if not self._pool:
            return True

        try:
            async with self._get_connection() as conn:
                # Delete all nodes (and their edges) for tenant
                # We need to do this per label since AGE doesn't support
                # matching across labels efficiently
                for label in [
                    NodeLabel.DOCUMENT.value,
                    NodeLabel.FOLDER.value,
                    NodeLabel.SITE.value,
                    NodeLabel.LAW.value,
                    NodeLabel.ARTICLE.value,
                ]:
                    try:
                        cypher = f"""
                            MATCH (n:{label} {{tenant_id: '{self.escape_string(tenant_id)}'}})
                            DETACH DELETE n
                            RETURN count(*) as deleted
                        """
                        await self._execute_cypher(conn, cypher, [("deleted", "agtype")])
                    except Exception:
                        pass  # Label might not exist

            logger.info(f"✅ Cleared graph data for tenant: {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to clear tenant data: {e}")
            return False

    async def get_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get statistics about the graph."""
        if not self._pool:
            return {"error": "Not connected"}

        try:
            stats = {
                "tenant_id": tenant_id,
                "graph_name": self._graph_name,
                "provider": self.provider_name,
                "nodes": {},
                "total_nodes": 0,
            }

            async with self._get_connection() as conn:
                for label in [
                    NodeLabel.DOCUMENT.value,
                    NodeLabel.FOLDER.value,
                    NodeLabel.LAW.value,
                    NodeLabel.ARTICLE.value,
                ]:
                    try:
                        cypher = f"""
                            MATCH (n:{label} {{tenant_id: '{self.escape_string(tenant_id)}'}})
                            WHERE n.valid_to = '' OR n.valid_to IS NULL
                            RETURN count(n) as total
                        """
                        result = await self._execute_cypher(
                            conn, cypher, [("total", "agtype")]
                        )
                        count = result[0].get("total", 0) if result else 0
                        stats["nodes"][label] = count
                        stats["total_nodes"] += count
                    except Exception:
                        stats["nodes"][label] = 0

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}

    # =========================================================================
    # Internal Helper Methods
    # =========================================================================

    async def _execute_cypher(
        self,
        conn,
        cypher: str,
        columns: List[tuple],
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.

        Args:
            conn: Database connection
            cypher: Cypher query string
            columns: List of (name, type) tuples for result columns

        Returns:
            List of result rows as dictionaries
        """
        # Build column casting
        column_specs = ", ".join(f"{name} {typ}" for name, typ in columns)

        # Wrap in ag_catalog.cypher call
        sql = f"""
            SELECT * FROM ag_catalog.cypher(
                '{self._graph_name}',
                $$ {cypher} $$
            ) AS ({column_specs});
        """

        try:
            rows = await conn.fetch(sql)
            results = []

            for row in rows:
                result_row = {}
                for name, _ in columns:
                    value = row.get(name)
                    result_row[name] = self._clean_agtype_value(value)
                results.append(result_row)

            return results

        except Exception as e:
            logger.error(f"Cypher execution error: {e}")
            raise  # Propagate error instead of returning empty list silently

    def _build_properties(self, props: Dict[str, Any]) -> str:
        """Build Cypher property map string."""
        parts = []

        for key, value in props.items():
            if value is None:
                continue
            if isinstance(value, str):
                parts.append(f"{key}: '{self.escape_string(value)}'")
            elif isinstance(value, bool):
                parts.append(f"{key}: {str(value).lower()}")
            elif isinstance(value, (int, float)):
                parts.append(f"{key}: {value}")
            elif isinstance(value, datetime):
                parts.append(f"{key}: '{value.isoformat()}'")
            elif isinstance(value, list):
                items = []
                for item in value:
                    if isinstance(item, str):
                        items.append(f"'{self.escape_string(item)}'")
                    else:
                        items.append(str(item))
                parts.append(f"{key}: [{', '.join(items)}]")

        return "{" + ", ".join(parts) + "}"

    def _clean_agtype_value(self, value: Any) -> Any:
        """Clean up agtype values (remove quotes from strings)."""
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip('"')
        return value

    def _parse_agtype_node(self, agtype_value: Any) -> Dict[str, Any]:
        """Parse an agtype node value into a dictionary."""
        if agtype_value is None:
            return {}

        # agtype is typically returned as a string representation
        if isinstance(agtype_value, str):
            # Parse the agtype string format
            # e.g., {"id": 123, "label": "doc", "properties": {...}}::vertex
            try:
                import json
                # Remove ::vertex suffix if present
                clean = agtype_value.split("::")[0]
                data = json.loads(clean)
                if "properties" in data:
                    return data["properties"]
                return data
            except (json.JSONDecodeError, ValueError):
                return {"raw": agtype_value}

        return {"raw": str(agtype_value)}

    def _extract_columns_from_query(self, query: str) -> List[str]:
        """Extract column names from RETURN clause."""
        import re

        # Find RETURN clause
        match = re.search(r'RETURN\s+(.+?)(?:ORDER|LIMIT|$)', query, re.IGNORECASE | re.DOTALL)
        if not match:
            return ["result"]

        return_clause = match.group(1).strip()

        # Parse column aliases
        columns = []
        for part in return_clause.split(","):
            part = part.strip()
            # Check for AS alias
            if " as " in part.lower():
                alias = part.lower().split(" as ")[-1].strip()
                columns.append(alias)
            else:
                # Use the expression itself (simplified)
                col = re.sub(r'[^a-zA-Z0-9_]', '_', part)
                columns.append(col)

        return columns if columns else ["result"]
