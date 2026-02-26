"""
Tests: SmartSearch Internals per Sector

Validates scope detection, Spanish stemming expansion, and multi-signal
re-ranking with sector-specific weights.

Mostly sync tests. Async tests mock Weaviate/KnowledgeTree clients.
"""

import math
from datetime import datetime, timezone, timedelta

import pytest

from app.agents.langgraph.tools.smart_search import (
    _expand_query_spanish,
    _rerank_results,
    _LEGISLATION_KEYWORDS,
    _DOCUMENT_KEYWORDS,
    SmartSearchTool,
)
from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS
from tests.sector_helpers import reset_sector_singleton, reset_tool_registry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_between_tests():
    yield
    reset_sector_singleton("")
    reset_tool_registry()


# =============================================================================
# Scope Detection
# =============================================================================


class TestScopeDetection:
    """Verify SmartSearch._detect_scope() routes queries correctly."""

    @pytest.fixture
    def tool(self):
        return SmartSearchTool()

    def test_explicit_documents_scope(self, tool):
        """scope='documents' → only documents, no legislation."""
        docs, legis = tool._detect_scope("documents", "anything", {})
        assert docs is True
        assert legis is False

    def test_explicit_legislation_scope(self, tool):
        """scope='legislation' → only legislation, no documents."""
        docs, legis = tool._detect_scope("legislation", "anything", {})
        assert docs is False
        assert legis is True

    def test_explicit_all_scope(self, tool):
        """scope='all' → both documents and legislation."""
        docs, legis = tool._detect_scope("all", "anything", {})
        assert docs is True
        assert legis is True

    def test_auto_legislation_keywords(self, tool):
        """Queries with legislation keywords should detect legislation scope."""
        docs, legis = tool._detect_scope("auto", "legislación vigente sobre IRPF", {})
        assert legis is True

    def test_auto_legislation_with_entity(self, tool):
        """Queries with legal entity (ley) should detect legislation scope."""
        docs, legis = tool._detect_scope("auto", "consulta general", {"ley": ["3/2018"]})
        assert legis is True

    def test_auto_document_keywords(self, tool):
        """Queries with document keywords should detect document scope."""
        docs, legis = tool._detect_scope("auto", "mis facturas pendientes", {})
        assert docs is True

    def test_auto_both_scopes(self, tool):
        """Queries mixing document + legislation keywords → both scopes."""
        docs, legis = tool._detect_scope(
            "auto", "facturas según el artículo 12", {"articulo": ["12"]}
        )
        assert docs is True
        assert legis is True

    def test_auto_default_documents(self, tool):
        """Ambiguous queries default to documents scope."""
        docs, legis = tool._detect_scope("auto", "dame información", {})
        assert docs is True
        assert legis is False

    def test_legislation_keywords_coverage(self):
        """Ensure key legislation keywords exist in the set."""
        assert "ley" in _LEGISLATION_KEYWORDS
        assert "artículo" in _LEGISLATION_KEYWORDS
        assert "boe" in _LEGISLATION_KEYWORDS
        assert "real decreto" in _LEGISLATION_KEYWORDS

    def test_document_keywords_coverage(self):
        """Ensure key document keywords exist in the set."""
        assert "factura" in _DOCUMENT_KEYWORDS
        assert "contrato" in _DOCUMENT_KEYWORDS
        assert "nómina" in _DOCUMENT_KEYWORDS
        assert "expediente" in _DOCUMENT_KEYWORDS


# =============================================================================
# Spanish Stemming Expansion
# =============================================================================


class TestSpanishStemming:
    """Verify _expand_query_spanish() adds stem variants for BM25 recall."""

    def test_facturas_expansion(self):
        """'facturas' should expand to include 'factura'."""
        result = _expand_query_spanish("facturas")
        assert "facturas" in result
        assert "factura" in result

    def test_contratos_expansion(self):
        """'contratos' should expand to include 'contrato'."""
        result = _expand_query_spanish("contratos")
        assert "contratos" in result
        assert "contrato" in result

    def test_nominas_expansion(self):
        """'nóminas' should expand to include 'nomina'."""
        result = _expand_query_spanish("nóminas")
        assert "nóminas" in result
        assert "nomina" in result

    def test_vigentes_expansion(self):
        """Adjective 'vigentes' should expand to 'vigente'."""
        result = _expand_query_spanish("vigentes")
        assert "vigentes" in result
        assert "vigente" in result

    def test_firmados_expansion(self):
        """Participle 'firmados' should expand to 'firma'."""
        result = _expand_query_spanish("firmados")
        assert "firmados" in result
        assert "firma" in result

    def test_no_duplicate_expansion(self):
        """Same word shouldn't produce duplicate stems."""
        result = _expand_query_spanish("factura")
        words = result.split()
        assert len(words) == len(set(words)), f"Duplicate stems in: {result}"

    def test_short_word_no_crash(self):
        """Short words shouldn't crash the stemmer."""
        result = _expand_query_spanish("ley")
        assert "ley" in result

    def test_multi_word_expansion(self):
        """Multi-word query should expand each word independently."""
        result = _expand_query_spanish("facturas pendientes firmadas")
        assert "factura" in result  # facturas → factura
        assert "pendiente" in result  # pendientes → pendiente
        assert "firma" in result  # firmadas → firma

    def test_unknown_word_passes_through(self):
        """Unknown words pass through (possibly with Snowball stem)."""
        result = _expand_query_spanish("NouxCubeIA")
        assert "NouxCubeIA" in result


# =============================================================================
# Multi-Signal Re-Ranking per Sector
# =============================================================================


class TestReRankBySector:
    """Verify re-ranking applies sector-specific weights correctly."""

    @staticmethod
    def _make_result(
        doc_id: str = "doc1",
        score: float = 0.8,
        quality_score: float = 0.5,
        title: str = "Test",
        created_at: str = "",
        **extra,
    ) -> dict:
        """Build a minimal search result dict."""
        result = {
            "document_id": doc_id,
            "score": score,
            "quality_score": quality_score,
            "title": title,
            "created_at": created_at,
        }
        result.update(extra)
        return result

    def test_rerank_uses_sector_weights(self, sector):
        """Re-ranking should use the sector's configured weights."""
        name, config = sector
        weights = config.rerank_weights

        results = [
            self._make_result(doc_id="a", score=0.9, quality_score=0.3),
            self._make_result(doc_id="b", score=0.5, quality_score=0.9),
        ]

        reranked = _rerank_results(results, set(), {}, weights)
        # Both should have _rerank_score set
        assert all("_rerank_score" in r for r in reranked)

    def test_rerank_legal_graph_priority(self):
        """Legal sector's high graph weight should boost graph-matched results."""
        weights = SECTOR_CONFIGS["legal"].rerank_weights

        results = [
            self._make_result(doc_id="graph_doc", score=0.5, quality_score=0.5),
            self._make_result(doc_id="non_graph", score=0.7, quality_score=0.5),
        ]

        graph_ids = {"graph_doc"}
        reranked = _rerank_results(results, graph_ids, {}, weights)

        # graph_doc should rank higher due to legal's graph weight (0.30)
        # The graph signal adds w_graph * 1.0 = 0.30 for graph_doc
        # vs w_sim difference of only (0.7-0.5)*0.35 = 0.07 for non_graph
        assert reranked[0]["document_id"] == "graph_doc"

    def test_rerank_medical_quality_priority(self):
        """Medical sector's high quality weight should boost high-quality docs."""
        weights = SECTOR_CONFIGS["medical"].rerank_weights

        results = [
            self._make_result(doc_id="low_sim_high_qual", score=0.3, quality_score=0.9),
            self._make_result(doc_id="high_sim_low_qual", score=0.5, quality_score=0.1),
        ]

        reranked = _rerank_results(results, set(), {}, weights)

        # Medical boosts quality (0.25) — with such a large quality gap (0.9 vs 0.1),
        # the quality contribution should overcome the similarity gap
        first = reranked[0]["document_id"]
        # quality diff: 0.8 * 0.25 = 0.20, sim diff: 0.2 * 0.40 = 0.08
        assert first == "low_sim_high_qual"

    def test_rerank_documental_recency(self):
        """Documental sector weights recency higher — recent docs should rank up."""
        weights = SECTOR_CONFIGS["documental"].rerank_weights
        legal_weights = SECTOR_CONFIGS["legal"].rerank_weights

        now = datetime.now(timezone.utc)
        recent_str = (now - timedelta(days=1)).isoformat()
        old_str = (now - timedelta(days=365)).isoformat()

        results_doc = [
            self._make_result(doc_id="old", score=0.6, quality_score=0.5, created_at=old_str),
            self._make_result(doc_id="recent", score=0.6, quality_score=0.5, created_at=recent_str),
        ]
        results_legal = [
            self._make_result(doc_id="old", score=0.6, quality_score=0.5, created_at=old_str),
            self._make_result(doc_id="recent", score=0.6, quality_score=0.5, created_at=recent_str),
        ]

        reranked_doc = _rerank_results(results_doc, set(), {}, weights)
        reranked_legal = _rerank_results(results_legal, set(), {}, legal_weights)

        # In both sectors recent should rank first (same sim/quality)
        assert reranked_doc[0]["document_id"] == "recent"
        assert reranked_legal[0]["document_id"] == "recent"

        # But documental's recency gap should be larger
        doc_gap = reranked_doc[0]["_rerank_score"] - reranked_doc[1]["_rerank_score"]
        legal_gap = reranked_legal[0]["_rerank_score"] - reranked_legal[1]["_rerank_score"]
        assert doc_gap > legal_gap, "Documental should amplify recency gap more than legal"

    def test_none_safe_scoring(self):
        """Results with score=None should not crash re-ranking."""
        weights = SECTOR_CONFIGS["legal"].rerank_weights
        results = [
            {"document_id": "x", "score": None, "quality_score": None, "title": "T"},
        ]
        reranked = _rerank_results(results, set(), {}, weights)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_entity_match_boosts_score(self):
        """Results matching query entities should get higher entity signal."""
        weights = SECTOR_CONFIGS["legal"].rerank_weights

        results = [
            self._make_result(
                doc_id="match", score=0.5, quality_score=0.5,
                title="Contrato García", associated_person="María García",
            ),
            self._make_result(
                doc_id="no_match", score=0.5, quality_score=0.5,
                title="Acta reunión", associated_person="Otro",
            ),
        ]

        entities = {"persona": ["María García"]}
        reranked = _rerank_results(results, set(), entities, weights)
        assert reranked[0]["document_id"] == "match"


# =============================================================================
# Sector-Specific Search Config
# =============================================================================


class TestSectorSearchConfig:
    """Verify each sector's search parameters are properly exposed."""

    def test_legal_uses_correct_alpha(self):
        """Legal sector should use hybrid_alpha=0.7."""
        config = SECTOR_CONFIGS["legal"]
        assert config.hybrid_alpha == 0.7

    def test_medical_uses_correct_alpha(self):
        """Medical sector should use hybrid_alpha=0.6."""
        config = SECTOR_CONFIGS["medical"]
        assert config.hybrid_alpha == 0.6

    def test_documental_uses_correct_alpha(self):
        """Documental sector should use hybrid_alpha=0.5."""
        config = SECTOR_CONFIGS["documental"]
        assert config.hybrid_alpha == 0.5

    def test_rerank_weights_exist(self, sector):
        """All sectors must have rerank_weights configured."""
        _, config = sector
        assert config.rerank_weights is not None
        assert isinstance(config.rerank_weights, dict)
        assert len(config.rerank_weights) == 5
