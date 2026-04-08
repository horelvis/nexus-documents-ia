"""
Shared fixtures for knowledge-tree-service tests.

Requires a running FalkorDB instance (docker-compose.onpremise.yml).
"""

import os

import pytest
import pytest_asyncio

# Set test env vars before importing app modules
os.environ.setdefault("FALKORDB_HOST", "localhost")
os.environ.setdefault("FALKORDB_PORT", "6380")
os.environ.setdefault("FALKORDB_GRAPH_NAME", "test_knowledge_graph")
os.environ.setdefault("FALKORDB_PASSWORD", "")
os.environ.setdefault("RAG_KNOWLEDGE_GRAPH_ENABLED", "true")
os.environ.setdefault("ACTIVE_SECTOR", "legal")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
# Keep AGE settings to avoid import errors (not used in FalkorDB tests)
os.environ.setdefault("DATABASE_URL", "postgresql://nexus_user:nexus_password@localhost:5432/nouxcube")


@pytest_asyncio.fixture
async def falkordb_client():
    """Per-test FalkorDB client — fresh connection for each test."""
    from app.services.falkordb_client import FalkorDBClient

    client = FalkorDBClient()
    await client.initialize()

    # Clean graph before test
    if client._graph:
        try:
            await client._graph.query("MATCH (n) DETACH DELETE n")
        except Exception:
            pass

    # Bootstrap schema so indexes are available for all tests
    await client.bootstrap_schema()

    yield client

    # Cleanup after test
    if client._graph:
        try:
            await client._graph.query("MATCH (n) DETACH DELETE n")
        except Exception:
            pass
    await client.close()
