"""
Tests for Knowledge Extraction Service

Covers:
- Entity normalization
- Entity type classification
- Relationship detection
- Domain detection
- Knowledge storage
"""

import pytest
from typing import Dict, Any, List
from datetime import datetime

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.knowledge.schemas import (
    EntityType,
    DomainType,
    RelationshipType,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeExtractionResult,
)
from app.services.knowledge.extraction_service import KnowledgeExtractionService


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def extraction_service():
    """Create a KnowledgeExtractionService instance."""
    return KnowledgeExtractionService()


@pytest.fixture
def sample_langextract_entities():
    """Sample entities from LangExtract service."""
    return [
        {
            "type": "PERSON",
            "value": "Juan García López",
            "start": 100,
            "end": 117
        },
        {
            "type": "ORG",
            "value": "Acme Corporation S.A.",
            "start": 200,
            "end": 221
        },
        {
            "type": "DATE",
            "value": "15 de enero de 2024",
            "start": 300,
            "end": 319
        },
        {
            "type": "MONEY",
            "value": "$50,000.00",
            "start": 400,
            "end": 410
        },
        {
            "type": "CLAUSE",
            "value": "Cláusula de Confidencialidad",
            "start": 500,
            "end": 528
        }
    ]


@pytest.fixture
def sample_contract_content():
    """Sample contract content for testing."""
    return """
    CONTRATO DE PRESTACIÓN DE SERVICIOS

    Entre las partes:
    - Juan García López, en calidad de CONTRATANTE
    - Acme Corporation S.A., en calidad de CONTRATISTA

    Fecha: 15 de enero de 2024
    Monto: $50,000.00 (cincuenta mil dólares)

    Cláusula de Confidencialidad:
    Las partes acuerdan mantener la confidencialidad de toda la información
    compartida durante la vigencia de este contrato.

    Artículo 5. Plazo del Contrato:
    El presente contrato tendrá una vigencia de doce (12) meses.
    """


# ============================================================================
# Unit Tests
# ============================================================================

class TestEntityType:
    """Tests for EntityType enum."""

    def test_standard_types(self):
        """Test standard entity types exist."""
        assert EntityType.PERSON == "person"
        assert EntityType.ORGANIZATION == "organization"
        assert EntityType.DATE == "date"
        assert EntityType.AMOUNT == "amount"
        assert EntityType.CLAUSE == "clause"

    def test_additional_types(self):
        """Test additional entity types."""
        assert EntityType.TERM == "term"
        assert EntityType.LOCATION == "location"
        assert EntityType.CONCEPT == "concept"
        assert EntityType.OBLIGATION == "obligation"
        assert EntityType.RIGHT == "right"
        assert EntityType.REFERENCE == "reference"


class TestDomainType:
    """Tests for DomainType enum."""

    def test_domain_types(self):
        """Test domain types."""
        assert DomainType.LEGAL == "legal"
        assert DomainType.FISCAL == "fiscal"
        assert DomainType.HR == "hr"
        assert DomainType.GENERAL == "general"
        assert DomainType.FINANCIAL == "financial"
        assert DomainType.TECHNICAL == "technical"


class TestKnowledgeEntity:
    """Tests for KnowledgeEntity schema."""

    def test_entity_creation(self):
        """Test creating a knowledge entity."""
        entity = KnowledgeEntity(
            entity_type=EntityType.PERSON,
            entity_value="Juan García",
            entity_label="Contratante Principal",
            context_text="Juan García actúa como contratante...",
            extraction_confidence=0.95,
            domain=DomainType.LEGAL
        )
        assert entity.entity_type == EntityType.PERSON
        assert entity.entity_value == "Juan García"
        assert entity.extraction_confidence == 0.95

    def test_entity_with_attributes(self):
        """Test entity with custom attributes."""
        entity = KnowledgeEntity(
            entity_type=EntityType.CLAUSE,
            entity_value="Cláusula de Penalidad",
            context_text="En caso de incumplimiento...",
            extraction_confidence=0.88,
            attributes={"penalty_percentage": 10, "applies_to": "late_delivery"}
        )
        assert entity.attributes["penalty_percentage"] == 10

    def test_entity_with_position(self):
        """Test entity with position information."""
        entity = KnowledgeEntity(
            entity_type=EntityType.AMOUNT,
            entity_value="$50,000",
            context_text="Monto total: $50,000",
            extraction_confidence=0.9,
            char_start=100,
            char_end=107,
            page_number=1
        )
        assert entity.char_start == 100
        assert entity.char_end == 107
        assert entity.page_number == 1


class TestKnowledgeRelationship:
    """Tests for KnowledgeRelationship schema."""

    def test_relationship_creation(self):
        """Test creating a relationship."""
        relationship = KnowledgeRelationship(
            source_entity_value="Juan García",
            target_entity_value="Acme Corporation",
            relationship_type=RelationshipType.RELATES_TO,
            relationship_strength=0.8,
            context_snippet="contrato entre Juan García y Acme Corporation"
        )
        assert relationship.relationship_type == RelationshipType.RELATES_TO
        assert relationship.relationship_strength == 0.8


class TestKnowledgeExtractionService:
    """Tests for KnowledgeExtractionService."""

    @pytest.mark.asyncio
    async def test_normalize_entities(
        self,
        extraction_service,
        sample_langextract_entities,
        sample_contract_content
    ):
        """Test entity normalization from LangExtract output."""
        entities = await extraction_service._normalize_entities(
            raw_entities=sample_langextract_entities,
            content=sample_contract_content,
            document_type="contract"
        )

        # Should have entities
        assert len(entities) > 0

        # Check entity types are properly mapped (entity_type is string, not enum)
        entity_types = [e.entity_type for e in entities]
        assert "person" in entity_types

    @pytest.mark.asyncio
    async def test_detect_domain_fiscal(self, extraction_service):
        """Test domain detection for fiscal content."""
        fiscal_content = """
        DECLARACIÓN DE IMPUESTO SOBRE LA RENTA

        Contribuyente: Empresa XYZ
        RFC: XYZX123456ABC
        Ejercicio fiscal: 2024

        Ingresos acumulables: $1,000,000.00
        Deducciones autorizadas: $300,000.00
        Base gravable: $700,000.00
        ISR a pagar: $210,000.00
        """

        domain = await extraction_service._detect_domain(
            content=fiscal_content,
            document_type="tax_form"
        )

        assert domain == DomainType.FISCAL

    @pytest.mark.asyncio
    async def test_detect_domain_hr(self, extraction_service):
        """Test domain detection for HR content."""
        hr_content = """
        CONTRATO LABORAL INDIVIDUAL

        El empleador: ABC Company
        El trabajador: María López

        Puesto: Analista Senior
        Salario mensual: $25,000.00
        Jornada laboral: 8 horas diarias
        Prestaciones: IMSS, INFONAVIT, aguinaldo
        """

        domain = await extraction_service._detect_domain(
            content=hr_content,
            document_type="employment_contract"
        )

        assert domain == DomainType.HR

    @pytest.mark.asyncio
    async def test_detect_relationships(self, extraction_service):
        """Test relationship detection between entities."""
        entities = [
            KnowledgeEntity(
                entity_type=EntityType.PERSON,
                entity_value="Juan García",
                context_text="Juan García como representante de",
                extraction_confidence=0.9
            ),
            KnowledgeEntity(
                entity_type=EntityType.ORGANIZATION,
                entity_value="Acme Corporation",
                context_text="Acme Corporation, empresa contratante",
                extraction_confidence=0.9
            ),
            KnowledgeEntity(
                entity_type=EntityType.CLAUSE,
                entity_value="Cláusula de Confidencialidad",
                context_text="se establece la Cláusula de Confidencialidad",
                extraction_confidence=0.85
            )
        ]

        content = """
        Juan García actúa como representante de Acme Corporation.
        El contrato incluye una Cláusula de Confidencialidad que
        obliga a ambas partes.
        """

        relationships = await extraction_service._detect_relationships(
            entities=entities,
            content=content
        )

        # Should detect relationships based on co-occurrence
        assert isinstance(relationships, list)


class TestExtractionResult:
    """Tests for KnowledgeExtractionResult."""

    def test_extraction_result_creation(self):
        """Test creating an extraction result."""
        result = KnowledgeExtractionResult(
            document_id="doc-123",
            tenant_id="tenant-456",
            entities=[
                KnowledgeEntity(
                    entity_type=EntityType.PERSON,
                    entity_value="Test Person",
                    context_text="Test context",
                    extraction_confidence=0.9
                )
            ],
            relationships=[],
            entities_count=1,
            relationships_count=0,
            success=True
        )

        assert result.document_id == "doc-123"
        assert result.entities_count == 1
        assert result.success is True
        assert len(result.entities) == 1


class TestDomainKeywords:
    """Tests for domain keyword detection."""

    @pytest.mark.asyncio
    async def test_detect_domain_general(self, extraction_service):
        """Test domain detection for general content."""
        general_content = """
        Este es un documento general sin contenido específico.
        No contiene términos legales, fiscales ni laborales.
        """

        domain = await extraction_service._detect_domain(
            content=general_content,
            document_type="general"
        )

        assert domain == DomainType.GENERAL

    @pytest.mark.asyncio
    async def test_detect_domain_financial(self, extraction_service):
        """Test domain detection for financial content."""
        financial_content = """
        ESTADO FINANCIERO CONSOLIDADO

        Balance General al 31 de diciembre de 2024
        Activos totales: $5,000,000
        Pasivos totales: $2,000,000
        Capital contable: $3,000,000
        ROI: 15%
        EBITDA: $800,000
        """

        domain = await extraction_service._detect_domain(
            content=financial_content,
            document_type="financial_report"
        )

        assert domain == DomainType.FINANCIAL


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.integration
class TestKnowledgeExtractionIntegration:
    """Integration tests requiring Weaviate and PostgreSQL."""

    @pytest.mark.asyncio
    async def test_full_extraction_flow(self):
        """Test complete extraction flow with storage."""
        pytest.skip("Requires Weaviate and PostgreSQL connection")


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
