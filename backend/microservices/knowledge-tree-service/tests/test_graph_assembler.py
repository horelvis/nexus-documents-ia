"""Tests for GraphAssembler — graph data assembly for reports."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.graph_assembler import GraphAssembler
from app.schemas.reports import AssembledGraph


class TestGraphAssembler:
    @pytest.mark.asyncio
    async def test_assembles_entity_profile(self):
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/core/label",
                 "object": "Juan Garcia", "object_type": "literal", "confidence": 0.9, "consensus_count": 2},
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/legal/empleado-de",
                 "object": "nouxcube://entity/default/acme", "object_type": "node", "confidence": 0.85, "consensus_count": 3},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert isinstance(result, AssembledGraph)
        assert result.entity_uri == "nouxcube://entity/default/juan"
        assert result.report_type == "entity_profile"
        assert len(result.sections) > 0
        assert result.trust_summary.total_facts > 0

    @pytest.mark.asyncio
    async def test_computes_kpis(self):
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "p1", "object": "o1", "object_type": "node", "confidence": 0.8},
                {"subject": "s1", "predicate": "p2", "object": "o2", "object_type": "literal", "confidence": 0.7},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert len(result.kpis) > 0
        total_kpi = next((k for k in result.kpis if k.name == "total_relaciones"), None)
        assert total_kpi is not None
        assert total_kpi.value >= 0

    @pytest.mark.asyncio
    async def test_unknown_report_type_uses_entity_profile(self):
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [], "template": "entity_relations", "hops": 1, "count": 0,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="nonexistent_type",
            user="test-tenant",
        )

        assert result.report_type == "entity_profile"

    @pytest.mark.asyncio
    async def test_collects_sources(self):
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "p1", "object": "o1", "object_type": "node",
                 "confidence": 0.9, "source_chunk": "nouxcube://document/default/doc-001#offset=0"},
            ],
            "template": "entity_relations", "hops": 1, "count": 1,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert len(result.sources) > 0
        assert "doc-001" in result.sources[0].document_id

    @pytest.mark.asyncio
    async def test_confidence_propagation(self):
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "p1", "object": "o1", "object_type": "node", "confidence": 0.9},
                {"subject": "s1", "predicate": "p2", "object": "o2", "object_type": "literal", "confidence": 0.5},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert result.trust_summary.min_confidence == 0.5
        assert result.trust_summary.avg_confidence == pytest.approx(0.7, abs=0.01)
