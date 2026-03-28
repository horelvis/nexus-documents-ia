"""
ExtractionCoordinator — orchestrates 4 parallel LLM extractors per chunk.

Runs DefinitionsExtractor, RelationshipsExtractor, ObjectsExtractor, and
TopicsExtractor in parallel via asyncio.gather, deduplicates the resulting
triples, stores them in the TripleStore, records PROV-O provenance, and
runs batch contradiction detection after all chunks in a document are
processed.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Set, Tuple

from app.services.contradiction import ContradictionDetector
from app.services.extractors.definitions import DefinitionsExtractor
from app.services.extractors.objects import ObjectsExtractor
from app.services.extractors.relationships import RelationshipsExtractor
from app.services.extractors.topics import TopicsExtractor
from app.services.provenance import ProvenanceService
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)


class ExtractionCoordinator:
    """Coordinates 4 LLM extractors for TrustGraph triple extraction.

    Args:
        store: TripleStore instance (wraps FalkorDBClient).
    """

    def __init__(self, store: TripleStore) -> None:
        self._store = store
        self._provenance = ProvenanceService(store)

        # Instantiate all 4 extractors
        self._definitions = DefinitionsExtractor()
        self._relationships = RelationshipsExtractor()
        self._objects = ObjectsExtractor()
        self._topics = TopicsExtractor()

    # ------------------------------------------------------------------
    # Chunk-level extraction
    # ------------------------------------------------------------------

    async def extract_chunk(
        self,
        chunk_text: str,
        document_uri: str,
        user: str,
        collection: str,
        chunk_offset: int = 0,
        model_name: str = "Qwen3.5-9B",
    ) -> Dict[str, Any]:
        """Extract and store triples from a single text chunk.

        Runs all 4 extractors in parallel, deduplicates results, stores
        each triple in the graph, and records PROV-O provenance.

        Args:
            chunk_text:    Raw text of the chunk.
            document_uri:  URI of the parent document :Node.
            user:          Tenant/user identifier.
            collection:    Collection scope.
            chunk_offset:  Character offset of this chunk within the document.
            model_name:    LLM model used for provenance metadata.

        Returns:
            Dict with keys:
              triples_created  — triples successfully stored
              triples_total    — triples before deduplication
              triples_deduped  — triples removed as duplicates
              extractors_run   — number of extractors that did not raise
              subjects         — unique subject URIs stored
              errors           — error messages from failed extractors
              elapsed_ms       — wall-clock ms for entire operation
        """
        t_start = time.monotonic()

        # Run 4 extractors in parallel
        results = await asyncio.gather(
            self._definitions.extract(chunk_text),
            self._relationships.extract(chunk_text),
            self._objects.extract(chunk_text),
            self._topics.extract(chunk_text),
            return_exceptions=True,
        )

        extractor_names = ["definitions", "relationships", "objects", "topics"]
        errors: List[str] = []
        all_triples: List[Dict[str, Any]] = []
        extractors_run = 0

        for name, result in zip(extractor_names, results):
            if isinstance(result, BaseException):
                errors.append(f"{name}: {result}")
                logger.warning("Extractor %s raised exception: %s", name, result)
            else:
                extractors_run += 1
                all_triples.extend(result)

        triples_total = len(all_triples)

        # Deduplicate by normalized key to catch case/accent variations
        # e.g. "Juan García" and "juan garcia" produce the same URI slug
        seen: Set[Tuple[str, str, str]] = set()
        deduped_triples: List[Dict[str, Any]] = []
        for triple in all_triples:
            raw_subj = triple.get("subject", "")
            raw_obj = triple.get("object", "")
            key = (
                URIBuilder.normalize_name(raw_subj) if raw_subj else "",
                triple.get("predicate_name", ""),
                URIBuilder.normalize_name(raw_obj) if raw_obj else "",
            )
            if key not in seen:
                seen.add(key)
                deduped_triples.append(triple)

        triples_deduped = triples_total - len(deduped_triples)

        # ── Entity linking: upgrade Literal → Node where object matches a known entity ──
        # Collect all subjects that extractors created as :Node entities
        known_entities: Set[str] = set()
        for triple in deduped_triples:
            subj = triple.get("subject", "")
            if subj:
                try:
                    known_entities.add(URIBuilder.normalize_name(subj))
                except ValueError:
                    pass

        # Predicates whose objects are always Literal (metadata, not relationships)
        _ALWAYS_LITERAL = {"label", "type", "definition", "has-topic", "references-law"}

        linked_count = 0
        for triple in deduped_triples:
            if triple.get("object_is_node"):
                continue  # Already a Node
            pred_name = triple.get("predicate_name", "")
            if pred_name in _ALWAYS_LITERAL:
                continue  # These are intrinsically Literal
            obj = triple.get("object", "")
            if not obj:
                continue
            try:
                normalized_obj = URIBuilder.normalize_name(obj)
            except ValueError:
                continue
            if normalized_obj in known_entities:
                triple["object_is_node"] = True
                linked_count += 1

        if linked_count:
            logger.info(
                "Entity linking: upgraded %d Literal→Node (of %d triples, %d known entities)",
                linked_count,
                len(deduped_triples),
                len(known_entities),
            )

        triples_created = 0
        subject_uris: List[str] = []

        # Store each triple
        source_chunk_id = f"{document_uri}#offset={chunk_offset}"

        for triple in deduped_triples:
            subject = triple.get("subject", "")
            predicate_ontology = triple.get("predicate_ontology", "core")
            predicate_name = triple.get("predicate_name", "")
            obj = triple.get("object", "")
            object_is_node = triple.get("object_is_node", False)
            extraction_method = triple.get("extraction_method", "llm")

            try:
                # Topic triples: subject=="" and predicate_name=="has-topic"
                # Link document_uri → topic literal directly
                if predicate_name == "has-topic" and subject == "":
                    await self._store.merge_literal(obj, user, collection)
                    predicate_uri = URIBuilder.predicate(predicate_ontology, predicate_name)
                    await self._store.create_rel(
                        subject_uri=document_uri,
                        predicate_uri=predicate_uri,
                        object_value=obj,
                        user=user,
                        collection=collection,
                        object_is_node=False,
                        extraction_method=extraction_method,
                        source_chunk=source_chunk_id,
                    )
                    if document_uri not in subject_uris:
                        subject_uris.append(document_uri)
                else:
                    subject_uri = await self._store.store_triple(
                        subject_name=subject,
                        predicate_ontology=predicate_ontology,
                        predicate_name=predicate_name,
                        object_value=obj,
                        object_is_node=object_is_node,
                        user=user,
                        collection=collection,
                        extraction_method=extraction_method,
                        source_chunk=source_chunk_id,
                    )
                    if subject_uri not in subject_uris:
                        subject_uris.append(subject_uri)

                triples_created += 1

            except Exception as exc:
                errors.append(f"store({subject!r}, {predicate_name!r}, {obj!r}): {exc}")
                logger.warning(
                    "Failed to store triple (%r, %r, %r): %s",
                    subject,
                    predicate_name,
                    obj,
                    exc,
                )

        # Record PROV-O provenance
        try:
            await self._provenance.record_extraction(
                document_uri=document_uri,
                extraction_method="llm_coordinator",
                model_name=model_name,
                chunk_text=chunk_text,
                chunk_offset=chunk_offset,
                user=user,
                collection=collection,
            )
        except Exception as exc:
            errors.append(f"provenance: {exc}")
            logger.warning("Failed to record provenance: %s", exc)

        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        return {
            "triples_created": triples_created,
            "triples_total": triples_total,
            "triples_deduped": triples_deduped,
            "extractors_run": extractors_run,
            "subjects": subject_uris,
            "errors": errors,
            "elapsed_ms": elapsed_ms,
        }

    # ------------------------------------------------------------------
    # Document-level extraction
    # ------------------------------------------------------------------

    async def extract_document(
        self,
        chunks: List[str],
        document_id: str,
        user: str,
        collection: str,
        title: str,
        file_path: str,
        semantic_type: str,
        domain: str,
    ) -> Dict[str, Any]:
        """Extract and store triples for all chunks of a document.

        1. Creates the document :Node with metadata triples.
        2. Processes each chunk sequentially via extract_chunk().
        3. Runs batch contradiction detection for all unique subjects.

        Args:
            chunks:        List of text chunks (in order).
            document_id:   Unique document identifier.
            user:          Tenant/user identifier.
            collection:    Collection scope.
            title:         Human-readable document title.
            file_path:     File path (used to derive folder URI).
            semantic_type: Document semantic type (e.g. "factura").
            domain:        Business domain (e.g. "legal").

        Returns:
            Dict with keys:
              success             — True on completion (even with partial errors)
              document_uri        — canonical URI of the document :Node
              triples_created     — total triples stored across all chunks
              contradictions_found — total contradiction :Nodes created
              chunks_processed    — number of chunks processed
              extraction_time_ms  — total wall-clock ms
              errors              — aggregated error messages
        """
        t_start = time.monotonic()
        errors: List[str] = []

        # Step 1: Create document :Node
        try:
            document_uri = await self._store.store_document_node(
                document_id=document_id,
                user=user,
                collection=collection,
                title=title,
                file_path=file_path,
                semantic_type=semantic_type,
                domain=domain,
            )
        except Exception as exc:
            errors.append(f"store_document_node: {exc}")
            logger.error("Failed to create document node for %s: %s", document_id, exc)
            document_uri = URIBuilder.document(collection, document_id)

        # Step 2: Process each chunk sequentially
        total_triples = 0
        all_subject_uris: Set[str] = set()

        for chunk_offset, chunk_text in enumerate(chunks):
            try:
                result = await self.extract_chunk(
                    chunk_text=chunk_text,
                    document_uri=document_uri,
                    user=user,
                    collection=collection,
                    chunk_offset=chunk_offset,
                )
                total_triples += result["triples_created"]
                all_subject_uris.update(result["subjects"])
                if result["errors"]:
                    errors.extend(
                        [f"chunk[{chunk_offset}]/{e}" for e in result["errors"]]
                    )
            except Exception as exc:
                errors.append(f"chunk[{chunk_offset}]: {exc}")
                logger.error("Failed to process chunk %d: %s", chunk_offset, exc)

        # Step 3: Batch contradiction detection per unique subject URI
        contradiction_uris: List[str] = []
        detector = ContradictionDetector(self._store._client)

        for subject_uri in all_subject_uris:
            try:
                uris = await detector.detect_and_store(
                    subject_uri=subject_uri,
                    user=user,
                    collection=collection,
                )
                contradiction_uris.extend(uris)
            except Exception as exc:
                errors.append(f"contradiction({subject_uri}): {exc}")
                logger.warning(
                    "Contradiction detection failed for %s: %s", subject_uri, exc
                )

        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        return {
            "success": True,
            "document_uri": document_uri,
            "triples_created": total_triples,
            "contradictions_found": len(contradiction_uris),
            "chunks_processed": len(chunks),
            "extraction_time_ms": elapsed_ms,
            "errors": errors,
        }
