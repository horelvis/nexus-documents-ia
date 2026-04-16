"""Tests for shared concept extraction."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.langgraph.tools.concept_extractor import (
    extract_concepts,
    ConceptResult,
    _fallback_regex_concepts,
)


def test_fallback_regex_extracts_entities():
    """Regex fallback extracts person names and legal refs."""
    result = _fallback_regex_concepts("contratos de Juan García sobre la LGT")
    # Should find at least Juan García or LGT
    all_concepts = [c.lower() for c in result.low_level]
    has_person_or_legal = any("juan" in c or "garc" in c for c in all_concepts) or any("lgt" in c for c in all_concepts)
    assert has_person_or_legal
    assert result.embeddings == {}


def test_fallback_regex_empty_query():
    """Empty query returns empty concepts."""
    result = _fallback_regex_concepts("")
    assert result.high_level == []
    assert result.low_level == []


@pytest.mark.asyncio
async def test_extract_concepts_success():
    """LLM extraction returns parsed concepts."""
    mock_response = MagicMock()
    mock_response.content = '{"high_level_keywords": ["derecho laboral"], "low_level_keywords": ["ET", "Juan García"]}'

    with patch(
        "app.agents.langgraph.tools.concept_extractor._call_llm",
        new_callable=AsyncMock,
        return_value=mock_response,
    ), patch(
        "app.agents.langgraph.tools.concept_extractor._batch_embed",
        new_callable=AsyncMock,
        return_value={"derecho laboral": [0.1] * 1024, "ET": [0.2] * 1024, "Juan García": [0.3] * 1024},
    ):
        result = await extract_concepts("derechos laborales de Juan García según ET")

    assert "derecho laboral" in result.high_level
    assert "ET" in result.low_level
    assert "Juan García" in result.low_level
    assert len(result.embeddings) == 3


@pytest.mark.asyncio
async def test_extract_concepts_llm_failure_falls_back():
    """On LLM failure, falls back to regex extraction."""
    with patch(
        "app.agents.langgraph.tools.concept_extractor._call_llm",
        new_callable=AsyncMock,
        side_effect=Exception("LLM down"),
    ):
        result = await extract_concepts("contratos de María López")

    assert isinstance(result, ConceptResult)
    assert result.embeddings == {}
