"""
Tests: Classify Node per Sector

Validates intent classification, fast-path routing, swarm detection,
and metadata generation. Mocks intent_router and LLM router to avoid
external calls.

Async tests with mocked dependencies.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.langgraph.nodes.classify import (
    _assess_complexity,
    classify_node,
)
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
    """Reset singletons and swarm config between tests."""
    os.environ["SWARM_ENABLED"] = "false"
    yield
    reset_sector_singleton("")
    reset_tool_registry()
    os.environ.pop("SWARM_ENABLED", None)


# =============================================================================
# Complexity Assessment (sync — no LLM calls)
# =============================================================================


class TestComplexityAssessment:
    """Verify _assess_complexity() heuristic scoring."""

    def test_simple_query_no_swarm(self, sector):
        """Short simple queries should not trigger swarm."""
        name, _ = sector
        os.environ["SWARM_ENABLED"] = "true"
        with patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", True
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_complexity_threshold", 3
        ):
            result = _assess_complexity("¿Qué dice el artículo 1?", "document_query", 0.9)
        assert result is False

    def test_swarm_disabled_always_false(self, sector):
        """When SWARM_ENABLED=false, _assess_complexity always returns False."""
        name, _ = sector
        with patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", False
        ):
            result = _assess_complexity(
                "Compara la legislación y jurisprudencia sobre contratos laborales "
                "con la normativa fiscal vigente y evalúa los riesgos de cumplimiento",
                "analysis", 0.9,
            )
        assert result is False

    def test_comparison_words_score(self):
        """Comparison words should contribute +2 to complexity score."""
        with patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", True
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_complexity_threshold", 3
        ):
            result = _assess_complexity(
                "Compara y analiza la legislación laboral con la normativa fiscal vigente "
                "para determinar las implicaciones en contratos de trabajo",
                "comparison", 0.9,
            )
        assert result is True

    def test_multi_source_words_score(self):
        """Multi-source keywords should contribute +2 to complexity score."""
        with patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", True
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_complexity_threshold", 3
        ):
            result = _assess_complexity(
                "Analiza la legislación y jurisprudencia sobre protección de datos "
                "incluyendo las sentencias recientes del tribunal supremo",
                "analysis", 0.8,
            )
        assert result is True

    def test_long_query_bonus(self):
        """Queries longer than 120 chars should get +1 signal."""
        with patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", True
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_complexity_threshold", 3
        ):
            short = "Compara algo versus otra cosa"
            long_q = short + " " + "x" * 100  # ensure > 120 chars
            result_short = _assess_complexity(short, "document_query", 0.8)
            result_long = _assess_complexity(long_q, "document_query", 0.8)
            # short: "compara" (+2) = 2 < 3 → False
            assert result_short is False
            # long: "compara" (+2) + len>120 (+1) = 3 >= 3 → True
            assert result_long is True

    def test_analysis_intent_bonus(self):
        """Intent=analysis should contribute +1 signal."""
        with patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", True
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_complexity_threshold", 3
        ):
            # "compara" (+2) + intent=analysis (+1) = 3 >= 3
            result = _assess_complexity("Compara los contratos", "analysis", 0.8)
        assert result is True


# =============================================================================
# Classify Node — Fast Path
# =============================================================================


class TestClassifyFastPath:
    """Verify classify_node routes to fast-path for conversational intents."""

    @pytest.mark.asyncio
    async def test_greeting_fast_path(self, sector):
        """Conversational intent with high confidence → fast-path."""
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
            state = make_react_state(query="Hola, buenos días", sector_name=name)
            result = await classify_node(state)

        assert result["fast_path_used"] is True
        assert result["is_complete"] is True
        assert result["success"] is True
        assert result["final_answer"] is not None
        assert len(result["final_answer"]) > 0

    @pytest.mark.asyncio
    async def test_identity_fast_path(self, sector):
        """Identity intent with high confidence → fast-path."""
        name, _ = sector

        mock_router = make_mock_router([MockLLMResponse(content="Soy Emma, tu asistente.")])

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("identity", 0.90),
        ), patch(
            "app.agents.llm_router.get_llm_router",
            new_callable=AsyncMock,
            return_value=mock_router,
        ):
            state = make_react_state(query="¿Quién eres?", sector_name=name)
            result = await classify_node(state)

        assert result["fast_path_used"] is True
        assert result["is_complete"] is True

    @pytest.mark.asyncio
    async def test_document_query_no_fast_path(self, sector):
        """Document query intent → should NOT fast-path."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("document_query", 0.85),
        ):
            state = make_react_state(
                query="Dame las facturas de enero 2024", sector_name=name
            )
            result = await classify_node(state)

        assert result["fast_path_used"] is False
        assert result.get("is_complete") is not True

    @pytest.mark.asyncio
    async def test_low_confidence_no_fast_path(self, sector):
        """Conversational intent with LOW confidence → should NOT fast-path."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("conversational", 0.5),
        ):
            state = make_react_state(query="Hola datos", sector_name=name)
            result = await classify_node(state)

        assert result["fast_path_used"] is False

    @pytest.mark.asyncio
    async def test_user_memory_in_fast_path(self, sector):
        """User memory should be passed to the conversational LLM call."""
        name, _ = sector

        captured_calls = []

        async def capture_chat(*args, **kwargs):
            captured_calls.append(kwargs.get("messages", args[0] if args else []))
            return MockLLMResponse(content="¡Hola, Carlos!")

        mock_router = MagicMock()
        mock_router.chat = capture_chat

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("conversational", 0.95),
        ), patch(
            "app.agents.llm_router.get_llm_router",
            new_callable=AsyncMock,
            return_value=mock_router,
        ):
            state = make_react_state(
                query="Hola",
                sector_name=name,
                user_memory="## Memoria del usuario\n- Nombre: Carlos\n- Departamento: Legal",
            )
            result = await classify_node(state)

        # Verify user memory was included in the system prompt
        assert len(captured_calls) > 0
        messages = captured_calls[0]
        system_msg = messages[0]["content"] if messages else ""
        assert "Memoria del usuario" in system_msg or "Carlos" in system_msg

    @pytest.mark.asyncio
    async def test_empty_query_fast_path(self, sector):
        """Empty query should fast-path with a clarification message."""
        name, _ = sector

        state = make_react_state(query="", sector_name=name)
        result = await classify_node(state)

        assert result["fast_path_used"] is True
        assert result["is_complete"] is True
        assert "formular" in result["final_answer"].lower()


# =============================================================================
# Classify Node — Metadata
# =============================================================================


class TestClassifyMetadata:
    """Verify classify_node populates metadata correctly."""

    @pytest.mark.asyncio
    async def test_intent_in_metadata(self, sector):
        """Metadata should include classify_intent."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("document_query", 0.85),
        ):
            state = make_react_state(query="Busca facturas", sector_name=name)
            result = await classify_node(state)

        assert "classify_intent" in result["metadata"]
        assert result["metadata"]["classify_intent"] == "document_query"

    @pytest.mark.asyncio
    async def test_confidence_in_metadata(self, sector):
        """Metadata should include classify_confidence as float."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("document_query", 0.85),
        ):
            state = make_react_state(query="Busca facturas", sector_name=name)
            result = await classify_node(state)

        assert "classify_confidence" in result["metadata"]
        assert isinstance(result["metadata"]["classify_confidence"], float)
        assert result["metadata"]["classify_confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_latency_in_metadata(self, sector):
        """Metadata should include classify_latency_ms >= 0."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("document_query", 0.85),
        ):
            state = make_react_state(query="Busca facturas", sector_name=name)
            result = await classify_node(state)

        assert "classify_latency_ms" in result["metadata"]
        assert result["metadata"]["classify_latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_intent_failure_defaults(self, sector):
        """When intent classification fails, should default to document_query."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            side_effect=RuntimeError("FastEmbed not available"),
        ):
            state = make_react_state(query="Busca algo", sector_name=name)
            result = await classify_node(state)

        assert result["fast_path_used"] is False
        assert result["metadata"]["classify_intent"] == "document_query"


# =============================================================================
# Classify Node — Swarm Detection
# =============================================================================


class TestSwarmDetection:
    """Verify swarm activation through classify_node."""

    @pytest.mark.asyncio
    async def test_swarm_enabled_complex_query(self, sector):
        """Complex query with SWARM_ENABLED=true should activate swarm."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("analysis", 0.8),
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", True
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_complexity_threshold", 3
        ):
            state = make_react_state(
                query="Compara la legislación y jurisprudencia sobre contratos laborales "
                      "con la normativa fiscal vigente y evalúa los riesgos de cumplimiento",
                sector_name=name,
            )
            result = await classify_node(state)

        assert result["fast_path_used"] is False
        assert result.get("use_swarm") is True

    @pytest.mark.asyncio
    async def test_swarm_disabled_no_swarm(self, sector):
        """Even complex queries should not swarm when disabled."""
        name, _ = sector

        with patch(
            "app.agents.langgraph.nodes.intent_router.classify_intent",
            new_callable=AsyncMock,
            return_value=("analysis", 0.8),
        ), patch(
            "app.agents.langgraph.nodes.classify.settings.swarm_enabled", False
        ):
            state = make_react_state(
                query="Compara legislación y jurisprudencia con análisis de riesgos",
                sector_name=name,
            )
            result = await classify_node(state)

        assert result.get("use_swarm", False) is False
