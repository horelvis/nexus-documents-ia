"""
Tests for RLM (Recursive Language Models) Processor — 3-Node Pipeline

Covers:
1. Disabled passthrough (feature flag off)
2. Below threshold passthrough
3. Above threshold activation with mocked LLM (plan → map → reduce)
4. Chunk documents function
5. Recursive aggregation with depth control
6. Graph routing (rlm_plan → rlm_map | plan | synthesize)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.agents.langgraph.nodes.rlm_processor import (
    _estimate_tokens,
    _chunk_documents,
    _process_chunk,
    _aggregate_results,
    rlm_plan_node,
    rlm_map_node,
    rlm_reduce_node,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

@dataclass
class MockLLMResponse:
    content: str


def _make_docs(n: int, content_size: int = 4000) -> list:
    """Create n mock documents with specified char content size."""
    return [
        {
            "id": f"doc-{i}",
            "title": f"Document {i}",
            "content": f"Content of document {i}. " * (content_size // 25),
            "score": 0.9 - i * 0.1,
        }
        for i in range(n)
    ]


def _make_state(docs=None, query="Test query", **overrides) -> dict:
    """Create a minimal RAGState dict for testing."""
    state = {
        "query": query,
        "retrieved_docs": docs or [],
        "agent_results": {},
        "metadata": {},
        "rlm_chunks": [],
        "rlm_cache_key": "",
        "rlm_sub_results": [],
        "rlm_relevant_count": 0,
        "rlm_total_tokens": 0,
        "rlm_activated": False,
    }
    state.update(overrides)
    return state


# ─── Test: _estimate_tokens ─────────────────────────────────────────────────

def test_estimate_tokens():
    assert _estimate_tokens("") == 0
    assert _estimate_tokens("abcd") == 1
    assert _estimate_tokens("a" * 100) == 25


# ─── Test 1: RLM disabled passthrough ───────────────────────────────────────

@pytest.mark.asyncio
async def test_rlm_disabled_passthrough():
    """When RLM_ENABLED=false, plan node returns passthrough."""
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.rlm_enabled = False

        state = _make_state(docs=_make_docs(5, content_size=80000))
        result = await rlm_plan_node(state)

        assert result["rlm_activated"] is False
        assert "agent_results" not in result


# ─── Test 2: Below threshold passthrough ─────────────────────────────────────

@pytest.mark.asyncio
async def test_rlm_below_threshold():
    """When content is below token threshold, plan node passes through."""
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.rlm_enabled = True
        mock_settings.rlm_token_threshold = 16000

        # Small docs — well below 16k tokens
        state = _make_state(docs=_make_docs(2, content_size=1000))
        result = await rlm_plan_node(state)

        assert result["rlm_activated"] is False
        assert result.get("rlm_total_tokens", 0) > 0


# ─── Test 3: Above threshold — full plan → map → reduce pipeline ────────────

@pytest.mark.asyncio
async def test_rlm_above_threshold_pipeline():
    """When content exceeds threshold, plan→map→reduce pipeline produces results."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MockLLMResponse(content="Synthesized answer from RLM")
    )

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.rlm_enabled = True
        mock_settings.rlm_token_threshold = 100  # Very low threshold
        mock_settings.rlm_chunk_size = 200
        mock_settings.rlm_chunk_overlap = 50
        mock_settings.rlm_max_depth = 2
        mock_settings.rlm_max_chunks = 10
        mock_settings.llm_max_concurrent = 4
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379

        with patch(
            "app.agents.llm_client.get_llm_client",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ), patch(
            "app.agents.langgraph.nodes.rlm_processor._get_cached_result",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.agents.langgraph.nodes.rlm_processor._set_cached_result",
            new_callable=AsyncMock,
        ):
            # Step 1: Plan
            state = _make_state(docs=_make_docs(5, content_size=4000))
            plan_result = await rlm_plan_node(state)

            assert plan_result["rlm_activated"] is True
            assert len(plan_result["rlm_chunks"]) > 0
            assert plan_result["rlm_cache_key"] != ""

            # Step 2: Map
            map_state = {**state, **plan_result}
            map_result = await rlm_map_node(map_state)

            assert "rlm_sub_results" in map_result
            assert "rlm_relevant_count" in map_result

            # Step 3: Reduce
            reduce_state = {**map_state, **map_result}
            reduce_result = await rlm_reduce_node(reduce_state)

            assert "agent_results" in reduce_result
            assert "rlm_agent" in reduce_result["agent_results"]
            assert reduce_result["agent_results"]["rlm_agent"]["output"] == "Synthesized answer from RLM"
            assert mock_llm.chat.call_count > 0


# ─── Test 4: _chunk_documents ────────────────────────────────────────────────

def test_chunk_documents():
    """Verify chunking splits content correctly."""
    docs = _make_docs(3, content_size=8000)

    chunks = _chunk_documents(docs, chunk_size=1000, overlap=100, max_chunks=20)

    assert len(chunks) > 1
    # Each chunk should be non-empty
    for chunk in chunks:
        assert len(chunk) > 0

    # Total content should be covered
    total_content = " ".join(doc["content"] for doc in docs)
    total_chunk_chars = sum(len(c) for c in chunks)
    # With overlap, total chars in chunks >= original (minus some trimming)
    assert total_chunk_chars > len(total_content) * 0.5


def test_chunk_documents_empty():
    """Empty docs produce no chunks."""
    chunks = _chunk_documents([], chunk_size=1000, overlap=100, max_chunks=20)
    assert chunks == []


def test_chunk_documents_max_limit():
    """Respects max_chunks limit."""
    docs = _make_docs(10, content_size=10000)
    chunks = _chunk_documents(docs, chunk_size=500, overlap=50, max_chunks=3)
    assert len(chunks) <= 3


# ─── Test 5: _aggregate_results recursive ────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_recursive():
    """Verify aggregation works and respects max_depth."""
    call_count = 0

    async def mock_chat(messages, temperature=0.3, max_tokens=2048):
        nonlocal call_count
        call_count += 1
        return MockLLMResponse(content=f"Aggregated result (call {call_count})")

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    sub_results = ["Result A " * 100, "Result B " * 100, "Result C " * 100]

    result = await _aggregate_results(
        mock_llm, "test query", sub_results,
        chunk_size=5000,  # Large enough to not re-chunk
        max_depth=3,
        depth=0,
    )

    assert "Aggregated result" in result
    assert call_count >= 1


@pytest.mark.asyncio
async def test_aggregate_stops_at_max_depth():
    """Even with large content, aggregation stops at max_depth."""
    call_count = 0

    async def mock_chat(messages, temperature=0.3, max_tokens=2048):
        nonlocal call_count
        call_count += 1
        return MockLLMResponse(content=f"Final summary {call_count}")

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    # 2 sub-results: combined ~3050 tokens > chunk_size=2000, triggers recursion
    sub_results = ["Word " * 1200] * 2

    result = await _aggregate_results(
        mock_llm, "test query", sub_results,
        chunk_size=2000,  # Triggers 1 recursion then stops at max_depth
        max_depth=1,
        depth=0,
    )

    # Should eventually return something (not infinite loop)
    assert result is not None
    assert len(result) > 0


# ─── Test 6: Graph routing ──────────────────────────────────────────────────

def test_graph_routing_rlm_not_activated():
    """When rlm_activated=False, route to plan."""
    from app.agents.langgraph.graph import _route_from_rlm_plan

    state = {"rlm_activated": False}
    assert _route_from_rlm_plan(state) == "plan"


def test_graph_routing_rlm_activated_no_cache():
    """When rlm_activated=True but no cache hit, route to rlm_map."""
    from app.agents.langgraph.graph import _route_from_rlm_plan

    state = {"rlm_activated": True, "agent_results": {}}
    assert _route_from_rlm_plan(state) == "rlm_map"


def test_graph_routing_rlm_cache_hit():
    """When rlm_activated=True with cache hit, route to synthesize."""
    from app.agents.langgraph.graph import _route_from_rlm_plan

    state = {"rlm_activated": True, "agent_results": {"rlm_agent": {"output": "cached"}}}
    assert _route_from_rlm_plan(state) == "synthesize"


def test_graph_routing_rlm_missing():
    """When rlm_activated not in state, route to plan."""
    from app.agents.langgraph.graph import _route_from_rlm_plan

    state = {}
    assert _route_from_rlm_plan(state) == "plan"
