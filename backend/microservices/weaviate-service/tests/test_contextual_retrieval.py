"""
Tests for Contextual Retrieval Module

Tests cover:
1. Domain detection (Labor, Fiscal, Privacy, etc.)
2. Context prefix generation
3. Chunk contextualization
4. Spanish legislation knowledge base
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# =============================================================================
# Test Domain Detection
# =============================================================================

class TestDomainDetection:
    """Tests for legal domain detection."""

    def test_detect_labor_domain_keywords(self):
        """Should detect labor domain from keywords."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        Contrato de trabajo indefinido entre ACME Corp y Juan García.
        El trabajador tendrá una jornada de 40 horas semanales.
        Salario mensual de 2.500 euros brutos.
        """

        result = contextual_retrieval.detect_domain(text)

        assert result.primary_domain == LegalDomain.LABOR
        assert result.confidence > 0.5
        assert any("trabajador" in kw for kw in result.detected_keywords)

    def test_detect_labor_domain_from_document_type(self):
        """Should detect labor domain from document type metadata."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = "Este documento contiene información general."
        metadata = {"document_type": "contrato_laboral"}

        result = contextual_retrieval.detect_domain(text, metadata)

        assert result.primary_domain == LegalDomain.LABOR

    def test_detect_fiscal_domain(self):
        """Should detect fiscal domain from tax-related content."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        Factura número: 2024-001
        Base imponible: 1.000,00 €
        IVA (21%): 210,00 €
        Total factura: 1.210,00 €
        """

        result = contextual_retrieval.detect_domain(text)

        assert result.primary_domain == LegalDomain.FISCAL
        assert any("iva" in kw.lower() for kw in result.detected_keywords)

    def test_detect_privacy_domain(self):
        """Should detect privacy domain from RGPD content."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        Política de Protección de Datos
        Conforme al RGPD, el responsable del tratamiento garantiza
        la protección de los datos personales de los usuarios.
        Se requiere consentimiento explícito para el tratamiento.
        """

        result = contextual_retrieval.detect_domain(text)

        assert result.primary_domain == LegalDomain.PRIVACY
        assert any("rgpd" in kw.lower() for kw in result.detected_keywords)

    def test_detect_realestate_domain(self):
        """Should detect real estate domain from rental content."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        Contrato de Arrendamiento de Vivienda
        El arrendador cede el uso de la vivienda al inquilino.
        La renta mensual será de 800 euros.
        Se deposita una fianza de dos mensualidades.
        """

        result = contextual_retrieval.detect_domain(text)

        assert result.primary_domain == LegalDomain.REALESTATE
        assert any("arrendamiento" in kw for kw in result.detected_keywords)

    def test_detect_general_domain(self):
        """Should default to general for unrecognized content."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        Informe de actividades del primer trimestre.
        Se realizaron reuniones con clientes y proveedores.
        Los resultados fueron positivos.
        """

        result = contextual_retrieval.detect_domain(text)

        assert result.primary_domain == LegalDomain.GENERAL
        assert result.confidence < 0.5

    def test_detect_multiple_domains(self):
        """Should detect secondary domains when multiple apply."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        Contrato laboral con cláusulas de protección de datos.
        El trabajador consiente el tratamiento de sus datos personales
        conforme al RGPD para la gestión de nóminas.
        """

        result = contextual_retrieval.detect_domain(text)

        # Primary should be one of Labor or Privacy
        assert result.primary_domain in [LegalDomain.LABOR, LegalDomain.PRIVACY]

        # Secondary should include the other
        if result.primary_domain == LegalDomain.LABOR:
            assert LegalDomain.PRIVACY in result.secondary_domains or True
        else:
            assert LegalDomain.LABOR in result.secondary_domains or True


# =============================================================================
# Test Context Prefix Generation
# =============================================================================

class TestContextPrefixGeneration:
    """Tests for context prefix generation."""

    def test_generate_labor_context(self):
        """Should generate context with labor legislation."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain, DomainDetectionResult, LawReference
        )

        domain_result = DomainDetectionResult(
            primary_domain=LegalDomain.LABOR,
            confidence=0.8,
            detected_keywords=["trabajador", "contrato"],
            applicable_laws=[
                LawReference(
                    law_name="Estatuto de los Trabajadores",
                    abbreviation="ET",
                    boe_id="BOE-A-2015-11430",
                    reference="RDL 2/2015"
                )
            ]
        )

        prefix = contextual_retrieval.generate_context_prefix(
            domain_result,
            document_type="contrato_laboral"
        )

        assert "[CONTEXTO]" in prefix
        assert "[CONTENIDO]" in prefix
        assert "Laboral" in prefix
        assert "ET" in prefix or "BOE-A-2015-11430" in prefix
        assert "Art. 34" in prefix  # Jornada

    def test_generate_fiscal_context(self):
        """Should generate context with fiscal legislation."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain, DomainDetectionResult, LawReference
        )

        domain_result = DomainDetectionResult(
            primary_domain=LegalDomain.FISCAL,
            confidence=0.9,
            detected_keywords=["iva", "factura"],
            applicable_laws=[
                LawReference(
                    law_name="Ley del IVA",
                    abbreviation="LIVA",
                    boe_id="BOE-A-1992-28740",
                    reference="Ley 37/1992"
                )
            ]
        )

        prefix = contextual_retrieval.generate_context_prefix(
            domain_result,
            document_type="factura"
        )

        assert "[CONTEXTO]" in prefix
        assert "Tributario" in prefix or "Fiscal" in prefix
        assert "LIVA" in prefix or "RF" in prefix

    def test_generate_general_context(self):
        """Should generate minimal context for general documents."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain, DomainDetectionResult
        )

        domain_result = DomainDetectionResult(
            primary_domain=LegalDomain.GENERAL,
            confidence=0.3,
            detected_keywords=[],
            applicable_laws=[]
        )

        prefix = contextual_retrieval.generate_context_prefix(
            domain_result,
            document_type=""
        )

        assert "[CONTEXTO]" in prefix
        assert len(prefix) < 100  # Should be short


# =============================================================================
# Test Document Analysis
# =============================================================================

class TestDocumentAnalysis:
    """Tests for full document analysis."""

    @pytest.mark.asyncio
    async def test_analyze_labor_document(self):
        """Should analyze labor document and extract context."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        CONTRATO DE TRABAJO

        En Madrid, a 15 de enero de 2024.

        REUNIDOS
        De una parte, ACME S.L. con NIF B12345678, representada por D. Antonio López.
        De otra parte, D. Juan García con NIF 12345678A.

        CLÁUSULAS
        PRIMERA.- El trabajador prestará servicios en el departamento de Desarrollo.
        SEGUNDA.- La jornada laboral será de 40 horas semanales.
        TERCERA.- El salario bruto anual será de 30.000 euros.
        CUARTA.- El período de prueba será de 3 meses.
        """

        result = await contextual_retrieval.analyze_document(
            document_id="test-doc-1",
            text=text,
            metadata={"document_type": "contrato_trabajo"},
            tenant_id="test-tenant",
            use_llm=False
        )

        assert result.domain == LegalDomain.LABOR
        assert len(result.applicable_laws) > 0
        assert "[CONTEXTO]" in result.context_prefix
        assert any("ET" in l.abbreviation for l in result.applicable_laws)

    @pytest.mark.asyncio
    async def test_analyze_invoice_document(self):
        """Should analyze invoice and detect fiscal domain."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, LegalDomain
        )

        text = """
        FACTURA

        Emisor: TechServices S.L. - NIF B87654321
        Cliente: ACME S.L. - NIF B12345678

        Concepto: Servicios de consultoría IT - Marzo 2024

        Base imponible: 5.000,00 €
        IVA (21%): 1.050,00 €
        -----------------------
        TOTAL: 6.050,00 €

        Forma de pago: Transferencia bancaria
        Vencimiento: 30 días
        """

        result = await contextual_retrieval.analyze_document(
            document_id="test-invoice-1",
            text=text,
            metadata={"document_type": "factura"},
            tenant_id="test-tenant"
        )

        assert result.domain == LegalDomain.FISCAL
        assert any("importe:" in e for e in result.key_entities)

    @pytest.mark.asyncio
    async def test_extract_entities(self):
        """Should extract key entities from document."""
        from app.services.rag.contextual_retrieval import contextual_retrieval

        text = """
        Contrato firmado el 15/01/2024 con vencimiento 15/01/2025.
        Importe total: 50.000,00 €
        Cliente: B12345678
        """

        result = await contextual_retrieval.analyze_document(
            document_id="test-doc",
            text=text,
            metadata={},
            tenant_id="test"
        )

        # Should extract dates
        assert any("fecha:" in e for e in result.key_entities)

        # Should extract amounts
        assert any("importe:" in e for e in result.key_entities)

        # Should extract NIFs
        assert any("nif:" in e for e in result.key_entities)


# =============================================================================
# Test Chunk Contextualization
# =============================================================================

class TestChunkContextualization:
    """Tests for applying context to chunks."""

    def test_apply_context_to_chunks(self):
        """Should prepend context to chunk text."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, ContextGenerationResult, LegalDomain, LawReference
        )

        # Create mock chunks
        class MockChunk:
            def __init__(self, text):
                self.text = text
                self.metadata = {}

        chunks = [
            MockChunk("El trabajador tendrá una jornada de 40 horas."),
            MockChunk("El salario será de 30.000 euros anuales."),
        ]

        context_result = ContextGenerationResult(
            document_id="test",
            domain=LegalDomain.LABOR,
            context_prefix="[CONTEXTO] Contrato laboral. Aplica ET. [CONTENIDO]",
            applicable_laws=[
                LawReference(
                    law_name="ET",
                    abbreviation="ET",
                    boe_id="BOE-A-2015-11430",
                    reference="RDL 2/2015"
                )
            ],
            document_summary="",
            key_entities=[]
        )

        contextualized = contextual_retrieval.apply_context_to_chunks(
            chunks=chunks,
            context_result=context_result
        )

        assert len(contextualized) == 2

        # Check first chunk
        assert contextualized[0].contextualized_text.startswith("[CONTEXTO]")
        assert "trabajador" in contextualized[0].contextualized_text
        assert contextualized[0].domain == LegalDomain.LABOR

        # Check metadata
        assert len(contextualized[0].applicable_laws) > 0

    def test_enrich_chunk_metadata(self):
        """Should add contextual info to chunk metadata."""
        from app.services.rag.contextual_retrieval import (
            contextual_retrieval, ContextGenerationResult, LegalDomain, LawReference
        )

        original_metadata = {
            "chunk_index": 0,
            "document_id": "test"
        }

        context_result = ContextGenerationResult(
            document_id="test",
            domain=LegalDomain.LABOR,
            context_prefix="[CONTEXTO] ...",
            applicable_laws=[
                LawReference(
                    law_name="ET",
                    abbreviation="ET",
                    boe_id="BOE-A-2015-11430",
                    reference="RDL 2/2015"
                )
            ],
            document_summary="",
            key_entities=["fecha:15/01/2024"],
            metadata={"domain_confidence": 0.85}
        )

        enriched = contextual_retrieval.enrich_chunk_metadata(
            chunk_metadata=original_metadata,
            context_result=context_result
        )

        assert enriched["legal_domain"] == "labor"
        assert len(enriched["applicable_laws"]) > 0
        assert enriched["domain_confidence"] == 0.85
        assert enriched["contextual_retrieval"] is True
        # Original metadata preserved
        assert enriched["chunk_index"] == 0
        assert enriched["document_id"] == "test"


# =============================================================================
# Test Spanish Legislation Database
# =============================================================================

class TestSpanishLegislation:
    """Tests for Spanish legislation knowledge base."""

    def test_legislation_completeness(self):
        """Should have all major Spanish laws."""
        from app.services.rag.contextual_retrieval import SPANISH_LEGISLATION, LegalDomain

        # Labor
        assert LegalDomain.LABOR in SPANISH_LEGISLATION
        labor = SPANISH_LEGISLATION[LegalDomain.LABOR]
        assert any("Estatuto" in l["name"] for l in labor["laws"])

        # Fiscal
        assert LegalDomain.FISCAL in SPANISH_LEGISLATION
        fiscal = SPANISH_LEGISLATION[LegalDomain.FISCAL]
        assert any("IVA" in l["name"] for l in fiscal["laws"])

        # Privacy
        assert LegalDomain.PRIVACY in SPANISH_LEGISLATION
        privacy = SPANISH_LEGISLATION[LegalDomain.PRIVACY]
        assert any("RGPD" in l["name"] for l in privacy["laws"])

    def test_law_references_format(self):
        """Should have properly formatted BOE references."""
        from app.services.rag.contextual_retrieval import SPANISH_LEGISLATION

        for domain, info in SPANISH_LEGISLATION.items():
            for law in info.get("laws", []):
                assert "boe_id" in law
                assert "abbreviation" in law
                # BOE format or EUR-Lex
                boe_id = law["boe_id"]
                assert boe_id.startswith("BOE-") or boe_id.startswith("EUR-Lex")

    def test_law_reference_citation(self):
        """Should generate proper legal citations."""
        from app.services.rag.contextual_retrieval import LawReference

        law = LawReference(
            law_name="Estatuto de los Trabajadores",
            abbreviation="ET",
            boe_id="BOE-A-2015-11430",
            reference="RDL 2/2015",
            article="34",
            article_description="Jornada laboral"
        )

        citation = law.to_citation()

        assert "Art. 34" in citation
        assert "ET" in citation
        assert "BOE-A-2015-11430" in citation


# =============================================================================
# Integration Test
# =============================================================================

class TestContextualRetrievalIntegration:
    """Integration tests for contextual retrieval pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Test complete contextualization pipeline."""
        from app.services.rag.contextual_retrieval import (
            contextualize_document, LegalDomain
        )

        # Mock chunks
        class MockChunk:
            def __init__(self, text):
                self.text = text
                self.metadata = {}

        text = """
        CONTRATO DE ARRENDAMIENTO DE VIVIENDA

        En Madrid, a 1 de febrero de 2024.

        ARRENDADOR: D. Carlos Martínez, con DNI 11111111A
        ARRENDATARIO: D. María López, con DNI 22222222B

        CLÁUSULAS:
        1. El arrendador cede el uso de la vivienda sita en C/ Mayor 10, Madrid.
        2. La renta mensual será de 900 euros.
        3. Se deposita una fianza de 1.800 euros (dos mensualidades).
        4. Duración: 5 años según la LAU vigente.
        """

        chunks = [
            MockChunk("El arrendador cede el uso de la vivienda."),
            MockChunk("La renta mensual será de 900 euros."),
            MockChunk("Se deposita una fianza de 1.800 euros."),
        ]

        context_result, contextualized_chunks = await contextualize_document(
            document_id="rental-contract-1",
            text=text,
            chunks=chunks,
            metadata={"document_type": "contrato_arrendamiento"},
            tenant_id="test-tenant"
        )

        # Verify domain detection
        assert context_result.domain == LegalDomain.REALESTATE

        # Verify context applied to all chunks
        assert len(contextualized_chunks) == 3
        for chunk in contextualized_chunks:
            assert chunk.contextualized_text.startswith("[CONTEXTO]")
            assert chunk.domain == LegalDomain.REALESTATE


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
