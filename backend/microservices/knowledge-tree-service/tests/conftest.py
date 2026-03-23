"""
Shared fixtures for knowledge-tree-service tests.

Requires a running FalkorDB instance (docker-compose.onpremise.yml).
"""

import asyncio
import os
from typing import AsyncGenerator

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
os.environ.setdefault("DATABASE_URL", "postgresql://nexus_user:nexus_password@localhost:5432/nexus_db")


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def falkordb_client():
    """Session-scoped FalkorDB client connected to test graph."""
    from app.services.falkordb_client import FalkorDBClient

    client = FalkorDBClient()
    await client.initialize()
    yield client
    # Cleanup: drop the test graph
    if client._graph:
        try:
            await client._graph.delete()
        except Exception:
            pass
    await client.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_graph(falkordb_client):
    """Clean the test graph before each test."""
    if falkordb_client._graph:
        try:
            # Delete all nodes and relationships
            await falkordb_client.execute_cypher("MATCH (n) DETACH DELETE n")
        except Exception:
            pass
    yield
