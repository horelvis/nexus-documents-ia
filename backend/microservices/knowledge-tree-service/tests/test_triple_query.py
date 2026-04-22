"""
Tests for TripleQuery — SPO query service for TrustGraph.

Requires a running FalkorDB instance (uses falkordb_client fixture from conftest.py).
"""

import pytest
import pytest_asyncio

from app.services.triple_query import TripleQuery
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_T1 = "tenant-1"
USER_T2 = "tenant-2"
COLLECTION = "col-test"


# ---------------------------------------------------------------------------
# Shared seed helpers
# ---------------------------------------------------------------------------


async def seed_base_graph(store: TripleStore, user: str, collection: str) -> dict:
    """Seed Juan García + ACME Corp with standard triples.

    Returns a dict of useful URIs for assertions.
    """
    # Juan García — type=person, label, empleado-de→ACME Corp
    juan_uri = await store.store_triple(
        subject_name="Juan García López",
        predicate_ontology="core",
        predicate_name="type",
        object_value="person",
        object_is_node=False,
        user=user,
        collection=collection,
        extraction_method="ner",
        source_chunk="chunk-001",
    )
    await store.store_triple(
        subject_name="Juan García López",
        predicate_ontology="core",
        predicate_name="label",
        object_value="Juan García López",
        object_is_node=False,
        user=user,
        collection=collection,
        extraction_method="system",
    )
    await store.store_triple(
        subject_name="Juan García López",
        predicate_ontology="legal",
        predicate_name="empleado-de",
        object_value="ACME Corp",
        object_is_node=True,
        user=user,
        collection=collection,
        extraction_method="llm",
        source_chunk="chunk-002",
    )

    # ACME Corp — type=organization, label
    acme_uri = await store.store_triple(
        subject_name="ACME Corp",
        predicate_ontology="core",
        predicate_name="type",
        object_value="organization",
        object_is_node=False,
        user=user,
        collection=collection,
        extraction_method="ner",
    )
    await store.store_triple(
        subject_name="ACME Corp",
        predicate_ontology="core",
        predicate_name="label",
        object_value="ACME Corp SL",
        object_is_node=False,
        user=user,
        collection=collection,
        extraction_method="system",
    )

    return {
        "juan_uri": juan_uri,
        "acme_uri": acme_uri,
        "type_pred": URIBuilder.predicate("core", "type"),
        "label_pred": URIBuilder.predicate("core", "label"),
        "empleado_pred": URIBuilder.predicate("legal", "empleado-de"),
    }


# ---------------------------------------------------------------------------
# TestSPOQueries
# ---------------------------------------------------------------------------


class TestSPOQueries:
    """Tests for the 8 SPO query patterns."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, falkordb_client):
        """Seed base graph before each test in this class."""
        store = TripleStore(falkordb_client)
        self.query = TripleQuery(falkordb_client)
        self.uris = await seed_base_graph(store, USER_T1, COLLECTION)

    @pytest.mark.asyncio
    async def test_query_by_subject(self):
        """Juan should have >= 3 triples (type, label, empleado-de)."""
        results = await self.query.by_subject(
            subject_uri=self.uris["juan_uri"],
            user=USER_T1,
            collection=COLLECTION,
        )
        assert len(results) >= 3

        # All triples must reference Juan as subject
        for triple in results:
            assert triple["subject"] == self.uris["juan_uri"]
            assert triple["predicate"] is not None
            assert triple["object"] is not None
            assert triple["object_type"] in ("node", "literal")

    @pytest.mark.asyncio
    async def test_query_by_predicate(self):
        """core/type predicate should return >= 2 triples (person, organization)."""
        results = await self.query.by_predicate(
            predicate_uri=self.uris["type_pred"],
            user=USER_T1,
            collection=COLLECTION,
        )
        assert len(results) >= 2

        object_values = [r["object"] for r in results]
        assert "person" in object_values
        assert "organization" in object_values

    @pytest.mark.asyncio
    async def test_query_by_object_literal(self):
        """Querying literal value 'person' should return Juan."""
        results = await self.query.by_object_value(
            value="person",
            user=USER_T1,
            collection=COLLECTION,
        )
        assert len(results) >= 1

        subjects = [r["subject"] for r in results]
        assert self.uris["juan_uri"] in subjects

        # All object_type must be literal
        for triple in results:
            assert triple["object_type"] == "literal"
            assert triple["object"] == "person"

    @pytest.mark.asyncio
    async def test_query_spo(self):
        """Exact S-P-O: Juan + core/type should yield exactly 'person'."""
        results = await self.query.by_spo(
            subject_uri=self.uris["juan_uri"],
            predicate_uri=self.uris["type_pred"],
            user=USER_T1,
            collection=COLLECTION,
        )
        assert len(results) == 1
        assert results[0]["object"] == "person"
        assert results[0]["object_type"] == "literal"

    @pytest.mark.asyncio
    async def test_query_neighbors(self):
        """Juan's 1-hop neighbors should include ACME Corp."""
        results = await self.query.neighbors(
            uri=self.uris["juan_uri"],
            user=USER_T1,
            max_hops=1,
            limit=50,
        )
        neighbor_uris = [r["uri"] for r in results]
        assert self.uris["acme_uri"] in neighbor_uris

    @pytest.mark.asyncio
    async def test_query_by_object_node(self):
        """Inbound query on ACME should return Juan as subject."""
        results = await self.query.by_object_node(
            object_uri=self.uris["acme_uri"],
            user=USER_T1,
            collection=COLLECTION,
        )
        assert len(results) >= 1
        subjects = [r["subject"] for r in results]
        assert self.uris["juan_uri"] in subjects

        for triple in results:
            assert triple["object_type"] == "node"
            assert triple["object"] == self.uris["acme_uri"]

    @pytest.mark.asyncio
    async def test_query_by_predicate_object_literal(self):
        """by_predicate_object: core/type → 'organization' should return ACME."""
        results = await self.query.by_predicate_object(
            predicate_uri=self.uris["type_pred"],
            object_value="organization",
            user=USER_T1,
            object_is_node=False,
        )
        assert len(results) >= 1
        subjects = [r["subject"] for r in results]
        assert self.uris["acme_uri"] in subjects

    @pytest.mark.asyncio
    async def test_query_by_predicate_object_node(self):
        """by_predicate_object (node): legal/empleado-de → ACME should return Juan."""
        results = await self.query.by_predicate_object(
            predicate_uri=self.uris["empleado_pred"],
            object_value=self.uris["acme_uri"],
            user=USER_T1,
            object_is_node=True,
        )
        assert len(results) >= 1
        subjects = [r["subject"] for r in results]
        assert self.uris["juan_uri"] in subjects

    @pytest.mark.asyncio
    async def test_query_by_subject_predicate_delegates(self):
        """by_subject_predicate delegates to by_spo, same results."""
        spo_results = await self.query.by_spo(
            subject_uri=self.uris["juan_uri"],
            predicate_uri=self.uris["type_pred"],
            user=USER_T1,
        )
        sp_results = await self.query.by_subject_predicate(
            subject_uri=self.uris["juan_uri"],
            predicate_uri=self.uris["type_pred"],
            user=USER_T1,
        )
        assert spo_results == sp_results


# ---------------------------------------------------------------------------
# TestTenantContext
# ---------------------------------------------------------------------------


class TestTenantContext:
    """Tests for get_stats and build_context."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, falkordb_client):
        store = TripleStore(falkordb_client)
        self.query = TripleQuery(falkordb_client)
        self.uris = await seed_base_graph(store, USER_T1, COLLECTION)

        # Add a document node mentioning Juan
        doc_uri = await store.store_document_node(
            document_id="doc-tq-001",
            user=USER_T1,
            collection=COLLECTION,
            title="Contrato de Trabajo",
            file_path="/docs/contratos/ct001.pdf",
            semantic_type="contrato",
        )
        # mentioned-in triple: Juan → document (node)
        await store.store_triple(
            subject_name="Juan García López",
            predicate_ontology="core",
            predicate_name="mentioned-in",
            object_value="doc-tq-001",
            object_is_node=False,  # store doc_id as literal for simplicity
            user=USER_T1,
            collection=COLLECTION,
            extraction_method="ner",
            source_chunk="chunk-003",
        )
        self.doc_uri = doc_uri

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """get_stats should report nodes >= 2, literals >= 1, rels >= 1."""
        stats = await self.query.get_stats(user=USER_T1, collection=COLLECTION)

        assert isinstance(stats, dict)
        assert "nodes" in stats
        assert "literals" in stats
        assert "rels" in stats

        assert stats["nodes"] >= 2, f"Expected >= 2 nodes, got {stats['nodes']}"
        assert stats["literals"] >= 1, f"Expected >= 1 literals, got {stats['literals']}"
        assert stats["rels"] >= 1, f"Expected >= 1 rels, got {stats['rels']}"

    @pytest.mark.asyncio
    async def test_build_context(self):
        """build_context should return a non-empty string with expected sections."""
        context = await self.query.build_context(user=USER_T1, limit=20)

        assert isinstance(context, str)
        assert len(context) > 0

        # Should contain the header
        assert "Knowledge Graph Context" in context
        # Should contain entity type info
        assert "person" in context or "organization" in context
        # Should contain some entity name or URI
        assert "connections" in context


# ---------------------------------------------------------------------------
# TestTenantIsolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Tests that queries do not cross tenant boundaries."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, falkordb_client):
        store = TripleStore(falkordb_client)
        self.query = TripleQuery(falkordb_client)

        # Tenant 1: Juan García
        self.t1_uris = await seed_base_graph(store, USER_T1, COLLECTION)

        # Tenant 2: María Fernández (different entity, same collection name)
        self.t2_maria_uri = await store.store_triple(
            subject_name="María Fernández",
            predicate_ontology="core",
            predicate_name="type",
            object_value="person",
            object_is_node=False,
            user=USER_T2,
            collection=COLLECTION,
            extraction_method="ner",
        )

    @pytest.mark.asyncio
    async def test_different_tenants_isolated(self):
        """Tenant 1 queries should not return tenant 2 data and vice versa."""
        # T1 by_predicate should see Juan + ACME (core/type results)
        t1_results = await self.query.by_predicate(
            predicate_uri=self.t1_uris["type_pred"],
            user=USER_T1,
            collection=COLLECTION,
        )
        t1_subjects = {r["subject"] for r in t1_results}

        # T1 results must NOT contain María's URI
        assert self.t2_maria_uri not in t1_subjects

        # T2 by_predicate should only see María
        t2_results = await self.query.by_predicate(
            predicate_uri=self.t1_uris["type_pred"],
            user=USER_T2,
            collection=COLLECTION,
        )
        t2_subjects = {r["subject"] for r in t2_results}

        # T2 results must NOT contain Juan or ACME
        assert self.t1_uris["juan_uri"] not in t2_subjects
        assert self.t1_uris["acme_uri"] not in t2_subjects

        # T2 must contain María
        assert self.t2_maria_uri in t2_subjects

    @pytest.mark.asyncio
    async def test_by_subject_isolation(self):
        """by_subject for T2's María should not see Juan's triples."""
        results = await self.query.by_subject(
            subject_uri=self.t2_maria_uri,
            user=USER_T2,
            collection=COLLECTION,
        )
        # All returned triples must have María as subject, not Juan
        for triple in results:
            assert triple["subject"] == self.t2_maria_uri

        # Querying Juan's URI under T2 should return nothing
        results_cross = await self.query.by_subject(
            subject_uri=self.t1_uris["juan_uri"],
            user=USER_T2,
            collection=COLLECTION,
        )
        assert len(results_cross) == 0

    @pytest.mark.asyncio
    async def test_get_stats_isolation(self):
        """get_stats for each tenant should return only their own counts."""
        t1_stats = await self.query.get_stats(user=USER_T1, collection=COLLECTION)
        t2_stats = await self.query.get_stats(user=USER_T2, collection=COLLECTION)

        # T1 has Juan + ACME + literals for both
        assert t1_stats["nodes"] >= 2
        # T2 has only María
        assert t2_stats["nodes"] >= 1
        # T2 should have fewer nodes than T1
        assert t2_stats["nodes"] < t1_stats["nodes"]
