"""
Async FalkorDB client for Knowledge Tree Service.

Provides graph database operations via FalkorDB (Redis-based graph DB
with OpenCypher support). Follows the same singleton + retry pattern
as the former age_client.py (now removed) for consistency.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from falkordb.asyncio import FalkorDB as AsyncFalkorDB

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
RETRY_BASE_DELAY = 2.0


class FalkorDBClient:
    """Async FalkorDB client with retry/backoff and schema bootstrap."""

    def __init__(self):
        self._connection: Optional[AsyncFalkorDB] = None
        self._graph = None
        self._initialized = False

    async def initialize(self) -> None:
        """Create async FalkorDB connection with retry/backoff."""
        if self._initialized:
            return

        host = settings.falkordb_host
        port = settings.falkordb_port
        password = settings.falkordb_password or None
        graph_name = settings.falkordb_graph_name

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._connection = AsyncFalkorDB(
                    host=host,
                    port=port,
                    password=password,
                )
                self._graph = self._connection.select_graph(graph_name)
                # Verify connectivity with a simple query
                await self._graph.query("RETURN 1")
                self._initialized = True
                logger.info(
                    f"FalkorDB client initialized (graph={graph_name}, "
                    f"host={host}:{port})"
                )
                return
            except (
                ConnectionError,
                OSError,
            ) as e:
                delay = RETRY_BASE_DELAY * attempt
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"FalkorDB not ready (attempt {attempt}/{MAX_RETRIES}): {e} "
                        f"-- retrying in {delay:.0f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Could not connect to FalkorDB after {MAX_RETRIES} attempts: {e}"
                    )
                    raise
            except Exception as e:
                # Catch redis.exceptions.ConnectionError and similar without
                # hard-importing redis at module level
                err_type = type(e).__name__
                if "ConnectionError" in err_type or "RedisError" in err_type:
                    delay = RETRY_BASE_DELAY * attempt
                    if attempt < MAX_RETRIES:
                        logger.warning(
                            f"FalkorDB not ready (attempt {attempt}/{MAX_RETRIES}): {e} "
                            f"-- retrying in {delay:.0f}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Could not connect to FalkorDB after {MAX_RETRIES} attempts: {e}"
                        )
                        raise
                else:
                    raise

    async def bootstrap_schema(self) -> None:
        """Read and execute schema from knowledge_graph_schema.cypher.

        Idempotent — FalkorDB ignores duplicate index creation.
        """
        if not self._initialized or not self._graph:
            logger.warning("FalkorDB not initialized, skipping schema bootstrap")
            return

        schema_path = (
            Path(__file__).resolve().parents[2]
            / "config"
            / "graphs"
            / "knowledge_graph_schema.cypher"
        )

        if not schema_path.exists():
            logger.warning(f"Schema file not found: {schema_path}")
            return

        schema_text = schema_path.read_text(encoding="utf-8")

        # Split on semicolons, skip empty/comment-only statements
        statements = [
            stmt.strip()
            for stmt in schema_text.split(";")
            if stmt.strip() and not stmt.strip().startswith("//")
        ]

        executed = 0
        for stmt in statements:
            # Skip pure comment lines
            lines = [
                line
                for line in stmt.split("\n")
                if line.strip() and not line.strip().startswith("//")
            ]
            if not lines:
                continue

            cypher = "\n".join(lines)
            try:
                await self._graph.query(cypher)
                executed += 1
            except Exception as e:
                # Log but don't fail — indexes may already exist
                logger.debug(f"Schema statement skipped (may already exist): {e}")

        logger.info(f"FalkorDB schema bootstrap complete ({executed} statements executed)")

    async def execute_cypher(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts.

        Args:
            query: OpenCypher query string.
            params: Optional query parameters.

        Returns:
            List of dicts mapping column names to values. Empty list if
            client is not initialized.
        """
        await self.initialize()
        if not self._graph:
            return []

        try:
            result = await self._graph.query(query, params=params)
        except Exception as e:
            logger.error(f"FalkorDB query failed: {e}\nQuery: {query}")
            raise

        # Convert FalkorDB ResultSet to list of dicts
        if not result.result_set:
            return []

        headers = result.header
        rows: List[Dict[str, Any]] = []
        for record in result.result_set:
            row = {}
            for idx, value in enumerate(record):
                col_name = headers[idx][1] if isinstance(headers[idx], (list, tuple)) else str(headers[idx])
                row[col_name] = value
            rows.append(row)

        return rows

    async def close(self) -> None:
        """Close the FalkorDB connection."""
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.debug(f"Error closing FalkorDB connection: {e}")
            finally:
                self._connection = None
                self._graph = None
                self._initialized = False
            logger.info("FalkorDB connection closed")


# Module-level singleton
falkordb_client = FalkorDBClient()
