"""
Tests for ExtractionCoordinator.

Uses a real FalkorDB instance (falkordb_client fixture).
Extractor extract() methods are mocked directly — extractor parsing
is already tested in test_extractors.py.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


SAMPLE_CHUNK = "Juan García es empleado de ACME S.L. con categoría de contrato laboral."
DOC_URI = "nouxcube://document/default/doc-001"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(falkordb_client) -> ExtractionCoordinator:
    store = TripleStore(falkordb_client)
    return ExtractionCoordinator(store)


def _label_triple(entity: str, chunk: str = SAMPLE_CHUNK) -> dict:
    """Build a definitions-style label triple."""
    return {
        "subject": entity,
        "predicate_ontology": "core",
        "predicate_name": "label",
        "object": entity,
        "object_is_node": False,
        "extraction_method": "llm_definitions",
        "source_chunk": chunk[:200],
    }


def _rel_triple(subj: str, obj: str, chunk: str = SAMPLE_CHUNK) -> dict:
    """Build a relationships-style triple (Node→Node)."""
    return {
        "subject": subj,
        "predicate_ontology": "core",
        "predicate_name": "empleado-de",
        "object": obj,
        "object_is_node": True,
        "extraction_method": "llm_relationships",
        "source_chunk": chunk[:200],
    }


def _type_triple(entity: str, type_val: str = "person", chunk: str = SAMPLE_CHUNK) -> dict:
    """Build an objects-style type triple."""
    return {
        "subject": entity,
        "predicate_ontology": "core",
        "predicate_name": "type",
        "object": type_val,
        "object_is_node": False,
        "extraction_method": "llm_objects",
        "source_chunk": chunk[:200],
    }


def _topic_triple(topic: str, chunk: str = SAMPLE_CHUNK) -> dict:
    """Build a topics-style triple (subject="" means coordinator sets it to doc URI)."""
    return {
        "subject": "",
        "predicate_ontology": "core",
        "predicate_name": "has-topic",
        "object": topic,
        "object_is_node": False,
        "extraction_method": "llm_topics",
        "source_chunk": chunk[:200],
    }


# ---------------------------------------------------------------------------
# TestCoordinator — chunk-level
# ---------------------------------------------------------------------------


class TestCoordinator:
    @pytest.mark.asyncio
    async def test_orchestrates_4_extractors(self, falkordb_client):
        """All 4 extractor mocks are called; triples are stored in the graph."""
        # Pre-create the document node so create_rel can find it
        store = TripleStore(falkordb_client)
        await store.merge_node(DOC_URI, user="t1", collection="default")

        coordinator = _make_coordinator(falkordb_client)

        with (
            patch.object(
                coordinator._definitions, "extract",
                new=AsyncMock(return_value=[_label_triple("Juan García")])
            ),
            patch.object(
                coordinator._relationships, "extract",
                new=AsyncMock(return_value=[_rel_triple("Juan García", "ACME S.L.")])
            ),
            patch.object(
                coordinator._objects, "extract",
                new=AsyncMock(return_value=[_type_triple("Juan García")])
            ),
            patch.object(
                coordinator._topics, "extract",
                new=AsyncMock(return_value=[_topic_triple("derecho laboral")])
            ),
        ):
            result = await coordinator.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="t1",
                collection="default",
            )

        assert result["extractors_run"] == 4
        # label + rel + type + topic = 4 total; deduplication may reduce
        assert result["triples_total"] == 4
        assert result["triples_deduped"] == 0
        assert result["triples_created"] >= 3  # at minimum label, type, topic stored
        assert isinstance(result["subjects"], list)
        assert len(result["errors"]) == 0
        assert result["elapsed_ms"] >= 0

        # Verify Juan García node exists
        juan_uri = URIBuilder.entity("default", "Juan García")
        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n",
            params={"uri": juan_uri},
        )
        assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_topic_triples_linked_to_document(self, falkordb_client):
        """Topic triples with subject='' are linked from document_uri, not a blank entity."""
        store = TripleStore(falkordb_client)
        doc_uri = "nouxcube://document/default/doc-topic-test"
        await store.merge_node(doc_uri, user="t1", collection="default")

        coordinator = _make_coordinator(falkordb_client)

        with (
            patch.object(coordinator._definitions, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._relationships, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._objects, "extract", new=AsyncMock(return_value=[])),
            patch.object(
                coordinator._topics, "extract",
                new=AsyncMock(return_value=[_topic_triple("fiscal")])
            ),
        ):
            result = await coordinator.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=doc_uri,
                user="t1",
                collection="default",
            )

        assert result["triples_created"] == 1
        assert result["errors"] == []

        # Verify doc_uri has a :Rel{uri: "nouxcube://pred/core/has-topic"} → Literal "fiscal"
        has_topic_uri = URIBuilder.predicate("core", "has-topic")
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $doc_uri})-[r:Rel {uri: $pred}]->(o:Literal {value: $topic}) "
            "RETURN r",
            params={"doc_uri": doc_uri, "pred": has_topic_uri, "topic": "fiscal"},
        )
        assert len(rows) == 1, (
            f"Expected a Rel from doc to 'fiscal' literal, got {rows}"
        )

    @pytest.mark.asyncio
    async def test_extractor_exception_counted_in_errors(self, falkordb_client):
        """An extractor that raises an exception is reported in errors, others still run."""
        store = TripleStore(falkordb_client)
        await store.merge_node(DOC_URI, user="t1", collection="default")

        coordinator = _make_coordinator(falkordb_client)

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("SGLang unavailable")

        with (
            patch.object(coordinator._definitions, "extract", new=AsyncMock(side_effect=_boom)),
            patch.object(coordinator._relationships, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._objects, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._topics, "extract", new=AsyncMock(return_value=[])),
        ):
            result = await coordinator.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="t1",
                collection="default",
            )

        assert result["extractors_run"] == 3
        assert len(result["errors"]) >= 1
        assert any("SGLang unavailable" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_deduplication_removes_duplicate_triples(self, falkordb_client):
        """Identical triples from different extractors are deduplicated."""
        store = TripleStore(falkordb_client)
        await store.merge_node(DOC_URI, user="t1", collection="default")

        coordinator = _make_coordinator(falkordb_client)

        # Both definitions and objects return the exact same triple
        shared_triple = _type_triple("Entity X", "concept")

        with (
            patch.object(
                coordinator._definitions, "extract",
                new=AsyncMock(return_value=[shared_triple])
            ),
            patch.object(
                coordinator._relationships, "extract",
                new=AsyncMock(return_value=[shared_triple])  # duplicate
            ),
            patch.object(coordinator._objects, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._topics, "extract", new=AsyncMock(return_value=[])),
        ):
            result = await coordinator.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="t1",
                collection="default",
            )

        assert result["triples_total"] == 2
        assert result["triples_deduped"] == 1
        assert result["triples_created"] == 1

    @pytest.mark.asyncio
    async def test_entity_linking_upgrades_literal_to_node(self, falkordb_client):
        """When RelationshipsExtractor marks an object as Literal but the
        object matches a known entity from ObjectsExtractor, the coordinator
        upgrades it to a Node→Node edge."""
        store = TripleStore(falkordb_client)
        doc_uri = "nouxcube://document/default/doc-entity-linking"
        await store.merge_node(doc_uri, user="t1", collection="default")

        coordinator = _make_coordinator(falkordb_client)

        # ObjectsExtractor creates "ACME S.L." as an entity (subject)
        obj_triple = _type_triple("ACME S.L.", "organization")

        # RelationshipsExtractor creates "Juan García" → empleado-de → "ACME S.L."
        # but INCORRECTLY marks object_is_node=False (LLM didn't recognize it)
        rel_triple = {
            "subject": "Juan García",
            "predicate_ontology": "legal",
            "predicate_name": "empleado-de",
            "object": "ACME S.L.",
            "object_is_node": False,  # ← LLM got this wrong
            "extraction_method": "llm_relationships",
            "source_chunk": SAMPLE_CHUNK[:200],
        }

        # DefinitionsExtractor creates labels for both
        label_juan = _label_triple("Juan García")
        label_acme = _label_triple("ACME S.L.")

        with (
            patch.object(
                coordinator._definitions, "extract",
                new=AsyncMock(return_value=[label_juan, label_acme])
            ),
            patch.object(
                coordinator._relationships, "extract",
                new=AsyncMock(return_value=[rel_triple])
            ),
            patch.object(
                coordinator._objects, "extract",
                new=AsyncMock(return_value=[obj_triple])
            ),
            patch.object(
                coordinator._topics, "extract",
                new=AsyncMock(return_value=[])
            ),
        ):
            result = await coordinator.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=doc_uri,
                user="t1",
                collection="default",
            )

        assert result["errors"] == []

        # Verify: the empleado-de edge should be Node→Node, not Node→Literal
        juan_uri = URIBuilder.entity("default", "Juan García")
        acme_uri = URIBuilder.entity("default", "ACME S.L.")
        empleado_pred = URIBuilder.predicate("legal", "empleado-de")

        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s})-[r:Rel {uri: $p}]->(o:Node {uri: $o}) RETURN r",
            params={"s": juan_uri, "p": empleado_pred, "o": acme_uri},
        )
        assert len(rows) == 1, (
            f"Expected Node→Node edge Juan→empleado-de→ACME, "
            f"but got {len(rows)} matches. Entity linking may have failed."
        )

    @pytest.mark.asyncio
    async def test_entity_linking_preserves_metadata_literals(self, falkordb_client):
        """Entity linking does NOT upgrade label/type/definition predicates —
        those are always Literal even if the value matches an entity name."""
        store = TripleStore(falkordb_client)
        doc_uri = "nouxcube://document/default/doc-no-upgrade"
        await store.merge_node(doc_uri, user="t1", collection="default")

        coordinator = _make_coordinator(falkordb_client)

        # "person" is both a type value AND could be normalized to match an entity
        # but type predicates should NEVER be upgraded to Node
        type_triple = _type_triple("Juan García", "person")
        label_triple = _label_triple("Juan García")

        with (
            patch.object(
                coordinator._definitions, "extract",
                new=AsyncMock(return_value=[label_triple])
            ),
            patch.object(coordinator._relationships, "extract", new=AsyncMock(return_value=[])),
            patch.object(
                coordinator._objects, "extract",
                new=AsyncMock(return_value=[type_triple])
            ),
            patch.object(coordinator._topics, "extract", new=AsyncMock(return_value=[])),
        ):
            result = await coordinator.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=doc_uri,
                user="t1",
                collection="default",
            )

        assert result["errors"] == []

        # Verify: type should still be a Literal, not a Node
        juan_uri = URIBuilder.entity("default", "Juan García")
        type_pred = URIBuilder.predicate("core", "type")
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s})-[r:Rel {uri: $p}]->(o:Literal {value: $v}) RETURN o",
            params={"s": juan_uri, "p": type_pred, "v": "person"},
        )
        assert len(rows) == 1, "type triple should remain as Literal"


# ---------------------------------------------------------------------------
# TestExtractDocument — document-level
# ---------------------------------------------------------------------------


class TestExtractDocument:
    @pytest.mark.asyncio
    async def test_processes_multiple_chunks(self, falkordb_client):
        """extract_document creates doc node and processes each chunk."""
        coordinator = _make_coordinator(falkordb_client)

        chunks = [
            "Primer párrafo del documento.",
            "Segundo párrafo con más información.",
        ]

        with (
            patch.object(coordinator._definitions, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._relationships, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._objects, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._topics, "extract", new=AsyncMock(return_value=[])),
        ):
            result = await coordinator.extract_document(
                chunks=chunks,
                document_id="doc-multi-chunk",
                user="t1",
                collection="default",
                title="Test Document",
                file_path="/docs/test/doc.pdf",
                semantic_type="contrato",
                domain="legal",
            )

        assert result["success"] is True
        assert result["chunks_processed"] == 2
        assert result["triples_created"] == 0  # no mocked triples
        assert result["contradictions_found"] == 0
        assert "document_uri" in result
        assert "nouxcube://document/" in result["document_uri"]

    @pytest.mark.asyncio
    async def test_document_node_stored_in_graph(self, falkordb_client):
        """The document :Node must exist in FalkorDB after extract_document."""
        coordinator = _make_coordinator(falkordb_client)

        with (
            patch.object(coordinator._definitions, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._relationships, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._objects, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._topics, "extract", new=AsyncMock(return_value=[])),
        ):
            result = await coordinator.extract_document(
                chunks=["Some text."],
                document_id="doc-node-verify",
                user="t1",
                collection="default",
                title="Node Verify Doc",
                file_path="/docs/node-verify.pdf",
                semantic_type="informe",
                domain="documental",
            )

        doc_uri = result["document_uri"]
        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n",
            params={"uri": doc_uri},
        )
        assert len(rows) >= 1, f"Document node {doc_uri} not found in graph"

    @pytest.mark.asyncio
    async def test_returns_aggregated_triple_count(self, falkordb_client):
        """triples_created aggregates across all chunks."""
        coordinator = _make_coordinator(falkordb_client)

        # Prepare: each chunk will produce 1 label triple for a unique entity
        async def _extract_chunk1(*_):
            return [_label_triple("Entidad Alpha")]

        async def _extract_chunk2(*_):
            return [_label_triple("Entidad Beta")]

        call_count = 0

        async def _smart_definitions(chunk_text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [_label_triple("Entidad Alpha")]
            return [_label_triple("Entidad Beta")]

        with (
            patch.object(
                coordinator._definitions, "extract",
                new=AsyncMock(side_effect=_smart_definitions)
            ),
            patch.object(coordinator._relationships, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._objects, "extract", new=AsyncMock(return_value=[])),
            patch.object(coordinator._topics, "extract", new=AsyncMock(return_value=[])),
        ):
            result = await coordinator.extract_document(
                chunks=["Chunk 1 text.", "Chunk 2 text."],
                document_id="doc-aggregate",
                user="t1",
                collection="default",
                title="Aggregate Test",
                file_path="/docs/aggregate.pdf",
                semantic_type="contrato",
                domain="legal",
            )

        assert result["success"] is True
        assert result["chunks_processed"] == 2
        assert result["triples_created"] == 2


# ---------------------------------------------------------------------------
# TestBlacklistFiltering
# ---------------------------------------------------------------------------


class TestBlacklistFiltering:
    """Blacklisted entities should be dropped before storage."""

    @pytest.mark.asyncio
    async def test_blacklisted_subject_dropped(self, falkordb_client):
        coord = _make_coordinator(falkordb_client)
        blacklisted_triples = [
            _label_triple("mayor de edad"),
            _type_triple("mayor de edad", "concept"),
        ]
        real_triples = [
            _label_triple("Juan García"),
            _rel_triple("Juan García", "ACME S.L."),
        ]

        with patch.object(coord._definitions, "extract", new_callable=AsyncMock) as mock_def, \
             patch.object(coord._relationships, "extract", new_callable=AsyncMock) as mock_rel, \
             patch.object(coord._objects, "extract", new_callable=AsyncMock) as mock_obj, \
             patch.object(coord._topics, "extract", new_callable=AsyncMock) as mock_top:
            mock_def.return_value = [blacklisted_triples[0], real_triples[0]]
            mock_rel.return_value = [real_triples[1]]
            mock_obj.return_value = [blacklisted_triples[1]]
            mock_top.return_value = []

            result = await coord.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="test-user",
                collection="default",
            )

        assert result["triples_created"] == 2

    @pytest.mark.asyncio
    async def test_blacklisted_object_dropped(self, falkordb_client):
        coord = _make_coordinator(falkordb_client)
        triples = [
            {
                "subject": "Juan García",
                "predicate_ontology": "legal",
                "predicate_name": "empleado-de",
                "object": "empresa",
                "object_is_node": True,
                "extraction_method": "llm_relationships",
                "source_chunk": SAMPLE_CHUNK[:200],
            },
        ]

        with patch.object(coord._definitions, "extract", new_callable=AsyncMock) as mock_def, \
             patch.object(coord._relationships, "extract", new_callable=AsyncMock) as mock_rel, \
             patch.object(coord._objects, "extract", new_callable=AsyncMock) as mock_obj, \
             patch.object(coord._topics, "extract", new_callable=AsyncMock) as mock_top:
            mock_def.return_value = []
            mock_rel.return_value = triples
            mock_obj.return_value = []
            mock_top.return_value = []

            result = await coord.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="test-user",
                collection="default",
            )

        assert result["triples_created"] == 0
