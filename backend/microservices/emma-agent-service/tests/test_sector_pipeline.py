"""
Tests: Pipeline Structure and End-to-End per Sector

Validates graph structure, routing functions, synthesize node behavior,
and system prompt construction. Uses mocked LLM and clients.

Mix of sync (routing) and async (node execution) tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.langgraph.graph import (
    _route_from_classify,
    _route_from_react,
    _route_from_decompose,
    create_react_graph,
)
from app.agents.langgraph.nodes.synthesize_react import synthesize_react_node
from tests.sector_helpers import (
    reset_sector_singleton,
    reset_tool_registry,
    make_react_state,
    make_mock_router,
    MockLLMResponse,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_between_tests():
    yield
    reset_sector_singleton("")
    reset_tool_registry()


# =============================================================================
# Graph Structure
# =============================================================================


class TestGraphStructure:
    """Verify the ReAct graph compiles with expected nodes and edges."""

    def test_react_graph_compiles(self):
        """create_react_graph() should not raise exceptions."""
        graph = create_react_graph(enable_checkpointing=False)
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """Graph should have all 6 expected nodes."""
        graph = create_react_graph(enable_checkpointing=False)
        # LangGraph compiled graph exposes nodes via .nodes
        node_names = set(graph.nodes.keys()) - {"__start__", "__end__"}
        expected_nodes = {
            "classify", "react_loop", "synthesize",
            "decompose", "swarm_worker", "synthesize_swarm",
        }
        assert expected_nodes.issubset(node_names), (
            f"Missing nodes: {expected_nodes - node_names}"
        )


# =============================================================================
# Routing Functions (sync — pure state inspection)
# =============================================================================


class TestRoutingFromClassify:
    """Verify _route_from_classify routes correctly."""

    def test_fast_path_routes_to_end(self):
        """fast_path_used=True → 'end'."""
        state = {"fast_path_used": True, "is_complete": True}
        assert _route_from_classify(state) == "end"

    def test_is_complete_routes_to_end(self):
        """is_complete=True (even without fast_path) → 'end'."""
        state = {"fast_path_used": False, "is_complete": True}
        assert _route_from_classify(state) == "end"

    def test_swarm_routes_to_decompose(self):
        """use_swarm=True → 'decompose'."""
        state = {"fast_path_used": False, "is_complete": False, "use_swarm": True}
        assert _route_from_classify(state) == "decompose"

    def test_normal_routes_to_react(self):
        """No fast-path, no swarm → 'react'."""
        state = {"fast_path_used": False, "is_complete": False, "use_swarm": False}
        assert _route_from_classify(state) == "react"

    def test_default_routes_to_react(self):
        """Missing fields should default to 'react'."""
        state = {}
        assert _route_from_classify(state) == "react"


class TestRoutingFromReact:
    """Verify _route_from_react routes correctly."""

    def test_complete_routes_to_synthesize(self):
        """is_complete=True → 'synthesize'."""
        state = {"is_complete": True}
        assert _route_from_react(state) == "synthesize"

    def test_incomplete_continues(self):
        """is_complete=False → 'continue'."""
        state = {"is_complete": False}
        assert _route_from_react(state) == "continue"

    def test_missing_defaults_continue(self):
        """Missing is_complete should default to 'continue'."""
        state = {}
        assert _route_from_react(state) == "continue"


class TestRoutingFromDecompose:
    """Verify _route_from_decompose handles fan-out and fallback."""

    def test_swarm_disabled_fallback(self):
        """use_swarm=False after decompose → fallback to react_loop via Send."""
        from langgraph.types import Send

        state = {"use_swarm": False}
        result = _route_from_decompose(state)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Send)
        assert result[0].node == "react_loop"

    def test_empty_subtasks_fallback(self):
        """Empty swarm_sub_tasks → fallback to react_loop."""
        from langgraph.types import Send

        state = {"use_swarm": True, "swarm_sub_tasks": []}
        result = _route_from_decompose(state)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Send)
        assert result[0].node == "react_loop"

    def test_multiple_tasks_fan_out(self):
        """Multiple sub-tasks → N parallel swarm_worker Sends."""
        from langgraph.types import Send

        tasks = [
            {"task": "sub1", "tools": ["smart_search"]},
            {"task": "sub2", "tools": ["structural_query"]},
            {"task": "sub3", "tools": ["smart_search"]},
        ]
        state = {
            "use_swarm": True,
            "swarm_sub_tasks": tasks,
            "messages": [],
            "query": "test",
        }
        result = _route_from_decompose(state)

        assert isinstance(result, list)
        assert len(result) == 3
        for send in result:
            assert isinstance(send, Send)
            assert send.node == "swarm_worker"


# =============================================================================
# Synthesize Node
# =============================================================================


class TestSynthesizeNode:
    """Verify synthesize_react_node behavior."""

    @pytest.mark.asyncio
    async def test_synthesize_with_answer(self, sector):
        """When final_answer exists, synthesize should pass it through."""
        name, _ = sector
        state = make_react_state(
            query="test", sector_name=name,
            final_answer="Here is the answer.",
            sources=[
                {"document_id": "d1", "title": "Doc 1"},
                {"document_id": "d2", "title": "Doc 2"},
            ],
        )

        result = await synthesize_react_node(state)

        assert result["final_answer"] == "Here is the answer."
        assert result["success"] is True
        assert len(result["sources"]) == 2

    @pytest.mark.asyncio
    async def test_synthesize_deduplicates_sources(self, sector):
        """Duplicate sources (same document_id) should be removed."""
        name, _ = sector
        state = make_react_state(
            query="test", sector_name=name,
            final_answer="Answer with dupes.",
            sources=[
                {"document_id": "d1", "title": "Doc 1"},
                {"document_id": "d1", "title": "Doc 1 copy"},
                {"document_id": "d2", "title": "Doc 2"},
            ],
        )

        result = await synthesize_react_node(state)

        assert len(result["sources"]) == 2
        doc_ids = [s["document_id"] for s in result["sources"]]
        assert "d1" in doc_ids
        assert "d2" in doc_ids

    @pytest.mark.asyncio
    async def test_synthesize_fallback_from_messages(self, sector):
        """When no final_answer, should extract from last AIMessage."""
        name, _ = sector
        state = make_react_state(
            query="test", sector_name=name,
            final_answer=None,
        )
        # Inject an AIMessage into state messages
        state["messages"].append(AIMessage(content="Extracted answer from messages."))

        result = await synthesize_react_node(state)

        assert result["final_answer"] == "Extracted answer from messages."
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_synthesize_last_resort(self, sector):
        """When no answer anywhere, should return a generic fallback."""
        name, _ = sector
        state = make_react_state(
            query="test", sector_name=name,
            final_answer=None,
        )
        # No AIMessage either — only the HumanMessage from make_react_state

        result = await synthesize_react_node(state)

        assert result["final_answer"] is not None
        assert "encontrar información" in result["final_answer"].lower()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_synthesize_metadata(self, sector):
        """Synthesize should add latency and source_count to metadata."""
        name, _ = sector
        state = make_react_state(
            query="test", sector_name=name,
            final_answer="Test answer",
            sources=[{"document_id": "d1", "title": "Doc"}],
        )

        result = await synthesize_react_node(state)

        assert "synthesize_latency_ms" in result["metadata"]
        assert result["metadata"]["source_count"] == 1


# =============================================================================
# System Prompt Construction
# =============================================================================


class TestSystemPrompt:
    """Verify system prompt includes sector context and user memory."""

    @pytest.mark.asyncio
    async def test_sector_in_system_prompt(self, sector):
        """System prompt should include 'Sector activo: {sector_name}'."""
        name, _ = sector

        from app.agents.langgraph.nodes.react_loop import _build_system_message

        with patch(
            "app.agents.langgraph.nodes.react_loop._load_react_system_prompt",
            new_callable=AsyncMock,
            return_value="You are Emma. {tools_description}",
        ):
            state = make_react_state(query="test", sector_name=name)
            msg = await _build_system_message(state)

        assert f"Sector activo: {name}" in msg.content

    @pytest.mark.asyncio
    async def test_user_memory_in_system_prompt(self, sector):
        """System prompt should include user memory when present."""
        name, _ = sector

        from app.agents.langgraph.nodes.react_loop import _build_system_message

        with patch(
            "app.agents.langgraph.nodes.react_loop._load_react_system_prompt",
            new_callable=AsyncMock,
            return_value="You are Emma. {tools_description}",
        ):
            memory_text = "## Memoria del usuario\n- Nombre: Carlos\n- Departamento: Legal"
            state = make_react_state(
                query="test",
                sector_name=name,
                user_memory=memory_text,
            )
            msg = await _build_system_message(state)

        assert "Memoria del usuario" in msg.content
        assert "Carlos" in msg.content

    @pytest.mark.asyncio
    async def test_no_sector_no_sector_line(self):
        """Without sector, 'Sector activo' should NOT appear in prompt."""
        from app.agents.langgraph.nodes.react_loop import _build_system_message

        with patch(
            "app.agents.langgraph.nodes.react_loop._load_react_system_prompt",
            new_callable=AsyncMock,
            return_value="You are Emma. {tools_description}",
        ):
            state = make_react_state(query="test", sector_name=None)
            msg = await _build_system_message(state)

        assert "Sector activo" not in msg.content

    @pytest.mark.asyncio
    async def test_tools_description_injected(self, sector):
        """System prompt should replace {tools_description} with actual tools."""
        name, _ = sector

        from app.agents.langgraph.nodes.react_loop import _build_system_message

        with patch(
            "app.agents.langgraph.nodes.react_loop._load_react_system_prompt",
            new_callable=AsyncMock,
            return_value="Available tools:\n{tools_description}\n\nEnd.",
        ):
            state = make_react_state(query="test", sector_name=name)
            msg = await _build_system_message(state)

        # {tools_description} should have been replaced
        assert "{tools_description}" not in msg.content
        # And actual tools should be listed
        assert "smart_search" in msg.content
        assert "terminate" in msg.content


# =============================================================================
# Conversational Pipeline (fast-path end-to-end)
# =============================================================================


class TestConversationalPipeline:
    """Verify fast-path classify → END pipeline with mocks."""

    @pytest.mark.asyncio
    async def test_conversational_pipeline(self, sector):
        """Conversational query: classify → fast_path → END (no react_loop)."""
        name, _ = sector

        mock_router = make_mock_router([MockLLMResponse(content="¡Hola! Soy Emma.")])

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("conversational", 0.95),
        ), patch(
            "app.agents.llm_router.get_llm_router",
            new_callable=AsyncMock,
            return_value=mock_router,
        ):
            from app.agents.langgraph.nodes.classify import classify_node

            state = make_react_state(query="Hola", sector_name=name)
            result = await classify_node(state)

        assert result["fast_path_used"] is True
        assert result["final_answer"] is not None
        assert result["success"] is True


# =============================================================================
# React Loop Helpers (covers react_loop.py lines 187-245)
# =============================================================================


class TestBuildToolContext:
    """Verify _build_tool_context extracts the right fields."""

    def test_context_has_required_fields(self, sector):
        """Tool context should include tenant_id, sector, features, etc."""
        name, _ = sector
        from app.agents.langgraph.nodes.react_loop import _build_tool_context

        state = make_react_state(query="test", sector_name=name)
        ctx = _build_tool_context(state)
        assert ctx["tenant_id"] is not None
        assert ctx["sector"] == name
        assert ctx["features"] is not None
        assert "query" in ctx

    def test_context_no_sector(self):
        """Without sector, context should have sector=None."""
        from app.agents.langgraph.nodes.react_loop import _build_tool_context

        state = make_react_state(query="test", sector_name=None)
        ctx = _build_tool_context(state)
        assert ctx["sector"] is None


class TestParseThinking:
    """Verify _parse_thinking() extraction from LLM response."""

    def test_parse_think_tags(self):
        """<think>...</think> should be extracted as thinking."""
        from app.agents.langgraph.nodes.react_loop import _parse_thinking

        thinking, remaining = _parse_thinking(
            "<think>I should search first</think>Let me find that."
        )
        assert thinking == "I should search first"
        assert remaining == "Let me find that."

    def test_parse_thinking_tags(self):
        """<thinking>...</thinking> should also be extracted."""
        from app.agents.langgraph.nodes.react_loop import _parse_thinking

        thinking, remaining = _parse_thinking(
            "<thinking>Analysis step</thinking>Here is the answer."
        )
        assert thinking == "Analysis step"
        assert remaining == "Here is the answer."

    def test_parse_pensamiento_tags(self):
        """<pensamiento>...</pensamiento> (Spanish) should be extracted."""
        from app.agents.langgraph.nodes.react_loop import _parse_thinking

        thinking, remaining = _parse_thinking(
            "<pensamiento>Debo buscar</pensamiento>Aquí está."
        )
        assert thinking == "Debo buscar"
        assert remaining == "Aquí está."

    def test_no_thinking_tags(self):
        """Without thinking tags, thinking should be None."""
        from app.agents.langgraph.nodes.react_loop import _parse_thinking

        thinking, remaining = _parse_thinking("Just a plain response.")
        assert thinking is None
        assert remaining == "Just a plain response."


class TestDetectStuck:
    """Verify _detect_stuck() heuristics."""

    def test_not_stuck_short_history(self):
        """Less than window entries should never be stuck."""
        from app.agents.langgraph.nodes.react_loop import _detect_stuck

        history = [{"name": "smart_search", "args": {"query": "test"}}]
        assert _detect_stuck(history, window=3) is False

    def test_stuck_exact_match(self):
        """Identical tool calls repeated window times → stuck."""
        from app.agents.langgraph.nodes.react_loop import _detect_stuck

        entry = {"name": "smart_search", "args": {"query": "facturas"}}
        history = [entry, entry, entry]
        assert _detect_stuck(history, window=3) is True

    def test_stuck_same_tool_different_args(self):
        """Same tool with different args repeated window times → near-stuck."""
        from app.agents.langgraph.nodes.react_loop import _detect_stuck

        history = [
            {"name": "smart_search", "args": {"query": "facturas"}},
            {"name": "smart_search", "args": {"query": "facturas 2024"}},
            {"name": "smart_search", "args": {"query": "facturas enero"}},
        ]
        assert _detect_stuck(history, window=3) is True

    def test_not_stuck_different_tools(self):
        """Different tools should not be detected as stuck."""
        from app.agents.langgraph.nodes.react_loop import _detect_stuck

        history = [
            {"name": "smart_search", "args": {"query": "test"}},
            {"name": "structural_query", "args": {"query": "count"}},
            {"name": "terminate", "args": {"response": "done"}},
        ]
        assert _detect_stuck(history, window=3) is False

    def test_terminate_not_stuck(self):
        """Repeated terminate calls should NOT be detected as near-stuck."""
        from app.agents.langgraph.nodes.react_loop import _detect_stuck

        history = [
            {"name": "terminate", "args": {"response": "a"}},
            {"name": "terminate", "args": {"response": "b"}},
            {"name": "terminate", "args": {"response": "c"}},
        ]
        # terminate is excluded from near-stuck detection
        assert _detect_stuck(history, window=3) is False
