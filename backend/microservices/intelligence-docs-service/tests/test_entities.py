import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.providers.entities.regex_spanish import RegexSpanishProvider
from app.providers.entities.sglang_ner import SglangNerProvider


# --- Regex provider tests ---

@pytest.mark.asyncio
async def test_extracts_dni():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("DNI del cliente: 12345678Z")
    assert any(e.type == "DNI" and e.value == "12345678Z" for e in entities)


@pytest.mark.asyncio
async def test_extracts_nie():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("NIE: X1234567L")
    assert any(e.type == "NIE" for e in entities)


@pytest.mark.asyncio
async def test_extracts_cif():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("CIF empresa: A12345678")
    assert any(e.type == "CIF" and e.value == "A12345678" for e in entities)


@pytest.mark.asyncio
async def test_is_always_available():
    provider = RegexSpanishProvider()
    assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_no_entities_in_clean_text():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("El tiempo hoy es soleado")
    assert len(entities) == 0


# --- SGLang NER provider tests ---

@pytest.mark.asyncio
async def test_sglang_ner_extracts_entities():
    provider = SglangNerProvider(base_url="http://sglang:8000/v1", model="test-model", timeout=30)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '[{"type":"PERSON","value":"Juan Garcia"},{"type":"ORGANIZATION","value":"Acme S.L."}]'}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        entities = await provider.extract_entities("Juan Garcia de Acme S.L.")
        types = {e.type for e in entities}
        assert "PERSON" in types
        assert "ORGANIZATION" in types


@pytest.mark.asyncio
async def test_sglang_ner_handles_invalid_json():
    provider = SglangNerProvider(base_url="http://sglang:8000/v1", model="test-model", timeout=30)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json"}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        entities = await provider.extract_entities("some text")
        assert entities == []


@pytest.mark.asyncio
async def test_sglang_ner_unavailable_when_no_model():
    provider = SglangNerProvider(base_url="http://sglang:8000/v1", model="", timeout=30)
    assert await provider.is_available() is False
