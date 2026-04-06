"""Tests for GraphRAGTool — 6-stage pipeline."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.langgraph.tools.graph_rag import GraphRAGTool, _build_edge_description


# ---------------------------------------------------------------------------
# 1. Pure function test
# ---------------------------------------------------------------------------


def test_build_edge_description():
    """_build_edge_description returns 'subject, predicate, object' format."""
    result = _build_edge_description("LGT", "regula", "IRPF")
    assert result == "LGT, regula, IRPF"


# ---------------------------------------------------------------------------
# 2. Disabled returns empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_rag_disabled_returns_empty():
    """When settings.graph_rag_enabled=False, tool returns empty ToolResult."""
    tool = GraphRAGTool()
    context = {"tenant_id": "tenant-1", "user_id": "user-1"}

    with patch("app.agents.langgraph.tools.graph_rag.settings") as mock_settings:
        mock_settings.graph_rag_enabled = False
        result = await tool.execute({"query": "¿Qué regula la LGT?"}, context)

    assert result.success is True
    assert result.output == ""
    assert result.data == {}


# ---------------------------------------------------------------------------
# 3. No entities → informative message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_rag_no_entities_returns_empty():
    """When entity vector search returns [], tool returns 'no entities' message."""
    from app.agents.langgraph.tools.concept_extractor import ConceptResult

    tool = GraphRAGTool()
    context = {"tenant_id": "tenant-1", "user_id": "user-1"}

    mock_concepts = ConceptResult(
        high_level=["derecho fiscal"],
        low_level=["LGT"],
        embeddings={"derecho fiscal": [0.1] * 1024, "LGT": [0.2] * 1024},
    )

    with patch("app.agents.langgraph.tools.graph_rag.settings") as mock_settings, \
         patch("app.agents.langgraph.tools.graph_rag.extract_concepts", new_callable=AsyncMock, return_value=mock_concepts), \
         patch("app.agents.langgraph.tools.graph_rag.get_weaviate_client") as mock_weaviate_factory:

        mock_settings.graph_rag_enabled = True
        mock_settings.graph_rag_entity_limit = 10
        mock_settings.graph_rag_max_hops = 2
        mock_settings.graph_rag_max_edges = 50
        mock_settings.graph_rag_prefilter_limit = 10
        mock_settings.graph_rag_edge_limit = 5
        mock_settings.graph_rag_label_cache_ttl = 300
        mock_settings.text_extraction_service_url = "http://mock-embed"
        mock_settings.MICROSERVICES_API_KEY = "test-key"

        mock_weaviate = AsyncMock()
        mock_weaviate.search_entities_by_embedding = AsyncMock(return_value=[])
        mock_weaviate_factory.return_value = mock_weaviate

        result = await tool.execute({"query": "¿Qué regula la LGT?"}, context)

    assert result.success is True
    assert "no entities" in result.output.lower() or "no se encontraron entidades" in result.output.lower() or result.output == ""


# ---------------------------------------------------------------------------
# 4. Full pipeline — all 6 stages mocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_rag_full_pipeline():
    """Mock all 6 stages and verify final output contains entity/relationship info."""
    from app.agents.langgraph.tools.concept_extractor import ConceptResult

    tool = GraphRAGTool()
    context = {"tenant_id": "tenant-1", "user_id": "user-1"}

    # Stage 1 inputs
    mock_concepts = ConceptResult(
        high_level=["derecho fiscal"],
        low_level=["LGT"],
        embeddings={"derecho fiscal": [0.1] * 1024, "LGT": [0.2] * 1024},
    )

    # Stage 1 output — entity hits from Weaviate
    mock_entities = [
        {
            "entity_uri": "nouxcube://entity/lgt",
            "label": "LGT",
            "entity_type": "law",
            "definition": "Ley General Tributaria",
            "score": 0.95,
        },
        {
            "entity_uri": "nouxcube://entity/irpf",
            "label": "IRPF",
            "entity_type": "tax",
            "definition": "Impuesto sobre la Renta de las Personas Físicas",
            "score": 0.88,
        },
    ]

    # Stage 2 output — BFS edges from KTS
    mock_neighbors = {
        "edges": [
            {
                "subject_uri": "nouxcube://entity/lgt",
                "predicate_uri": "nouxcube://predicate/legal/regula",
                "object_uri": "nouxcube://entity/irpf",
            },
            {
                "subject_uri": "nouxcube://entity/lgt",
                "predicate_uri": "nouxcube://predicate/legal/define",
                "object_uri": "nouxcube://entity/contribuyente",
            },
        ],
        "entities_visited": 2,
        "hops_used": 1,
    }

    # Stage 3 — label resolution (query_triples per URI)
    mock_label_triple = {
        "success": True,
        "triples": [{"object_value": "Contribuyente"}],
    }

    # Stage 5 — LLM scoring response
    mock_llm_response = MagicMock()
    mock_llm_response.content = json.dumps([
        {"id": "nouxcube://entity/lgt@@nouxcube://predicate/legal/regula@@nouxcube://entity/irpf", "score": 0.92},
        {"id": "nouxcube://entity/lgt@@nouxcube://predicate/legal/define@@nouxcube://entity/contribuyente", "score": 0.78},
    ])

    # Stage 4 — batch embed for semantic pre-filter
    mock_edge_embeddings = [[0.15] * 1024, [0.18] * 1024]

    with patch("app.agents.langgraph.tools.graph_rag.settings") as mock_settings, \
         patch("app.agents.langgraph.tools.graph_rag.extract_concepts", new_callable=AsyncMock, return_value=mock_concepts), \
         patch("app.agents.langgraph.tools.graph_rag.get_weaviate_client") as mock_weaviate_factory, \
         patch("app.agents.langgraph.tools.graph_rag.get_knowledge_tree_client") as mock_kts_factory, \
         patch("app.agents.langgraph.tools.graph_rag.get_planner_model") as mock_planner_factory, \
         patch("app.agents.langgraph.tools.graph_rag.get_langfuse_prompt_client") as mock_langfuse_factory, \
         patch("app.agents.langgraph.tools.graph_rag._batch_embed_edges", new_callable=AsyncMock, return_value=mock_edge_embeddings):

        mock_settings.graph_rag_enabled = True
        mock_settings.graph_rag_entity_limit = 10
        mock_settings.graph_rag_max_hops = 2
        mock_settings.graph_rag_max_edges = 50
        mock_settings.graph_rag_prefilter_limit = 10
        mock_settings.graph_rag_edge_limit = 5
        mock_settings.graph_rag_label_cache_ttl = 300
        mock_settings.text_extraction_service_url = "http://mock-embed"
        mock_settings.MICROSERVICES_API_KEY = "test-key"

        # Weaviate client
        mock_weaviate = AsyncMock()
        mock_weaviate.search_entities_by_embedding = AsyncMock(return_value=mock_entities)
        mock_weaviate_factory.return_value = mock_weaviate

        # KTS client
        mock_kts = AsyncMock()
        mock_kts.batch_neighbors = AsyncMock(return_value=mock_neighbors)
        mock_kts.query_triples = AsyncMock(return_value=mock_label_triple)
        mock_kts_factory.return_value = mock_kts

        # Planner LLM
        mock_planner = AsyncMock()
        mock_planner.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_planner_factory.return_value = mock_planner

        # Langfuse
        mock_langfuse = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.content = "Score edges by relevance. Return JSON: [{\"id\": ..., \"score\": ...}]"
        mock_langfuse.get_prompt = AsyncMock(return_value=mock_prompt)
        mock_langfuse_factory.return_value = mock_langfuse

        result = await tool.execute({"query": "¿Qué regula la LGT?"}, context)

    # Verify output
    assert result.success is True
    assert len(result.output) > 0

    # Output should contain entity and relationship info
    output_lower = result.output.lower()
    assert "lgt" in output_lower or "knowledge graph" in output_lower

    # data should contain structured info
    assert "entities" in result.data
    assert "avg_score" in result.data
    assert isinstance(result.data["avg_score"], float)
