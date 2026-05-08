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

        mock_client.execute_cypher = AsyncMock(return_value=[])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",

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
                {"subject": "s1", "predicate": "nouxcube://predicate/legal/empleado-de", "object": "o1", "object_type": "node", "confidence": 0.8},
                {"subject": "s1", "predicate": "nouxcube://predicate/legal/firmante-de", "object": "o2", "object_type": "literal", "confidence": 0.7},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        mock_client.execute_cypher = AsyncMock(return_value=[])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",

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

        mock_client.execute_cypher = AsyncMock(return_value=[])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="nonexistent_type",

        )

        assert result.report_type == "entity_profile"

    @pytest.mark.asyncio
    async def test_collects_sources_with_resolved_titles(self):
        """Document source IDs should be resolved to human-readable titles."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "nouxcube://predicate/legal/empleado-de", "object": "o1", "object_type": "node",
                 "confidence": 0.9, "source_chunk": "nouxcube://document/default/doc-001#offset=0"},
            ],
            "template": "entity_relations", "hops": 1, "count": 1,
        })

        mock_client.execute_cypher = AsyncMock(return_value=[
            {"uri": "nouxcube://document/default/doc-001", "label": "Contrato Laboral 2025-001.pdf"},
        ])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",

        )

        assert len(result.sources) > 0
        assert result.sources[0].document_id == "Contrato Laboral 2025-001.pdf"

    @pytest.mark.asyncio
    async def test_source_titles_fallback_to_uuid(self):
        """If document label not found, source ID should be the UUID slug."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "nouxcube://predicate/legal/empleado-de", "object": "o1", "object_type": "node",
                 "confidence": 0.9, "source_chunk": "nouxcube://document/default/doc-001#offset=0"},
            ],
            "template": "entity_relations", "hops": 1, "count": 1,
        })

        mock_client.execute_cypher = AsyncMock(return_value=[])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",

        )

        assert len(result.sources) > 0
        # Fallback: Title-cased slug from URI
        assert result.sources[0].document_id == "Doc 001"

    @pytest.mark.asyncio
    async def test_resolves_node_labels(self):
        """Node URIs in fact objects should be resolved to human-readable labels."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()

        section_result = {
            "results": [
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/core/label",
                 "object": "Juan Garcia", "object_type": "literal", "confidence": 0.9},
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/legal/empleado-de",
                 "object": "nouxcube://entity/default/acme-sl", "object_type": "node", "confidence": 0.85,
                 "source_chunk": "nouxcube://document/default/doc-abc123#offset=0"},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        }
        mock_executor.execute = AsyncMock(return_value=section_result)

        mock_client.execute_cypher = AsyncMock(return_value=[
            {"uri": "nouxcube://entity/default/acme-sl", "label": "Acme S.L."},
        ])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",

        )

        all_facts = [f for s in result.sections for f in s.facts]
        empleado_fact = next((f for f in all_facts if "empleado" in f.predicate), None)
        assert empleado_fact is not None
        assert empleado_fact.object == "Acme S.L."

    @pytest.mark.asyncio
    async def test_label_resolution_fallback_on_failure(self):
        """If label resolution fails, URIs should be formatted as title-case slugs."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()

        section_result = {
            "results": [
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/legal/empleado-de",
                 "object": "nouxcube://entity/default/empresa-xyz", "object_type": "node", "confidence": 0.8},
            ],
            "template": "entity_relations", "hops": 1, "count": 1,
        }
        mock_executor.execute = AsyncMock(return_value=section_result)

        mock_client.execute_cypher = AsyncMock(side_effect=Exception("FalkorDB down"))

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",

        )

        all_facts = [f for s in result.sections for f in s.facts]
        empleado_fact = next((f for f in all_facts if "empleado" in f.predicate), None)
        assert empleado_fact is not None
        assert empleado_fact.object == "Empresa Xyz"

    @pytest.mark.asyncio
    async def test_confidence_propagation(self):
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "nouxcube://predicate/legal/empleado-de", "object": "o1", "object_type": "node", "confidence": 0.9},
                {"subject": "s1", "predicate": "nouxcube://predicate/legal/firmante-de", "object": "o2", "object_type": "literal", "confidence": 0.5},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        mock_client.execute_cypher = AsyncMock(return_value=[])

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",

        )

        assert result.trust_summary.min_confidence == 0.5
        assert 0.5 <= result.trust_summary.avg_confidence <= 0.9
