"""
Tests: ReAct State Initialization per Sector

Validates that create_initial_react_state() correctly populates
sector config, user memory, features, and ACL context in the state.

Async tests with mocked user_facts to avoid DB calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.sector_helpers import (
    reset_sector_singleton,
    reset_tool_registry,
    TENANT_ID,
    USER_ID,
    THREAD_ID,
    make_react_state,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_between_tests():
    """Reset singletons before and after each test."""
    yield
    reset_sector_singleton("")
    reset_tool_registry()


# =============================================================================
# State Builder (sync helper) — no DB calls
# =============================================================================


class TestReActStateBuilder:
    """Validate the make_react_state() sync helper produces correct states."""

    def test_sector_name_in_state(self, sector):
        """State should have the correct sector name."""
        name, _ = sector
        state = make_react_state(query="test", sector_name=name)
        assert state["sector"] == name

    def test_sector_config_serialized(self, sector):
        """State should have a serialized sector_config dict with key params."""
        name, config = sector
        state = make_react_state(query="test", sector_name=name)
        sc = state["sector_config"]
        assert sc is not None
        assert sc["hybrid_alpha"] == config.hybrid_alpha
        assert sc["top_k"] == config.top_k
        assert sc["sector"] == name
        assert sc["rerank_enabled"] == config.rerank_enabled

    def test_agents_in_config(self, sector):
        """State sector_config should contain the full agents list."""
        name, config = sector
        state = make_react_state(query="test", sector_name=name)
        assert state["sector_config"]["agents"] == config.agents

    def test_default_agent_in_config(self, sector):
        """State sector_config should contain the default agent."""
        name, config = sector
        state = make_react_state(query="test", sector_name=name)
        assert state["sector_config"]["default_agent"] == config.default_agent

    def test_system_prompt_key_in_config(self, sector):
        """State sector_config should contain system_prompt_key."""
        name, config = sector
        state = make_react_state(query="test", sector_name=name)
        assert state["sector_config"]["system_prompt_key"] == config.system_prompt_key

    def test_chunk_strategy_in_config(self, sector):
        """State sector_config should contain chunk_strategy."""
        name, config = sector
        state = make_react_state(query="test", sector_name=name)
        assert state["sector_config"]["chunk_strategy"] == config.chunk_strategy


# =============================================================================
# User Memory in State
# =============================================================================


class TestUserMemoryState:
    """Validate user memory injection into state."""

    def test_user_memory_present(self, sector):
        """When user_memory is provided, it should be in the state."""
        name, _ = sector
        memory_text = "## Memoria del usuario\n- Nombre: Test User"
        state = make_react_state(
            query="Hola", sector_name=name, user_memory=memory_text
        )
        assert state["user_memory"] == memory_text

    def test_user_memory_none_by_default(self, sector):
        """Without user_memory, state should have None."""
        name, _ = sector
        state = make_react_state(query="Hola", sector_name=name)
        assert state["user_memory"] is None


# =============================================================================
# Features Defaults
# =============================================================================


class TestFeaturesState:
    """Validate features dict in state."""

    def test_default_features(self, sector):
        """Default features should disable web_search and connectors."""
        name, _ = sector
        state = make_react_state(query="test", sector_name=name)
        features = state["features"]
        assert features["web_search_enabled"] is False
        assert features["connectors_enabled"] is False
        assert features["social_channel_mode"] is False

    def test_override_features(self, sector):
        """Features should be overridable via make_react_state."""
        name, _ = sector
        state = make_react_state(
            query="test",
            sector_name=name,
            features={
                "web_search_enabled": True,
                "connectors_enabled": True,
                "social_channel_mode": True,
            },
        )
        features = state["features"]
        assert features["web_search_enabled"] is True
        assert features["connectors_enabled"] is True
        assert features["social_channel_mode"] is True


# =============================================================================
# Generic Mode (no sector)
# =============================================================================


class TestGenericModeState:
    """Validate state when no sector is configured."""

    def test_no_sector_state(self):
        """Without sector, state should have None for sector and sector_config."""
        reset_sector_singleton("")
        state = make_react_state(query="test", sector_name=None)
        assert state["sector"] is None
        assert state["sector_config"] is None

    def test_acl_context_present(self):
        """ACL fields should always be present regardless of sector."""
        state = make_react_state(query="test")
        assert state["tenant_id"] == TENANT_ID
        assert state["user_id"] == USER_ID
        assert state["thread_id"] == THREAD_ID
        assert state["is_admin"] is False
        assert state["user_role_ids"] == []


# =============================================================================
# Swarm Fields in State
# =============================================================================


class TestSwarmFieldsState:
    """Validate swarm-related fields in state."""

    def test_swarm_defaults(self, sector):
        """Swarm fields should be properly initialized."""
        name, _ = sector
        state = make_react_state(query="test", sector_name=name)
        assert state["use_swarm"] is False
        assert state["swarm_sub_tasks"] == []
        assert state["swarm_current_task"] is None
        assert state["swarm_worker_id"] is None
        assert state["swarm_worker_results"] == []
        assert state["swarm_pending_events"] == []

    def test_swarm_can_be_enabled(self, sector):
        """use_swarm should be settable via make_react_state."""
        name, _ = sector
        state = make_react_state(query="test", sector_name=name, use_swarm=True)
        assert state["use_swarm"] is True


# =============================================================================
# Async create_initial_react_state (with mocked user_facts)
# =============================================================================


class TestAsyncStateInit:
    """Validate the real create_initial_react_state function with mocks."""

    @pytest.mark.asyncio
    async def test_state_has_sector(self, sector):
        """Async state init should populate sector fields."""
        name, config = sector

        mock_facts_service = MagicMock()
        mock_facts_service.format_facts_for_prompt = AsyncMock(return_value="")

        with patch(
            "app.services.memory.user_facts.get_user_facts_service",
            return_value=mock_facts_service,
        ):
            from app.agents.langgraph.state import create_initial_react_state

            state = await create_initial_react_state(
                query="Test query",
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                thread_id=THREAD_ID,
            )
        assert state["sector"] == name
        assert state["sector_config"]["hybrid_alpha"] == config.hybrid_alpha

    @pytest.mark.asyncio
    async def test_user_memory_loaded(self, sector):
        """Async state init should load user memory from facts service."""
        name, _ = sector
        memory = "## Memoria del usuario\n- Departamento: Legal"

        mock_facts_service = MagicMock()
        mock_facts_service.format_facts_for_prompt = AsyncMock(return_value=memory)

        with patch(
            "app.services.memory.user_facts.get_user_facts_service",
            return_value=mock_facts_service,
        ):
            from app.agents.langgraph.state import create_initial_react_state

            state = await create_initial_react_state(
                query="Hola",
                tenant_id=TENANT_ID,
                user_id=USER_ID,
            )
        assert state["user_memory"] == memory
        mock_facts_service.format_facts_for_prompt.assert_awaited_once_with(
            TENANT_ID, USER_ID
        )

    @pytest.mark.asyncio
    async def test_user_memory_skipped_no_user(self, sector):
        """When user_id is None, user memory should not be loaded."""
        name, _ = sector

        mock_facts_service = MagicMock()
        mock_facts_service.format_facts_for_prompt = AsyncMock(
            return_value="should not be called"
        )

        with patch(
            "app.services.memory.user_facts.get_user_facts_service",
            return_value=mock_facts_service,
        ):
            from app.agents.langgraph.state import create_initial_react_state

            state = await create_initial_react_state(
                query="Test",
                tenant_id=TENANT_ID,
                user_id=None,
            )
        assert state["user_memory"] is None
        mock_facts_service.format_facts_for_prompt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_features_from_context(self, sector):
        """Features should be derived from request_context."""
        name, _ = sector

        mock_facts_service = MagicMock()
        mock_facts_service.format_facts_for_prompt = AsyncMock(return_value="")

        with patch(
            "app.services.memory.user_facts.get_user_facts_service",
            return_value=mock_facts_service,
        ):
            from app.agents.langgraph.state import create_initial_react_state

            state = await create_initial_react_state(
                query="Test",
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                request_context={
                    "social_channel_mode": True,
                    "connectors_enabled": True,
                },
            )
        assert state["features"]["social_channel_mode"] is True
        assert state["features"]["web_search_enabled"] is True  # derived from social_channel_mode
        assert state["features"]["connectors_enabled"] is True
