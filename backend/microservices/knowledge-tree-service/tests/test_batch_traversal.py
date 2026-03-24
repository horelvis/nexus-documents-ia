"""Tests for batch graph traversal optimizations."""

import pytest
import pytest_asyncio
from app.services.falkordb_client import QueryCounter


@pytest.mark.asyncio
class TestQueryCounter:
    """Verify query counting infrastructure."""

    async def test_counter_tracks_queries(self, falkordb_client):
        async with QueryCounter() as counter:
            await falkordb_client.execute_cypher("RETURN 1 AS n")
            await falkordb_client.execute_cypher("RETURN 2 AS n")
            assert counter.count == 2

    async def test_counter_zero_without_queries(self, falkordb_client):
        async with QueryCounter() as counter:
            assert counter.count == 0

    async def test_counter_isolated_between_contexts(self, falkordb_client):
        async with QueryCounter() as outer:
            await falkordb_client.execute_cypher("RETURN 1 AS n")
            async with QueryCounter() as inner:
                await falkordb_client.execute_cypher("RETURN 2 AS n")
                assert inner.count == 1
            assert outer.count == 2
