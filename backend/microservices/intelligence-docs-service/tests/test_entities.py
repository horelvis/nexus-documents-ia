import pytest
from app.providers.base import Entity
from app.providers.guardrails.spanish_id_validator import SpanishIdValidator


# --- SpanishIdValidator guardrail tests ---

@pytest.fixture
def validator():
    return SpanishIdValidator()


@pytest.mark.asyncio
async def test_guardrail_finds_dni_in_text(validator):
    entities = validator.validate_and_enrich([], "DNI del cliente: 12345678Z")
    assert any(e.type == "DNI" and e.value == "12345678Z" for e in entities)


@pytest.mark.asyncio
async def test_guardrail_finds_nie_in_text(validator):
    entities = validator.validate_and_enrich([], "NIE: X1234567L")
    assert any(e.type == "NIE" for e in entities)


@pytest.mark.asyncio
async def test_guardrail_finds_cif_in_text(validator):
    entities = validator.validate_and_enrich([], "CIF empresa: A12345678")
    assert any(e.type == "CIF" and e.value == "A12345678" for e in entities)


@pytest.mark.asyncio
async def test_guardrail_no_entities_in_clean_text(validator):
    entities = validator.validate_and_enrich([], "El tiempo hoy es soleado")
    assert len(entities) == 0


@pytest.mark.asyncio
async def test_guardrail_validates_valid_dni(validator):
    entity = Entity(type="DNI", value="12345678Z", provider="langextract", confidence=0.8)
    result = validator.validate_and_enrich([entity], "")
    assert result[0].confidence == 0.95
    assert result[0].attributes["checksum_valid"] is True


@pytest.mark.asyncio
async def test_guardrail_flags_invalid_dni(validator):
    entity = Entity(type="DNI", value="12345678A", provider="langextract", confidence=0.8)
    result = validator.validate_and_enrich([entity], "")
    assert result[0].confidence == 0.3
    assert result[0].attributes["checksum_valid"] is False


@pytest.mark.asyncio
async def test_guardrail_validates_valid_nie(validator):
    entity = Entity(type="NIE", value="X1234567L", provider="langextract", confidence=0.8)
    result = validator.validate_and_enrich([entity], "")
    assert result[0].confidence == 0.95
    assert result[0].attributes["checksum_valid"] is True


@pytest.mark.asyncio
async def test_guardrail_catches_missed_ids(validator):
    """Guardrail should find IDs in text that the LLM missed."""
    existing = Entity(type="PERSON", value="Juan Garcia", provider="langextract", confidence=0.8)
    result = validator.validate_and_enrich([existing], "Contrato de Juan Garcia, DNI 12345678Z")
    types = {e.type for e in result}
    assert "PERSON" in types
    assert "DNI" in types
    assert len(result) == 2


@pytest.mark.asyncio
async def test_guardrail_no_duplicates(validator):
    """Should not add IDs already present in entities."""
    existing = Entity(type="DNI", value="12345678Z", provider="langextract", confidence=0.8)
    result = validator.validate_and_enrich([existing], "DNI: 12345678Z aparece en el texto")
    dni_entities = [e for e in result if e.value == "12345678Z"]
    assert len(dni_entities) == 1
