"""
Tests for Orchestrator – domain classification component.

The actual model is NOT loaded; we test initialization, domain
extraction, alias resolution, and state management.
"""

import pytest

from app.services.orchestrator import Orchestrator


class TestOrchestratorInit:
    """Test initialization and state."""

    def test_default_domains(self):
        orch = Orchestrator()
        assert "legal" in orch.domains
        assert "contract" in orch.domains
        assert "general" in orch.domains
        assert "none" in orch.domains

    def test_custom_domains(self):
        orch = Orchestrator(domains=["custom1", "custom2"])
        assert orch.domains == ["custom1", "custom2"]

    def test_not_loaded_initially(self):
        orch = Orchestrator()
        assert orch.is_loaded is False

    def test_unload_when_not_loaded(self):
        orch = Orchestrator()
        orch.unload()  # should not raise
        assert orch.is_loaded is False


class TestDomainExtraction:
    """Test _extract_domain parsing logic."""

    @pytest.fixture(autouse=True)
    def _orch(self):
        self.orch = Orchestrator()

    def test_exact_match(self):
        assert self.orch._extract_domain("legal") == "legal"
        assert self.orch._extract_domain("contract") == "contract"
        assert self.orch._extract_domain("compliance") == "compliance"
        assert self.orch._extract_domain("finance") == "finance"
        assert self.orch._extract_domain("hr") == "hr"
        assert self.orch._extract_domain("technical") == "technical"
        assert self.orch._extract_domain("general") == "general"
        assert self.orch._extract_domain("none") == "none"

    def test_spanish_aliases(self):
        assert self.orch._extract_domain("contratos") == "contract"
        assert self.orch._extract_domain("contrato") == "contract"
        assert self.orch._extract_domain("juridico") == "legal"
        assert self.orch._extract_domain("jurídico") == "legal"
        assert self.orch._extract_domain("cumplimiento") == "compliance"
        assert self.orch._extract_domain("financiero") == "finance"
        assert self.orch._extract_domain("finanzas") == "finance"
        assert self.orch._extract_domain("recursos humanos") == "hr"
        assert self.orch._extract_domain("rrhh") == "hr"
        assert self.orch._extract_domain("técnico") == "technical"
        assert self.orch._extract_domain("tecnico") == "technical"

    def test_embedded_in_sentence(self):
        assert self.orch._extract_domain("el dominio es legal") == "legal"
        assert self.orch._extract_domain("clasificado como contract") == "contract"

    def test_unknown_falls_to_general(self):
        assert self.orch._extract_domain("unknown_xyz") == "general"
        assert self.orch._extract_domain("") == "general"

    def test_case_insensitive(self):
        assert self.orch._extract_domain("LEGAL") == "legal"
        assert self.orch._extract_domain("Contract") == "contract"


class TestClassificationPrompt:
    """Test that the classification prompt template is valid."""

    def test_prompt_has_placeholder(self):
        assert "{query}" in Orchestrator.CLASSIFICATION_PROMPT

    def test_prompt_formats_correctly(self):
        prompt = Orchestrator.CLASSIFICATION_PROMPT.format(query="test query")
        assert "test query" in prompt
        assert "{query}" not in prompt
