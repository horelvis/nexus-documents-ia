"""
ContradictionDetector — batch contradiction detection for TrustGraph.

Detects same-subject + same-predicate + different-object-value contradictions,
stores them as :Node instances with structured provenance edges.

Run per-document after all extractors finish (called by coordinator, Task 9).
"""

import logging
from typing import Dict, List

from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)


class ContradictionDetector:
    """Detect and persist contradictions in extracted TrustGraph triples."""

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client
        self._store = TripleStore(client)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    async def detect_for_subject(self, subject_uri: str, user: str) -> List[Dict]:
        """Find contradictions for a single subject: same predicate, different literal values.

        Returns a list of dicts with keys:
            predicate, value_a, value_b, chunk_a, chunk_b
        """
        query = (
            "MATCH (s:Node {uri: $uri})-[r1:Rel]->(o1:Literal) "
            "WHERE r1.user = $user "
            "MATCH (s)-[r2:Rel]->(o2:Literal) "
            "WHERE r2.uri = r1.uri AND r2.user = $user "
            "  AND id(o1) < id(o2) "
            "  AND o1.value <> o2.value "
            "RETURN DISTINCT r1.uri AS predicate, o1.value AS value_a, o2.value AS value_b, "
            "r1.source_chunk AS chunk_a, r2.source_chunk AS chunk_b"
        )
        rows = await self._client.execute_cypher(
            query, params={"uri": subject_uri, "user": user}
        )
        return [
            {
                "predicate": row["predicate"],
                "value_a": row["value_a"],
                "value_b": row["value_b"],
                "chunk_a": row["chunk_a"],
                "chunk_b": row["chunk_b"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Detection + storage
    # ------------------------------------------------------------------

    async def detect_and_store(
        self, subject_uri: str, user: str, collection: str
    ) -> List[str]:
        """Detect contradictions for subject and persist each as a :Node.

        For each contradiction found:
          - Creates a contradiction :Node (core/contradiction-subject → subject_node)
          - Stores predicate string (core/contradiction-predicate → predicate_uri_string)
          - Links both conflicting values (core/contradiction-value-a / -value-b)

        Returns:
            List of contradiction URIs created.
        """
        contradictions = await self.detect_for_subject(subject_uri, user)
        uris: List[str] = []

        for c in contradictions:
            contradiction_uri = URIBuilder.contradiction()
            logger.debug(
                "Storing contradiction %s for subject %s predicate %s",
                contradiction_uri,
                subject_uri,
                c["predicate"],
            )

            # 1. Merge the contradiction node itself
            await self._store.merge_node(contradiction_uri, user=user, collection=collection)

            # 2. Link to subject node  (Node → Node)
            subject_pred_uri = URIBuilder.predicate("core", "contradiction-subject")
            await self._store.create_rel(
                subject_uri=contradiction_uri,
                predicate_uri=subject_pred_uri,
                object_value=subject_uri,
                user=user,
                collection=collection,
                object_is_node=True,
                extraction_method="system",
            )

            # 3. Store predicate string  (Node → Literal)
            await self._store.merge_literal(c["predicate"], user=user, collection=collection)
            predicate_pred_uri = URIBuilder.predicate("core", "contradiction-predicate")
            await self._store.create_rel(
                subject_uri=contradiction_uri,
                predicate_uri=predicate_pred_uri,
                object_value=c["predicate"],
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="system",
            )

            # 4. Link value_a  (Node → Literal)
            await self._store.merge_literal(c["value_a"], user=user, collection=collection)
            val_a_pred_uri = URIBuilder.predicate("core", "contradiction-value-a")
            await self._store.create_rel(
                subject_uri=contradiction_uri,
                predicate_uri=val_a_pred_uri,
                object_value=c["value_a"],
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="system",
            )

            # 5. Link value_b  (Node → Literal)
            await self._store.merge_literal(c["value_b"], user=user, collection=collection)
            val_b_pred_uri = URIBuilder.predicate("core", "contradiction-value-b")
            await self._store.create_rel(
                subject_uri=contradiction_uri,
                predicate_uri=val_b_pred_uri,
                object_value=c["value_b"],
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="system",
            )

            uris.append(contradiction_uri)

        return uris

    # ------------------------------------------------------------------
    # Batch detection for a whole document
    # ------------------------------------------------------------------

    async def detect_batch_for_document(
        self, document_uri: str, user: str, collection: str
    ) -> List[str]:
        """Find all entity subjects for tenant, run detect_and_store for each.

        Args:
            document_uri:  Document URI (used for scoping context; entities are
                           fetched by user+entity URI prefix).
            user:          Tenant/user identifier.
            collection:    Collection scope.

        Returns:
            Flat list of all contradiction URIs created across all entities.
        """
        # Find all entity nodes for this tenant
        entity_query = (
            "MATCH (s:Node) "
            "WHERE s.user = $user AND s.uri STARTS WITH 'nouxcube://entity/' "
            "RETURN DISTINCT s.uri AS entity_uri"
        )
        rows = await self._client.execute_cypher(
            entity_query, params={"user": user}
        )

        all_uris: List[str] = []
        for row in rows:
            entity_uri = row["entity_uri"]
            try:
                uris = await self.detect_and_store(entity_uri, user=user, collection=collection)
                all_uris.extend(uris)
            except Exception:
                logger.exception(
                    "Error detecting contradictions for entity %s", entity_uri
                )

        logger.info(
            "detect_batch_for_document: doc=%s user=%s → %d contradiction(s) stored",
            document_uri,
            user,
            len(all_uris),
        )
        return all_uris
