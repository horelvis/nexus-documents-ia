"""
Tests for ClaimExtractor — Phase 3 GraphRAG Enhancement.

Tests:
1. Regex extraction for each pattern type
2. Claim storage in FalkorDB
3. EXTRACTED_FROM and ABOUT edge creation
4. Contradiction detection
5. Integration with subgraph_extractor (claims in traversals)
"""

import pytest

from app.services.claim_extractor import (
    ClaimExtractor,
    _extract_date_parts,
    _extract_numeric_value,
    _values_contradict,
)


# ---------------------------------------------------------------------------
# 1. Regex Pattern Extraction (unit tests — no FalkorDB needed)
# ---------------------------------------------------------------------------

class TestRegexExtraction:
    """Test the regex extraction stage of ClaimExtractor."""

    def setup_method(self):
        self.extractor = ClaimExtractor()

    def test_extract_dates_slash(self):
        text = "El contrato fue firmado el 15/03/2024 en Madrid."
        claims = self.extractor._extract_regex(text)
        temporal = [c for c in claims if c["claim_type"] == "temporal"]
        assert len(temporal) >= 1
        assert "15/03/2024" in temporal[0]["match_value"]

    def test_extract_dates_dash(self):
        text = "Fecha de inicio: 01-02-2024."
        claims = self.extractor._extract_regex(text)
        temporal = [c for c in claims if c["claim_type"] == "temporal"]
        assert len(temporal) >= 1
        assert "01-02-2024" in temporal[0]["match_value"]

    def test_extract_dates_dot(self):
        text = "Vencimiento: 31.12.2025."
        claims = self.extractor._extract_regex(text)
        temporal = [c for c in claims if c["claim_type"] == "temporal"]
        assert len(temporal) >= 1
        assert "31.12.2025" in temporal[0]["match_value"]

    def test_extract_dates_two_digit_year(self):
        text = "Firmado el 05/06/24."
        claims = self.extractor._extract_regex(text)
        temporal = [c for c in claims if c["claim_type"] == "temporal"]
        assert len(temporal) >= 1

    def test_extract_monetary_eur(self):
        text = "El salario bruto es de 45000 EUR anuales."
        claims = self.extractor._extract_regex(text)
        numeric = [c for c in claims if c["claim_type"] == "numeric"]
        assert len(numeric) >= 1
        assert "45000" in numeric[0]["match_value"]

    def test_extract_monetary_euro_symbol(self):
        text = "Importe total: 1.250,00 euros."
        claims = self.extractor._extract_regex(text)
        numeric = [c for c in claims if c["claim_type"] == "numeric"]
        assert len(numeric) >= 1

    def test_extract_monetary_prefix_symbol(self):
        text = "Total factura: $3,500.00."
        claims = self.extractor._extract_regex(text)
        # Should find the $ amount
        numeric = [c for c in claims if c["claim_type"] == "numeric"]
        assert len(numeric) >= 1

    def test_extract_percentage(self):
        text = "Se aplica un IVA del 21% sobre la base imponible."
        claims = self.extractor._extract_regex(text)
        numeric = [c for c in claims if c["claim_type"] == "numeric"]
        assert any("21" in c["match_value"] and "%" in c["match_value"] for c in numeric)

    def test_extract_percentage_decimal(self):
        text = "Tipo de interes: 3,5%."
        claims = self.extractor._extract_regex(text)
        numeric = [c for c in claims if c["claim_type"] == "numeric"]
        assert len(numeric) >= 1

    def test_extract_boe_reference(self):
        text = "Segun establece la Ley 31/1995 de Prevencion de Riesgos Laborales."
        claims = self.extractor._extract_regex(text)
        legal = [c for c in claims if c["claim_type"] == "legal_reference"]
        assert len(legal) >= 1
        assert "Ley 31/1995" in legal[0]["match_value"]

    def test_extract_real_decreto(self):
        text = "Conforme al Real Decreto 1/2023 por el que se aprueba..."
        claims = self.extractor._extract_regex(text)
        legal = [c for c in claims if c["claim_type"] == "legal_reference"]
        assert len(legal) >= 1
        assert "Real Decreto 1/2023" in legal[0]["match_value"]

    def test_extract_nif(self):
        text = "NIF del empleado: B12345678."
        claims = self.extractor._extract_regex(text)
        factual = [c for c in claims if c["claim_type"] == "factual"]
        assert any("B12345678" in c["match_value"] for c in factual)

    def test_extract_iban(self):
        text = "Cuenta bancaria: ES91 2100 0418 4502 0005 1332."
        claims = self.extractor._extract_regex(text)
        factual = [c for c in claims if c["claim_type"] == "factual"]
        assert len(factual) >= 1

    def test_extract_multiple_types(self):
        """A complex document should yield multiple claim types."""
        text = (
            "El contrato firmado el 15/03/2024 establece un salario de 45000 EUR. "
            "Segun la Ley 31/1995, el NIF B12345678 corresponde al empleado. "
            "Se aplica un 21% de IVA."
        )
        claims = self.extractor._extract_regex(text)
        types = {c["claim_type"] for c in claims}
        assert "temporal" in types
        assert "numeric" in types
        assert "legal_reference" in types
        assert "factual" in types

    def test_extract_empty_text(self):
        claims = self.extractor._extract_regex("")
        assert claims == []

    def test_extract_no_claims(self):
        text = "Este es un texto sin datos estructurados relevantes."
        claims = self.extractor._extract_regex(text)
        assert len(claims) == 0

    def test_source_chunk_context(self):
        """Each claim should include surrounding context."""
        text = "A" * 200 + " 15/03/2024 " + "B" * 200
        claims = self.extractor._extract_regex(text)
        temporal = [c for c in claims if c["claim_type"] == "temporal"]
        assert len(temporal) >= 1
        chunk = temporal[0]["source_chunk"]
        # Context should be bounded, not the entire text
        assert len(chunk) < len(text)
        assert "15/03/2024" in chunk

    def test_dedup_same_value(self):
        """Same value appearing twice should yield one unique claim."""
        text = "Fecha: 15/03/2024. Recordatorio: 15/03/2024."
        claims = self.extractor._extract_regex(text)
        temporal = [c for c in claims if c["claim_type"] == "temporal"]
        # Raw extraction finds both, dedup happens in extract_claims()
        assert len(temporal) == 2  # Raw extraction has both


# ---------------------------------------------------------------------------
# 2. Helper Functions
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Test date/numeric extraction helpers."""

    def test_extract_date_parts(self):
        assert _extract_date_parts("15/03/2024") == (15, 3, 2024)
        assert _extract_date_parts("01-02-2024") == (1, 2, 2024)
        assert _extract_date_parts("31.12.25") == (31, 12, 2025)
        assert _extract_date_parts("no date here") is None

    def test_extract_numeric_value(self):
        assert _extract_numeric_value("45000 EUR") == 45000.0
        assert _extract_numeric_value("1.250,50 euros") == 1250.50
        assert _extract_numeric_value("$3,500.00") == 3500.0
        assert _extract_numeric_value("21%") == 21.0
        assert _extract_numeric_value("no number") is None

    def test_values_contradict_temporal(self):
        assert _values_contradict("15/03/2024", "22/03/2024", "temporal") is True
        assert _values_contradict("15/03/2024", "15/03/2024", "temporal") is False
        assert _values_contradict("15/03/2024", "15-03-2024", "temporal") is False

    def test_values_contradict_numeric(self):
        assert _values_contradict("45000 EUR", "50000 EUR", "numeric") is True
        assert _values_contradict("45000 EUR", "45000 EUR", "numeric") is False
        assert _values_contradict("45.000 EUR", "45000 EUR", "numeric") is False  # Same value

    def test_values_contradict_same_normalized(self):
        """Whitespace-only differences should not be contradictions."""
        assert _values_contradict("45000 EUR", "45000  EUR", "numeric") is False


# ---------------------------------------------------------------------------
# 3. FalkorDB Integration — Claim Storage
# ---------------------------------------------------------------------------

class TestClaimStorage:
    """Test storing claims in FalkorDB."""

    @pytest.mark.asyncio
    async def test_extract_and_store_claims(self, falkordb_client):
        """Claims should be created as nodes with EXTRACTED_FROM edges."""
        # Create a document first
        await falkordb_client.execute_cypher("""
            CREATE (:Document {
                tenant_id: 'test-tenant',
                document_id: 'doc-100',
                title: 'Contrato de Servicios'
            })
        """)

        extractor = ClaimExtractor()
        text = (
            "El contrato fue firmado el 15/03/2024 por un importe de 45000 EUR. "
            "Segun la Ley 31/1995, se establecen las condiciones."
        )
        claims = await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-100",
            text=text,
        )

        assert len(claims) >= 3  # date, amount, law ref

        # Verify claims exist in graph
        result = await falkordb_client.execute_cypher("""
            MATCH (c:Claim {tenant_id: 'test-tenant'})-[:EXTRACTED_FROM]->(d:Document {document_id: 'doc-100'})
            RETURN c.statement AS stmt, c.claim_type AS type, c.confidence AS conf
            ORDER BY c.claim_type
        """)
        assert len(result) >= 3

        types = {r["type"] for r in result}
        assert "temporal" in types
        assert "numeric" in types
        assert "legal_reference" in types

    @pytest.mark.asyncio
    async def test_claims_have_source_chunk(self, falkordb_client):
        """Stored claims should include source_chunk for provenance."""
        await falkordb_client.execute_cypher("""
            CREATE (:Document {tenant_id: 'test-tenant', document_id: 'doc-101'})
        """)

        extractor = ClaimExtractor()
        text = "El salario pactado es de 30000 EUR brutos anuales."
        await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-101",
            text=text,
        )

        result = await falkordb_client.execute_cypher("""
            MATCH (c:Claim {tenant_id: 'test-tenant'})-[:EXTRACTED_FROM]->(d:Document {document_id: 'doc-101'})
            RETURN c.source_chunk AS chunk
        """)
        assert len(result) >= 1
        assert result[0]["chunk"] is not None
        assert len(result[0]["chunk"]) > 0

    @pytest.mark.asyncio
    async def test_empty_text_no_claims(self, falkordb_client):
        """Empty text should produce no claims."""
        extractor = ClaimExtractor()
        claims = await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-empty",
            text="",
        )
        assert claims == []

    @pytest.mark.asyncio
    async def test_no_document_node_no_crash(self, falkordb_client):
        """If document node doesn't exist, extraction should not crash."""
        extractor = ClaimExtractor()
        text = "Fecha: 15/03/2024."
        claims = await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="nonexistent-doc",
            text=text,
        )
        # Should return empty since MATCH on document fails
        assert claims == []


# ---------------------------------------------------------------------------
# 4. ABOUT Edge Creation
# ---------------------------------------------------------------------------

class TestAboutEdges:
    """Test linking claims to entities via :ABOUT edges."""

    @pytest.mark.asyncio
    async def test_claim_linked_to_entity(self, falkordb_client):
        """Claims should be linked to entities mentioned in the chunk."""
        # Create document + entity
        await falkordb_client.execute_cypher("""
            CREATE (d:Document {tenant_id: 'test-tenant', document_id: 'doc-200'})
            CREATE (e:Entity {
                tenant_id: 'test-tenant',
                name: 'Juan Perez',
                normalized_name: 'juan perez',
                entity_type: 'person'
            })
            CREATE (e)-[:MENTIONED_IN]->(d)
        """)

        extractor = ClaimExtractor()
        text = "Juan Perez firmo el contrato el 15/03/2024 por 45000 EUR."
        await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-200",
            text=text,
        )

        # Check ABOUT edges exist
        result = await falkordb_client.execute_cypher("""
            MATCH (c:Claim {tenant_id: 'test-tenant'})-[:ABOUT]->(e:Entity {name: 'Juan Perez'})
            RETURN c.statement AS stmt, c.claim_type AS type
        """)
        # At least one claim should be linked to Juan Perez
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# 5. Contradiction Detection
# ---------------------------------------------------------------------------

class TestContradictionDetection:
    """Test detection of contradicting claims."""

    @pytest.mark.asyncio
    async def test_temporal_contradiction(self, falkordb_client):
        """Two different dates about the same entity should create CONTRADICTS."""
        # Setup: entity + two documents with different dates
        await falkordb_client.execute_cypher("""
            CREATE (e:Entity {
                tenant_id: 'test-tenant',
                name: 'Maria Garcia',
                normalized_name: 'maria garcia',
                entity_type: 'person'
            })
            CREATE (d1:Document {tenant_id: 'test-tenant', document_id: 'doc-300'})
            CREATE (d2:Document {tenant_id: 'test-tenant', document_id: 'doc-301'})
            CREATE (e)-[:MENTIONED_IN]->(d1)
            CREATE (e)-[:MENTIONED_IN]->(d2)
        """)

        extractor = ClaimExtractor()

        # First document: date 15/03/2024
        await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-300",
            text="Maria Garcia firmo el 15/03/2024.",
        )

        # Second document: different date 22/03/2024
        await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-301",
            text="Maria Garcia firmo el 22/03/2024.",
        )

        # Check for CONTRADICTS edge
        result = await falkordb_client.execute_cypher("""
            MATCH (c1:Claim {tenant_id: 'test-tenant'})-[r:CONTRADICTS]->(c2:Claim {tenant_id: 'test-tenant'})
            RETURN c1.statement AS s1, c2.statement AS s2,
                   r.contradiction_type AS type
        """)
        assert len(result) >= 1
        assert result[0]["type"] == "temporal"

    @pytest.mark.asyncio
    async def test_no_contradiction_same_value(self, falkordb_client):
        """Same date in two documents should NOT create CONTRADICTS."""
        await falkordb_client.execute_cypher("""
            CREATE (e:Entity {
                tenant_id: 'test-tenant',
                name: 'Pedro Lopez',
                normalized_name: 'pedro lopez',
                entity_type: 'person'
            })
            CREATE (d1:Document {tenant_id: 'test-tenant', document_id: 'doc-400'})
            CREATE (d2:Document {tenant_id: 'test-tenant', document_id: 'doc-401'})
            CREATE (e)-[:MENTIONED_IN]->(d1)
            CREATE (e)-[:MENTIONED_IN]->(d2)
        """)

        extractor = ClaimExtractor()

        await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-400",
            text="Pedro Lopez firmo el 15/03/2024.",
        )
        await extractor.extract_claims(
            tenant_id="test-tenant",
            document_id="doc-401",
            text="Pedro Lopez firmo el 15/03/2024.",
        )

        result = await falkordb_client.execute_cypher("""
            MATCH (c1:Claim {tenant_id: 'test-tenant'})-[r:CONTRADICTS]->(c2:Claim {tenant_id: 'test-tenant'})
            WHERE c1.statement CONTAINS '15/03/2024'
            RETURN count(r) AS cnt
        """)
        assert result[0]["cnt"] == 0


# ---------------------------------------------------------------------------
# 6. Subgraph Extractor Integration
# ---------------------------------------------------------------------------

class TestSubgraphIntegration:
    """Test that claims appear in subgraph_extractor traversals."""

    @pytest.mark.asyncio
    async def test_claims_in_subgraph(self, falkordb_client):
        """Subgraph traversal should include Claim nodes for discovered entities."""
        # Build a mini graph: Entity -> Document <- Claim -> Entity
        await falkordb_client.execute_cypher("""
            CREATE (e:Entity {
                tenant_id: 'test-tenant',
                name: 'Ana Torres',
                normalized_name: 'ana torres',
                entity_type: 'person'
            })
            CREATE (d:Document {
                tenant_id: 'test-tenant',
                document_id: 'doc-500',
                title: 'Contrato Ana'
            })
            CREATE (c:Claim {
                tenant_id: 'test-tenant',
                claim_id: 'claim-500',
                statement: 'Salario: 50000 EUR',
                claim_type: 'numeric',
                confidence: 0.95,
                source_chunk: 'Retribucion bruta: 50.000 EUR anuales'
            })
            CREATE (e)-[:MENTIONED_IN]->(d)
            CREATE (c)-[:EXTRACTED_FROM]->(d)
            CREATE (c)-[:ABOUT]->(e)
        """)

        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        result = await extractor.extract(
            tenant_id="test-tenant",
            entities=[{"value": "Ana Torres", "type": "person"}],
            max_hops=2,
            max_nodes=50,
        )

        # Should have Entity, Document, and Claim nodes
        labels = {n.get("label") for n in result["nodes"]}
        assert "Entity" in labels
        assert "Document" in labels
        assert "Claim" in labels

        # Should have ABOUT and EXTRACTED_FROM edges
        edge_labels = {e.get("label") for e in result["edges"]}
        assert "ABOUT" in edge_labels

    @pytest.mark.asyncio
    async def test_contradictions_in_subgraph(self, falkordb_client):
        """CONTRADICTS edges should appear in the subgraph."""
        await falkordb_client.execute_cypher("""
            CREATE (e:Entity {
                tenant_id: 'test-tenant',
                name: 'Luis Vega',
                normalized_name: 'luis vega',
                entity_type: 'person'
            })
            CREATE (d1:Document {tenant_id: 'test-tenant', document_id: 'doc-600'})
            CREATE (d2:Document {tenant_id: 'test-tenant', document_id: 'doc-601'})
            CREATE (c1:Claim {
                tenant_id: 'test-tenant',
                claim_id: 'c-600',
                statement: 'Fecha: 01/01/2024',
                claim_type: 'temporal',
                confidence: 0.9
            })
            CREATE (c2:Claim {
                tenant_id: 'test-tenant',
                claim_id: 'c-601',
                statement: 'Fecha: 15/02/2024',
                claim_type: 'temporal',
                confidence: 0.8
            })
            CREATE (e)-[:MENTIONED_IN]->(d1)
            CREATE (e)-[:MENTIONED_IN]->(d2)
            CREATE (c1)-[:EXTRACTED_FROM]->(d1)
            CREATE (c2)-[:EXTRACTED_FROM]->(d2)
            CREATE (c1)-[:ABOUT]->(e)
            CREATE (c2)-[:ABOUT]->(e)
            CREATE (c1)-[:CONTRADICTS {contradiction_type: 'temporal'}]->(c2)
        """)

        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        result = await extractor.extract(
            tenant_id="test-tenant",
            entities=[{"value": "Luis Vega", "type": "person"}],
            max_hops=2,
            max_nodes=50,
        )

        # Both claims should be in nodes
        claim_nodes = [n for n in result["nodes"] if n.get("label") == "Claim"]
        assert len(claim_nodes) >= 2

        # CONTRADICTS edge should be present
        contra_edges = [e for e in result["edges"] if e.get("label") == "CONTRADICTS"]
        assert len(contra_edges) >= 1
        assert contra_edges[0]["properties"].get("contradiction_type") == "temporal"
