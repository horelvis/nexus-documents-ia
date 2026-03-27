"""
Tests for ContradictionDetector — TrustGraph batch contradiction detection.

Requires a running FalkorDB instance (uses falkordb_client fixture from conftest.py).
"""

import pytest

from app.services.contradiction import ContradictionDetector
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER = "tenant-test"
COLLECTION = "col-contradiction-tests"
SALARY_PREDICATE = "fiscal/salario-anual"


async def _seed_juan_contradicting_salaries(store: TripleStore) -> str:
    """Seed Juan with two different salary values — produces 1 contradiction."""
    # Triple 1: Juan → salary → 30000 EUR
    subject_uri = await store.store_triple(
        subject_name="Juan Pérez",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="30000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-001",
    )
    # Triple 2: Juan → salary → 28000 EUR  (different value = contradiction)
    await store.store_triple(
        subject_name="Juan Pérez",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="28000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-002",
    )
    return subject_uri


async def _seed_maria_same_salary(store: TripleStore) -> str:
    """Seed María with the same salary value twice — no contradiction expected."""
    subject_uri = await store.store_triple(
        subject_name="María López",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="25000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-010",
    )
    # Same value again — deduped literal, no contradiction
    await store.store_triple(
        subject_name="María López",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="25000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-011",
    )
    return subject_uri


# ---------------------------------------------------------------------------
# TestContradictionDetection
# ---------------------------------------------------------------------------


class TestContradictionDetection:
    @pytest.mark.asyncio
    async def test_detects_contradiction(self, falkordb_client):
        """detect_for_subject finds exactly 1 contradiction with both salary values."""
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)

        subject_uri = await _seed_juan_contradicting_salaries(store)

        contradictions = await detector.detect_for_subject(subject_uri, user=USER)

        assert len(contradictions) == 1
        c = contradictions[0]
        assert c["predicate"] == URIBuilder.predicate("fiscal", "salario-anual")
        assert set([c["value_a"], c["value_b"]]) == {"30000 EUR", "28000 EUR"}
        # Source chunks should be populated
        assert c["chunk_a"] is not None
        assert c["chunk_b"] is not None

    @pytest.mark.asyncio
    async def test_stores_contradiction_node(self, falkordb_client):
        """detect_and_store persists a :Node with a contradiction-subject edge to subject."""
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)

        subject_uri = await _seed_juan_contradicting_salaries(store)

        contradiction_uris = await detector.detect_and_store(
            subject_uri, user=USER, collection=COLLECTION
        )

        assert len(contradiction_uris) == 1
        c_uri = contradiction_uris[0]
        assert c_uri.startswith("nouxcube://contradiction/")

        # Verify :Node exists in graph
        nodes = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n",
            params={"uri": c_uri},
        )
        assert len(nodes) == 1, "Contradiction :Node must exist in graph"

        # Verify contradiction-subject edge points to original subject
        subject_pred_uri = URIBuilder.predicate("core", "contradiction-subject")
        edges = await falkordb_client.execute_cypher(
            "MATCH (c:Node {uri: $c_uri})-[r:Rel {uri: $p_uri}]->(s:Node {uri: $s_uri}) RETURN r",
            params={
                "c_uri": c_uri,
                "p_uri": subject_pred_uri,
                "s_uri": subject_uri,
            },
        )
        assert len(edges) == 1, "contradiction-subject edge must exist"

        # Verify contradiction-predicate literal exists
        predicate_pred_uri = URIBuilder.predicate("core", "contradiction-predicate")
        pred_edges = await falkordb_client.execute_cypher(
            "MATCH (c:Node {uri: $c_uri})-[r:Rel {uri: $p_uri}]->(l:Literal) RETURN l.value AS val",
            params={"c_uri": c_uri, "p_uri": predicate_pred_uri},
        )
        assert len(pred_edges) == 1
        assert pred_edges[0]["val"] == URIBuilder.predicate("fiscal", "salario-anual")

        # Verify both value literals are linked
        val_a_pred_uri = URIBuilder.predicate("core", "contradiction-value-a")
        val_b_pred_uri = URIBuilder.predicate("core", "contradiction-value-b")
        val_edges = await falkordb_client.execute_cypher(
            "MATCH (c:Node {uri: $c_uri})-[r:Rel]->(l:Literal) "
            "WHERE r.uri IN [$pa, $pb] "
            "RETURN l.value AS val",
            params={"c_uri": c_uri, "pa": val_a_pred_uri, "pb": val_b_pred_uri},
        )
        stored_vals = {row["val"] for row in val_edges}
        assert stored_vals == {"30000 EUR", "28000 EUR"}

    @pytest.mark.asyncio
    async def test_no_contradiction_when_same_value(self, falkordb_client):
        """detect_for_subject returns 0 contradictions when both triples share the same value."""
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)

        subject_uri = await _seed_maria_same_salary(store)

        contradictions = await detector.detect_for_subject(subject_uri, user=USER)

        assert contradictions == [], (
            f"Expected no contradictions for same value, got: {contradictions}"
        )
