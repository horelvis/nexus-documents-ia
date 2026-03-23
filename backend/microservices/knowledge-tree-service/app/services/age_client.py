"""
Minimal Apache AGE client for Knowledge Tree Service.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
RETRY_BASE_DELAY = 2.0


class AGEClient:
    """Minimal AGE client with asyncpg pool and cypher execution."""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        if not settings.rag_knowledge_graph_enabled:
            logger.info("ℹ️ Knowledge graph disabled by configuration")
            self._initialized = True
            return

        db_url = settings.database_url
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._pool = await asyncpg.create_pool(
                    db_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=30,
                )
                self._initialized = True
                logger.info("✅ AGE client initialized")
                return
            except (
                asyncpg.exceptions.CannotConnectNowError,
                ConnectionRefusedError,
                OSError,
            ) as e:
                delay = RETRY_BASE_DELAY * attempt
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"⏳ Database not ready (attempt {attempt}/{MAX_RETRIES}): {e} "
                        f"— retrying in {delay:.0f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"❌ Could not connect to database after {MAX_RETRIES} attempts: {e}"
                    )
                    raise

    @asynccontextmanager
    async def _get_connection(self):
        if not self._pool:
            raise RuntimeError("AGE client not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute("SET search_path = ag_catalog, \"$user\", public;")
            yield conn

    async def execute_cypher(self, query: str) -> List[Dict[str, Any]]:
        """Execute a cypher query and return rows as dicts."""
        if not settings.rag_knowledge_graph_enabled:
            return []
        await self.initialize()
        if not self._pool:
            return []
        async with self._get_connection() as conn:
            records = await conn.fetch(query)
            return [dict(r) for r in records]


age_client = AGEClient()
