"""
LangGraph PostgresSaver Checkpointer + AsyncPostgresStore — Phase 1a/2

Provides:
    1. AsyncPostgresSaver — graph checkpointer for conversation continuity
    2. AsyncPostgresStore — cross-thread memory (user facts, preferences)

Both share the same psycopg3 connection pool for efficiency.

Usage:
    from app.core.checkpointer import get_checkpointer, get_store, close_checkpointer

    # At graph compilation:
    checkpointer = await get_checkpointer()
    store = await get_store()
    graph = workflow.compile(checkpointer=checkpointer, store=store)

    # Cross-thread memory (any module):
    store = await get_store()
    await store.aput(("user_facts", user_id), "identity/name", {"value": "Carlos"})
    item = await store.aget(("user_facts", user_id), "identity/name")

    # At shutdown:
    await close_checkpointer()

Config:
    LANGGRAPH_CHECKPOINTER_ENABLED=true  (default)
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
"""

import logging
from typing import Optional

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from app.core.config import settings

logger = logging.getLogger(__name__)

_checkpointer: Optional[AsyncPostgresSaver] = None
_store: Optional[AsyncPostgresStore] = None
_pool: Optional[AsyncConnectionPool] = None


def _get_psycopg_conninfo() -> str:
    """Convert DATABASE_URL to psycopg3 connection string.

    DATABASE_URL uses SQLAlchemy format: postgresql+asyncpg://user:pass@host:port/db
    psycopg3 needs: postgresql://user:pass@host:port/db
    """
    url = settings.database_url
    # Strip SQLAlchemy driver prefix
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    # Already standard format or uses individual settings
    if url.startswith("postgresql://"):
        return url
    # Fallback: build from individual settings
    return (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


async def _ensure_pool() -> AsyncConnectionPool:
    """Ensure the shared psycopg3 connection pool is open."""
    global _pool
    if _pool is None:
        conninfo = _get_psycopg_conninfo()
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await _pool.open()
        logger.info("LangGraph psycopg3 pool opened")
    return _pool


async def get_checkpointer() -> Optional[AsyncPostgresSaver]:
    """Get or create the singleton AsyncPostgresSaver.

    Returns None if checkpointer is disabled via config.
    Creates tables on first call (idempotent).
    """
    global _checkpointer

    if not settings.langgraph_checkpointer_enabled:
        return None

    if _checkpointer is not None:
        return _checkpointer

    pool = await _ensure_pool()
    logger.info("Initializing LangGraph PostgresSaver checkpointer")

    _checkpointer = AsyncPostgresSaver(pool)
    await _checkpointer.setup()

    logger.info("LangGraph PostgresSaver ready (tables created)")
    return _checkpointer


async def get_store() -> Optional[AsyncPostgresStore]:
    """Get or create the singleton AsyncPostgresStore for cross-thread memory.

    Returns None if checkpointer is disabled via config (Store piggybacks
    on the same infrastructure flag since both use the same pool).

    Creates store tables on first call (idempotent).
    """
    global _store

    if not settings.langgraph_checkpointer_enabled:
        return None

    if _store is not None:
        return _store

    pool = await _ensure_pool()
    logger.info("Initializing LangGraph AsyncPostgresStore")

    _store = AsyncPostgresStore(pool)
    await _store.setup()

    logger.info("LangGraph Store ready (tables created)")
    return _store


async def close_checkpointer() -> None:
    """Close the checkpointer + store connection pool. Call on app shutdown."""
    global _checkpointer, _store, _pool

    if _pool is not None:
        await _pool.close()
        logger.info("LangGraph psycopg3 pool closed")

    _checkpointer = None
    _store = None
    _pool = None
