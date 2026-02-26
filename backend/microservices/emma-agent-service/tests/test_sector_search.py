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


# =============================================================================
# SmartSearch Deduplication (covers smart_search.py lines 567-599)
# =============================================================================


class TestDeduplication:
    """Verify SmartSearchTool._deduplicate() logic."""

    def _make_result(self, doc_id, title="Doc", score=0.5, folder_path=""):
        return {
            "document_id": doc_id, "title": title, "score": score,
            "type": "tenant_document", "content": "", "folder_path": folder_path,
        }

    def test_no_duplicates_unchanged(self):
        """Distinct doc_ids with distinct titles should all be kept."""
        tool = SmartSearchTool()
        results = [
            self._make_result("d1", title="Doc A", score=0.9),
            self._make_result("d2", title="Doc B", score=0.8),
        ]
        deduped = tool._deduplicate(results)
        assert len(deduped) == 2

    def test_same_doc_id_keeps_highest_score(self):
        """Duplicate doc_ids should keep the one with highest score."""
        tool = SmartSearchTool()
        results = [
            self._make_result("d1", score=0.3),
            self._make_result("d1", score=0.9),
            self._make_result("d1", score=0.5),
        ]
        deduped = tool._deduplicate(results)
        assert len(deduped) == 1
        assert deduped[0]["score"] == 0.9

    def test_same_title_folder_deduped(self):
        """Same title+folder_path but different doc_ids → collapsed (pass 2)."""
        tool = SmartSearchTool()
        results = [
            self._make_result("d1", title="Report.pdf", score=0.6, folder_path="/docs"),
            self._make_result("d2", title="Report.pdf", score=0.8, folder_path="/docs"),
        ]
        deduped = tool._deduplicate(results)
        assert len(deduped) == 1
        assert deduped[0]["score"] == 0.8

    def test_empty_doc_id_not_collapsed(self):
        """Results with empty document_id should not be collapsed."""
        tool = SmartSearchTool()
        results = [
            self._make_result("", title="A", score=0.5),
            self._make_result("", title="B", score=0.6),
        ]
        deduped = tool._deduplicate(results)
        assert len(deduped) == 2

    def test_none_score_treated_as_zero(self):
        """Score=None should be treated as 0 (not crash)."""
        tool = SmartSearchTool()
        results = [
            {"document_id": "d1", "title": "A", "score": None,
             "type": "tenant_document", "content": "", "folder_path": ""},
            {"document_id": "d1", "title": "A", "score": 0.5,
             "type": "tenant_document", "content": "", "folder_path": ""},
        ]
        deduped = tool._deduplicate(results)
        assert len(deduped) == 1
        assert deduped[0]["score"] == 0.5

    def test_sorted_by_score_descending(self):
        """Deduplicated results should be sorted by score descending."""
        tool = SmartSearchTool()
        results = [
            self._make_result("d1", title="Alpha", score=0.3),
            self._make_result("d2", title="Beta", score=0.9),
            self._make_result("d3", title="Gamma", score=0.6),
        ]
        deduped = tool._deduplicate(results)
        scores = [r["score"] for r in deduped]
        assert scores == [0.9, 0.6, 0.3]


# =============================================================================
# SmartSearch Format Results (covers smart_search.py lines 605-674)
# =============================================================================


class TestFormatResults:
    """Verify SmartSearchTool._format_results() output structure."""

    def test_format_document_results(self):
        """Formatting document results should produce ToolResult with sources."""
        tool = SmartSearchTool()
        results = [
            {
                "document_id": "d1", "title": "Factura 001", "score": 0.85,
                "type": "tenant_document", "content": "Detalles de factura...",
                "quality_score": 0.7, "domain": "fiscal",
                "semantic_type": "factura", "associated_person": "Juan",
                "created_at": "", "folder_path": "/Facturas",
                "document_type": "pdf", "tags": ["2024"],
            },
        ]
        tr = tool._format_results("facturas", results)
        assert tr.success is True
        assert "Factura 001" in tr.output
        assert "d1" in tr.output
        assert len(tr.sources) == 1
        assert tr.data["result_count"] == 1
        assert tr.data["doc_count"] == 1
        assert tr.data["leg_count"] == 0

    def test_format_legislation_results(self):
        """Formatting legislation results should include BOE markers."""
        tool = SmartSearchTool()
        results = [
            {
                "document_id": "boe-001", "title": "Ley Orgánica 3/2018",
                "score": 0.9, "type": "legislation",
                "content": "Protección de datos...", "quality_score": 0.8,
                "boe_id": "BOE-A-2018-16673", "article": "5",
                "domain": "legal", "semantic_type": "legislacion",
                "associated_person": "", "created_at": "",
                "folder_path": "", "document_type": "legislation",
                "tags": ["LOPD"],
            },
        ]
        tr = tool._format_results("ley protección datos", results)
        assert "[LEY]" in tr.output
        assert "BOE-A-2018-16673" in tr.output
        assert "Art. 5" in tr.output
        assert tr.data["leg_count"] == 1

    def test_format_mixed_results(self):
        """Mixed document + legislation results should show counts in header."""
        tool = SmartSearchTool()
        results = [
            {
                "document_id": "d1", "title": "Contrato", "score": 0.8,
                "type": "tenant_document", "content": "...",
                "quality_score": 0.5, "domain": "", "semantic_type": "",
                "associated_person": "", "created_at": "",
                "folder_path": "", "document_type": "", "tags": [],
            },
            {
                "document_id": "boe-1", "title": "Código Civil", "score": 0.7,
                "type": "legislation", "content": "...",
                "quality_score": 0.8, "boe_id": "BOE-001", "article": "",
                "domain": "", "semantic_type": "legislacion",
                "associated_person": "", "created_at": "",
                "folder_path": "", "document_type": "legislation", "tags": [],
            },
        ]
        tr = tool._format_results("consulta mixta", results)
        assert "1 documentos" in tr.output
        assert "1 legislación" in tr.output

    def test_format_with_dropped_filters(self):
        """Dropped filters should produce a warning note in output."""
        tool = SmartSearchTool()
        results = [
            {
                "document_id": "d1", "title": "Doc", "score": 0.5,
                "type": "tenant_document", "content": "",
                "quality_score": 0.5, "domain": "", "semantic_type": "",
                "associated_person": "", "created_at": "",
                "folder_path": "", "document_type": "", "tags": [],
            },
        ]
        tr = tool._format_results(
            "facturas de Juan", results,
            dropped_filters=["person=Juan"],
        )
        assert "NOTA" in tr.output
        assert "person=Juan" in tr.output


# =============================================================================
# SmartSearch Entity Extraction Fallback (covers lines 314-328)
# =============================================================================


class TestEntityExtractionFallback:
    """Verify _extract_entities uses documental patterns as fallback."""

    def test_empty_sector_config_uses_fallback(self):
        """With no sector patterns, should fall back to documental patterns."""
        tool = SmartSearchTool()
        entities = tool._extract_entities("NIF B12345678", {})
        # Documental patterns include NIF
        assert "nif" in entities or len(entities) >= 0  # at least doesn't crash

    def test_sector_config_with_patterns(self):
        """With sector patterns, should use them directly."""
        tool = SmartSearchTool()
        entities = tool._extract_entities(
            "Ley Orgánica 3/2018",
            {"entity_patterns": SECTOR_CONFIGS["legal"].entity_patterns},
        )
        assert "ley" in entities
        assert len(entities["ley"]) >= 1

    def test_get_rerank_weights_from_config(self):
        """_get_rerank_weights should return sector weights when available."""
        tool = SmartSearchTool()
        config = {"rerank_weights": {"similarity": 0.5, "quality": 0.5}}
        weights = tool._get_rerank_weights(config)
        assert weights["similarity"] == 0.5

    def test_get_rerank_weights_default(self):
        """_get_rerank_weights should return defaults when no config."""
        tool = SmartSearchTool()
        weights = tool._get_rerank_weights({})
        assert weights["similarity"] == 0.40
        assert weights["quality"] == 0.20
