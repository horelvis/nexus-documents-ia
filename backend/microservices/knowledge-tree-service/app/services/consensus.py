"""
ConsensusScorer — counts independent sources confirming each triple.

For a given subject, groups outgoing edges by predicate and counts how
many distinct source_chunk values produced the same triple.
Stores consensus_count as a property on each :Rel edge.

Score formula: consensus_score = min(1.0, consensus_count / 3)
  - 1 source  → 0.33
  - 2 sources → 0.67
  - 3+ sources → 1.0
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CONSENSUS_DIVISOR = 3


class ConsensusScorer:
    """Compute and store consensus scores on graph edges."""

    def __init__(self, client) -> None:
        self._client = client

    async def compute_for_subject(
        self,
        subject_uri: str,
    ) -> List[Dict[str, Any]]:
        """Count independent sources per (subject, predicate) pair.

        Returns list of dicts with predicate, source_count, consensus_score.
        """
        query = (
            "MATCH (s:Node {uri: $uri})-[r:Rel]->(o) "
            "WHERE r.source_chunk IS NOT NULL "
            "WITH r.uri AS predicate, count(DISTINCT r.source_chunk) AS source_count "
            "RETURN predicate, source_count"
        )
        rows = await self._client.execute_cypher(
            query, params={"uri": subject_uri}
        )

        results = []
        for row in rows:
            count = row.get("source_count", 1)
            results.append({
                "predicate": row.get("predicate", ""),
                "source_count": count,
                "consensus_score": min(1.0, count / CONSENSUS_DIVISOR),
            })

        return results

    async def compute_and_store(
        self,
        subject_uri: str,
    ) -> int:
        """Compute consensus and SET consensus_count on edges.

        Returns number of predicates updated.
        """
        results = await self.compute_for_subject(subject_uri)
        if not results:
            return 0

        for item in results:
            update_query = (
                "MATCH (s:Node {uri: $uri})-[r:Rel {uri: $predicate}]->(o) "
                "SET r.consensus_count = $count"
            )
            await self._client.execute_cypher(
                update_query,
                params={
                    "uri": subject_uri,
                    "predicate": item["predicate"],
                    "count": item["source_count"],
                },
            )

        return len(results)
