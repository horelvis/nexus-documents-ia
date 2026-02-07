"""
Tests for Stop-and-Go LangGraph — shared graph for Predictive + Verified.

Covers:
1. State: create_initial_state() defaults
2. Strategy registry: register/get + unknown mode error
3. Nodes: initialize, extract_item, search_and_evaluate, decide, synthesize
4. Graph compilation + routing logic
5. Runner SSE bridge (pending_events draining)
6. PredictiveStrategy: extract, evaluate, dedup, on_accepted/rejected, synthesize
7. VerifiedStrategy: extract, evaluate, dedup, on_accepted/rejected, synthesize
8. Service integration: analyze() and generate_verified_document() emit correct events

Run:
    cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service
    python -m pytest tests/test_stop_and_go.py -v -s
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


# ─── Helpers ────────────────────────────────────────────────────────────────

@dataclass
class MockLLMResponse:
    content: str


def _make_state(mode="predictive", **overrides) -> dict:
    """Create a minimal StopAndGoState dict for testing."""
    from app.agents.langgraph.stop_and_go.state import create_initial_state
    state = create_initial_state(
        tenant_id="test-tenant",
        query="Reclamación por accidente de tráfico",
        mode=mode,
        max_items=5,
        confidence_threshold=0.7,
    )
    state.update(overrides)
    return state


def _make_item(item_id="item-1", text="Factor de prueba", **extra):
    """Create a mock extracted item dict."""
    return {
        "id": item_id,
        "text": text,
        "type": "test_factor",
        "_raw_factor": {
            "id": item_id,
            "factor_type": "test_factor",
            "description": text,
            "legal_basis": None,
            "source_query": "test query",
            "extraction_order": 1,
            "context_document_ids": [],
            "extracted_at": "2026-01-01T00:00:00",
            "metadata": {},
        },
        "event_data": {"factor_type": "test_factor", "description": text},
        **extra,
    }


def _make_evidence(n=2):
    """Create mock evidence list."""
    return [
        {
            "document_id": f"doc-{i}",
            "document_title": f"Document {i}",
            "chunk_id": f"chunk-{i}",
            "text_excerpt": f"Evidence text {i} relevant excerpt...",
            "similarity_score": 0.85 - i * 0.05,
            "source": "internal",
        }
        for i in range(n)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# 1. State Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestStopAndGoState:

    def test_create_initial_state_defaults(self):
        """create_initial_state sets all required fields."""
        from app.agents.langgraph.stop_and_go.state import create_initial_state

        state = create_initial_state(
            tenant_id="t-1",
            query="test query",
            mode="predictive",
            max_items=10,
        )

        assert state["tenant_id"] == "t-1"
        assert state["query"] == "test query"
        assert state["mode"] == "predictive"
        assert state["max_items"] == 10
        assert state["confidence_threshold"] == 0.7  # default
        assert state["items_extracted"] == 0
        assert state["items_accepted"] == 0
        assert state["items_rejected"] == 0
        assert state["is_complete"] is False
        assert state["pending_events"] == []
        assert state["all_extracted_items"] == []
        assert state["result"] is None

    def test_create_initial_state_auto_session_id(self):
        """Session ID is auto-generated if not provided."""
        from app.agents.langgraph.stop_and_go.state import create_initial_state

        s1 = create_initial_state(tenant_id="t", query="q", mode="verified", max_items=5)
        s2 = create_initial_state(tenant_id="t", query="q", mode="verified", max_items=5)

        assert s1["session_id"] != s2["session_id"]
        assert len(s1["session_id"]) == 36  # UUID

    def test_create_initial_state_custom_params(self):
        """Custom params override defaults."""
        from app.agents.langgraph.stop_and_go.state import create_initial_state

        state = create_initial_state(
            session_id="my-session",
            tenant_id="t-2",
            query="q",
            mode="verified",
            max_items=20,
            confidence_threshold=0.9,
            uploaded_texts=[{"text": "hello"}],
            collections=["col1"],
            mode_config={"auto_correct": True},
        )

        assert state["session_id"] == "my-session"
        assert state["confidence_threshold"] == 0.9
        assert len(state["uploaded_texts"]) == 1
        assert state["collections"] == ["col1"]
        assert state["mode_config"]["auto_correct"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 2. Strategy Registry Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestStrategyRegistry:

    def test_strategies_registered_on_import(self):
        """Both strategies are registered when the package is imported."""
        from app.agents.langgraph.stop_and_go.strategy import get_strategy

        predictive = get_strategy("predictive")
        verified = get_strategy("verified")

        assert predictive.mode == "predictive"
        assert verified.mode == "verified"

    def test_unknown_mode_raises(self):
        """get_strategy raises ValueError for unknown mode."""
        from app.agents.langgraph.stop_and_go.strategy import get_strategy

        with pytest.raises(ValueError, match="Unknown stop-and-go mode"):
            get_strategy("nonexistent")

    def test_register_custom_strategy(self):
        """Can register a custom strategy."""
        from app.agents.langgraph.stop_and_go.strategy import register_strategy, get_strategy, _strategies

        class FakeStrategy:
            mode = "test_mode"

        register_strategy("test_mode", FakeStrategy())
        assert get_strategy("test_mode").mode == "test_mode"

        # Cleanup
        del _strategies["test_mode"]


# ═════════════════════════════════════════════════════════════════════════════
# 3. Node Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestInitializeNode:

    @pytest.mark.asyncio
    async def test_initialize_loads_source_context(self):
        """initialize_node calls _get_source_context and returns it."""
        from app.agents.langgraph.stop_and_go.nodes.initialize import initialize_node

        state = _make_state(uploaded_texts=[{"filename": "test.pdf", "text": "Hello world content"}])

        mock_strategy = AsyncMock()
        mock_strategy.initialize = AsyncMock()

        with patch("app.agents.langgraph.stop_and_go.nodes.initialize.get_strategy", return_value=mock_strategy):
            result = await initialize_node(state)

        assert "source_context" in result
        assert "Hello world content" in result["source_context"]
        assert len(result["pending_events"]) == 1
        assert result["pending_events"][0]["event_type"] == "progress"

    @pytest.mark.asyncio
    async def test_initialize_weaviate_fallback(self):
        """When no uploads, tries Weaviate (mocked to fail gracefully)."""
        from app.agents.langgraph.stop_and_go.nodes.initialize import initialize_node

        state = _make_state(uploaded_texts=[])

        mock_strategy = AsyncMock()
        mock_strategy.initialize = AsyncMock()

        with patch("app.agents.langgraph.stop_and_go.nodes.initialize.get_strategy", return_value=mock_strategy), \
             patch("app.agents.langgraph.stop_and_go.nodes.initialize.httpx.AsyncClient") as mock_client:
            # Simulate Weaviate failure
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

            result = await initialize_node(state)

        # Should still return a result with empty context
        assert "source_context" in result
        assert result["source_context"] == ""


class TestExtractItemNode:

    @pytest.mark.asyncio
    async def test_extract_item_success(self):
        """extract_item_node returns item and increments counter."""
        from app.agents.langgraph.stop_and_go.nodes.extract_item import extract_item_node

        state = _make_state(source_context="some context", items_extracted=0)
        item = _make_item()

        mock_strategy = AsyncMock()
        mock_strategy.extract_item = AsyncMock(return_value=item)
        mock_strategy.is_duplicate = MagicMock(return_value=False)

        with patch("app.agents.langgraph.stop_and_go.nodes.extract_item.get_strategy", return_value=mock_strategy):
            result = await extract_item_node(state)

        assert result["current_item"]["id"] == "item-1"
        assert result["items_extracted"] == 1
        assert result["duplicate_streak"] == 0
        assert len(result["pending_events"]) == 1

    @pytest.mark.asyncio
    async def test_extract_item_duplicate_detected(self):
        """Duplicate items are skipped, streak incremented."""
        from app.agents.langgraph.stop_and_go.nodes.extract_item import extract_item_node

        state = _make_state(items_extracted=2, duplicate_streak=0)
        item = _make_item()

        mock_strategy = AsyncMock()
        mock_strategy.extract_item = AsyncMock(return_value=item)
        mock_strategy.is_duplicate = MagicMock(return_value=True)

        with patch("app.agents.langgraph.stop_and_go.nodes.extract_item.get_strategy", return_value=mock_strategy):
            result = await extract_item_node(state)

        assert result["current_item"] is None
        assert result["duplicate_streak"] == 1
        assert result["items_extracted"] == 3

    @pytest.mark.asyncio
    async def test_extract_item_consecutive_dups_complete(self):
        """2 consecutive duplicates → is_complete=True."""
        from app.agents.langgraph.stop_and_go.nodes.extract_item import extract_item_node

        state = _make_state(items_extracted=3, duplicate_streak=1)
        item = _make_item()

        mock_strategy = AsyncMock()
        mock_strategy.extract_item = AsyncMock(return_value=item)
        mock_strategy.is_duplicate = MagicMock(return_value=True)

        with patch("app.agents.langgraph.stop_and_go.nodes.extract_item.get_strategy", return_value=mock_strategy):
            result = await extract_item_node(state)

        assert result["is_complete"] is True
        assert result["duplicate_streak"] == 2

    @pytest.mark.asyncio
    async def test_extract_item_error_marks_complete(self):
        """Extraction failure → is_complete=True + error event."""
        from app.agents.langgraph.stop_and_go.nodes.extract_item import extract_item_node

        state = _make_state()

        mock_strategy = AsyncMock()
        mock_strategy.extract_item = AsyncMock(side_effect=Exception("LLM timeout"))

        with patch("app.agents.langgraph.stop_and_go.nodes.extract_item.get_strategy", return_value=mock_strategy):
            result = await extract_item_node(state)

        assert result["is_complete"] is True
        assert result["pending_events"][0]["event_type"] == "error"


class TestSearchAndEvaluateNode:

    @pytest.mark.asyncio
    async def test_accepted_item(self):
        """Accepted item increments items_accepted."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import search_and_evaluate_node

        item = _make_item()
        state = _make_state(current_item=item, items_accepted=0)

        mock_strategy = AsyncMock()
        mock_strategy.evaluate_item = AsyncMock(return_value={"status": "accepted", "confidence": 0.9})
        mock_strategy.on_accepted = AsyncMock(return_value={
            "event_type": "factor_weighted",
            "factor_id": "item-1",
            "data": {"weight": 0.8},
        })

        with patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate.get_strategy", return_value=mock_strategy), \
             patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate._search_evidence", new_callable=AsyncMock, return_value=_make_evidence()):
            result = await search_and_evaluate_node(state)

        assert result["items_accepted"] == 1
        assert len(result["pending_events"]) == 2  # verification_started + factor_weighted
        assert result["all_extracted_items"][0]["id"] == "item-1"

    @pytest.mark.asyncio
    async def test_rejected_item(self):
        """Rejected item increments items_rejected."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import search_and_evaluate_node

        item = _make_item()
        state = _make_state(current_item=item, items_rejected=0)

        mock_strategy = AsyncMock()
        mock_strategy.evaluate_item = AsyncMock(return_value={"status": "rejected", "reason": "No evidence"})
        mock_strategy.on_rejected = AsyncMock(return_value={
            "event_type": "factor_rejected",
            "factor_id": "item-1",
            "data": {"reason": "No evidence"},
        })

        with patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate.get_strategy", return_value=mock_strategy), \
             patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate._search_evidence", new_callable=AsyncMock, return_value=[]):
            result = await search_and_evaluate_node(state)

        assert result["items_rejected"] == 1

    @pytest.mark.asyncio
    async def test_corrected_item(self):
        """Corrected item increments items_corrected."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import search_and_evaluate_node

        item = _make_item()
        state = _make_state(current_item=item, items_corrected=0, mode="verified")

        mock_strategy = AsyncMock()
        mock_strategy.evaluate_item = AsyncMock(return_value={"status": "corrected", "confidence": 0.75})
        mock_strategy.on_accepted = AsyncMock(return_value={
            "event_type": "claim_corrected",
            "claim_id": "item-1",
            "data": {"corrected_text": "fixed claim"},
        })

        with patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate.get_strategy", return_value=mock_strategy), \
             patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate._search_evidence", new_callable=AsyncMock, return_value=_make_evidence()):
            result = await search_and_evaluate_node(state)

        assert result["items_corrected"] == 1

    @pytest.mark.asyncio
    async def test_null_item_passthrough(self):
        """If current_item is None (dup skip), returns empty dict."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import search_and_evaluate_node

        state = _make_state(current_item=None)
        result = await search_and_evaluate_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_sources_map_collected(self):
        """Evidence sources are collected in sources_map."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import search_and_evaluate_node

        item = _make_item()
        state = _make_state(current_item=item, sources_map={})

        evidence = _make_evidence(2)

        mock_strategy = AsyncMock()
        mock_strategy.evaluate_item = AsyncMock(return_value={"status": "accepted", "confidence": 0.9})
        mock_strategy.on_accepted = AsyncMock(return_value={"event_type": "ok", "data": {}})

        with patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate.get_strategy", return_value=mock_strategy), \
             patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate._search_evidence", new_callable=AsyncMock, return_value=evidence):
            result = await search_and_evaluate_node(state)

        assert "doc-0" in result["sources_map"]
        assert "doc-1" in result["sources_map"]


class TestDecideNode:

    @pytest.mark.asyncio
    async def test_already_complete(self):
        """If is_complete is already True, just increments step."""
        from app.agents.langgraph.stop_and_go.nodes.decide import decide_node

        state = _make_state(is_complete=True, current_step=2)
        result = await decide_node(state)

        assert result["current_step"] == 3

    @pytest.mark.asyncio
    async def test_max_items_reached(self):
        """Reaching max_items → is_complete=True."""
        from app.agents.langgraph.stop_and_go.nodes.decide import decide_node

        state = _make_state(max_items=5, items_extracted=5)
        result = await decide_node(state)
        assert result["is_complete"] is True

    @pytest.mark.asyncio
    async def test_early_exit_3_rejections(self):
        """3+ rejections with 0 accepted → stop."""
        from app.agents.langgraph.stop_and_go.nodes.decide import decide_node

        state = _make_state(items_rejected=3, items_accepted=0)
        result = await decide_node(state)
        assert result["is_complete"] is True

    @pytest.mark.asyncio
    async def test_no_early_exit_with_accepts(self):
        """3 rejections but 1+ accepted → continue."""
        from app.agents.langgraph.stop_and_go.nodes.decide import decide_node

        state = _make_state(items_rejected=3, items_accepted=1, items_extracted=4)

        mock_strategy = AsyncMock()
        mock_strategy.check_completion = AsyncMock(return_value=False)

        with patch("app.agents.langgraph.stop_and_go.nodes.decide.get_strategy", return_value=mock_strategy):
            result = await decide_node(state)

        assert result["is_complete"] is False

    @pytest.mark.asyncio
    async def test_llm_completion_check_after_3_accepted(self):
        """LLM completion is called only when 3+ items accepted."""
        from app.agents.langgraph.stop_and_go.nodes.decide import decide_node

        state = _make_state(items_accepted=3, items_extracted=4, source_context="ctx")

        mock_strategy = AsyncMock()
        mock_strategy.check_completion = AsyncMock(return_value=True)

        with patch("app.agents.langgraph.stop_and_go.nodes.decide.get_strategy", return_value=mock_strategy):
            result = await decide_node(state)

        assert result["is_complete"] is True
        mock_strategy.check_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_when_not_complete(self):
        """Normal case: not complete → is_complete=False."""
        from app.agents.langgraph.stop_and_go.nodes.decide import decide_node

        state = _make_state(items_accepted=1, items_rejected=0, items_extracted=2)
        result = await decide_node(state)
        assert result["is_complete"] is False


class TestSynthesizeNode:

    @pytest.mark.asyncio
    async def test_synthesize_returns_result(self):
        """synthesize_node calls strategy and returns result + completion event."""
        from app.agents.langgraph.stop_and_go.nodes.synthesize import synthesize_node

        state = _make_state()
        mock_result = {"session_id": "s1", "probability": 0.75}

        mock_strategy = AsyncMock()
        mock_strategy.synthesize = AsyncMock(return_value=mock_result)

        with patch("app.agents.langgraph.stop_and_go.nodes.synthesize.get_strategy", return_value=mock_strategy):
            result = await synthesize_node(state)

        assert result["result"] == mock_result
        assert len(result["pending_events"]) == 1
        assert result["pending_events"][0]["event_type"] == "predictive_complete"
        assert result["pending_events"][0]["progress_percent"] == 100

    @pytest.mark.asyncio
    async def test_synthesize_error_handling(self):
        """Synthesis failure returns error event."""
        from app.agents.langgraph.stop_and_go.nodes.synthesize import synthesize_node

        state = _make_state()

        mock_strategy = AsyncMock()
        mock_strategy.synthesize = AsyncMock(side_effect=Exception("Synthesis failed"))

        with patch("app.agents.langgraph.stop_and_go.nodes.synthesize.get_strategy", return_value=mock_strategy):
            result = await synthesize_node(state)

        assert "error" in result["result"]
        assert result["pending_events"][0]["event_type"] == "error"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Graph Compilation Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestGraphCompilation:

    def test_graph_compiles(self):
        """Graph compiles without errors."""
        from app.agents.langgraph.stop_and_go.graph import create_stop_and_go_graph

        graph = create_stop_and_go_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """Graph contains all 5 nodes."""
        from app.agents.langgraph.stop_and_go.graph import create_stop_and_go_graph

        graph = create_stop_and_go_graph()

        # LangGraph compiled graph exposes nodes via .nodes
        node_names = set(graph.nodes.keys())
        expected = {"initialize", "extract_item", "search_and_evaluate", "decide", "synthesize"}
        # __start__ and __end__ are internal LangGraph nodes
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"

    def test_route_from_decide_complete(self):
        """Routing: is_complete=True → synthesize."""
        from app.agents.langgraph.stop_and_go.graph import _route_from_decide

        assert _route_from_decide({"is_complete": True}) == "synthesize"

    def test_route_from_decide_continue(self):
        """Routing: is_complete=False → extract_item."""
        from app.agents.langgraph.stop_and_go.graph import _route_from_decide

        assert _route_from_decide({"is_complete": False}) == "extract_item"
        assert _route_from_decide({}) == "extract_item"  # default

    def test_singleton_graph(self):
        """get_stop_and_go_graph returns the same instance."""
        from app.agents.langgraph.stop_and_go.graph import get_stop_and_go_graph

        g1 = get_stop_and_go_graph()
        g2 = get_stop_and_go_graph()
        assert g1 is g2


# ═════════════════════════════════════════════════════════════════════════════
# 5. Runner SSE Bridge Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestRunner:

    @pytest.mark.asyncio
    async def test_runner_drains_new_events_only(self):
        """Runner only yields new events, not previously seen ones."""
        from app.agents.langgraph.stop_and_go.runner import stream_stop_and_go

        # Mock graph that yields 3 snapshots with accumulating events
        snapshots = [
            {"pending_events": [{"event_type": "e1"}]},
            {"pending_events": [{"event_type": "e1"}, {"event_type": "e2"}]},
            {"pending_events": [{"event_type": "e1"}, {"event_type": "e2"}, {"event_type": "e3"}]},
        ]

        async def mock_astream(state, config, stream_mode):
            for s in snapshots:
                yield s

        mock_graph = MagicMock()
        mock_graph.astream = mock_astream

        events = []
        async for event in stream_stop_and_go(mock_graph, {}):
            events.append(event)

        # Should yield exactly 3 events, one from each snapshot
        assert len(events) == 3
        assert events[0]["event_type"] == "e1"
        assert events[1]["event_type"] == "e2"
        assert events[2]["event_type"] == "e3"

    @pytest.mark.asyncio
    async def test_runner_handles_empty_events(self):
        """Runner handles snapshots with no events gracefully."""
        from app.agents.langgraph.stop_and_go.runner import stream_stop_and_go

        snapshots = [
            {"pending_events": []},
            {"pending_events": [{"event_type": "e1"}]},
            {},  # no pending_events key
        ]

        async def mock_astream(state, config, stream_mode):
            for s in snapshots:
                yield s

        mock_graph = MagicMock()
        mock_graph.astream = mock_astream

        events = []
        async for event in stream_stop_and_go(mock_graph, {}):
            events.append(event)

        assert len(events) == 1
        assert events[0]["event_type"] == "e1"


# ═════════════════════════════════════════════════════════════════════════════
# 6. Shared _search_evidence Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestSearchEvidence:

    @pytest.mark.asyncio
    async def test_search_evidence_weaviate(self):
        """_search_evidence returns Weaviate results filtered by similarity."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import _search_evidence

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"document_id": "d1", "title": "T1", "content": "text", "distance": 0.2},
                {"document_id": "d2", "title": "T2", "content": "text", "distance": 0.8},  # too far
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate.httpx.AsyncClient", return_value=mock_client):
            evidence = await _search_evidence(
                query_text="test query",
                tenant_id="test-tenant",
                collections=["my_collection"],
                uploaded_texts=[],
                mode_config={},
            )

        # Only doc d1 should pass (similarity=0.8 >= 0.60)
        assert len(evidence) == 1
        assert evidence[0]["document_id"] == "d1"
        assert evidence[0]["similarity_score"] == 0.8

    @pytest.mark.asyncio
    async def test_search_evidence_rlm_fallback(self):
        """Falls back to RLM when Weaviate returns nothing."""
        from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import _search_evidence

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        rlm_evidence = [{"document_id": "upload-1", "text_excerpt": "uploaded text", "source": "uploaded"}]

        with patch("app.agents.langgraph.stop_and_go.nodes.search_and_evaluate.httpx.AsyncClient", return_value=mock_client), \
             patch("app.services.verified_generation.service._rlm_filter_evidence", new_callable=AsyncMock, return_value=rlm_evidence):
            evidence = await _search_evidence(
                query_text="test",
                tenant_id="t",
                collections=[],
                uploaded_texts=[{"text": "something"}],
                mode_config={},
            )

        assert len(evidence) == 1
        assert evidence[0]["source"] == "uploaded"


# ═════════════════════════════════════════════════════════════════════════════
# 7. PredictiveStrategy Unit Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestPredictiveStrategy:

    def test_mode_property(self):
        from app.agents.langgraph.stop_and_go.strategies.predictive import PredictiveStrategy
        assert PredictiveStrategy().mode == "predictive"

    def test_is_duplicate_no_previous(self):
        """No previous items → not a duplicate."""
        from app.agents.langgraph.stop_and_go.strategies.predictive import PredictiveStrategy

        strategy = PredictiveStrategy()
        item = _make_item(text="Un factor completamente nuevo sobre responsabilidad civil extracontractual")
        state = _make_state(all_extracted_items=[])

        assert strategy.is_duplicate(item, state) is False

    def test_is_duplicate_detected(self):
        """High word overlap → duplicate detected."""
        from app.agents.langgraph.stop_and_go.strategies.predictive import PredictiveStrategy

        strategy = PredictiveStrategy()
        existing = _make_item(item_id="old", text="Factor de responsabilidad civil por negligencia médica")
        item = _make_item(text="Factor de responsabilidad civil por negligencia médica grave")
        state = _make_state(all_extracted_items=[existing])

        assert strategy.is_duplicate(item, state) is True


# ═════════════════════════════════════════════════════════════════════════════
# 8. VerifiedStrategy Unit Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestVerifiedStrategy:

    def test_mode_property(self):
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy
        assert VerifiedStrategy().mode == "verified"

    def test_is_duplicate_no_previous(self):
        """No previous items → not a duplicate."""
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy

        strategy = VerifiedStrategy()
        item = {"text": "El contrato establece una vigencia de 24 meses desde enero 2024"}
        state = {"all_extracted_items": []}

        assert strategy.is_duplicate(item, state) is False

    def test_is_duplicate_detected(self):
        """High word overlap → duplicate detected."""
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy

        strategy = VerifiedStrategy()
        existing = {"text": "El contrato establece una vigencia de 24 meses desde enero 2024"}
        item = {"text": "El contrato establece una vigencia de 24 meses desde febrero 2024"}
        state = {"all_extracted_items": [existing]}

        assert strategy.is_duplicate(item, state) is True

    def test_is_duplicate_short_text_skipped(self):
        """Very short texts are never considered duplicates."""
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy

        strategy = VerifiedStrategy()
        item = {"text": "sí"}
        state = {"all_extracted_items": [{"text": "sí"}]}

        assert strategy.is_duplicate(item, state) is False

    @pytest.mark.asyncio
    async def test_llm_evaluate_claim_success(self):
        """LLM evaluation parses JSON correctly."""
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy

        strategy = VerifiedStrategy()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MockLLMResponse(
            '{"supported": true, "confidence": 0.88, "reason": "evidencia clara", "correction": null}'
        ))

        mock_prompt_client = AsyncMock()
        mock_prompt_client.get_prompt = AsyncMock(return_value=None)

        with patch("app.services.langfuse_prompt_client.get_langfuse_prompt_client", return_value=mock_prompt_client), \
             patch("app.agents.llm_client.get_llm_client", new_callable=AsyncMock, return_value=mock_llm):
            result = await strategy._llm_evaluate_claim(
                "El contrato es de 24 meses",
                _make_evidence(1),
            )

        assert result["supported"] is True
        assert result["confidence"] == 0.88
        assert result["correction"] is None

    @pytest.mark.asyncio
    async def test_llm_evaluate_claim_with_think_tags(self):
        """LLM evaluation strips <think> tags from Qwen3."""
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy

        strategy = VerifiedStrategy()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MockLLMResponse(
            '<think>Let me analyze...</think>{"supported": true, "confidence": 0.75, "reason": "ok", "correction": null}'
        ))

        mock_prompt_client = AsyncMock()
        mock_prompt_client.get_prompt = AsyncMock(return_value=None)

        with patch("app.services.langfuse_prompt_client.get_langfuse_prompt_client", return_value=mock_prompt_client), \
             patch("app.agents.llm_client.get_llm_client", new_callable=AsyncMock, return_value=mock_llm):
            result = await strategy._llm_evaluate_claim("claim", _make_evidence(1))

        assert result["supported"] is True
        assert result["confidence"] == 0.75
