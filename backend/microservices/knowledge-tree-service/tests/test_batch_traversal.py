"""Tests for batch graph traversal optimizations."""

import pytest
import pytest_asyncio
from app.services.falkordb_client import QueryCounter


@pytest.mark.asyncio
class TestQueryCounter:
    """Verify query counting infrastructure."""

    async def test_counter_tracks_queries(self, falkordb_client):
        async with QueryCounter() as counter:
            await falkordb_client.execute_cypher("RETURN 1 AS n")
            await falkordb_client.execute_cypher("RETURN 2 AS n")
            assert counter.count == 2

    async def test_counter_zero_without_queries(self, falkordb_client):
        async with QueryCounter() as counter:
            assert counter.count == 0

    async def test_counter_isolated_between_contexts(self, falkordb_client):
        async with QueryCounter() as outer:
            await falkordb_client.execute_cypher("RETURN 1 AS n")
            async with QueryCounter() as inner:
                await falkordb_client.execute_cypher("RETURN 2 AS n")
                assert inner.count == 1
            assert outer.count == 2


@pytest.mark.asyncio
class TestBatchDocumentsByEntity:

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (d1:Document {document_id: 'doc-batch-1', title: 'Contrato Juan', tenant_id: 't1', associated_person: 'juan garcia'})
            CREATE (d2:Document {document_id: 'doc-batch-2', title: 'Nomina Maria', tenant_id: 't1'})
            CREATE (d3:Document {document_id: 'doc-batch-3', title: 'Factura', tenant_id: 't1'})
            CREATE (e1:Entity {name: 'Juan Garcia', entity_type: 'person', tenant_id: 't1'})
            CREATE (f1:Folder {name: 'Maria Lopez', tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (d2)-[:CONTAINED_IN]->(f1)
        """)

    async def test_finds_by_entity_name(self, falkordb_client):
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('juan garcia', 't1', client=falkordb_client)
        assert 'doc-batch-1' in doc_ids

    async def test_finds_by_associated_person(self, falkordb_client):
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('juan garcia', 't1', client=falkordb_client)
        assert 'doc-batch-1' in doc_ids

    async def test_finds_by_folder_name(self, falkordb_client):
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('maria lopez', 't1', client=falkordb_client)
        assert 'doc-batch-2' in doc_ids

    async def test_uses_max_two_queries(self, falkordb_client):
        """Must use 1 query (UNION) or 2 queries (fallback), not 3."""
        from app.api.tree import _batch_documents_by_entity
        async with QueryCounter() as counter:
            await _batch_documents_by_entity('juan garcia', 't1', client=falkordb_client)
            assert counter.count <= 2, f"Expected ≤2 queries, got {counter.count}"

    async def test_deduplicates_results(self, falkordb_client):
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('juan garcia', 't1', client=falkordb_client)
        assert len(doc_ids) == len(set(doc_ids))


@pytest.mark.asyncio
class TestBatchSeedResolution:

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (e1:Entity {name: 'Juan Garcia', entity_type: 'person', tenant_id: 't1', normalized_name: 'juan garcia'})
            CREATE (e2:Entity {name: 'Acme Corp', entity_type: 'organization', tenant_id: 't1', normalized_name: 'acme corp'})
            CREATE (d1:Document {document_id: 'doc-seed-1', title: 'Contrato Laboral', tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (e2)-[:MENTIONED_IN]->(d1)
        """)

    def _make_extractor(self, falkordb_client):
        """Create a SubgraphExtractor wired to the fixture's client connection."""
        import app.services.subgraph_extractor as mod
        # Point the module-level singleton at the fixture's live client
        mod.falkordb_client = falkordb_client
        extractor = mod.SubgraphExtractor()
        extractor._initialized = True  # client already initialized by fixture
        return extractor

    async def test_resolves_multiple_seeds_in_one_query(self, falkordb_client):
        extractor = self._make_extractor(falkordb_client)

        entities = [
            {"value": "juan garcia", "type": "person"},
            {"value": "acme corp", "type": "organization"},
        ]
        async with QueryCounter() as counter:
            seeds, seed_names = await extractor._resolve_seeds('t1', entities)
            assert counter.count == 1, f"Expected 1 query, got {counter.count}"

        seed_names_lower = [s["name"].lower() for s in seeds]
        assert any("juan" in n for n in seed_names_lower)
        assert any("acme" in n for n in seed_names_lower)

    async def test_returns_node_ids(self, falkordb_client):
        extractor = self._make_extractor(falkordb_client)

        entities = [{"value": "juan garcia", "type": "person"}]
        seeds, _ = await extractor._resolve_seeds('t1', entities)
        assert len(seeds) >= 1
        assert "nid" in seeds[0], "Seed must include node ID for Phase 2"
        assert isinstance(seeds[0]["nid"], int), "Node ID must be integer"

    async def test_matches_by_title(self, falkordb_client):
        extractor = self._make_extractor(falkordb_client)

        entities = [{"value": "contrato laboral", "type": "document"}]
        seeds, _ = await extractor._resolve_seeds('t1', entities)
        assert len(seeds) >= 1

    async def test_empty_entities_returns_empty(self, falkordb_client):
        extractor = self._make_extractor(falkordb_client)

        seeds, seed_names = await extractor._resolve_seeds('t1', [])
        assert seeds == []
        assert seed_names == set()

    async def test_deduplicates_nodes_across_entities(self, falkordb_client):
        """Same node matched by two search terms must appear only once."""
        extractor = self._make_extractor(falkordb_client)

        # Duplicate search terms — same node must appear only once
        entities = [
            {"value": "juan garcia", "type": "person"},
            {"value": "juan garcia", "type": "person"},
        ]
        seeds, _ = await extractor._resolve_seeds('t1', entities)
        ids = [s["id"] for s in seeds]
        assert len(ids) == len(set(ids)), "Duplicate node IDs found in seed results"
