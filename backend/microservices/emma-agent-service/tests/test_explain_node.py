"""
Tests for the explain node — humanized query trace.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.langgraph.nodes.explain import (
    FALLBACK_TEMPLATE,
    explain_node,
    extract_facts,
)


# ── extract_facts tests ─────────────────────────────────────────────────────


def test_extracts_tool_call_facts():
    """smart_search tool_call produces a fact."""
    reasoning_steps = [
        {
            "type": "tool_call",
            "name": "smart_search",
            "stores": "documentos y legislación",
            "result_count": 5,
        }
    ]
    facts = extract_facts(reasoning_steps, [])
    assert len(facts) == 1
    assert "Busqué en documentos y legislación" in facts[0]
    assert "5 resultados" in facts[0]


def test_extracts_source_facts():
    """Source titles not already mentioned appear in facts."""
    sources = [
        {"title": "Contrato de arrendamiento", "pages": "1-3"},
        {"title": "Factura 2025-001"},
    ]
    facts = extract_facts([], sources)
    assert len(facts) == 2
    assert any("Contrato de arrendamiento" in f for f in facts)
    assert any("páginas 1-3" in f for f in facts)
    assert any("Factura 2025-001" in f for f in facts)


def test_empty_reasoning_steps():
    """Empty input produces empty facts (no sources either)."""
    facts = extract_facts([], [])
    assert facts == []


def test_unknown_step_type_skipped():
    """Unknown step types produce no facts."""
    reasoning_steps = [
        {"type": "internal_thinking", "content": "hmm..."},
        {"type": "observation", "content": "I see something"},
    ]
    facts = extract_facts(reasoning_steps, [])
    assert facts == []


# ── explain_node tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.agents.langgraph.nodes.explain.settings")
async def test_skips_fast_path(mock_settings):
    """fast_path_used=True returns is_complete=True, no explanation."""
    mock_settings.explain_enabled = True
    state = {"fast_path_used": True}
    result = await explain_node(state)
    assert result == {"is_complete": True}
    assert "explanation" not in result


@pytest.mark.asyncio
@patch("app.agents.langgraph.nodes.explain.settings")
async def test_skips_when_disabled(mock_settings):
    """settings.explain_enabled=False returns is_complete=True, no explanation."""
    mock_settings.explain_enabled = False
    state = {"fast_path_used": False}
    result = await explain_node(state)
    assert result == {"is_complete": True}
    assert "explanation" not in result


@pytest.mark.asyncio
@patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
@patch("app.agents.langgraph.nodes.explain._call_llm", new_callable=AsyncMock)
@patch("app.agents.langgraph.nodes.explain._detect_fabricated_data")
@patch("app.agents.langgraph.nodes.explain.settings")
async def test_generates_explanation(
    mock_settings, mock_detect, mock_llm, mock_sector
):
    """Mocked LLM returns text, explanation field is populated."""
    mock_settings.explain_enabled = True
    mock_detect.return_value = []
    mock_llm.return_value = "Busqué tus documentos y encontré 3 resultados relevantes."
    mock_sector.return_value = MagicMock(
        explain_guidance="Usa terminología jurídica."
    )

    state = {
        "fast_path_used": False,
        "reasoning_steps": [
            {"type": "tool_call", "name": "smart_search", "stores": "documentos", "result_count": 3},
        ],
        "sources": [{"title": "Contrato"}],
        "tool_calls_history": [{"name": "smart_search"}],
        "messages": [],
        "sector": "legal",
    }

    result = await explain_node(state)
    assert result["is_complete"] is True
    assert result["explanation"] == "Busqué tus documentos y encontré 3 resultados relevantes."
    assert "metadata" in result
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
@patch("app.agents.langgraph.nodes.explain._call_llm", new_callable=AsyncMock)
@patch("app.agents.langgraph.nodes.explain.settings")
async def test_empty_facts_uses_fallback(mock_settings, mock_llm, mock_sector):
    """No reasoning_steps and no sources with titles -> fallback, LLM not called."""
    mock_settings.explain_enabled = True
    mock_sector.return_value = MagicMock(
        explain_guidance="Usa terminología jurídica."
    )

    state = {
        "fast_path_used": False,
        "reasoning_steps": [],
        "sources": [],
        "tool_calls_history": [],
        "messages": [],
    }

    result = await explain_node(state)
    assert result["is_complete"] is True
    assert "explanation" in result
    # Fallback should mention 0 fuente(s)
    assert "0 fuente(s)" in result["explanation"]
    mock_llm.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
@patch("app.agents.langgraph.nodes.explain._call_llm", new_callable=AsyncMock)
@patch("app.agents.langgraph.nodes.explain.settings")
async def test_llm_failure_uses_fallback(mock_settings, mock_llm, mock_sector):
    """LLM raises Exception, fallback template is used."""
    mock_settings.explain_enabled = True
    mock_llm.side_effect = Exception("LLM timeout")
    mock_sector.return_value = MagicMock(
        explain_guidance="Usa terminología jurídica."
    )

    state = {
        "fast_path_used": False,
        "reasoning_steps": [
            {"type": "tool_call", "name": "smart_search", "stores": "docs", "result_count": 2},
        ],
        "sources": [{"title": "Doc A"}],
        "tool_calls_history": [{"name": "smart_search"}],
        "messages": [],
        "sector": "legal",
    }

    result = await explain_node(state)
    assert result["is_complete"] is True
    assert "explanation" in result
    # Should be fallback template, not LLM output
    assert "Doc A" in result["explanation"]
    assert "búsqueda inteligente" in result["explanation"]


@pytest.mark.asyncio
@patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
@patch("app.agents.langgraph.nodes.explain._call_llm", new_callable=AsyncMock)
@patch("app.agents.langgraph.nodes.explain._detect_fabricated_data")
@patch("app.agents.langgraph.nodes.explain.settings")
async def test_fabricated_data_uses_fallback(
    mock_settings, mock_detect, mock_llm, mock_sector
):
    """LLM returns text but _detect_fabricated_data flags it -> fallback."""
    mock_settings.explain_enabled = True
    mock_detect.return_value = ["12345"]
    mock_llm.return_value = "Encontré la factura 12345 por valor de 67890 euros."
    mock_sector.return_value = MagicMock(
        explain_guidance="Usa terminología jurídica."
    )

    state = {
        "fast_path_used": False,
        "reasoning_steps": [
            {"type": "tool_call", "name": "smart_search", "stores": "docs", "result_count": 1},
        ],
        "sources": [{"title": "Factura ejemplo"}],
        "tool_calls_history": [{"name": "smart_search"}],
        "messages": [],
        "sector": "legal",
    }

    result = await explain_node(state)
    assert result["is_complete"] is True
    # Should be fallback, not the fabricated LLM output
    assert "12345" not in result["explanation"]
    assert "Factura ejemplo" in result["explanation"]
