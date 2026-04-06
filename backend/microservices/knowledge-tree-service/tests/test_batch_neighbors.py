"""Tests for TripleQuery.batch_neighbors — BFS subgraph traversal."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.triple_query import TripleQuery


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.execute_cypher = AsyncMock(return_value=[])
    return client


@pytest.fixture
def tq(mock_client):
    return TripleQuery(mock_client)


@pytest.mark.asyncio
async def test_batch_neighbors_empty_seeds(tq):
    """Empty seed list returns empty result."""
    result = await tq.batch_neighbors(
        seed_uris=[], user="tenant-1",
    )
    assert result["edges"] == []
    assert result["entities_visited"] == 0
    assert result["hops_used"] == 0


@pytest.mark.asyncio
async def test_batch_neighbors_single_hop(tq, mock_client):
    """Single seed entity returns its direct neighbors."""
    mock_client.execute_cypher = AsyncMock(return_value=[
        {
            "subject": "nouxcube://entity/default/lgt",
            "predicate": "nouxcube://predicate/legal/regula",
            "object": "nouxcube://entity/default/irpf",
            "object_type": "node",
            "extraction_method": "relationship_extractor",
            "source_chunk": None,
        },
    ])
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/lgt"],
        user="tenant-1",
        max_hops=1,
        max_edges=150,
    )
    assert len(result["edges"]) == 1
    assert result["edges"][0]["subject"] == "nouxcube://entity/default/lgt"
    assert result["edges"][0]["predicate"] == "nouxcube://predicate/legal/regula"
    assert result["entities_visited"] >= 1
    assert result["hops_used"] == 1


@pytest.mark.asyncio
async def test_batch_neighbors_excludes_prov_predicates(tq, mock_client):
    """Edges with prov/* predicates are excluded."""
    mock_client.execute_cypher = AsyncMock(return_value=[
        {
            "subject": "nouxcube://entity/default/lgt",
            "predicate": "nouxcube://predicate/prov/generated-by",
            "object": "nouxcube://entity/default/extractor",
            "object_type": "node",
        },
        {
            "subject": "nouxcube://entity/default/lgt",
            "predicate": "nouxcube://predicate/legal/regula",
            "object": "nouxcube://entity/default/irpf",
            "object_type": "node",
        },
    ])
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/lgt"],
        user="tenant-1",
        max_hops=1,
        exclude_predicates=["prov/.*"],
    )
    assert len(result["edges"]) == 1
    assert "prov/" not in result["edges"][0]["predicate"]


@pytest.mark.asyncio
async def test_batch_neighbors_respects_max_edges(tq, mock_client):
    """Stop collecting when max_edges is reached."""
    edges = [
        {
            "subject": f"nouxcube://entity/default/e{i}",
            "predicate": "nouxcube://predicate/core/related-to",
            "object": f"nouxcube://entity/default/e{i+100}",
            "object_type": "node",
        }
        for i in range(10)
    ]
    mock_client.execute_cypher = AsyncMock(return_value=edges)
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/e0"],
        user="tenant-1",
        max_hops=3,
        max_edges=5,
    )
    assert len(result["edges"]) <= 5


@pytest.mark.asyncio
async def test_batch_neighbors_multi_hop(tq, mock_client):
    """Two hops: seeds → hop1 neighbors → hop2 neighbors."""
    call_count = 0

    async def mock_cypher(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{
                "subject": "nouxcube://entity/default/a",
                "predicate": "nouxcube://predicate/core/related-to",
                "object": "nouxcube://entity/default/b",
                "object_type": "node",
            }]
        else:
            return [{
                "subject": "nouxcube://entity/default/b",
                "predicate": "nouxcube://predicate/legal/modifica",
                "object": "nouxcube://entity/default/c",
                "object_type": "node",
            }]

    mock_client.execute_cypher = AsyncMock(side_effect=mock_cypher)
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/a"],
        user="tenant-1",
        max_hops=2,
        max_edges=150,
    )
    assert len(result["edges"]) == 2
    assert result["hops_used"] == 2
