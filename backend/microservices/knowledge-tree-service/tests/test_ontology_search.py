"""Tests for ontology search — vector-based predicate resolution."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.ontology_search import OntologySearch


class TestOntologySearch:
    @pytest.mark.asyncio
    async def test_exact_match_returns_predicate(self):
        """Known predicates should resolve via exact match (no vector search needed)."""
        search = OntologySearch()
        with patch("app.services.ontology_search.get_namespace", return_value="legal"):
            result = await search.resolve_predicate("empleado-de")
        assert result is not None
        assert result["predicate_name"] == "empleado-de"
        assert result["namespace"] == "legal"
        assert result["method"] == "exact"

    @pytest.mark.asyncio
    async def test_unknown_predicate_calls_vector_search(self):
        """Unknown predicates should trigger vector search."""
        search = OntologySearch()
        mock_results = [
            {"predicate_name": "empleado-de", "namespace": "legal", "description": "...", "score": 0.91},
        ]
        with patch.object(search, "_vector_search", new_callable=AsyncMock, return_value=mock_results):
            result = await search.resolve_predicate("trabaja en")
        assert result is not None
        assert result["predicate_name"] == "empleado-de"
        assert result["method"] == "semantic_match"

    @pytest.mark.asyncio
    async def test_low_score_returns_none(self):
        """Predicates with no close semantic match should return None."""
        search = OntologySearch()
        mock_results = [
            {"predicate_name": "label", "namespace": "core", "description": "...", "score": 0.50},
        ]
        with patch.object(search, "_vector_search", new_callable=AsyncMock, return_value=mock_results):
            result = await search.resolve_predicate("zzz-unknown-thing")
        assert result is None

    @pytest.mark.asyncio
    async def test_vector_search_failure_returns_none(self):
        """If vector search fails, gracefully return None."""
        search = OntologySearch()
        with patch.object(search, "_vector_search", new_callable=AsyncMock, side_effect=Exception("timeout")):
            result = await search.resolve_predicate("trabaja en")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_results_returns_none(self):
        """If vector search returns empty list, return None."""
        search = OntologySearch()
        with patch.object(search, "_vector_search", new_callable=AsyncMock, return_value=[]):
            result = await search.resolve_predicate("something-odd")
        assert result is None
