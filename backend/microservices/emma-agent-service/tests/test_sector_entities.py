"""
Tests: Sector Entity Extraction

Validates that regex patterns extract the correct entities from
domain-specific queries. Also tests cross-sector false positives.

No async, no mocks — pure regex tests.
"""

import pytest

from app.agents.langgraph.sectors.entity_extractor import extract_entities
from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS


# =============================================================================
# Legal Entity Extraction
# =============================================================================


class TestLegalEntityExtraction:
    """Verify legal sector patterns extract laws, articles, sentences, etc."""

    @pytest.fixture
    def legal_patterns(self):
        return SECTOR_CONFIGS["legal"].entity_patterns

    def test_extract_organic_law(self, legal_patterns):
        result = extract_entities("Ley Orgánica 3/2018 de protección de datos", legal_patterns)
        assert "ley" in result
        assert any("3/2018" in m for m in result["ley"])

    def test_extract_royal_decree(self, legal_patterns):
        result = extract_entities("Real Decreto Legislativo 2/2015", legal_patterns)
        assert "ley" in result
        assert any("2/2015" in m for m in result["ley"])

    def test_extract_rd_abbreviation(self, legal_patterns):
        result = extract_entities("R.D. 1234/2020 sobre comercio", legal_patterns)
        assert "ley" in result
        assert any("1234/2020" in m for m in result["ley"])

    def test_extract_article(self, legal_patterns):
        result = extract_entities("El Art. 1902 del Código Civil establece", legal_patterns)
        assert "articulo" in result
        assert any("1902" in m for m in result["articulo"])

    def test_extract_article_bis(self, legal_patterns):
        result = extract_entities("artículo 23 bis de la ley", legal_patterns)
        assert "articulo" in result
        assert any("23 bis" in m for m in result["articulo"])

    def test_extract_sentence_sts(self, legal_patterns):
        result = extract_entities("Según la STS 123/2020", legal_patterns)
        assert "sentencia" in result
        assert any("123/2020" in m for m in result["sentencia"])

    def test_extract_sentence_sap(self, legal_patterns):
        result = extract_entities("La SAP Madrid 456/2021 confirma", legal_patterns)
        assert "sentencia" in result

    def test_extract_boe(self, legal_patterns):
        result = extract_entities("Publicado en BOE núm. 34", legal_patterns)
        assert "boe" in result
        assert any("34" in m for m in result["boe"])

    def test_extract_expediente(self, legal_patterns):
        result = extract_entities("Expediente núm. EXP-2024/001", legal_patterns)
        assert "expediente" in result

    def test_extract_multiple_entities(self, legal_patterns):
        query = "Art. 54 del Real Decreto 2/2015 según STS 789/2023"
        result = extract_entities(query, legal_patterns)
        assert "articulo" in result
        assert "ley" in result
        assert "sentencia" in result

    def test_empty_query(self, legal_patterns):
        result = extract_entities("", legal_patterns)
        assert result == {}

    def test_no_match(self, legal_patterns):
        result = extract_entities("Buenos días, ¿cómo estás?", legal_patterns)
        assert result == {}


# =============================================================================
# Medical Entity Extraction
# =============================================================================


class TestMedicalEntityExtraction:
    """Verify medical sector patterns extract diagnoses, drugs, patients, etc."""

    @pytest.fixture
    def medical_patterns(self):
        return SECTOR_CONFIGS["medical"].entity_patterns

    def test_extract_cie10(self, medical_patterns):
        result = extract_entities("Diagnóstico: J45.0 asma bronquial", medical_patterns)
        assert "cie10" in result
        assert any("J45" in m for m in result["cie10"])

    def test_extract_dosage_mg(self, medical_patterns):
        result = extract_entities("Prescripción: 500 mg de amoxicilina", medical_patterns)
        assert "farmaco" in result

    def test_extract_dosage_ml(self, medical_patterns):
        result = extract_entities("Administrar 10 ml cada 8 horas", medical_patterns)
        assert "farmaco" in result

    def test_extract_procedure(self, medical_patterns):
        result = extract_entities("Procedimiento CIE-9-MC 99.84", medical_patterns)
        assert "procedimiento" in result

    def test_extract_patient_hc(self, medical_patterns):
        result = extract_entities("Historia Clínica núm. HC-2024-001", medical_patterns)
        assert "paciente" in result

    def test_extract_patient_nhc(self, medical_patterns):
        result = extract_entities("NHC PAC-12345 ingresado ayer", medical_patterns)
        assert "paciente" in result


# =============================================================================
# Documental Entity Extraction
# =============================================================================


class TestDocumentalEntityExtraction:
    """Verify documental sector patterns extract persons, NIFs, amounts, etc."""

    @pytest.fixture
    def documental_patterns(self):
        return SECTOR_CONFIGS["documental"].entity_patterns

    def test_extract_person_two_names(self, documental_patterns):
        result = extract_entities("Facturas de María García", documental_patterns)
        assert "persona" in result
        assert any("María García" in m for m in result["persona"])

    def test_extract_person_three_names(self, documental_patterns):
        result = extract_entities("Contrato de Javier Martínez López", documental_patterns)
        assert "persona" in result

    def test_extract_nif_company(self, documental_patterns):
        result = extract_entities("Empresa con NIF B12345678", documental_patterns)
        assert "nif" in result
        assert any("B12345678" in m for m in result["nif"])

    def test_extract_nif_personal(self, documental_patterns):
        result = extract_entities("DNI 12345678Z del titular", documental_patterns)
        assert "nif" in result
        assert any("12345678Z" in m for m in result["nif"])

    def test_extract_importe_euros(self, documental_patterns):
        result = extract_entities("Importe de 10.000,00 €", documental_patterns)
        assert "importe" in result

    def test_extract_importe_euro_prefix(self, documental_patterns):
        result = extract_entities("Coste: € 5.000,00", documental_patterns)
        assert "importe" in result

    def test_extract_date_slash(self, documental_patterns):
        result = extract_entities("Fecha: 15/01/2024", documental_patterns)
        assert "fecha" in result

    def test_extract_date_natural(self, documental_patterns):
        result = extract_entities("El 15 de enero de 2024 se firmó", documental_patterns)
        assert "fecha" in result

    def test_extract_reference(self, documental_patterns):
        result = extract_entities("Ref. PO-2024-001 adjunto", documental_patterns)
        assert "referencia" in result


# =============================================================================
# Cross-Sector False Positives
# =============================================================================


class TestCrossSectorFalsePositives:
    """Ensure patterns from one sector don't match queries from another."""

    def test_legal_text_no_medical_match(self):
        """A legal query shouldn't produce medical entity matches."""
        medical_patterns = SECTOR_CONFIGS["medical"].entity_patterns
        legal_query = "El Art. 1902 del Código Civil según STS 123/2020"
        result = extract_entities(legal_query, medical_patterns)
        # CIE-10 and farmaco should not match legal text
        assert "cie10" not in result
        assert "farmaco" not in result
        assert "procedimiento" not in result

    def test_medical_text_no_legal_match(self):
        """A medical query shouldn't produce legal entity matches."""
        legal_patterns = SECTOR_CONFIGS["legal"].entity_patterns
        medical_query = "Paciente con diagnóstico J45.0, dosis 500 mg"
        result = extract_entities(medical_query, legal_patterns)
        # Law and sentence patterns should not match medical text
        assert "ley" not in result
        assert "sentencia" not in result
        assert "boe" not in result

    def test_empty_query_all_sectors(self, sector):
        """Empty query produces no matches in any sector."""
        _, config = sector
        result = extract_entities("", config.entity_patterns)
        assert result == {}
