"""
Tests for FalkorDB client — Phase 1 infrastructure validation.

These tests verify:
1. Connection and initialization with retry
2. Schema bootstrap (indexes created)
3. Basic CRUD operations via Cypher
4. Tenant isolation via property filtering
5. Evidence-oriented data model (Entity, Claim, Document)
6. Graph traversals for GraphRAG
"""

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# 1. Connection & Initialization
# ---------------------------------------------------------------------------

class TestFalkorDBConnection:
    """Verify FalkorDB client connects and initializes correctly."""

    @pytest.mark.asyncio
    async def test_client_initializes(self, falkordb_client):
        """Client should connect to FalkorDB and be marked initialized."""
        assert falkordb_client._initialized is True
        assert falkordb_client._graph is not None

    @pytest.mark.asyncio
    async def test_client_idempotent_init(self, falkordb_client):
        """Calling initialize() twice should be safe (no-op)."""
        await falkordb_client.initialize()
        assert falkordb_client._initialized is True

    @pytest.mark.asyncio
    async def test_execute_cypher_returns_list(self, falkordb_client):
        """execute_cypher should return a list of dicts."""
        result = await falkordb_client.execute_cypher("RETURN 1 AS value")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["value"] == 1

    @pytest.mark.asyncio
    async def test_execute_cypher_empty_result(self, falkordb_client):
        """Query with no matches should return empty list."""
        result = await falkordb_client.execute_cypher(
            "MATCH (n:NonExistentLabel) RETURN n"
        )
        assert result == []


# ---------------------------------------------------------------------------
# 2. Schema Bootstrap
# ---------------------------------------------------------------------------

class TestSchemaBootstrap:
    """Verify the unified graph schema bootstraps correctly."""

    @pytest.mark.asyncio
    async def test_bootstrap_schema_runs(self, falkordb_client):
        """Bootstrap should execute without errors."""
        await falkordb_client.bootstrap_schema()

    @pytest.mark.asyncio
    async def test_bootstrap_idempotent(self, falkordb_client):
        """Running bootstrap twice should not raise errors."""
        await falkordb_client.bootstrap_schema()
        await falkordb_client.bootstrap_schema()


# ---------------------------------------------------------------------------
# 3. Node CRUD — Evidence-Oriented Data Model
# ---------------------------------------------------------------------------

class TestDocumentNodes:
    """Test :Document node operations."""

    @pytest.mark.asyncio
    async def test_create_document(self, falkordb_client):
        result = await falkordb_client.execute_cypher("""
            CREATE (d:Document {
                tenant_id: 'tenant-1',
                document_id: 'doc-001',
                title: 'Contrato de Servicios',
                semantic_type: 'contrato',
                domain: 'legal',
                quality_score: 0.92,
                chunk_count: 15,
                indexed_at: datetime()
            })
            RETURN d.document_id AS id, d.title AS title
        """)
        assert len(result) == 1
        assert result[0]["id"] == "doc-001"
        assert result[0]["title"] == "Contrato de Servicios"

    @pytest.mark.asyncio
    async def test_merge_document_idempotent(self, falkordb_client):
        """MERGE should not duplicate documents."""
        for _ in range(3):
            await falkordb_client.execute_cypher("""
                MERGE (d:Document {document_id: 'doc-002', tenant_id: 'tenant-1'})
                SET d.title = 'Factura 2024'
            """)
        result = await falkordb_client.execute_cypher("""
            MATCH (d:Document {document_id: 'doc-002'})
            RETURN count(d) AS cnt
        """)
        assert result[0]["cnt"] == 1


class TestEntityNodes:
    """Test :Entity node operations — universal typed entities."""

    @pytest.mark.asyncio
    async def test_create_person_entity(self, falkordb_client):
        result = await falkordb_client.execute_cypher("""
            CREATE (e:Entity {
                tenant_id: 'tenant-1',
                name: 'Juan Perez',
                normalized_name: 'juan perez',
                entity_type: 'person',
                sector: 'legal',
                confidence: 0.95,
                source_count: 3,
                shared: false
            })
            RETURN e.name AS name, e.entity_type AS type
        """)
        assert result[0]["name"] == "Juan Perez"
        assert result[0]["type"] == "person"

    @pytest.mark.asyncio
    async def test_create_law_entity_shared(self, falkordb_client):
        """Law entities should have shared=true and no tenant_id."""
        result = await falkordb_client.execute_cypher("""
            CREATE (e:Entity {
                name: 'Estatuto de los Trabajadores',
                normalized_name: 'estatuto de los trabajadores',
                entity_type: 'law',
                sector: 'legal',
                confidence: 1.0,
                source_count: 47,
                shared: true
            })
            RETURN e.entity_type AS type, e.shared AS shared
        """)
        assert result[0]["type"] == "law"
        assert result[0]["shared"] is True

    @pytest.mark.asyncio
    async def test_filter_by_entity_type(self, falkordb_client):
        """Should filter entities by type property (replaces old vlabel filtering)."""
        await falkordb_client.execute_cypher("""
            CREATE (:Entity {tenant_id: 't1', name: 'Ana', entity_type: 'person'})
        """)
        await falkordb_client.execute_cypher("""
            CREATE (:Entity {tenant_id: 't1', name: 'Acme Corp', entity_type: 'organization'})
        """)
        await falkordb_client.execute_cypher("""
            CREATE (:Entity {tenant_id: 't1', name: 'Ibuprofeno', entity_type: 'medication'})
        """)

        persons = await falkordb_client.execute_cypher("""
            MATCH (e:Entity {entity_type: 'person', tenant_id: 't1'})
            RETURN e.name AS name
        """)
        assert len(persons) == 1
        assert persons[0]["name"] == "Ana"


class TestClaimNodes:
    """Test :Claim node operations — key for anti-hallucination."""

    @pytest.mark.asyncio
    async def test_create_claim(self, falkordb_client):
        result = await falkordb_client.execute_cypher("""
            CREATE (c:Claim {
                tenant_id: 'tenant-1',
                statement: 'Juan Perez firmo el contrato el 15/03/2024',
                claim_type: 'factual',
                confidence: 0.95,
                source_chunk: 'El Sr. Juan Perez, en calidad de representante legal, firmo el contrato...',
                verified: false
            })
            RETURN c.statement AS stmt, c.confidence AS conf
        """)
        assert result[0]["conf"] == 0.95
        assert "Juan Perez" in result[0]["stmt"]

    @pytest.mark.asyncio
    async def test_claim_types(self, falkordb_client):
        """All claim types should be storable."""
        for claim_type in ["factual", "temporal", "legal_reference", "numeric"]:
            await falkordb_client.execute_cypher(f"""
                CREATE (:Claim {{
                    tenant_id: 'tenant-1',
                    statement: 'Test {claim_type}',
                    claim_type: '{claim_type}',
                    confidence: 0.8
                }})
            """)

        result = await falkordb_client.execute_cypher("""
            MATCH (c:Claim {tenant_id: 'tenant-1'})
            RETURN DISTINCT c.claim_type AS type
            ORDER BY type
        """)
        types = [r["type"] for r in result]
        assert "factual" in types
        assert "temporal" in types
        assert "legal_reference" in types
        assert "numeric" in types


class TestOntologyNodes:
    """Test :EntityType and :RelationType nodes."""

    @pytest.mark.asyncio
    async def test_create_entity_type(self, falkordb_client):
        result = await falkordb_client.execute_cypher("""
            CREATE (et:EntityType {
                name: 'contrato',
                display_name: 'Contrato',
                category: 'document',
                parent: 'legal_document',
                sector: 'legal'
            })
            RETURN et.name AS name, et.category AS cat
        """)
        assert result[0]["name"] == "contrato"
        assert result[0]["cat"] == "document"


# ---------------------------------------------------------------------------
# 4. Relationships — Provenance and Evidence
# ---------------------------------------------------------------------------

class TestEvidenceRelationships:
    """Test evidence-bearing relationships for GraphRAG."""

    @pytest.mark.asyncio
    async def test_mentioned_in_with_provenance(self, falkordb_client):
        """MENTIONED_IN should carry extraction metadata."""
        await falkordb_client.execute_cypher("""
            CREATE (e:Entity {name: 'Juan', entity_type: 'person', tenant_id: 't1'})
            CREATE (d:Document {document_id: 'doc-1', title: 'Contrato', tenant_id: 't1'})
            CREATE (e)-[:MENTIONED_IN {
                chunk_index: 3,
                extraction_method: 'ner',
                confidence: 0.92,
                context_snippet: '...firmado por Juan Perez en calidad de...'
            }]->(d)
        """)

        result = await falkordb_client.execute_cypher("""
            MATCH (e:Entity {name: 'Juan'})-[r:MENTIONED_IN]->(d:Document)
            RETURN r.confidence AS conf, r.extraction_method AS method,
                   r.context_snippet AS snippet, d.document_id AS doc
        """)
        assert len(result) == 1
        assert result[0]["conf"] == 0.92
        assert result[0]["method"] == "ner"
        assert "Juan Perez" in result[0]["snippet"]

    @pytest.mark.asyncio
    async def test_related_to_with_evidence(self, falkordb_client):
        """RELATED_TO between entities should carry evidence."""
        await falkordb_client.execute_cypher("""
            CREATE (p:Entity {name: 'Juan', entity_type: 'person', tenant_id: 't1'})
            CREATE (o:Entity {name: 'Acme', entity_type: 'organization', tenant_id: 't1'})
            CREATE (p)-[:RELATED_TO {
                relation_type: 'emplea',
                confidence: 0.88,
                evidence_doc: 'doc-1',
                evidence_chunk: 'Juan Perez, empleado de Acme Corp desde 2020'
            }]->(o)
        """)

        result = await falkordb_client.execute_cypher("""
            MATCH (p:Entity)-[r:RELATED_TO {relation_type: 'emplea'}]->(o:Entity)
            RETURN p.name AS person, o.name AS org, r.evidence_chunk AS evidence
        """)
        assert result[0]["person"] == "Juan"
        assert result[0]["org"] == "Acme"
        assert "2020" in result[0]["evidence"]

    @pytest.mark.asyncio
    async def test_claim_extracted_from_document(self, falkordb_client):
        """Claims should link back to their source document."""
        await falkordb_client.execute_cypher("""
            CREATE (c:Claim {statement: 'Salario: 45000 EUR', claim_type: 'numeric', tenant_id: 't1'})
            CREATE (d:Document {document_id: 'doc-1', tenant_id: 't1'})
            CREATE (c)-[:EXTRACTED_FROM {chunk_index: 7, extraction_method: 'regex'}]->(d)
        """)

        result = await falkordb_client.execute_cypher("""
            MATCH (c:Claim)-[r:EXTRACTED_FROM]->(d:Document)
            RETURN c.statement AS claim, r.chunk_index AS chunk, d.document_id AS doc
        """)
        assert result[0]["claim"] == "Salario: 45000 EUR"
        assert result[0]["chunk"] == 7

    @pytest.mark.asyncio
    async def test_claim_contradicts(self, falkordb_client):
        """CONTRADICTS relationship between conflicting claims."""
        await falkordb_client.execute_cypher("""
            CREATE (c1:Claim {statement: 'Fecha firma: 15/03/2024', claim_type: 'temporal', tenant_id: 't1'})
            CREATE (c2:Claim {statement: 'Fecha firma: 22/03/2024', claim_type: 'temporal', tenant_id: 't1'})
            CREATE (c1)-[:CONTRADICTS {contradiction_type: 'temporal'}]->(c2)
        """)

        result = await falkordb_client.execute_cypher("""
            MATCH (c1:Claim)-[r:CONTRADICTS]->(c2:Claim)
            RETURN c1.statement AS claim1, c2.statement AS claim2,
                   r.contradiction_type AS type
        """)
        assert len(result) == 1
        assert result[0]["type"] == "temporal"
        assert "15/03" in result[0]["claim1"]
        assert "22/03" in result[0]["claim2"]

    @pytest.mark.asyncio
    async def test_claim_supports(self, falkordb_client):
        """SUPPORTS relationship between reinforcing claims."""
        await falkordb_client.execute_cypher("""
            CREATE (c1:Claim {statement: 'Salario: 45000', tenant_id: 't1'})
            CREATE (c2:Claim {statement: 'Retribucion anual: 45000 EUR', tenant_id: 't1'})
            CREATE (c1)-[:SUPPORTS]->(c2)
        """)

        result = await falkordb_client.execute_cypher("""
            MATCH (c1:Claim)-[:SUPPORTS]->(c2:Claim)
            RETURN c1.statement AS s1, c2.statement AS s2
        """)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 5. Tenant Isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Verify tenant data isolation via property filtering."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_documents(self, falkordb_client):
        """Documents from different tenants should not mix."""
        await falkordb_client.execute_cypher("""
            CREATE (:Document {tenant_id: 'tenant-A', document_id: 'dA1', title: 'Doc A'})
        """)
        await falkordb_client.execute_cypher("""
            CREATE (:Document {tenant_id: 'tenant-B', document_id: 'dB1', title: 'Doc B'})
        """)

        result_a = await falkordb_client.execute_cypher("""
            MATCH (d:Document {tenant_id: 'tenant-A'})
            RETURN d.title AS title
        """)
        assert len(result_a) == 1
        assert result_a[0]["title"] == "Doc A"

        result_b = await falkordb_client.execute_cypher("""
            MATCH (d:Document {tenant_id: 'tenant-B'})
            RETURN d.title AS title
        """)
        assert len(result_b) == 1
        assert result_b[0]["title"] == "Doc B"

    @pytest.mark.asyncio
    async def test_shared_entities_visible_to_all(self, falkordb_client):
        """Shared entities (laws) should be visible regardless of tenant."""
        await falkordb_client.execute_cypher("""
            CREATE (:Entity {name: 'ET', entity_type: 'law', shared: true})
        """)
        await falkordb_client.execute_cypher("""
            CREATE (:Document {tenant_id: 'tenant-X', document_id: 'dX1'})
        """)

        # Query from any tenant context should find shared laws
        result = await falkordb_client.execute_cypher("""
            MATCH (e:Entity {entity_type: 'law', shared: true})
            RETURN e.name AS name
        """)
        assert len(result) == 1
        assert result[0]["name"] == "ET"


# ---------------------------------------------------------------------------
# 6. GraphRAG Traversals — Multi-hop Evidence Assembly
# ---------------------------------------------------------------------------

class TestGraphRAGTraversals:
    """Test multi-hop traversals for evidence assembly."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_graph(self, falkordb_client):
        """Seed a small graph for traversal tests."""
        await falkordb_client.execute_cypher("""
            CREATE (juan:Entity {name: 'Juan Perez', entity_type: 'person', tenant_id: 't1', normalized_name: 'juan perez'})
            CREATE (acme:Entity {name: 'Acme Corp', entity_type: 'organization', tenant_id: 't1'})
            CREATE (doc1:Document {document_id: 'doc-1', title: 'Contrato Acme', tenant_id: 't1', quality_score: 0.92})
            CREATE (doc2:Document {document_id: 'doc-2', title: 'Nomina Enero', tenant_id: 't1', quality_score: 0.85})
            CREATE (claim1:Claim {statement: 'Juan firmo el contrato', claim_type: 'factual', confidence: 0.95, tenant_id: 't1', source_chunk: 'El Sr. Juan Perez firmo...'})
            CREATE (claim2:Claim {statement: 'Salario: 45000 EUR', claim_type: 'numeric', confidence: 0.99, tenant_id: 't1', source_chunk: 'Retribucion bruta anual: 45.000 EUR'})
            CREATE (claim3:Claim {statement: 'Fecha inicio: 01/02/2024', claim_type: 'temporal', confidence: 0.90, tenant_id: 't1'})
            CREATE (claim4:Claim {statement: 'Fecha inicio: 15/02/2024', claim_type: 'temporal', confidence: 0.80, tenant_id: 't1'})

            CREATE (juan)-[:MENTIONED_IN {chunk_index: 2, extraction_method: 'ner', confidence: 0.95}]->(doc1)
            CREATE (juan)-[:MENTIONED_IN {chunk_index: 0, extraction_method: 'ner', confidence: 0.90}]->(doc2)
            CREATE (acme)-[:MENTIONED_IN {chunk_index: 1, extraction_method: 'ner', confidence: 0.88}]->(doc1)
            CREATE (juan)-[:RELATED_TO {relation_type: 'firmado_por', confidence: 0.95, evidence_doc: 'doc-1'}]->(acme)

            CREATE (claim1)-[:EXTRACTED_FROM {chunk_index: 2, extraction_method: 'ner'}]->(doc1)
            CREATE (claim2)-[:EXTRACTED_FROM {chunk_index: 5, extraction_method: 'regex'}]->(doc1)
            CREATE (claim3)-[:EXTRACTED_FROM {chunk_index: 1, extraction_method: 'regex'}]->(doc1)
            CREATE (claim4)-[:EXTRACTED_FROM {chunk_index: 3, extraction_method: 'regex'}]->(doc2)

            CREATE (claim1)-[:ABOUT]->(juan)
            CREATE (claim2)-[:ABOUT]->(juan)
            CREATE (claim3)-[:ABOUT]->(juan)
            CREATE (claim4)-[:ABOUT]->(juan)

            CREATE (claim3)-[:CONTRADICTS {contradiction_type: 'temporal'}]->(claim4)
        """)

    @pytest.mark.asyncio
    async def test_find_entity_documents(self, falkordb_client):
        """Find all documents where an entity is mentioned."""
        result = await falkordb_client.execute_cypher("""
            MATCH (e:Entity {normalized_name: 'juan perez', tenant_id: 't1'})
                  -[:MENTIONED_IN]->(d:Document)
            RETURN d.document_id AS doc, d.title AS title
            ORDER BY doc
        """)
        assert len(result) == 2
        assert result[0]["doc"] == "doc-1"
        assert result[1]["doc"] == "doc-2"

    @pytest.mark.asyncio
    async def test_evidence_assembly_2hop(self, falkordb_client):
        """2-hop traversal: Entity -> Document -> Claims with evidence."""
        result = await falkordb_client.execute_cypher("""
            MATCH (e:Entity {normalized_name: 'juan perez', tenant_id: 't1'})
                  -[:MENTIONED_IN]->(d:Document)
                  <-[:EXTRACTED_FROM]-(c:Claim)
            RETURN d.document_id AS doc, c.statement AS claim,
                   c.confidence AS conf, c.source_chunk AS source
            ORDER BY c.confidence DESC
        """)
        assert len(result) >= 3
        # Highest confidence claim first
        assert result[0]["conf"] >= result[1]["conf"]

    @pytest.mark.asyncio
    async def test_find_contradictions(self, falkordb_client):
        """Detect contradicting claims about an entity."""
        result = await falkordb_client.execute_cypher("""
            MATCH (c1:Claim)-[r:CONTRADICTS]->(c2:Claim)
            WHERE c1.tenant_id = 't1'
            RETURN c1.statement AS claim1, c2.statement AS claim2,
                   r.contradiction_type AS type,
                   c1.confidence AS conf1, c2.confidence AS conf2
        """)
        assert len(result) == 1
        assert result[0]["type"] == "temporal"
        # The higher confidence claim should be preferred by the LLM
        assert result[0]["conf1"] > result[0]["conf2"]

    @pytest.mark.asyncio
    async def test_entity_relationship_traversal(self, falkordb_client):
        """Traverse entity relationships with evidence."""
        result = await falkordb_client.execute_cypher("""
            MATCH (p:Entity {entity_type: 'person', tenant_id: 't1'})
                  -[r:RELATED_TO]->(o:Entity {entity_type: 'organization'})
            RETURN p.name AS person, o.name AS org,
                   r.relation_type AS rel, r.confidence AS conf
        """)
        assert len(result) == 1
        assert result[0]["person"] == "Juan Perez"
        assert result[0]["org"] == "Acme Corp"
        assert result[0]["rel"] == "firmado_por"

    @pytest.mark.asyncio
    async def test_full_graphrag_context_query(self, falkordb_client):
        """Full GraphRAG query: entity -> docs -> claims -> contradictions.

        This simulates the evidence assembly that subgraph_extractor will do.
        The LLM should receive structured context with provenance.
        """
        result = await falkordb_client.execute_cypher("""
            MATCH (e:Entity {normalized_name: 'juan perez', tenant_id: 't1'})
                  -[m:MENTIONED_IN]->(d:Document)
                  <-[ef:EXTRACTED_FROM]-(c:Claim)
            OPTIONAL MATCH (c)-[contra:CONTRADICTS]->(c2:Claim)
            RETURN d.document_id AS doc_id,
                   d.title AS doc_title,
                   d.quality_score AS doc_quality,
                   c.statement AS claim,
                   c.confidence AS claim_confidence,
                   c.source_chunk AS source,
                   c2.statement AS contradicted_by
            ORDER BY c.confidence DESC
        """)
        assert len(result) >= 3

        # Verify structure: each row has document context + claim + optional contradiction
        for row in result:
            assert row["doc_id"] is not None
            assert row["claim"] is not None
            assert row["claim_confidence"] is not None

        # At least one row should have a contradiction
        contradictions = [r for r in result if r["contradicted_by"] is not None]
        assert len(contradictions) >= 1

    @pytest.mark.asyncio
    async def test_traversal_performance_small_graph(self, falkordb_client):
        """Verify 2-hop traversal completes in reasonable time."""
        import time
        start = time.monotonic()

        await falkordb_client.execute_cypher("""
            MATCH (e:Entity {tenant_id: 't1'})
                  -[:MENTIONED_IN|RELATED_TO*1..2]-(connected)
            RETURN count(connected) AS total
        """)

        elapsed_ms = (time.monotonic() - start) * 1000
        # FalkorDB should handle this in <100ms even on small graphs
        assert elapsed_ms < 500, f"Traversal took {elapsed_ms:.0f}ms — too slow"
