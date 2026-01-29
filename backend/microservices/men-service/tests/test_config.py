"""
Tests for MEN service configuration.
"""

import os

import pytest


class TestSettings:
    """Test Settings class loads correctly from environment."""

    def test_default_values(self):
        from app.core.config import Settings

        s = Settings()
        assert s.service_name == "men-service"
        assert s.service_port == 8010
        assert s.men_enabled is True
        assert s.modeler_enabled is True
        assert s.experts_enabled is True
        assert s.orchestrator_model == "Qwen/Qwen2.5-1.5B-Instruct"
        assert s.llm_modeler_model == "Qwen/Qwen2.5-3B-Instruct"
        assert s.expert_base_model == "Qwen/Qwen2.5-0.5B-Instruct"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MEN_ENABLED", "false")
        monkeypatch.setenv("MEN_MODELER_MAX_TOKENS", "1024")

        from app.core.config import Settings

        s = Settings()
        assert s.men_enabled is False
        assert s.llm_modeler_max_tokens == 1024


class TestMENConfig:
    """Test MENConfig dataclass."""

    def test_defaults(self):
        from app.core.config import MENConfig

        c = MENConfig()
        assert c.orchestrator_confidence_threshold == 0.6
        assert c.llm_modeler_history_turns == 5
        assert c.unload_experts_after_query is True
        assert "legal" in c.domains
        assert "general" in c.domains

    def test_from_settings(self):
        from app.core.config import MENConfig, Settings

        s = Settings()
        c = MENConfig.from_settings(s)
        assert c.orchestrator_model == s.orchestrator_model
        assert c.llm_modeler_model == s.llm_modeler_model
        assert c.experts_dir == s.experts_dir
        assert c.modeler_enabled == s.modeler_enabled


class TestVRAMEstimates:
    """Test VRAM constants."""

    def test_estimates_present(self):
        from app.core.config import VRAM_ESTIMATES

        assert VRAM_ESTIMATES["orchestrator"] == 1.5
        assert VRAM_ESTIMATES["modeler"] == 2.5
        assert VRAM_ESTIMATES["expert"] == 0.5
        assert VRAM_ESTIMATES["base_total"] == 4.0
        assert VRAM_ESTIMATES["peak_total"] == 5.0
