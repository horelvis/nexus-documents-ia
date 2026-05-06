"""
Tests for ContradictionDetector — TrustGraph batch contradiction detection.

Tests edge-metadata storage (has_contradiction property on :Rel edges).
Requires a running FalkorDB instance (uses falkordb_client fixture from conftest.py).
"""

import pytest

from app.services.contradiction import ContradictionDetector
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


COLLECTION = "col-contradiction-tests"


async def _seed_juan_contradicting_salaries(store: TripleStore) -> str:
    subject_uri = await store.store_triple(
        subject_name="Juan Pérez",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="30000 EUR",
        object_is_node=False,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-001",
    )
    await store.store_triple(
        subject_name="Juan Pérez",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="28000 EUR",
        object_is_node=False,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-002",
    )
    return subject_uri


async def _seed_maria_same_salary(store: TripleStore) -> str:
    subject_uri = await store.store_triple(
        subject_name="María López",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="25000 EUR",
        object_is_node=False,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-010",
    )
    await store.store_triple(
        subject_name="María López",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="25000 EUR",
        object_is_node=False,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-011",
    )
    return subject_uri


class TestContradictionDetection:
    @pytest.mark.asyncio
    async def test_detects_contradiction(self, falkordb_client):
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)
        subject_uri = await _seed_juan_contradicting_salaries(store)
        contradictions = await detector.detect_for_subject(subject_uri)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert c["predicate"] == URIBuilder.predicate("fiscal", "salario-anual")
        assert set([c["value_a"], c["value_b"]]) == {"30000 EUR", "28000 EUR"}
        assert c["rel_a_id"] is not None
        assert c["rel_b_id"] is not None

    @pytest.mark.asyncio
    async def test_marks_edges_with_contradiction_metadata(self, falkordb_client):
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)
        subject_uri = await _seed_juan_contradicting_salaries(store)
        count = await detector.detect_and_mark(subject_uri)
        assert count == 1

        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $uri})-[r:Rel]->(o:Literal) "
            "WHERE r.has_contradiction = true "
            "RETURN r.contradiction_with AS other_id, o.value AS val",
            {"uri": subject_uri},
        )
        assert len(rows) == 2
        values = {row["val"] for row in rows}
        assert values == {"30000 EUR", "28000 EUR"}

        c_nodes = await falkordb_client.execute_cypher(
            "MATCH (n:Node) WHERE n.uri STARTS WITH 'nouxcube://contradiction/' RETURN n"
        )
        assert len(c_nodes) == 0, "Contradictions must be edge metadata, not :Node triples"

    @pytest.mark.asyncio
    async def test_no_contradiction_when_same_value(self, falkordb_client):
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)
        subject_uri = await _seed_maria_same_salary(store)
        contradictions = await detector.detect_for_subject(subject_uri)
        assert contradictions == []
