"""
Tests for Emma v2 Components

Tests cover:
1. LLM Client (async httpx)
2. Domain Router
3. Dynamic Prompt Loader
4. Emma v2 Agent
5. Consolidated Tools
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# =============================================================================
# Test Domain Router
# =============================================================================

class TestDomainRouter:
    """Tests for domain detection."""

    def test_detect_labor_domain(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        # Test labor keywords
        result = router.detect_domain("Analiza este contrato laboral")
        assert result.domain == DomainType.LABOR
        assert result.confidence >= 0.3

        result = router.detect_domain("¿Cuál es la jornada laboral máxima?")
        assert result.domain == DomainType.LABOR

        result = router.detect_domain("Revisa el estatuto de los trabajadores")
        assert result.domain == DomainType.LABOR

    def test_detect_fiscal_domain(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        result = router.detect_domain("Verifica esta factura de IVA")
        assert result.domain == DomainType.FISCAL

        result = router.detect_domain("¿Cómo se calcula el IRPF?")
        assert result.domain == DomainType.FISCAL

    def test_detect_privacy_domain(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        result = router.detect_domain("¿Cumple con el RGPD?")
        assert result.domain == DomainType.PRIVACY

        result = router.detect_domain("Protección de datos personales")
        assert result.domain == DomainType.PRIVACY

    def test_detect_realestate_domain(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        result = router.detect_domain("Revisa este contrato de arrendamiento")
        assert result.domain == DomainType.REALESTATE

        result = router.detect_domain("¿Cuál es la fianza del alquiler?")
        assert result.domain == DomainType.REALESTATE

    def test_detect_general_domain(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        # Generic query should return general
        result = router.detect_domain("¿Qué documentos tengo?")
        assert result.domain == DomainType.GENERAL

    def test_detect_from_document_type(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        # When document type is provided, it should influence detection
        result = router.detect_domain(
            "Analiza este documento",
            document_type="contrato_laboral"
        )
        assert result.domain == DomainType.LABOR

    def test_multiple_domains(self):
        from app.agents.domain_router import DomainRouter, DomainType

        router = DomainRouter()

        results = router.get_domains_for_query(
            "Contrato laboral con cláusulas RGPD",
            threshold=0.3
        )

        domains = [r.domain for r in results]
        assert DomainType.LABOR in domains or DomainType.PRIVACY in domains


# =============================================================================
# Test Dynamic Prompt Loader
# =============================================================================

class TestDynamicPromptLoader:
    """Tests for prompt loading."""

    def test_get_base_prompt(self):
        from app.agents.dynamic_prompt_loader import DynamicPromptLoader

        loader = DynamicPromptLoader()
        prompt = loader.get_base_prompt()

        assert len(prompt) > 0
        assert "Emma" in prompt or "assistant" in prompt.lower()

    def test_get_domain_prompt(self):
        from app.agents.dynamic_prompt_loader import DynamicPromptLoader, DomainType

        loader = DynamicPromptLoader()

        labor_prompt = loader.get_domain_prompt(DomainType.LABOR)
        assert len(labor_prompt) > 0
        assert "laboral" in labor_prompt.lower() or "labor" in labor_prompt.lower()

        # General domain should return empty or minimal
        general_prompt = loader.get_domain_prompt(DomainType.GENERAL)
        assert general_prompt == "" or len(general_prompt) < 100

    def test_build_system_prompt(self):
        from app.agents.dynamic_prompt_loader import DynamicPromptLoader, DomainType

        loader = DynamicPromptLoader()

        full_prompt = loader.build_system_prompt(
            domain=DomainType.LABOR,
            tenant_context="[Tenant: test-123]"
        )

        assert len(full_prompt) > 0
        assert "test-123" in full_prompt

    def test_token_estimation(self):
        from app.agents.dynamic_prompt_loader import DynamicPromptLoader

        loader = DynamicPromptLoader()

        text = "a" * 400  # 400 characters
        tokens = loader.estimate_tokens(text)

        # ~4 chars per token
        assert 90 <= tokens <= 110


# =============================================================================
# Test LLM Client
# =============================================================================

class TestLLMClient:
    """Tests for async LLM client."""

    def test_llm_config_creation(self):
        from app.agents.llm_client import LLMConfig, LLMProvider

        config = LLMConfig(
            provider=LLMProvider.VLLM,
            base_url="http://localhost:8000/v1",
            model="Qwen/Qwen3-4B",
            temperature=0.7,
        )

        assert config.provider == LLMProvider.VLLM
        assert config.model == "Qwen/Qwen3-4B"
        assert config.temperature == 0.7

    def test_parse_thinking(self):
        from app.agents.llm_client import _parse_thinking

        # With thinking tags
        text = "<think>Let me analyze this...</think>The answer is 42."
        thinking, content = _parse_thinking(text)

        assert thinking == "Let me analyze this..."
        assert content == "The answer is 42."

        # Without thinking tags
        text = "The answer is 42."
        thinking, content = _parse_thinking(text)

        assert thinking is None
        assert content == "The answer is 42."

    def test_llm_response_from_openai(self):
        from app.agents.llm_client import LLMResponse

        openai_data = {
            "choices": [{
                "message": {
                    "content": "Hello, I'm Emma!",
                    "tool_calls": None
                },
                "finish_reason": "stop"
            }],
            "model": "Qwen/Qwen3-4B",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }

        response = LLMResponse.from_openai(openai_data)

        assert response.content == "Hello, I'm Emma!"
        assert response.finish_reason == "stop"
        assert not response.has_tool_calls

    def test_llm_response_with_tool_calls(self):
        from app.agents.llm_client import LLMResponse

        openai_data = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "contratos"}'
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }],
            "model": "Qwen/Qwen3-4B"
        }

        response = LLMResponse.from_openai(openai_data)

        assert response.has_tool_calls
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
        assert response.tool_calls[0].arguments == {"query": "contratos"}

    @pytest.mark.asyncio
    async def test_build_request_body(self):
        from app.agents.llm_client import LLMClient, LLMConfig, LLMProvider

        config = LLMConfig(
            provider=LLMProvider.VLLM,
            base_url="http://localhost:8000/v1",
            model="test-model",
        )
        client = LLMClient(config)

        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"name": "search", "description": "Search", "parameters": {}}]

        body = client._build_request_body(messages, tools)

        assert body["model"] == "test-model"
        assert body["messages"] == messages
        assert "tools" in body
        assert body["stream"] is False


# =============================================================================
# Test Emma v2 Tools
# =============================================================================

class TestEmmaV2Tools:
    """Tests for consolidated tools."""

    def test_tool_schemas(self):
        from app.agents.emma_v2_tools import EMMA_V2_TOOLS, get_emma_v2_tools

        tools = get_emma_v2_tools()

        assert len(tools) == 6
        tool_names = [t["name"] for t in tools]

        assert "search" in tool_names
        assert "read_document" in tool_names
        assert "analyze" in tool_names
        assert "sil_query" in tool_names
        assert "ask_user" in tool_names
        assert "legal_search" in tool_names

    def test_search_tool_schema(self):
        from app.agents.emma_v2_tools import SEARCH_TOOL

        assert SEARCH_TOOL["name"] == "search"
        assert "query" in SEARCH_TOOL["parameters"]["properties"]
        assert "search_type" in SEARCH_TOOL["parameters"]["properties"]
        assert "query" in SEARCH_TOOL["parameters"]["required"]

    def test_tool_result_to_json(self):
        from app.agents.emma_v2_tools import ToolResult

        result = ToolResult(
            success=True,
            data={"count": 5, "results": []},
            metadata={"search_type": "hybrid"}
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["success"] is True
        assert parsed["data"]["count"] == 5

    def test_tool_result_error(self):
        from app.agents.emma_v2_tools import ToolResult

        result = ToolResult(
            success=False,
            data=None,
            error="Document not found"
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["success"] is False
        assert parsed["error"] == "Document not found"


# =============================================================================
# Test Emma v2 Agent
# =============================================================================

class TestEmmaV2:
    """Tests for Emma v2 agent."""

    def test_config_defaults(self):
        from app.agents.emma_v2 import EmmaV2Config

        config = EmmaV2Config()

        assert config.max_iterations == 10
        assert config.enable_sil_fast_path is True
        assert config.enable_domain_routing is True

    def test_execution_context(self):
        from app.agents.emma_v2 import ExecutionContext

        ctx = ExecutionContext(
            tenant_id="tenant-123",
            user_id="user-456",
            thread_id="thread-789"
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.user_id == "user-456"
        assert ctx.thread_id == "thread-789"

    def test_result_to_dict(self):
        from app.agents.emma_v2 import EmmaV2Result
        from app.agents.domain_router import DomainType

        result = EmmaV2Result(
            success=True,
            answer="Encontré 5 documentos",
            domain=DomainType.GENERAL,
            tools_called=["search"],
            iterations=1,
            sil_answered=False,
            tokens_saved=0,
            latency_ms=150.5,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["answer"] == "Encontré 5 documentos"
        assert d["domain"] == "general"
        assert "search" in d["tools_called"]

    @pytest.mark.asyncio
    async def test_sil_answer_formatting(self):
        from app.agents.emma_v2 import EmmaV2

        emma = EmmaV2()

        # Mock SIL result
        class MockStructuralContext:
            query_type = "count"
            document_count = 5
            document_titles = []
            folder_hierarchy = []
            query_result = {"count": 5}

        class MockSILResult:
            type = "structural"
            requires_rag = False
            structural_context = MockStructuralContext()
            reasoning_explanation = "Found 5 documents"

        answer = emma._format_sil_answer(MockSILResult())
        assert "5" in answer


# =============================================================================
# Test API Endpoints
# =============================================================================

class TestEmmaV2API:
    """Tests for Emma v2 API endpoints."""

    def test_query_model(self):
        from app.api.emma_v2 import EmmaV2Query

        query = EmmaV2Query(
            query="¿Cuántos contratos tengo?",
            tenant_id="tenant-123",
            enable_sil=True,
        )

        assert query.query == "¿Cuántos contratos tengo?"
        assert query.tenant_id == "tenant-123"
        assert query.enable_sil is True

    def test_response_model(self):
        from app.api.emma_v2 import EmmaV2Response

        response = EmmaV2Response(
            success=True,
            answer="Tienes 5 contratos.",
            domain="labor",
            sil_answered=True,
            tokens_saved=2500,
        )

        assert response.success is True
        assert response.domain == "labor"
        assert response.sil_answered is True

    def test_feature_flag(self):
        from app.api.emma_v2 import is_emma_v2_enabled
        import os

        # Save original value
        original = os.environ.get("EMMA_V2_ENABLED")

        # Test enabled
        os.environ["EMMA_V2_ENABLED"] = "true"
        assert is_emma_v2_enabled() is True

        # Test disabled
        os.environ["EMMA_V2_ENABLED"] = "false"
        assert is_emma_v2_enabled() is False

        # Restore
        if original:
            os.environ["EMMA_V2_ENABLED"] = original
        else:
            os.environ.pop("EMMA_V2_ENABLED", None)


# =============================================================================
# Integration Test Helpers
# =============================================================================

@pytest.fixture
def mock_weaviate_service():
    """Mock WeaviateService for testing."""
    with patch("app.agents.emma_v2_tools._get_weaviate_service") as mock:
        service = AsyncMock()
        service.initialize = AsyncMock()
        service.semantic_search = AsyncMock(return_value=[])
        service.hybrid_search = AsyncMock(return_value=[])
        mock.return_value = service
        yield service


@pytest.fixture
def mock_sil_engine():
    """Mock SIL engine for testing."""
    with patch("app.agents.emma_v2._get_sil_engine") as mock:
        engine = AsyncMock()
        engine.initialize = AsyncMock()
        engine.process_query = AsyncMock()
        mock.return_value = engine
        yield engine


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
