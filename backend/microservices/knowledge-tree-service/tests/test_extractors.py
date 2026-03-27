"""
Tests for TrustGraph LLM extractors.

All tests mock _call_llm — no real SGLang calls are made.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.extractors.definitions import DefinitionsExtractor
from app.services.extractors.relationships import RelationshipsExtractor
from app.services.extractors.objects import ObjectsExtractor
from app.services.extractors.topics import TopicsExtractor


SAMPLE_CHUNK = "Juan García trabaja en Empresa ABC S.L. con un salario bruto de 3000€ mensuales."


# ---------------------------------------------------------------------------
# DefinitionsExtractor
# ---------------------------------------------------------------------------


class TestDefinitionsExtractor:
    """Tests for DefinitionsExtractor."""

    @pytest.mark.asyncio
    async def test_parses_llm_output(self):
        """Two entities → 4 triples (label + definition each)."""
        mock_json = json.dumps([
            {"entity": "Contrato de Trabajo", "definition": "Acuerdo entre empleador y trabajador"},
            {"entity": "Salario", "definition": "Retribución económica del trabajador"},
        ])
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 4

        labels = [t for t in triples if t["predicate_name"] == "label"]
        definitions = [t for t in triples if t["predicate_name"] == "definition"]
        assert len(labels) == 2
        assert len(definitions) == 2

        # Check structure
        for t in triples:
            assert t["predicate_ontology"] == "core"
            assert t["extraction_method"] == "llm_definitions"
            assert t["object_is_node"] is False
            assert len(t["source_chunk"]) <= 200

        # Check subjects
        subjects = {t["subject"] for t in triples}
        assert "Contrato de Trabajo" in subjects
        assert "Salario" in subjects

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        """Empty array → empty list."""
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="[]")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        """Non-JSON output → empty list (no exception raised)."""
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="not json at all")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []

    @pytest.mark.asyncio
    async def test_handles_wrapped_dict(self):
        """Wrapped JSON dict with 'results' key is unwrapped correctly."""
        mock_json = json.dumps({
            "results": [
                {"entity": "Empresa", "definition": "Organización mercantil"},
            ]
        })
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert len(triples) == 2  # label + definition


# ---------------------------------------------------------------------------
# RelationshipsExtractor
# ---------------------------------------------------------------------------


class TestRelationshipsExtractor:
    """Tests for RelationshipsExtractor."""

    @pytest.mark.asyncio
    async def test_parses_entity_relationships(self):
        """Two relationships (one entity object, one literal) → 2 triples."""
        mock_json = json.dumps([
            {
                "subject": "Juan García",
                "predicate": "empleado-de",
                "object": "Empresa ABC S.L.",
                "object-entity": True,
            },
            {
                "subject": "Contrato",
                "predicate": "salario-bruto",
                "object": "3000",
                "object-entity": False,
            },
        ])
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 2

        # First triple — entity relationship
        t0 = triples[0]
        assert t0["subject"] == "Juan García"
        assert t0["predicate_name"] == "empleado-de"
        assert t0["predicate_ontology"] == "legal"
        assert t0["object"] == "Empresa ABC S.L."
        assert t0["object_is_node"] is True
        assert t0["extraction_method"] == "llm_relationships"

        # Second triple — literal value
        t1 = triples[1]
        assert t1["predicate_name"] == "salario-bruto"
        assert t1["predicate_ontology"] == "legal"
        assert t1["object_is_node"] is False

    @pytest.mark.asyncio
    async def test_uses_mini_ontology_predicates(self):
        """Prompt must contain known extractable predicates (prov excluded)."""
        extractor = RelationshipsExtractor()
        prompt = extractor._build_prompt(SAMPLE_CHUNK)

        assert "empleado-de" in prompt
        assert "firmante-de" in prompt
        assert "regulado-por" in prompt
        assert "modifica" in prompt
        # prov predicates are system-only — NOT shown to LLM
        assert "timestamp" not in prompt
        assert "chunk-text" not in prompt

    @pytest.mark.asyncio
    async def test_prov_predicate_rejected_from_extraction(self):
        """'derived-from' (prov) is system-only — rejected from LLM extraction."""
        mock_json = json.dumps([
            {
                "subject": "Doc A",
                "predicate": "derived-from",
                "object": "Doc B",
                "object-entity": True,
            }
        ])
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        # prov predicates are system-only — not extractable by LLM
        assert len(triples) == 0

    @pytest.mark.asyncio
    async def test_unknown_predicate_rejected(self):
        """Unknown predicate → rejected (not stored)."""
        mock_json = json.dumps([
            {
                "subject": "A",
                "predicate": "some-custom-predicate",
                "object": "B",
                "object-entity": False,
            }
        ])
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 0

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="[]")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []


# ---------------------------------------------------------------------------
# ObjectsExtractor
# ---------------------------------------------------------------------------


class TestObjectsExtractor:
    """Tests for ObjectsExtractor."""

    @pytest.mark.asyncio
    async def test_parses_named_entities(self):
        """Two entities → 4 triples (label + type each)."""
        mock_json = json.dumps([
            {"name": "Juan García", "type": "person"},
            {"name": "Empresa ABC S.L.", "type": "organization"},
        ])
        extractor = ObjectsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 4

        labels = [t for t in triples if t["predicate_name"] == "label"]
        types = [t for t in triples if t["predicate_name"] == "type"]
        assert len(labels) == 2
        assert len(types) == 2

        # Check structure
        for t in triples:
            assert t["predicate_ontology"] == "core"
            assert t["extraction_method"] == "llm_objects"
            assert t["object_is_node"] is False

        # Check objects for type triples
        type_objects = {t["object"] for t in types}
        assert "person" in type_objects
        assert "organization" in type_objects

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        extractor = ObjectsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="[]")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        extractor = ObjectsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="bad json {")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []

    @pytest.mark.asyncio
    async def test_skips_entities_without_name(self):
        """Items without 'name' key are silently skipped."""
        mock_json = json.dumps([
            {"type": "person"},  # no name
            {"name": "Empresa XYZ", "type": "organization"},
        ])
        extractor = ObjectsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert len(triples) == 2  # only Empresa XYZ


# ---------------------------------------------------------------------------
# TopicsExtractor
# ---------------------------------------------------------------------------


class TestTopicsExtractor:
    """Tests for TopicsExtractor."""

    @pytest.mark.asyncio
    async def test_parses_topics(self):
        """Two topics → 2 triples with predicate_name='has-topic'."""
        mock_json = json.dumps([
            {"topic": "derecho laboral"},
            {"topic": "contrato de trabajo"},
        ])
        extractor = TopicsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 2

        for t in triples:
            assert t["predicate_name"] == "has-topic"
            assert t["predicate_ontology"] == "core"
            assert t["extraction_method"] == "llm_topics"
            assert t["subject"] == ""  # coordinator sets document_uri
            assert t["object_is_node"] is False

        topic_values = {t["object"] for t in triples}
        assert "derecho laboral" in topic_values
        assert "contrato de trabajo" in topic_values

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        extractor = TopicsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="[]")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        extractor = TopicsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value="not json")):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert triples == []

    @pytest.mark.asyncio
    async def test_skips_empty_topics(self):
        """Items with empty topic string are skipped."""
        mock_json = json.dumps([
            {"topic": ""},
            {"topic": "protección de datos"},
        ])
        extractor = TopicsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)
        assert len(triples) == 1
        assert triples[0]["object"] == "protección de datos"

    @pytest.mark.asyncio
    async def test_source_chunk_truncated_to_200(self):
        """source_chunk in triples is at most 200 characters."""
        long_chunk = "x" * 500
        mock_json = json.dumps([{"topic": "derecho"}])
        extractor = TopicsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(long_chunk)
        assert len(triples) == 1
        assert len(triples[0]["source_chunk"]) == 200


# ---------------------------------------------------------------------------
# __init__.py exports
# ---------------------------------------------------------------------------


class TestExtractorsPackage:
    """Sanity-check that the package exports all 4 extractors."""

    def test_package_exports(self):
        from app.services.extractors import (
            DefinitionsExtractor,
            ObjectsExtractor,
            RelationshipsExtractor,
            TopicsExtractor,
        )
        assert DefinitionsExtractor.EXTRACTOR_NAME == "definitions"
        assert RelationshipsExtractor.EXTRACTOR_NAME == "relationships"
        assert ObjectsExtractor.EXTRACTOR_NAME == "objects"
        assert TopicsExtractor.EXTRACTOR_NAME == "topics"
