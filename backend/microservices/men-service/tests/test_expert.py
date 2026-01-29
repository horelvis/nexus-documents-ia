"""
Tests for MicroLLMExpert – domain-specific knowledge component.

The actual model is NOT loaded; we test initialization, domain
descriptions, prompt templates, and state management.
"""

import pytest

from app.services.expert import MicroLLMExpert


class TestExpertInit:
    """Test initialization and defaults."""

    def test_default_values(self):
        e = MicroLLMExpert(domain="legal")
        assert e.domain == "legal"
        assert e.base_model == "Qwen/Qwen2.5-0.5B-Instruct"
        assert e.max_tokens == 300
        assert e.is_loaded is False
        assert e.has_lora_adapter is False
        assert e.model_path is None

    def test_custom_values(self):
        e = MicroLLMExpert(
            domain="finance",
            model_path="/path/to/lora",
            base_model="custom/model",
            max_tokens=500,
        )
        assert e.domain == "finance"
        assert e.model_path == "/path/to/lora"
        assert e.base_model == "custom/model"
        assert e.max_tokens == 500


class TestDomainDescriptions:
    """Test domain → description mapping."""

    def test_known_domains(self):
        for domain, expected in [
            ("legal", "derecho y legislación"),
            ("contract", "contratos y acuerdos comerciales"),
            ("compliance", "cumplimiento normativo y auditorías"),
            ("finance", "finanzas y contabilidad empresarial"),
            ("hr", "recursos humanos y gestión de personal"),
            ("technical", "documentación técnica y sistemas"),
            ("general", "gestión documental general"),
        ]:
            e = MicroLLMExpert(domain=domain)
            assert e._get_domain_description() == expected

    def test_unknown_domain_returns_name(self):
        e = MicroLLMExpert(domain="custom_xyz")
        assert e._get_domain_description() == "custom_xyz"


class TestExpertPrompt:
    """Test prompt template."""

    def test_prompt_has_placeholders(self):
        assert "{domain}" in MicroLLMExpert.EXPERT_PROMPT
        assert "{query}" in MicroLLMExpert.EXPERT_PROMPT

    def test_prompt_formats_correctly(self):
        prompt = MicroLLMExpert.EXPERT_PROMPT.format(
            domain="derecho y legislación",
            query="¿Qué dice el artículo 1902?",
        )
        assert "derecho y legislación" in prompt
        assert "1902" in prompt
        assert "{" not in prompt


class TestExpertState:
    """Test load/unload state transitions."""

    def test_not_loaded_initially(self):
        e = MicroLLMExpert(domain="legal")
        assert e.is_loaded is False
        assert e.has_lora_adapter is False

    def test_unload_when_not_loaded(self):
        e = MicroLLMExpert(domain="legal")
        e.unload()  # should not raise
        assert e.is_loaded is False
