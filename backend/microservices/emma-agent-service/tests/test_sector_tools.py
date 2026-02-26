"""
Tests: Tool Registry per Sector

Validates that the ToolRegistry returns the correct set of tools
based on sector, feature flags, and context. Each sector should get
the always-available tools plus conditional tools when flags are set.

No async, no LLM calls — pure registry filtering tests.
"""

import pytest

from app.agents.langgraph.tools.registry import get_tool_registry
from tests.sector_helpers import reset_sector_singleton, reset_tool_registry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_between_tests():
    """Reset singletons before and after each test."""
    reset_tool_registry()
    yield
    reset_tool_registry()
    reset_sector_singleton("")


# =============================================================================
# Tool Availability Matrix
# =============================================================================


ALWAYS_AVAILABLE = {
    "terminate",
    "smart_search",
    "get_document_content",
    "structural_query",
    "list_sources",
}


class TestToolAvailability:
    """Verify correct tools are returned for each sector and feature flag combination."""

    def test_always_available_tools(self, sector):
        """Core tools must be present regardless of sector or features."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=name, features={}
        )
        tool_names = {t.name for t in tools}
        assert ALWAYS_AVAILABLE.issubset(tool_names), (
            f"Missing always-available tools: {ALWAYS_AVAILABLE - tool_names}"
        )

    def test_analyze_domain_available(self, sector):
        """analyze_domain should be included because all sectors have agents."""
        name, config = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=name, features={}
        )
        tool_names = {t.name for t in tools}
        # All sectors have ≥1 agent, so analyze_domain should be included
        assert "analyze_domain" in tool_names

    def test_web_search_excluded_by_default(self, sector):
        """web_search must NOT be included without feature flag."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=name, features={}
        )
        tool_names = {t.name for t in tools}
        assert "web_search" not in tool_names

    def test_web_search_included_with_flag(self, sector):
        """web_search must be included when web_search_enabled=True."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant",
            sector=name,
            features={"web_search_enabled": True},
        )
        tool_names = {t.name for t in tools}
        assert "web_search" in tool_names

    def test_cendoj_excluded_by_default(self, sector):
        """search_jurisprudence must NOT be included without feature flag."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=name, features={}
        )
        tool_names = {t.name for t in tools}
        assert "search_jurisprudence" not in tool_names

    def test_cendoj_included_with_flag(self, sector):
        """search_jurisprudence must be included when cendoj_enabled=True."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant",
            sector=name,
            features={"cendoj_enabled": True},
        )
        tool_names = {t.name for t in tools}
        assert "search_jurisprudence" in tool_names

    def test_connector_excluded_by_default(self, sector):
        """query_connector must NOT be included without feature flag."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=name, features={}
        )
        tool_names = {t.name for t in tools}
        assert "query_connector" not in tool_names

    def test_connector_included_with_flag(self, sector):
        """query_connector must be included when connectors_enabled=True."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant",
            sector=name,
            features={"connectors_enabled": True},
        )
        tool_names = {t.name for t in tools}
        assert "query_connector" in tool_names

    def test_tool_count_base(self, sector):
        """Without feature flags, exactly 6 tools should be available."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=name, features={}
        )
        # 5 always-available + analyze_domain = 6
        assert len(tools) == 6, (
            f"Expected 6 base tools, got {len(tools)}: "
            f"{[t.name for t in tools]}"
        )

    def test_all_flags_enabled(self, sector):
        """With all feature flags on, exactly 9 tools should be available."""
        name, _ = sector
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant",
            sector=name,
            features={
                "web_search_enabled": True,
                "cendoj_enabled": True,
                "connectors_enabled": True,
            },
        )
        assert len(tools) == 9, (
            f"Expected 9 tools with all flags, got {len(tools)}: "
            f"{[t.name for t in tools]}"
        )


# =============================================================================
# Tool OpenAI Schema Generation
# =============================================================================


class TestToolSchemas:
    """Verify OpenAI-compatible schemas are generated correctly."""

    def test_openai_params_generated(self, sector):
        """get_openai_params must return valid dicts for each tool."""
        name, _ = sector
        registry = get_tool_registry()
        params = registry.get_openai_params(
            tenant_id="test-tenant", sector=name, features={}
        )
        assert len(params) == 6  # base tool count
        for p in params:
            assert "type" in p
            assert "function" in p
            assert "name" in p["function"]
            assert "description" in p["function"]

    def test_tools_description_generated(self, sector):
        """get_tools_description must return a non-empty markdown string."""
        name, _ = sector
        registry = get_tool_registry()
        desc = registry.get_tools_description(
            tenant_id="test-tenant", sector=name, features={}
        )
        assert isinstance(desc, str)
        assert "smart_search" in desc
        assert "terminate" in desc


# =============================================================================
# Generic Mode (no sector)
# =============================================================================


class TestGenericMode:
    """Verify tool availability when no sector is configured."""

    def test_no_sector_all_base_tools(self):
        """With no sector, analyze_domain should still be included (has_specialists=True default)."""
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector=None, features={}
        )
        tool_names = {t.name for t in tools}
        assert ALWAYS_AVAILABLE.issubset(tool_names)
        assert "analyze_domain" in tool_names

    def test_no_sector_empty_string(self):
        """Empty string sector should behave like None."""
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test-tenant", sector="", features={}
        )
        tool_names = {t.name for t in tools}
        assert ALWAYS_AVAILABLE.issubset(tool_names)


# =============================================================================
# Tool Execution Safety
# =============================================================================


class TestToolExecution:
    """Verify tool execution error handling."""

    def test_unknown_tool_returns_error(self):
        """Executing a non-existent tool should return ToolResult with error."""
        import asyncio

        registry = get_tool_registry()
        result = asyncio.get_event_loop().run_until_complete(
            registry.execute("nonexistent_tool", {}, {"tenant_id": "test"})
        )
        assert not result.success
        assert "Unknown tool" in result.output


# =============================================================================
# ToolResult & EmmaTool base class (covers base.py lines 40-55, 137-165)
# =============================================================================


class TestToolResultFactory:
    """Verify ToolResult.from_error and construction."""

    def test_from_error_basic(self):
        """from_error should create a failed ToolResult."""
        from app.agents.langgraph.tools.base import ToolResult

        result = ToolResult.from_error("Something broke")
        assert not result.success
        assert "Something broke" in result.output
        assert result.error == "Something broke"

    def test_from_error_with_suggestion(self):
        """from_error with suggestion should include it in output."""
        from app.agents.langgraph.tools.base import ToolResult

        result = ToolResult.from_error("No results", suggestion="Try broader query")
        assert "Try broader query" in result.output
        assert not result.success

    def test_tool_result_defaults(self):
        """Default ToolResult should be successful with empty sources."""
        from app.agents.langgraph.tools.base import ToolResult

        result = ToolResult(output="hello")
        assert result.success is True
        assert result.sources == []
        assert result.data == {}
        assert result.error is None


class TestToolError:
    """Verify ToolError exception class."""

    def test_tool_error_attributes(self):
        """ToolError should store tool_name and retryable."""
        from app.agents.langgraph.tools.base import ToolError

        err = ToolError("connection failed", tool_name="smart_search", retryable=True)
        assert str(err) == "connection failed"
        assert err.tool_name == "smart_search"
        assert err.retryable is True

    def test_tool_error_defaults(self):
        """ToolError defaults should be empty name and not retryable."""
        from app.agents.langgraph.tools.base import ToolError

        err = ToolError("fail")
        assert err.tool_name == ""
        assert err.retryable is False


class TestEmmaToolBase:
    """Verify EmmaTool abstract base behavior via a concrete tool."""

    def test_tool_repr(self):
        """EmmaTool.__repr__ should include the tool name."""
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test", sector=None, features={}
        )
        tool = tools[0]
        assert tool.name in repr(tool)
        assert "<EmmaTool:" in repr(tool)

    @pytest.mark.asyncio
    async def test_safe_execute_invalid_args(self):
        """safe_execute with invalid args should return error ToolResult."""
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test", sector=None, features={}
        )
        # Find smart_search tool (requires "query" argument)
        smart = next(t for t in tools if t.name == "smart_search")
        result = await smart.safe_execute(
            {"not_a_valid_param": 123},
            {"tenant_id": "test"},
        )
        assert not result.success
        assert "Invalid arguments" in result.output

    @pytest.mark.asyncio
    async def test_safe_execute_validation_passes(self):
        """safe_execute with valid args should call execute (which may fail on missing client)."""
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            tenant_id="test", sector=None, features={}
        )
        # terminate tool uses "answer" field name
        terminate = next(t for t in tools if t.name == "terminate")
        result = await terminate.safe_execute(
            {"answer": "Test answer", "sources": []},
            {"tenant_id": "test"},
        )
        assert result.success is True
        assert "Test answer" in result.output
