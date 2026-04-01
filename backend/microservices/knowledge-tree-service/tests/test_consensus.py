"""Tests for consensus scoring — cross-source agreement counting."""

import pytest
from unittest.mock import AsyncMock

from app.services.consensus import ConsensusScorer


class TestConsensusScorer:
    @pytest.mark.asyncio
    async def test_single_source_gets_score_one_third(self):
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(return_value=[
            {"predicate": "nouxcube://predicate/legal/empleado-de", "source_count": 1}
        ])

        scorer = ConsensusScorer(mock_client)
        result = await scorer.compute_for_subject(
            subject_uri="nouxcube://entity/default/juan",
            user="test-user",
        )
        assert len(result) == 1
        assert result[0]["consensus_score"] == pytest.approx(0.33, abs=0.01)

    @pytest.mark.asyncio
    async def test_three_sources_gets_max_score(self):
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(return_value=[
            {"predicate": "nouxcube://predicate/legal/empleado-de", "source_count": 5}
        ])

        scorer = ConsensusScorer(mock_client)
        result = await scorer.compute_for_subject(
            subject_uri="nouxcube://entity/default/juan",
            user="test-user",
        )
        assert len(result) == 1
        assert result[0]["consensus_score"] == 1.0

    @pytest.mark.asyncio
    async def test_stores_consensus_count_on_edges(self):
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(side_effect=[
            [{"predicate": "nouxcube://predicate/legal/empleado-de", "source_count": 2}],
            [],
        ])

        scorer = ConsensusScorer(mock_client)
        await scorer.compute_and_store(
            subject_uri="nouxcube://entity/default/juan",
            user="test-user",
        )

        assert mock_client.execute_cypher.call_count == 2
        update_call = mock_client.execute_cypher.call_args_list[1]
        assert "consensus_count" in update_call[0][0]

    @pytest.mark.asyncio
    async def test_no_edges_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(return_value=[])

        scorer = ConsensusScorer(mock_client)
        result = await scorer.compute_for_subject(
            subject_uri="nouxcube://entity/default/empty",
            user="test-user",
        )
        assert result == []
