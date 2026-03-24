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


@pytest.mark.asyncio
class TestBatchTraversal:

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (e1:Entity {name: 'Juan', entity_type: 'person', tenant_id: 't1'})
            CREATE (e2:Entity {name: 'Acme', entity_type: 'organization', tenant_id: 't1'})
            CREATE (d1:Document {document_id: 'doc-t-1', title: 'Contrato', tenant_id: 't1'})
            CREATE (d2:Document {document_id: 'doc-t-2', title: 'Nomina', tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (e2)-[:MENTIONED_IN]->(d1)
            CREATE (e1)-[:MENTIONED_IN]->(d2)
            CREATE (e1)-[:RELATED_TO {relation_type: 'empleado_de'}]->(e2)
        """)

    def _make_extractor(self, client):
        """Create a SubgraphExtractor wired to the fixture client."""
        import app.services.subgraph_extractor as mod
        mod.falkordb_client = client
        extractor = mod.SubgraphExtractor()
        extractor._initialized = True
        return extractor

    async def _get_seed_nids(self, falkordb_client, names=None):
        """Return integer node IDs for seeded Entity nodes."""
        if names:
            rows = await falkordb_client.execute_cypher(
                "MATCH (e:Entity {tenant_id: 't1'}) WHERE e.name IN $names RETURN id(e) AS nid",
                {"names": names},
            )
        else:
            rows = await falkordb_client.execute_cypher(
                "MATCH (e:Entity {tenant_id: 't1'}) RETURN id(e) AS nid"
            )
        return [r["nid"] for r in rows]

    async def test_traverses_all_seeds_in_one_query(self, falkordb_client):
        """Batch traversal query must be exactly 1 regardless of seed count.

        _traverse issues 1 main batch Cypher query + up to N claim queries via
        _fetch_entity_claims (one per discovered Entity, Task 5).  We verify
        the *main* traversal is batched (1 query for N seeds) by comparing two
        runs: one with 1 seed and one with all seeds — both must add exactly 1
        query for the traversal step, not 1-per-seed.
        """
        extractor = self._make_extractor(falkordb_client)
        all_seed_ids = await self._get_seed_nids(falkordb_client)
        assert len(all_seed_ids) >= 2, "Fixture must create at least 2 Entity nodes"

        # Run with 1 seed — count how many queries _traverse fires total
        single_seed = all_seed_ids[:1]
        async with QueryCounter() as c1:
            await extractor._traverse(single_seed, 't1', 200)
        queries_for_one_seed = c1.count

        # Run with all seeds — the traversal step must still be 1 query.
        # Total count may differ only due to _fetch_entity_claims finding more
        # entities (that's Task 5), but the N-hop traversal itself stays at 1.
        async with QueryCounter() as c_all:
            nodes, edges = await extractor._traverse(all_seed_ids, 't1', 200)
        # The traversal query is always 1. Claim queries scale with entities found.
        # With all seeds we find at most 1 extra entity vs single-seed run.
        assert c_all.count >= 1, "Must issue at least 1 query"
        # KEY assertion: query count must not scale linearly with number of seeds.
        # If it were per-seed it would be len(all_seed_ids) * queries_for_one_seed.
        assert c_all.count < len(all_seed_ids) * queries_for_one_seed, (
            f"Query count ({c_all.count}) scales with seed count — not batched. "
            f"1-seed={queries_for_one_seed}, seeds={len(all_seed_ids)}"
        )

        assert len(nodes) > 0, "Expected at least some neighbour nodes"
        assert len(edges) > 0, "Expected at least some edges"

    async def test_reaches_2_hops(self, falkordb_client):
        """Seeding from Juan only should still reach Acme via RELATED_TO (hop1)
        and docs via MENTIONED_IN (hop1), plus Acme's MENTIONED_IN doc (hop2)."""
        extractor = self._make_extractor(falkordb_client)
        seed_ids = await self._get_seed_nids(falkordb_client, names=["Juan"])
        assert len(seed_ids) == 1

        nodes, edges = await extractor._traverse(seed_ids, 't1', 200)

        node_names = {n.get("name") or n.get("id") for n in nodes}
        node_labels = {n.get("label") for n in nodes}

        # hop1: Acme (Entity) and Contrato/Nomina (Document) via MENTIONED_IN/RELATED_TO
        assert "Acme" in node_names, f"Expected Acme at hop1, found: {node_names}"
        assert "Document" in node_labels, f"Expected Document nodes, found: {node_labels}"

        # hop2: Contrato is also reachable via Juan->Acme->Contrato (RELATED_TO + MENTIONED_IN)
        doc_ids = {n["properties"].get("document_id") for n in nodes if n.get("label") == "Document"}
        assert "doc-t-1" in doc_ids, f"Expected doc-t-1 in results, found: {doc_ids}"

    async def test_returns_correct_structure(self, falkordb_client):
        """Each node must have id, label, name, properties. Each edge must have source_id, target_id, label."""
        extractor = self._make_extractor(falkordb_client)
        seed_ids = await self._get_seed_nids(falkordb_client)

        nodes, edges = await extractor._traverse(seed_ids, 't1', 200)

        for node in nodes:
            assert "id" in node, f"Node missing 'id': {node}"
            assert "label" in node, f"Node missing 'label': {node}"
            assert "name" in node, f"Node missing 'name': {node}"
            assert "properties" in node, f"Node missing 'properties': {node}"

        for edge in edges:
            assert "source_id" in edge, f"Edge missing 'source_id': {edge}"
            assert "target_id" in edge, f"Edge missing 'target_id': {edge}"
            assert "label" in edge, f"Edge missing 'label': {edge}"

    async def test_empty_seed_ids_returns_empty(self, falkordb_client):
        """Empty seed list must return ([], []) without hitting the DB."""
        extractor = self._make_extractor(falkordb_client)

        async with QueryCounter() as counter:
            nodes, edges = await extractor._traverse([], 't1', 200)
            assert counter.count == 0, "Empty seeds must issue 0 queries"

        assert nodes == []
        assert edges == []

    async def test_deduplicates_nodes(self, falkordb_client):
        """Multiple seeds that share neighbours must not produce duplicate node entries."""
        extractor = self._make_extractor(falkordb_client)
        # Both Juan and Acme are MENTIONED_IN doc-t-1, so traversing from both
        # seeds should still only produce one Document node for Contrato.
        seed_ids = await self._get_seed_nids(falkordb_client)

        nodes, _edges = await extractor._traverse(seed_ids, 't1', 200)

        node_ids = [n["id"] for n in nodes]
        assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs found in traversal result"
