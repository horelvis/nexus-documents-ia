"""
Tests: Sector Configuration Integrity

Validates that sector configs (legal, medical, documental) maintain their
expected values. If someone accidentally changes hybrid_alpha, removes an
agent, or breaks a regex pattern, these tests catch it.

No async, no mocks — pure data validation.
"""

import re

import pytest

from app.agents.langgraph.sectors.config import Sector, SectorConfig
from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS


# =============================================================================
# Config Integrity
# =============================================================================


class TestSectorConfigIntegrity:
    """Validate structural invariants across all sectors."""

    def test_exactly_three_sectors_registered(self):
        assert set(SECTOR_CONFIGS.keys()) == {"legal", "medical", "documental"}

    def test_frozen_immutable(self, sector):
        _, config = sector
        with pytest.raises(AttributeError):
            config.hybrid_alpha = 0.99

    def test_sector_enum_matches_key(self, sector):
        name, config = sector
        assert config.sector.value == name

    def test_agents_not_empty(self, sector):
        _, config = sector
        assert len(config.agents) >= 1, f"{sector[0]} must have at least 1 agent"

    def test_default_agent_in_list(self, sector):
        _, config = sector
        assert config.default_agent in config.agents, (
            f"{config.default_agent} not in {config.agents}"
        )

    def test_hybrid_alpha_range(self, sector):
        _, config = sector
        assert 0.0 < config.hybrid_alpha <= 1.0

    def test_top_k_reasonable(self, sector):
        _, config = sector
        assert 5 <= config.top_k <= 30

    def test_chunk_size_greater_than_overlap(self, sector):
        _, config = sector
        assert config.chunk_size > config.chunk_overlap > 0

    def test_graph_name_not_empty(self, sector):
        _, config = sector
        assert config.graph_name, "graph_name must not be empty"

    def test_system_prompt_key_format(self, sector):
        name, config = sector
        assert config.system_prompt_key.startswith("sectors."), (
            f"Expected 'sectors.X', got '{config.system_prompt_key}'"
        )

    def test_entity_patterns_not_empty(self, sector):
        _, config = sector
        assert len(config.entity_patterns) > 0, "entity_patterns must not be empty"


# =============================================================================
# Pinned Values — catch accidental changes to production-critical params
# =============================================================================


class TestPinnedValues:
    """Pin exact values that affect RAG quality and would break if changed."""

    def test_legal_hybrid_alpha(self):
        assert SECTOR_CONFIGS["legal"].hybrid_alpha == 0.7

    def test_legal_top_k(self):
        assert SECTOR_CONFIGS["legal"].top_k == 12

    def test_legal_chunk_strategy(self):
        assert SECTOR_CONFIGS["legal"].chunk_strategy == "legal_sections"

    def test_legal_agents_count(self):
        assert len(SECTOR_CONFIGS["legal"].agents) == 7

    def test_legal_graph_name(self):
        assert SECTOR_CONFIGS["legal"].graph_name == "knowledge_graph_public"

    def test_medical_hybrid_alpha(self):
        assert SECTOR_CONFIGS["medical"].hybrid_alpha == 0.6

    def test_medical_top_k(self):
        assert SECTOR_CONFIGS["medical"].top_k == 15

    def test_medical_chunk_strategy(self):
        assert SECTOR_CONFIGS["medical"].chunk_strategy == "paragraph"

    def test_documental_hybrid_alpha(self):
        assert SECTOR_CONFIGS["documental"].hybrid_alpha == 0.5

    def test_documental_top_k(self):
        assert SECTOR_CONFIGS["documental"].top_k == 10

    def test_documental_chunk_strategy(self):
        assert SECTOR_CONFIGS["documental"].chunk_strategy == "semantic"

    def test_documental_rerank_disabled(self):
        assert SECTOR_CONFIGS["documental"].rerank_enabled is False

    def test_legal_rerank_enabled(self):
        assert SECTOR_CONFIGS["legal"].rerank_enabled is True


# =============================================================================
# Re-Rank Weights
# =============================================================================


class TestReRankWeights:
    """Validate re-ranking weight constraints."""

    EXPECTED_SIGNALS = {"similarity", "quality", "graph", "recency", "entity"}

    def test_weights_have_all_signals(self, sector):
        _, config = sector
        assert set(config.rerank_weights.keys()) == self.EXPECTED_SIGNALS

    def test_weights_sum_to_one(self, sector):
        _, config = sector
        total = sum(config.rerank_weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected ~1.0"

    def test_weights_all_positive(self, sector):
        _, config = sector
        for signal, weight in config.rerank_weights.items():
            assert weight > 0, f"{signal} weight must be positive, got {weight}"

    def test_legal_boosts_graph(self):
        """Legal sector must prioritize graph (legal precedent) with weight >= 0.25."""
        w = SECTOR_CONFIGS["legal"].rerank_weights
        assert w["graph"] >= 0.25, f"Legal graph weight {w['graph']} too low"

    def test_medical_boosts_quality(self):
        """Medical sector must prioritize quality (accuracy) with weight >= 0.20."""
        w = SECTOR_CONFIGS["medical"].rerank_weights
        assert w["quality"] >= 0.20, f"Medical quality weight {w['quality']} too low"

    def test_documental_boosts_recency(self):
        """Documental sector must weight recency higher than legal."""
        doc_w = SECTOR_CONFIGS["documental"].rerank_weights
        legal_w = SECTOR_CONFIGS["legal"].rerank_weights
        assert doc_w["recency"] > legal_w["recency"]


# =============================================================================
# Entity Pattern Compilation
# =============================================================================


class TestEntityPatterns:
    """Validate all regex patterns compile and are well-formed."""

    def test_all_patterns_compile(self, sector):
        _, config = sector
        for entity_type, patterns in config.entity_patterns.items():
            for pattern_str in patterns:
                try:
                    re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    pytest.fail(
                        f"{sector[0]}/{entity_type}: regex '{pattern_str}' "
                        f"fails to compile: {e}"
                    )

    def test_no_empty_pattern_lists(self, sector):
        _, config = sector
        for entity_type, patterns in config.entity_patterns.items():
            assert len(patterns) > 0, f"{sector[0]}/{entity_type} has empty pattern list"

    def test_legal_has_law_patterns(self):
        patterns = SECTOR_CONFIGS["legal"].entity_patterns
        assert "ley" in patterns
        assert len(patterns["ley"]) >= 3, "Legal must have ≥3 law patterns"

    def test_legal_has_article_pattern(self):
        patterns = SECTOR_CONFIGS["legal"].entity_patterns
        assert "articulo" in patterns

    def test_legal_has_sentencia_pattern(self):
        patterns = SECTOR_CONFIGS["legal"].entity_patterns
        assert "sentencia" in patterns

    def test_medical_has_cie10(self):
        patterns = SECTOR_CONFIGS["medical"].entity_patterns
        assert "cie10" in patterns

    def test_medical_has_farmaco(self):
        patterns = SECTOR_CONFIGS["medical"].entity_patterns
        assert "farmaco" in patterns

    def test_documental_has_persona(self):
        patterns = SECTOR_CONFIGS["documental"].entity_patterns
        assert "persona" in patterns

    def test_documental_has_nif(self):
        patterns = SECTOR_CONFIGS["documental"].entity_patterns
        assert "nif" in patterns

    def test_documental_has_importe(self):
        patterns = SECTOR_CONFIGS["documental"].entity_patterns
        assert "importe" in patterns


# =============================================================================
# Sector Registry Singleton — edge cases (covers registry.py lines 194-212)
# =============================================================================


class TestRegistrySingleton:
    """Cover the get_active_sector_config() singleton paths."""

    def test_cached_returns_same_config(self, sector):
        """Calling get_active_sector_config twice returns cached result."""
        name, _ = sector
        from tests.sector_helpers import reset_sector_singleton
        reset_sector_singleton(name)
        from app.agents.langgraph.sectors.registry import get_active_sector_config
        first = get_active_sector_config()
        second = get_active_sector_config()
        assert first is second
        assert first is not None
        assert first.sector.value == name

    def test_empty_sector_returns_none(self):
        """Empty ACTIVE_SECTOR → generic mode (None)."""
        from tests.sector_helpers import reset_sector_singleton
        reset_sector_singleton("")
        from app.agents.langgraph.sectors.registry import get_active_sector_config
        result = get_active_sector_config()
        assert result is None

    def test_invalid_sector_returns_none(self):
        """Invalid ACTIVE_SECTOR → fallback to None with error log."""
        from tests.sector_helpers import reset_sector_singleton
        reset_sector_singleton("invalid_sector_xyz")
        from app.agents.langgraph.sectors.registry import get_active_sector_config
        result = get_active_sector_config()
        assert result is None

    def test_valid_sector_returns_config(self):
        """Valid ACTIVE_SECTOR → returns matching SectorConfig."""
        from tests.sector_helpers import reset_sector_singleton
        reset_sector_singleton("medical")
        from app.agents.langgraph.sectors.registry import get_active_sector_config
        result = get_active_sector_config()
        assert result is not None
        assert result.sector.value == "medical"
        assert result.hybrid_alpha == 0.6


# =============================================================================
# Predictive Config
# =============================================================================


class TestPredictiveConfig:
    """Validate predictive config presence for sectors that have it."""

    def test_legal_has_predictive_config(self):
        config = SECTOR_CONFIGS["legal"]
        assert config.predictive_config is not None
        assert "contract_breach" in config.predictive_config.factor_types

    def test_predictive_config_has_disclaimer(self):
        config = SECTOR_CONFIGS["legal"]
        assert config.predictive_config.disclaimer
        assert "profesional" in config.predictive_config.disclaimer.lower()
