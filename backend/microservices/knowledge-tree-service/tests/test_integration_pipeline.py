"""
Integration test — full extraction pipeline with mocked LLM calls.

Verifies the complete path:
  chunks → 4 extractors → triple store → provenance → contradictions → queryable graph

Uses a real FalkorDB instance (falkordb_client fixture) but patches each
extractor's _call_llm method so no SGLang calls are made. The parsing logic
in _parse_output() runs for real — only the HTTP call is mocked.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.triple_store import TripleStore
from app.services.triple_query import TripleQuery
from app.services.uri_builder import URIBuilder


# ---------------------------------------------------------------------------
# Test data — Spanish employment contract
# ---------------------------------------------------------------------------

CONTRACT_CHUNKS = [
    """Contrato de trabajo entre D. Juan García López (DNI: 12345678A),
    en adelante el TRABAJADOR, y la empresa TechCorp SL (CIF: B87654321),
    en adelante la EMPRESA, para el puesto de Abogado Senior en el
    Departamento Legal. Salario bruto anual: 30.000 EUR.""",

    """El presente contrato se rige por el Real Decreto Legislativo 2/2015,
    de 23 de octubre, por el que se aprueba el texto refundido de la Ley
    del Estatuto de los Trabajadores. Fecha de inicio: 01/02/2025.
    Jornada completa de 40 horas semanales.""",
]

# Mock LLM outputs per chunk — keyed on keyword in chunk text

_CHUNK1_DEFINITIONS = json.dumps([
    {"entity": "Juan García López", "definition": "Abogado Senior en TechCorp SL"},
    {"entity": "TechCorp SL", "definition": "Empresa tecnológica"},
])

_CHUNK1_RELATIONSHIPS = json.dumps([
    {
        "subject": "Juan García López",
        "predicate": "empleado-de",
        "object": "TechCorp SL",
        "object-entity": True,
    },
    {
        "subject": "Juan García López",
        "predicate": "salario-bruto",
        "object": "30000 EUR",
        "object-entity": False,
    },
])

_CHUNK1_OBJECTS = json.dumps([
    {"name": "Juan García López", "type": "person"},
    {"name": "TechCorp SL", "type": "organization"},
])

_CHUNK1_TOPICS = json.dumps([
    {"topic": "derecho laboral"},
    {"topic": "contratación"},
])

_CHUNK2_DEFINITIONS = json.dumps([
    {"entity": "Estatuto de los Trabajadores", "definition": "Ley laboral básica de España"},
])

_CHUNK2_RELATIONSHIPS = json.dumps([
    {
        "subject": "contrato",
        "predicate": "regulado-por",
        "object": "Estatuto de los Trabajadores",
        "object-entity": True,
    },
    {
        "subject": "Juan García López",
        "predicate": "vigente-desde",
        "object": "01/02/2025",
        "object-entity": False,
    },
])

_CHUNK2_OBJECTS = json.dumps([
    {"name": "Estatuto de los Trabajadores", "type": "law"},
])

_CHUNK2_TOPICS = json.dumps([
    {"topic": "legislación laboral"},
])


# ---------------------------------------------------------------------------
# Mock side_effect factories
# ---------------------------------------------------------------------------

def _make_definitions_mock():
    async def _side_effect(prompt: str) -> str:
        if "TechCorp" in prompt or "Abogado" in prompt or "TRABAJADOR" in prompt:
            return _CHUNK1_DEFINITIONS
        return _CHUNK2_DEFINITIONS
    return _side_effect


def _make_relationships_mock():
    async def _side_effect(prompt: str) -> str:
        if "TechCorp" in prompt or "Abogado" in prompt or "TRABAJADOR" in prompt:
            return _CHUNK1_RELATIONSHIPS
        return _CHUNK2_RELATIONSHIPS
    return _side_effect


def _make_objects_mock():
    async def _side_effect(prompt: str) -> str:
        if "TechCorp" in prompt or "Abogado" in prompt or "TRABAJADOR" in prompt:
            return _CHUNK1_OBJECTS
        return _CHUNK2_OBJECTS
    return _side_effect


def _make_topics_mock():
    async def _side_effect(prompt: str) -> str:
        if "TechCorp" in prompt or "Abogado" in prompt or "TRABAJADOR" in prompt:
            return _CHUNK1_TOPICS
        return _CHUNK2_TOPICS
    return _side_effect


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFullPipeline:
    async def test_extract_contract(self, falkordb_client):
        """End-to-end pipeline: 2 chunks → 4 extractors → graph + query."""

        # 1. Create coordinator
        store = TripleStore(falkordb_client)
        coordinator = ExtractionCoordinator(store)

        # 2. Patch all 4 extractors' _call_llm with side_effect functions
        with (
            patch.object(
                coordinator._definitions,
                "_call_llm",
                new=AsyncMock(side_effect=_make_definitions_mock()),
            ),
            patch.object(
                coordinator._relationships,
                "_call_llm",
                new=AsyncMock(side_effect=_make_relationships_mock()),
            ),
            patch.object(
                coordinator._objects,
                "_call_llm",
                new=AsyncMock(side_effect=_make_objects_mock()),
            ),
            patch.object(
                coordinator._topics,
                "_call_llm",
                new=AsyncMock(side_effect=_make_topics_mock()),
            ),
        ):
            # 3. Run full document extraction
            result = await coordinator.extract_document(
                chunks=CONTRACT_CHUNKS,
                document_id="contract-integration-001",

                collection="legal",
                title="Contrato TechCorp - Juan García López",
                file_path="/docs/legal/contract-001.pdf",
                semantic_type="contrato",
            )

        # 4. Assert top-level success
        assert result["success"] is True, f"Extraction failed: {result.get('errors')}"

        # 5. Assert sufficient triples created (across both chunks)
        assert result["triples_created"] > 10, (
            f"Expected >10 triples, got {result['triples_created']}. "
            f"Errors: {result.get('errors')}"
        )

        # 6. Assert both chunks were processed
        assert result["chunks_processed"] == 2

        # 7. Verify graph contents via TripleQuery
        query = TripleQuery(falkordb_client)

        # 7a. get_stats: meaningful number of nodes and relationships
        stats = await query.get_stats(collection="legal")
        assert stats["nodes"] >= 3, f"Expected >=3 nodes, got {stats['nodes']}"
        assert stats["rels"] >= 5, f"Expected >=5 rels, got {stats['rels']}"

        # 7b. Juan García López has core/type = "person"
        juan_uri = URIBuilder.entity("legal", "Juan García López")
        type_pred_uri = URIBuilder.predicate("core", "type")
        type_triples = await query.by_spo(
            subject_uri=juan_uri,
            predicate_uri=type_pred_uri,

            collection="legal",
        )
        assert len(type_triples) >= 1, (
            f"Expected Juan García López to have a core/type triple, got {type_triples}"
        )
        type_values = {t["object"] for t in type_triples}
        assert "person" in type_values, (
            f"Expected type='person' for Juan García López, got {type_values}"
        )

        # 7c. Document node exists with core/label
        doc_uri = result["document_uri"]
        label_pred_uri = URIBuilder.predicate("core", "label")
        doc_label_triples = await query.by_spo(
            subject_uri=doc_uri,
            predicate_uri=label_pred_uri,

            collection="legal",
        )
        assert len(doc_label_triples) >= 1, (
            f"Expected document node {doc_uri} to have a core/label triple"
        )

        # 7d. Topics linked to document
        has_topic_pred_uri = URIBuilder.predicate("core", "has-topic")
        topic_triples = await query.by_spo(
            subject_uri=doc_uri,
            predicate_uri=has_topic_pred_uri,

            collection="legal",
        )
        assert len(topic_triples) >= 1, (
            f"Expected at least one has-topic triple for document {doc_uri}"
        )
        topic_values = {t["object"] for t in topic_triples}
        # At least one known topic should be present
        known_topics = {"derecho laboral", "contratación", "legislación laboral"}
        assert topic_values & known_topics, (
            f"Expected at least one known topic in {topic_values}"
        )

        # 8. Verify context can be built: build_context returns string with content
        context = await query.build_context()
        assert isinstance(context, str)
        assert len(context) > 0, "build_context returned empty string"
        assert "Knowledge Graph Context" in context, (
            f"Expected '## Knowledge Graph Context' header in context output"
        )
