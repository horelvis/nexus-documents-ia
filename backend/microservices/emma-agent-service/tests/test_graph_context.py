"""Tests for graph context extraction and injection."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_graph_recall_produces_context():
    """_graph_recall should combine structural summary + subgraph into markdown."""
    from app.agents.langgraph.nodes.memory_recall import _graph_recall

    mock_summary = {
        "summary": "45 documentos: 12 contratos, 8 facturas",
        "total_nodes": 45,
    }
    mock_subgraph = {
        "nodes": [
            {"id": "1", "name": "Juan García", "label": "Persona", "properties": {}},
            {"id": "2", "name": "Contrato-2024.pdf", "label": "structural_document",
             "properties": {"document_id": "abc-123", "semantic_type": "contrato"}},
        ],
        "edges": [
            {"source_id": "1", "target_id": "2", "label": "ASOCIADO_A", "properties": {}},
        ],
        "root_entities": ["Juan García"],
    }

    with patch("app.agents.langgraph.nodes.memory_recall.get_knowledge_tree_client") as mock_client_fn:
        client = AsyncMock()
        client.get_structural_summary.return_value = mock_summary
        client.extract_subgraph.return_value = mock_subgraph
        mock_client_fn.return_value = client

        result = await _graph_recall(
            query="contratos de Juan García",
            sector_config={"entity_patterns": {"persona": [r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)"]}},
        )

    assert result is not None
    assert "## Contexto del repositorio" in result
    assert "Juan García" in result
    assert "Contrato-2024" in result


@pytest.mark.asyncio
async def test_graph_recall_returns_none_when_disabled():
    """_graph_recall should return None when graph_context_enabled is False."""
    from app.agents.langgraph.nodes.memory_recall import _graph_recall

    with patch("app.agents.langgraph.nodes.memory_recall.settings") as mock_settings:
        mock_settings.graph_context_enabled = False
        result = await _graph_recall(
            query="contratos", sector_config=None,
        )

    assert result is None


@pytest.mark.asyncio
async def test_graph_recall_returns_none_on_failure():
    """_graph_recall should return None gracefully if knowledge-tree is down."""
    from app.agents.langgraph.nodes.memory_recall import _graph_recall

    with patch("app.agents.langgraph.nodes.memory_recall.get_knowledge_tree_client") as mock_client_fn:
        client = AsyncMock()
        client.get_structural_summary.side_effect = Exception("connection refused")
        client.extract_subgraph.side_effect = Exception("connection refused")
        mock_client_fn.return_value = client

        result = await _graph_recall(
            query="contratos", sector_config=None,
        )

    assert result is None


@pytest.mark.asyncio
async def test_graph_recall_respects_token_budget():
    """Graph context should be truncated to token budget."""
    from app.agents.langgraph.nodes.memory_recall import _graph_recall

    long_summary = {"summary": "x" * 10000, "total_nodes": 100}

    with patch("app.agents.langgraph.nodes.memory_recall.get_knowledge_tree_client") as mock_client_fn:
        client = AsyncMock()
        client.get_structural_summary.return_value = long_summary
        client.extract_subgraph.return_value = {"nodes": [], "edges": []}
        mock_client_fn.return_value = client

        with patch("app.agents.langgraph.nodes.memory_recall.settings") as mock_settings:
            mock_settings.graph_context_enabled = True
            mock_settings.graph_context_summary_enabled = True
            mock_settings.graph_context_subgraph_enabled = True
            mock_settings.graph_context_token_budget = 200
            mock_settings.graphrag_max_hops = 2
            mock_settings.graphrag_max_nodes = 30
            mock_settings.graphrag_include_legal = True

            result = await _graph_recall(
                query="test", sector_config=None,
            )

    if result:
        assert len(result) <= 200 * 4 + 200


@pytest.mark.asyncio
async def test_graph_recall_summary_only_when_no_entities():
    """When no entities are extracted, only structural summary should be returned."""
    from app.agents.langgraph.nodes.memory_recall import _graph_recall

    mock_summary = {"summary": "20 documentos: 5 contratos, 10 facturas", "total_nodes": 20}

    with patch("app.agents.langgraph.nodes.memory_recall.get_knowledge_tree_client") as mock_client_fn:
        client = AsyncMock()
        client.get_structural_summary.return_value = mock_summary
        mock_client_fn.return_value = client

        result = await _graph_recall(
            query="cuantos documentos hay",
            sector_config=None,
        )

    assert result is not None
    assert "## Contexto del repositorio" in result
    assert "20 documentos" in result
    client.extract_subgraph.assert_not_called()


@pytest.mark.asyncio
async def test_memory_recall_node_produces_graph_context():
    """memory_recall_node should return graph_context alongside memory_clues."""
    from app.agents.langgraph.nodes.memory_recall import memory_recall_node

    state = {
        "query": "contratos de Juan García",
        "sector_config": {"entity_patterns": {"persona": [r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)"]}},
    }

    mock_summary = {"summary": "10 documentos", "total_nodes": 10}
    mock_subgraph = {
        "nodes": [
            {"id": "1", "name": "Juan García", "label": "Persona", "properties": {}},
        ],
        "edges": [],
        "root_entities": ["Juan García"],
    }

    with patch("app.agents.langgraph.nodes.memory_recall.settings") as mock_settings:
        mock_settings.memory_recall_enabled = False
        mock_settings.graph_context_enabled = True
        mock_settings.graph_context_summary_enabled = True
        mock_settings.graph_context_subgraph_enabled = True
        mock_settings.graph_context_token_budget = 1200
        mock_settings.graphrag_max_hops = 2
        mock_settings.graphrag_max_nodes = 30
        mock_settings.graphrag_include_legal = True

        with patch("app.agents.langgraph.nodes.memory_recall.get_knowledge_tree_client") as mock_client_fn:
            client = AsyncMock()
            client.get_structural_summary.return_value = mock_summary
            client.extract_subgraph.return_value = mock_subgraph
            mock_client_fn.return_value = client

            result = await memory_recall_node(state)

    assert "graph_context" in result
    assert result["graph_context"] is not None
    assert "Juan García" in result["graph_context"]


@pytest.mark.asyncio
async def test_build_system_message_includes_graph_context():
    """_build_system_message should inject graph_context into the prompt."""
    from app.agents.langgraph.nodes.react_loop import _build_system_message

    state = {
        "sector": "legal",
        "features": {},
        "query": "test",
        "metadata": {},
        "user_memory": None,
        "memory_clues": None,
        "graph_context": "## Contexto del repositorio\n### Estructura\n10 contratos",
    }

    with patch("app.agents.langgraph.nodes.react_loop._load_react_system_prompt",
               return_value="System prompt {tools_description} {current_date}"):
        with patch("app.agents.langgraph.nodes.react_loop.get_tool_registry") as mock_reg:
            mock_reg.return_value.get_tools_description.return_value = "tools here"

            msg = await _build_system_message(state)

    assert "Contexto del repositorio" in msg.content
    assert "10 contratos" in msg.content


@pytest.mark.asyncio
async def test_build_system_message_omits_graph_context_when_none():
    """_build_system_message should not add graph section when graph_context is None."""
    from app.agents.langgraph.nodes.react_loop import _build_system_message

    state = {
        "sector": "",
        "features": {},
        "query": "hola",
        "metadata": {},
        "user_memory": None,
        "memory_clues": None,
        "graph_context": None,
    }

    with patch("app.agents.langgraph.nodes.react_loop._load_react_system_prompt",
               return_value="System prompt {tools_description} {current_date}"):
        with patch("app.agents.langgraph.nodes.react_loop.get_tool_registry") as mock_reg:
            mock_reg.return_value.get_tools_description.return_value = "tools here"

            msg = await _build_system_message(state)

    assert "Contexto del repositorio" not in msg.content
