"""
ContradictionDetector — batch contradiction detection for TrustGraph.

Detects same-subject + same-predicate + different-object-value contradictions
and stores them as edge properties (has_contradiction, contradiction_with)
instead of creating separate :Node triples.
"""

import logging
from typing import Dict, List

from app.services.falkordb_client import FalkorDBClient

logger = logging.getLogger(__name__)


class ContradictionDetector:
    """Detect and mark contradictions as edge metadata in TrustGraph."""

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client

    async def detect_for_subject(self, subject_uri: str) -> List[Dict]:
        """Find contradictions for a single subject: same predicate, different literal values.

        Returns a list of dicts with keys:
            predicate, value_a, value_b, chunk_a, chunk_b, rel_a_id, rel_b_id
        """
        query = (
            "MATCH (s:Node {uri: $uri})-[r1:Rel]->(o1:Literal) "
            "MATCH (s)-[r2:Rel]->(o2:Literal) "
            "WHERE r2.uri = r1.uri "
            "  AND id(o1) < id(o2) "
            "  AND o1.value <> o2.value "
            "RETURN DISTINCT r1.uri AS predicate, o1.value AS value_a, o2.value AS value_b, "
            "r1.source_chunk AS chunk_a, r2.source_chunk AS chunk_b, "
            "id(r1) AS rel_a_id, id(r2) AS rel_b_id"
        )
        rows = await self._client.execute_cypher(
            query, params={"uri": subject_uri}
        )
        return [
            {
                "predicate": row["predicate"],
                "value_a": row["value_a"],
                "value_b": row["value_b"],
                "chunk_a": row["chunk_a"],
                "chunk_b": row["chunk_b"],
                "rel_a_id": row["rel_a_id"],
                "rel_b_id": row["rel_b_id"],
            }
            for row in rows
        ]

    async def detect_and_mark(
        self, subject_uri: str
    ) -> int:
        """Detect contradictions and mark edges with metadata properties.

        For each contradiction pair (r1, r2):
          - SET r1.has_contradiction = true, r1.contradiction_with = id(r2)
          - SET r2.has_contradiction = true, r2.contradiction_with = id(r1)

        Returns the number of contradictions found.
        """
        contradictions = await self.detect_for_subject(subject_uri)

        for c in contradictions:
            try:
                await self._client.execute_cypher(
                    "MATCH ()-[r:Rel]->() WHERE id(r) = $rel_id "
                    "SET r.has_contradiction = true, r.contradiction_with = $other_id",
                    {"rel_id": c["rel_a_id"], "other_id": c["rel_b_id"]},
                )
                await self._client.execute_cypher(
                    "MATCH ()-[r:Rel]->() WHERE id(r) = $rel_id "
                    "SET r.has_contradiction = true, r.contradiction_with = $other_id",
                    {"rel_id": c["rel_b_id"], "other_id": c["rel_a_id"]},
                )
            except Exception as exc:
                logger.warning(
                    "Failed to mark contradiction edges for %s: %s",
                    subject_uri, exc,
                )

        if contradictions:
            logger.info(
                "Marked %d contradiction(s) for subject %s",
                len(contradictions), subject_uri,
            )

        return len(contradictions)

    async def apply_confidence_penalty(self) -> int:
        """Batch-reduce confidence on all edges marked has_contradiction=true.

        Sets confidence = max(confidence - 0.25, 0.10).
        Returns the number of edges updated.
        """
        query = (
            "MATCH ()-[r:Rel]->() "
            "WHERE r.has_contradiction = true "
            "AND r.confidence IS NOT NULL "
            "SET r.confidence = CASE "
            "  WHEN r.confidence - 0.25 < 0.10 THEN 0.10 "
            "  ELSE r.confidence - 0.25 "
            "END "
            "RETURN count(r) AS updated"
        )
        rows = await self._client.execute_cypher(query, params={})
        count = rows[0]["updated"] if rows else 0
        if count:
            logger.info("Applied confidence penalty to %d contradicted edges", count)
        return count

    async def detect_batch_for_document(
        self, document_uri: str, collection: str
    ) -> int:
        """Find all entity subjects, run detect_and_mark for each.

        Returns the total number of contradictions found.
        """
        entity_query = (
            "MATCH (s:Node) "
            "WHERE s.uri STARTS WITH 'nouxcube://entity/' "
            "RETURN DISTINCT s.uri AS entity_uri"
        )
        rows = await self._client.execute_cypher(
            entity_query, params={}
        )

        total = 0
        for row in rows:
            entity_uri = row["entity_uri"]
            try:
                count = await self.detect_and_mark(entity_uri)
                total += count
            except Exception:
                logger.exception(
                    "Error detecting contradictions for entity %s", entity_uri
                )

        logger.info(
            "detect_batch_for_document: doc=%s → %d contradiction(s) marked",
            document_uri, total,
        )
        return total
