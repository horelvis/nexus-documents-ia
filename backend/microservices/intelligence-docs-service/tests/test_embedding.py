import pytest
from unittest.mock import MagicMock
from app.providers.embedding.sentence_transformers import SentenceTransformersProvider


@pytest.mark.asyncio
async def test_embed_single_returns_correct_dimensions():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3", device="cpu", expected_dimensions=1024,
    )
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 1024)
    provider._model = mock_model

    result = await provider.embed_single("test text")
    assert len(result) == 1024


@pytest.mark.asyncio
async def test_embed_batch():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3", device="cpu", expected_dimensions=1024,
    )
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [[0.1] * 1024, [0.2] * 1024])
    provider._model = mock_model

    result = await provider.embed(["text1", "text2"])
    assert len(result) == 2


@pytest.mark.asyncio
async def test_dimensions():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3", device="cpu", expected_dimensions=1024,
    )
    assert provider.dimensions() == 1024


@pytest.mark.asyncio
async def test_is_available_when_model_loaded():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3", device="cpu", expected_dimensions=1024,
    )
    provider._model = MagicMock()
    assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_is_available_when_model_not_loaded():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3", device="cpu", expected_dimensions=1024,
    )
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_task_adapter_fallback():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3", device="cpu", expected_dimensions=1024,
    )
    mock_model = MagicMock()
    mock_model.encode.side_effect = [
        TypeError("prompt_name not supported"),
        MagicMock(tolist=lambda: [0.1] * 1024),
    ]
    provider._model = mock_model

    result = await provider.embed_single("test", task="retrieval.query")
    assert len(result) == 1024
    assert mock_model.encode.call_count == 2
