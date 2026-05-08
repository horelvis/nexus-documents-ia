"""
Tests for TripleStore — TrustGraph core CRUD layer.

Requires a running FalkorDB instance (uses falkordb_client fixture from conftest.py).
"""

import pytest
import pytest_asyncio

from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder
from app.services.provenance import ProvenanceService

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_store(falkordb_client) -> TripleStore:
    return TripleStore(falkordb_client)


# ---------------------------------------------------------------------------
# TestMergeNode
# ---------------------------------------------------------------------------

class TestMergeNode:
    @pytest.mark.asyncio
    async def test_creates_node(self, falkordb_client):
        """merge_node creates a :Node that can be matched by URI."""
        store = _make_store(falkordb_client)
        uri = URIBuilder.entity("col1", "Juan García")
        await store.merge_node(uri, collection="col1")

        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n",
            params={"uri": uri},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_merge_idempotent(self, falkordb_client):
        """Two merges with the same URI produce exactly one :Node."""
        store = _make_store(falkordb_client)
        uri = URIBuilder.entity("col1", "ACME SA")
        await store.merge_node(uri, collection="col1")
        await store.merge_node(uri, collection="col1")

        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri, collection: $col}) RETURN count(n) AS cnt",
            params={"uri": uri, "col": "col1"},
        )
        assert rows[0]["cnt"] == 1


# ---------------------------------------------------------------------------
# TestMergeLiteral
# ---------------------------------------------------------------------------

class TestMergeLiteral:
    @pytest.mark.asyncio
    async def test_creates_literal(self, falkordb_client):
        """merge_literal creates a :Literal node in the graph."""
        store = _make_store(falkordb_client)
        await store.merge_literal("person", collection="col1")

        rows = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: $val, collection: $col}) RETURN l",
            params={"val": "person", "col": "col1"},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_dedup_same_value(self, falkordb_client):
        """Two merges with identical (value, collection) produce one :Literal."""
        store = _make_store(falkordb_client)
        await store.merge_literal("document", collection="col1")
        await store.merge_literal("document", collection="col1")

        rows = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: $val, collection: $col}) RETURN count(l) AS cnt",
            params={"val": "document", "col": "col1"},
        )
        assert rows[0]["cnt"] == 1

    @pytest.mark.asyncio
    async def test_different_collections_separate(self, falkordb_client):
        """Same value for different collections produces two separate :Literal nodes."""
        store = _make_store(falkordb_client)
        await store.merge_literal("contrato", collection="col1")
        await store.merge_literal("contrato", collection="col2")

        rows = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: $val}) RETURN count(l) AS cnt",
            params={"val": "contrato"},
        )
        assert rows[0]["cnt"] == 2


# ---------------------------------------------------------------------------
# TestCreateRel
# ---------------------------------------------------------------------------

class TestCreateRel:
    @pytest.mark.asyncio
    async def test_creates_relationship_node_to_literal(self, falkordb_client):
        """create_rel connects a :Node to a :Literal via a :Rel edge."""
        store = _make_store(falkordb_client)
        col = "col1"

        subject_uri = URIBuilder.entity(col, "Juan")
        predicate_uri = URIBuilder.predicate("core", "type")
        literal_val = "person"

        await store.merge_node(subject_uri, collection=col)
        await store.merge_literal(literal_val, collection=col)
        await store.create_rel(
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_value=literal_val,
            collection=col,
            object_is_node=False,
            extraction_method="ner",
            source_chunk="chunk-001",
        )

        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s_uri})-[r:Rel]->(o:Literal {value: $val}) RETURN r",
            params={"s_uri": subject_uri, "val": literal_val},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_rel_to_node(self, falkordb_client):
        """create_rel connects a :Node to another :Node, preserving extraction metadata."""
        store = _make_store(falkordb_client)
        col = "col1"

        subject_uri = URIBuilder.entity(col, "Juan")
        object_uri = URIBuilder.entity(col, "ACME SA")
        predicate_uri = URIBuilder.predicate("legal", "empleado-de")

        await store.merge_node(subject_uri, collection=col)
        await store.merge_node(object_uri, collection=col)
        await store.create_rel(
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_value=object_uri,
            collection=col,
            object_is_node=True,
            extraction_method="llm",
            source_chunk="chunk-042",
        )

        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s_uri})-[r:Rel]->(o:Node {uri: $o_uri}) "
            "RETURN r.extraction_method AS method, r.source_chunk AS chunk",
            params={"s_uri": subject_uri, "o_uri": object_uri},
        )
        assert len(rows) == 1
        assert rows[0]["method"] == "llm"
        assert rows[0]["chunk"] == "chunk-042"


# ---------------------------------------------------------------------------
# TestStoreTriple
# ---------------------------------------------------------------------------

class TestStoreTriple:
    @pytest.mark.asyncio
    async def test_store_entity_type_triple(self, falkordb_client):
        """store_triple creates (Juan)-[:Rel core/type]->(Literal 'person')."""
        store = _make_store(falkordb_client)
        col = "col1"

        subject_uri = await store.store_triple(
            subject_name="Juan García",
            predicate_ontology="core",
            predicate_name="type",
            object_value="person",
            object_is_node=False,
            collection=col,
            extraction_method="ner",
            source_chunk="chunk-001",
        )

        # Verify returned URI is canonical
        expected_uri = URIBuilder.entity(col, "Juan García")
        assert subject_uri == expected_uri

        # Verify graph structure
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s_uri})-[r:Rel]->(o:Literal {value: 'person'}) RETURN r",
            params={"s_uri": expected_uri},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_store_entity_to_entity_triple(self, falkordb_client):
        """store_triple creates (Juan)-[:Rel legal/empleado-de]->(ACME) as Node→Node."""
        store = _make_store(falkordb_client)
        col = "col1"

        subject_uri = await store.store_triple(
            subject_name="Juan",
            predicate_ontology="legal",
            predicate_name="empleado-de",
            object_value="ACME SA",
            object_is_node=True,
            collection=col,
            extraction_method="llm",
            source_chunk="chunk-007",
        )

        expected_subject = URIBuilder.entity(col, "Juan")
        expected_object = URIBuilder.entity(col, "ACME SA")
        expected_predicate = URIBuilder.predicate("legal", "empleado-de")

        assert subject_uri == expected_subject

        # Both nodes must exist
        for uri in (expected_subject, expected_object):
            rows = await falkordb_client.execute_cypher(
                "MATCH (n:Node {uri: $uri}) RETURN n",
                params={"uri": uri},
            )
            assert len(rows) == 1, f"Node not found: {uri}"

        # Relationship must exist with correct predicate URI
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s_uri})-[r:Rel {uri: $p_uri}]->(o:Node {uri: $o_uri}) RETURN r",
            params={
                "s_uri": expected_subject,
                "o_uri": expected_object,
                "p_uri": expected_predicate,
            },
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# TestStoreDocumentNode
# ---------------------------------------------------------------------------

class TestStoreDocumentNode:
    @pytest.mark.asyncio
    async def test_creates_document_with_metadata(self, falkordb_client):
        """store_document_node creates doc :Node with core/type, core/label triples."""
        store = _make_store(falkordb_client)
        col = "col1"

        doc_uri = await store.store_document_node(
            document_id="doc-001",
            collection=col,
            title="Contrato de Trabajo",
            file_path="/docs/contratos/ct001.pdf",
            semantic_type="contrato",
        )

        expected_uri = URIBuilder.document(col, "doc-001")
        assert doc_uri == expected_uri

        # Document node exists
        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n",
            params={"uri": expected_uri},
        )
        assert len(rows) == 1

        # core/type literal exists
        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri})-[:Rel]->(l:Literal {value: 'document'}) RETURN l",
            params={"uri": expected_uri},
        )
        assert len(rows) == 1

        # core/label literal exists
        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri})-[:Rel]->(l:Literal {value: 'Contrato de Trabajo'}) RETURN l",
            params={"uri": expected_uri},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_document_contained_in_folder(self, falkordb_client):
        """store_document_node creates a contained-in edge to a folder :Node."""
        store = _make_store(falkordb_client)
        col = "col1"

        doc_uri = await store.store_document_node(
            document_id="doc-002",
            collection=col,
            title="Nómina Enero",
            file_path="/docs/nominas/nom001.pdf",
        )

        folder_uri = URIBuilder.folder(col, "/docs/nominas")
        predicate_uri = URIBuilder.predicate("core", "contained-in")

        rows = await falkordb_client.execute_cypher(
            "MATCH (d:Node {uri: $doc_uri})-[r:Rel {uri: $p_uri}]->(f:Node {uri: $folder_uri}) RETURN r",
            params={"doc_uri": doc_uri, "p_uri": predicate_uri, "folder_uri": folder_uri},
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# TestClearOperations
# ---------------------------------------------------------------------------

class TestClearOperations:
    @pytest.mark.asyncio
    async def test_clear_collection(self, falkordb_client):
        """clear_collection removes all nodes/literals for a given collection."""
        store = _make_store(falkordb_client)
        col = "col1"

        await store.merge_node(URIBuilder.entity(col, "Entity A"), collection=col)
        await store.merge_literal("some value", collection=col)

        await store.clear_collection(collection=col)

        rows = await falkordb_client.execute_cypher(
            "MATCH (n) WHERE (n:Node OR n:Literal) AND n.collection = $col "
            "RETURN count(n) AS cnt",
            params={"col": col},
        )
        assert rows[0]["cnt"] == 0

    @pytest.mark.asyncio
    async def test_clear_collection_isolates_other_collections(self, falkordb_client):
        """clear_collection does not affect nodes in other collections."""
        store = _make_store(falkordb_client)

        await store.merge_node(URIBuilder.entity("col1", "Entity A"), collection="col1")
        await store.merge_node(URIBuilder.entity("col2", "Entity B"), collection="col2")

        await store.clear_collection(collection="col1")

        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {collection: $col}) RETURN count(n) AS cnt",
            params={"col": "col2"},
        )
        assert rows[0]["cnt"] == 1

    @pytest.mark.asyncio
    async def test_clear_scope(self, falkordb_client):
        """clear_scope removes all nodes across all collections."""
        store = _make_store(falkordb_client)

        await store.merge_node(URIBuilder.entity("col1", "Entity A"), collection="col1")
        await store.merge_node(URIBuilder.entity("col2", "Entity B"), collection="col2")

        await store.clear_scope()

        rows = await falkordb_client.execute_cypher(
            "MATCH (n) WHERE (n:Node OR n:Literal) RETURN count(n) AS cnt",
            params={},
        )
        assert rows[0]["cnt"] == 0


# ---------------------------------------------------------------------------
# TestProvenance
# ---------------------------------------------------------------------------

class TestProvenance:
    @pytest.mark.asyncio
    async def test_creates_extraction_node(self, falkordb_client):
        """record_extraction creates an extraction :Node with 6 provenance triples."""
        store = _make_store(falkordb_client)
        prov = ProvenanceService(store)
        doc_uri = URIBuilder.document("default", "doc-1")
        await store.merge_node(uri=doc_uri, collection="default")
        ext_uri = await prov.record_extraction(
            document_uri=doc_uri,
            extraction_method="llm_relationships",
            model_name="Qwen3.5-9B",
            chunk_text="Juan García trabaja en ACME Corp desde 2020.",
            chunk_offset=1500,
            collection="default",
        )
        assert ext_uri.startswith("nouxcube://extraction/")
        # Verify provenance triples
        result = await falkordb_client.execute_cypher(
            "MATCH (e:Node {uri: $uri})-[r:Rel]->(o) "
            "RETURN r.uri AS pred, CASE WHEN o:Node THEN o.uri ELSE o.value END AS obj",
            {"uri": ext_uri},
        )
        preds = {r["pred"]: r["obj"] for r in result}
        assert preds["nouxcube://predicate/prov/derived-from"] == doc_uri
        assert preds["nouxcube://predicate/prov/method"] == "llm_relationships"
        assert preds["nouxcube://predicate/prov/model"] == "Qwen3.5-9B"
        assert "Juan García" in preds["nouxcube://predicate/prov/chunk-text"]
        assert preds["nouxcube://predicate/prov/chunk-offset"] == "1500"


# ---------------------------------------------------------------------------
# TestBatchStoreTriples
# ---------------------------------------------------------------------------

class TestBatchStoreTriples:
    @pytest.mark.asyncio
    async def test_batch_stores_node_and_literal_triples(self, falkordb_client):
        store = _make_store(falkordb_client)
        triples = [
            {
                "s_uri": "nouxcube://entity/col/juan",
                "o_uri": "nouxcube://entity/col/empresa",
                "p_uri": "nouxcube://predicate/legal/empleado-de",
                "object_is_entity": True,
                "method": "llm_relationships",
                "chunk": "chunk-001",
            },
            {
                "s_uri": "nouxcube://entity/col/contrato",
                "o_val": "3000 EUR",
                "p_uri": "nouxcube://predicate/legal/salario-bruto",
                "object_is_entity": False,
                "method": "llm_relationships",
                "chunk": "chunk-001",
            },
        ]
        await store.batch_store_triples(triples, collection="col")

        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s})-[r:Rel]->(o:Node {uri: $o}) RETURN r.uri AS p",
            {"s": "nouxcube://entity/col/juan", "o": "nouxcube://entity/col/empresa"},
        )
        assert len(rows) == 1

        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s})-[r:Rel]->(o:Literal {value: $v}) RETURN r.uri AS p",
            {"s": "nouxcube://entity/col/contrato", "v": "3000 EUR"},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, falkordb_client):
        store = _make_store(falkordb_client)
        result = await store.batch_store_triples([], collection="col")
        assert result == 0
