"""
ProvenanceService — PROV-O provenance tracking for TrustGraph extractions.

Records provenance metadata for each extraction event using PROV-O-inspired
predicates. An extraction :Node captures the document source, extraction method,
model, timestamp, and the chunk of text that produced the triples.

PROV-O predicates used:
  prov/derived-from   — links extraction to the source document (Node→Node)
  prov/method         — extraction algorithm/strategy (Node→Literal)
  prov/model          — LLM/NER model used (Node→Literal)
  prov/timestamp      — ISO-8601 UTC datetime (Node→Literal)
  prov/chunk-text     — first 500 chars of source chunk (Node→Literal)
  prov/chunk-offset   — byte/char offset of chunk in document (Node→Literal)
"""

import logging
from datetime import datetime, timezone

from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)

# Predicate ontology namespace for PROV-O terms
_PROV = "prov"

# Maximum characters to store from chunk text
_MAX_CHUNK_TEXT = 500


class ProvenanceService:
    """Records PROV-O provenance triples for each extraction event."""

    def __init__(self, store: TripleStore) -> None:
        self._store = store

    async def record_extraction(
        self,
        document_uri: str,
        extraction_method: str,
        model_name: str,
        chunk_text: str,
        chunk_offset: int,
        user: str,
        collection: str,
    ) -> str:
        """Create an extraction :Node and record 6 provenance triples.

        Args:
            document_uri:      URI of the source document :Node.
            extraction_method: Algorithm used (e.g. "llm_relationships", "ner").
            model_name:        Model identifier (e.g. "Qwen3.5-9B").
            chunk_text:        Raw chunk text (truncated to 500 chars for storage).
            chunk_offset:      Character/byte offset of the chunk within the document.
            user:              Tenant/user identifier.
            collection:        Collection scope.

        Returns:
            extraction_uri — the canonical URI of the extraction :Node.
        """
        extraction_uri = URIBuilder.extraction()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        truncated_chunk = chunk_text[:_MAX_CHUNK_TEXT]

        # Merge the extraction :Node itself
        await self._store.merge_node(extraction_uri, user=user, collection=collection)

        # Triple 1: prov/derived-from → document_uri (Node→Node)
        await self._store.create_rel(
            subject_uri=extraction_uri,
            predicate_uri=URIBuilder.predicate(_PROV, "derived-from"),
            object_value=document_uri,
            user=user,
            collection=collection,
            object_is_node=True,
            extraction_method="system",
        )

        # Triples 2–6: Node→Literal provenance metadata
        literal_triples = [
            ("method", extraction_method),
            ("model", model_name),
            ("timestamp", timestamp),
            ("chunk-text", truncated_chunk),
            ("chunk-offset", str(chunk_offset)),
        ]
        for predicate_name, value in literal_triples:
            await self._store.merge_literal(value, user=user, collection=collection)
            await self._store.create_rel(
                subject_uri=extraction_uri,
                predicate_uri=URIBuilder.predicate(_PROV, predicate_name),
                object_value=value,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="system",
            )

        logger.debug(
            "Recorded provenance for extraction %s (method=%s, model=%s, offset=%d)",
            extraction_uri,
            extraction_method,
            model_name,
            chunk_offset,
        )
        return extraction_uri

    async def batch_record_extractions(
        self,
        document_uri: str,
        chunks_metadata: list,
        user: str,
        collection: str,
    ) -> int:
        """Record provenance for multiple chunks in 2 batch UNWIND queries.

        Args:
            document_uri:    URI of the source document :Node.
            chunks_metadata: List of dicts with keys:
                extraction_method, model_name, chunk_text, chunk_offset
            user:           Tenant/user identifier.
            collection:     Collection scope.

        Returns:
            Number of provenance records created.
        """
        if not chunks_metadata:
            return 0

        derived_from_uri = URIBuilder.predicate(_PROV, "derived-from")

        records = []
        for meta in chunks_metadata:
            records.append({
                "extraction_uri": URIBuilder.extraction(),
                "document_uri": document_uri,
                "derived_from_uri": derived_from_uri,
                "method": meta.get("extraction_method", "llm_coordinator"),
                "model": meta.get("model_name", "unknown"),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "chunk_text": meta.get("chunk_text", "")[:_MAX_CHUNK_TEXT],
                "chunk_offset": str(meta.get("chunk_offset", 0)),
            })

        return await self._store.batch_store_provenance(
            records, user=user, collection=collection
        )
