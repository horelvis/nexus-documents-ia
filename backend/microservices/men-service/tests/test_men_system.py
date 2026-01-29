"""
Tests for MENSystem coordinator – the 3-stage pipeline logic.

All ML components are mocked; we test orchestration, routing, session
management, and status reporting.
"""

import pytest

from app.core.config import MENConfig
from app.services.men_system import MENSystem


class TestMENSystemQuery:
    """Test the full query pipeline."""

    @pytest.mark.asyncio
    async def test_query_returns_expected_fields(self, mock_men_system):
        result = await mock_men_system.query(
            user_input="¿Qué dice la ley sobre arrendamientos?",
            tenant_id="tenant-test",
            session_id="s1",
        )
        assert "response" in result
        assert "domain" in result
        assert "session_id" in result
        assert "tenant_id" in result
        assert result["tenant_id"] == "tenant-test"
        assert result["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_query_calls_orchestrator(self, mock_men_system):
        await mock_men_system.query(
            user_input="Consulta legal",
            tenant_id="t1",
        )
        mock_men_system.orchestrator.route.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_calls_modeler(self, mock_men_system):
        await mock_men_system.query(
            user_input="Consulta legal",
            tenant_id="t1",
        )
        mock_men_system.llm_modeler.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_tenant_schema(self, mock_men_system):
        result = await mock_men_system.query(
            user_input="¿Cuántos contratos tiene ACME?",
            tenant_id="tenant-test",
            tenant_schema={
                "tenant_name": "TestCorp",
                "document_types": ["contrato", "factura"],
                "known_clients": ["ACME"],
            },
        )
        assert result["response"]

    @pytest.mark.asyncio
    async def test_query_domain_none_skips_expert(self, mock_men_system):
        mock_men_system.orchestrator.route.return_value = ["none"]
        result = await mock_men_system.query(
            user_input="Hola",
            tenant_id="t1",
        )
        assert result["has_expert_data"] is False
        assert result["expert_used"] is None


class TestMENSystemDecide:
    """Test classification-only endpoint."""

    @pytest.mark.asyncio
    async def test_decide_returns_domain_and_confidence(self, mock_men_system):
        result = await mock_men_system.decide("¿Es legal este contrato?")
        assert result["domain"] == "legal"
        assert 0 <= result["confidence"] <= 1
        assert isinstance(result["requires_expert"], bool)


class TestMENSystemSessions:
    """Test session history management."""

    @pytest.mark.asyncio
    async def test_session_history_after_query(self, mock_men_system):
        await mock_men_system.query(
            user_input="Primera pregunta",
            tenant_id="t1",
            session_id="sess-1",
        )
        history = mock_men_system.get_session_history("t1", "sess-1")
        assert len(history) == 2  # user + assistant
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_clear_session(self, mock_men_system):
        await mock_men_system.query(
            user_input="Pregunta",
            tenant_id="t1",
            session_id="sess-2",
        )
        cleared = mock_men_system.clear_session("t1", "sess-2")
        assert cleared is True
        history = mock_men_system.get_session_history("t1", "sess-2")
        assert len(history) == 0

    def test_clear_nonexistent_session(self, mock_men_system):
        cleared = mock_men_system.clear_session("t1", "no-existe")
        assert cleared is False


class TestMENSystemStatus:
    """Test status reporting."""

    def test_status_when_loaded(self, mock_men_system):
        status = mock_men_system.get_status()
        assert status["loaded"] is True
        assert status["modeler_enabled"] is True
        assert status["experts_enabled"] is True
        assert isinstance(status["loaded_experts"], list)
        assert isinstance(status["active_sessions"], int)

    def test_is_loaded_property(self, mock_men_system):
        assert mock_men_system.is_loaded is True


class TestMENSystemHelpers:
    """Test internal helper methods."""

    def test_infer_doc_type_from_query(self, mock_men_system):
        schema = {"document_types": ["contrato", "factura"]}
        result = mock_men_system._infer_doc_type(
            "Revisar el contrato de ACME", schema
        )
        assert result == "contrato"

    def test_infer_doc_type_no_match(self, mock_men_system):
        schema = {"document_types": ["contrato", "factura"]}
        result = mock_men_system._infer_doc_type("Hola mundo", schema)
        assert result is None

    def test_infer_doc_type_no_schema(self, mock_men_system):
        result = mock_men_system._infer_doc_type("Hola", None)
        assert result is None

    def test_format_tenant_context(self, mock_men_system):
        schema = {
            "tenant_name": "TestCorp",
            "document_types": ["contrato"],
            "known_clients": ["ACME"],
            "terminology": {"NDA": "Non-Disclosure Agreement"},
        }
        ctx = mock_men_system._format_tenant_context(schema)
        assert "TestCorp" in ctx
        assert "contrato" in ctx
        assert "ACME" in ctx
        assert "NDA" in ctx

    def test_format_tenant_context_empty(self, mock_men_system):
        ctx = mock_men_system._format_tenant_context({})
        assert ctx is None
