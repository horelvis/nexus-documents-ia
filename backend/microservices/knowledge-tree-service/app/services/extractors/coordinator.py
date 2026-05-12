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

from app.core.config import settings
from app.services.consensus import ConsensusScorer
from app.services.contradiction import ContradictionDetector
from app.services.extractors.definitions import DefinitionsExtractor
from app.services.extractors.objects import ObjectsExtractor
from app.services.extractors.relationships import RelationshipsExtractor
from app.services.extractors.topics import TopicsExtractor
from app.services.provenance import ProvenanceService
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder
from app.services.entity_blacklist import EntityBlacklist

logger = logging.getLogger(__name__)

# Confidence base scores by extraction method
_CONFIDENCE_BASE: Dict[str, float] = {
    "system": 1.00,
    "llm_definitions": 0.90,
    "llm_topics": 0.85,
    "llm_objects": 0.85,
    "llm_relationships": 0.90,
    "llm_relationships_fuzzy": 0.75,
    "llm_relationships_freeform": 0.60,
    "llm_relationships_semantic": 0.85,
}
_DEFAULT_CONFIDENCE = 0.70


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

        # Predicates where only one value per entity is meaningful —
        # the LLM often rephrases the same definition across extractors,
        # producing variants like "Código de Comercio (BOE-A-1885-6627)"
        # vs "Código de Comercio, con referencia BOE-A-1885-6627".
        _UNIQUE_PER_ENTITY = {"definition", "label"}

        # Deduplicate by normalized key to catch case/accent variations
        # e.g. "Juan García" and "juan garcia" produce the same URI slug
        seen: Set[Tuple[str, str, str]] = set()
        deduped_triples: List[Dict[str, Any]] = []
        for triple in all_triples:
            raw_subj = triple.get("subject", "")
            raw_obj = triple.get("object", "")
            pred_name = triple.get("predicate_name", "")
            norm_subj = URIBuilder.normalize_name(raw_subj) if raw_subj else ""

            if pred_name in _UNIQUE_PER_ENTITY:
                # One definition/label per entity — ignore object text variance
                key = (norm_subj, pred_name, "")
            else:
                key = (
                    norm_subj,
                    pred_name,
                    URIBuilder.normalize_name(raw_obj) if raw_obj else "",
                )

            if key not in seen:
                seen.add(key)
                deduped_triples.append(triple)

        triples_deduped = triples_total - len(deduped_triples)

        # ── Blacklist filtering: drop triples with blacklisted subjects/objects ──
        _blacklist = EntityBlacklist()
        pre_blacklist = len(deduped_triples)
        filtered_triples: List[Dict[str, Any]] = []
        for triple in deduped_triples:
            subject = triple.get("subject", "")
            obj = triple.get("object", "")
            obj_is_node = triple.get("object_is_node", False)

            if _blacklist.is_blacklisted(subject):
                continue
            if obj_is_node and _blacklist.is_blacklisted(obj):
                continue
            filtered_triples.append(triple)

        blacklisted_count = pre_blacklist - len(filtered_triples)
        if blacklisted_count:
            logger.info("Blacklist filtered %d triples", blacklisted_count)
        deduped_triples = filtered_triples

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

        subject_uris: List[str] = []
        source_chunk_id = f"{document_uri}#offset={chunk_offset}"

        # Materialize the chunk as a first-class :Chunk node and link it to
        # its parent document. Every :Rel produced in this extraction run
        # references the same chunk, so a single MERGE per chunk is enough.
        # Legacy `source_chunk` string stays on each edge so trace_sources()
        # keeps working during the migration to :Chunk-based traversal.
        # document_id is derived from document_uri (last URI path segment).
        _doc_id_from_uri = document_uri.rstrip("/").rsplit("/", 1)[-1]
        chunk_uri = URIBuilder.chunk(collection, _doc_id_from_uri, chunk_offset)
        try:
            await self._store.merge_chunk_node(
                chunk_uri=chunk_uri,
                document_uri=document_uri,
                chunk_offset=chunk_offset,
                collection=collection,
            )
        except Exception as exc:
            # Pipeline-critical: no :Chunk node means source_evidence can't
            # link triples to chunks in evidence_graph. Errors[] already
            # propagates to the API response; elevate log level so prod
            # monitoring catches repeated failures.
            errors.append(f"merge_chunk: {exc}")
            logger.error("Chunk node MERGE failed for document %s: %s", document_id, exc)

        # ── Build batch triples ──────────────────────────────────────────
        batch_triples: List[Dict[str, Any]] = []

        for triple in deduped_triples:
            subject = triple.get("subject", "")
            predicate_ontology = triple.get("predicate_ontology", "core")
            predicate_name = triple.get("predicate_name", "")
            obj = triple.get("object", "")
            object_is_node = triple.get("object_is_node", False)
            extraction_method = triple.get("extraction_method", "llm")

            if not predicate_name:
                continue

            predicate_uri = URIBuilder.predicate(predicate_ontology, predicate_name)
            confidence = _CONFIDENCE_BASE.get(extraction_method, _DEFAULT_CONFIDENCE)

            # Topic triples: subject="" → link document_uri → topic literal
            if predicate_name == "has-topic" and subject == "":
                batch_triples.append({
                    "s_uri": document_uri,
                    "p_uri": predicate_uri,
                    "o_val": obj,
                    "object_is_entity": False,
                    "method": extraction_method,
                    "chunk": source_chunk_id,
                    "confidence": confidence,
                })
                if document_uri not in subject_uris:
                    subject_uris.append(document_uri)
            else:
                try:
                    s_uri = URIBuilder.entity(collection, subject)
                except ValueError:
                    continue
                if object_is_node:
                    try:
                        o_uri = URIBuilder.entity(collection, obj)
                    except ValueError:
                        continue
                    batch_triples.append({
                        "s_uri": s_uri,
                        "o_uri": o_uri,
                        "p_uri": predicate_uri,
                        "object_is_entity": True,
                        "method": extraction_method,
                        "chunk": source_chunk_id,
                        "confidence": confidence,
                    })
                else:
                    batch_triples.append({
                        "s_uri": s_uri,
                        "o_val": obj.strip() if obj else obj,
                        "p_uri": predicate_uri,
                        "object_is_entity": False,
                        "method": extraction_method,
                        "chunk": source_chunk_id,
                        "confidence": confidence,
                    })
                if s_uri not in subject_uris:
                    subject_uris.append(s_uri)

        # ── Store all triples in 1-2 batch Cypher calls ──────────────────
        triples_created = 0
        try:
            triples_created = await self._store.batch_store_triples(
                batch_triples, collection=collection
            )
        except Exception as exc:
            # Pipeline-critical: batch_store failure means NO triples are
            # persisted for this chunk. This was the class of bug that
            # surfaced on 2026-04-23 (FalkorDBClient missing methods).
            # errors[] is already returned to the API; log at ERROR so the
            # failure stops blending in with routine warnings.
            errors.append(f"batch_store: {exc}")
            logger.error("Batch store failed for document %s: %s", document_id, exc)

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
        collection: str,
        title: str,
        file_path: str,
        semantic_type: str,
    ) -> Dict[str, Any]:
        """Extract and store triples for all chunks of a document.

        1. Creates the document :Node with metadata triples.
        2. Processes chunks in parallel (bounded by extraction_parallel_chunks).
        3. Runs batch contradiction detection for all unique subjects.

        Returns dict with success, document_uri, triples_created,
        contradictions_found, chunks_processed, extraction_time_ms, errors,
        parse_failures, empty_responses, validation_failures.
        """
        t_start = time.monotonic()
        errors: List[str] = []

        # Step 1: Create document :Node
        try:
            document_uri = await self._store.store_document_node(
                document_id=document_id,
                collection=collection,
                title=title,
                file_path=file_path,
                semantic_type=semantic_type,
            )
        except Exception as exc:
            errors.append(f"store_document_node: {exc}")
            logger.error("Failed to create document node for %s: %s", document_id, exc)
            document_uri = URIBuilder.document(collection, document_id)

        # Step 2: Process chunks in parallel (bounded)
        total_triples = 0
        all_subject_uris: Set[str] = set()
        sem = asyncio.Semaphore(settings.extraction_parallel_chunks)

        async def _process_chunk(offset: int, text: str) -> Dict[str, Any]:
            async with sem:
                return await self.extract_chunk(
                    chunk_text=text,
                    document_uri=document_uri,
                    collection=collection,
                    chunk_offset=offset,
                )

        tasks = [_process_chunk(i, text) for i, text in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        provenance_metadata: List[Dict[str, Any]] = []

        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                errors.append(f"chunk[{i}]: {result}")
                logger.error("Failed to process chunk %d: %s", i, result)
            else:
                total_triples += result["triples_created"]
                all_subject_uris.update(result["subjects"])
                if result["errors"]:
                    errors.extend(
                        [f"chunk[{i}]/{e}" for e in result["errors"]]
                    )
                provenance_metadata.append({
                    "extraction_method": "llm_coordinator",
                    "model_name": "Qwen3.5-27B-AWQ",
                    "chunk_text": chunks[i],
                    "chunk_offset": i,
                })

        # Step 2b: Batch record provenance for all chunks (2 UNWIND queries)
        try:
            await self._provenance.batch_record_extractions(
                document_uri=document_uri,
                chunks_metadata=provenance_metadata,
                collection=collection,
            )
        except Exception as exc:
            errors.append(f"batch_provenance: {exc}")
            logger.warning("Batch provenance recording failed: %s", exc)

        # Step 3: Parallel contradiction detection (edge metadata)
        contradictions_found = 0
        detector = ContradictionDetector(self._store._client)
        contra_sem = asyncio.Semaphore(10)

        async def _detect_subject(subject_uri: str) -> int:
            async with contra_sem:
                return await detector.detect_and_mark(subject_uri=subject_uri)

        contra_tasks = [_detect_subject(uri) for uri in all_subject_uris]
        contra_results = await asyncio.gather(*contra_tasks, return_exceptions=True)

        subject_list = list(all_subject_uris)
        for i, result in enumerate(contra_results):
            if isinstance(result, BaseException):
                subj = subject_list[i] if i < len(subject_list) else "?"
                errors.append(f"contradiction({subj}): {result}")
                logger.warning("Contradiction detection failed: %s", result)
            else:
                contradictions_found += result

        # Step 3b: Apply confidence penalty to contradicted edges
        try:
            await detector.apply_confidence_penalty()
        except Exception as exc:
            errors.append(f"confidence_penalty: {exc}")
            logger.warning("Confidence penalty failed: %s", exc)

        # Step 3c: Consensus scoring — count independent sources per triple
        consensus_scorer = ConsensusScorer(self._store._client)
        consensus_sem = asyncio.Semaphore(10)

        async def _score_subject(subject_uri: str) -> int:
            async with consensus_sem:
                return await consensus_scorer.compute_and_store(subject_uri=subject_uri)

        consensus_tasks = [_score_subject(uri) for uri in all_subject_uris]
        consensus_results = await asyncio.gather(*consensus_tasks, return_exceptions=True)

        total_consensus = 0
        for i, result in enumerate(consensus_results):
            if isinstance(result, BaseException):
                subj = subject_list[i] if i < len(subject_list) else "?"
                errors.append(f"consensus({subj}): {result}")
                logger.warning("Consensus scoring failed: %s", result)
            else:
                total_consensus += result

        # Step 3c.5: Normalize unique-per-entity predicates. FalkorDB's
        # MERGE on relationships does not dedup across separate transactions,
        # so per-chunk extraction batches leave duplicate (s, p, o) edges for
        # core/type, core/label, core/definition. Cross-extractor disagreement
        # also stacks (e.g. one chunk types Horelvis as person, another as
        # organization). This pass runs AFTER consensus scoring (which needs
        # raw counts) and BEFORE entity resolution (which expects clean state).
        normalize_summary: Dict[str, int] = {}
        try:
            normalize_summary = await self._store.normalize_unique_predicates_for_subjects(
                subject_uris=list(all_subject_uris),
                collection=collection,
            )
        except Exception as exc:
            errors.append(f"normalize_unique_predicates: {exc}")
            logger.warning("Normalize unique predicates failed: %s", exc)

        # Step 3c.6: Backstop default core/type for untyped nodes. The 4
        # extractors sometimes emit subjects with no type triple (address
        # tokens, billing concepts, license-plate fragments). Untyped nodes
        # are invisible to the type-scoped EntityResolver and accumulate as
        # orphans. This assigns core/type → "other" so the resolver can
        # at least see them; "other" is explicitly skipped by the resolver
        # so it doesn't trigger accidental clustering.
        untyped_backfilled = 0
        try:
            untyped_backfilled = await self._store.assign_default_type_to_untyped_nodes(
                subject_uris=list(all_subject_uris),
                collection=collection,
            )
        except Exception as exc:
            errors.append(f"untyped_backstop: {exc}")
            logger.warning("Untyped node backstop failed: %s", exc)

        # Step 3d: Entity resolution — merge duplicate :Nodes emitted under
        # slightly different labels by the 4 extractors. Runs per-document
        # over the full collection scope so cross-document duplicates
        # collapse as soon as a later doc adds a clearer label variant of
        # an existing entity. Idempotent: re-running when nothing is
        # duplicated returns zero-cost.
        #
        # Scope: every SUPPORTED_TYPES key (person, organization, place).
        # Unsupported types (amount, date, other) are skipped because they
        # either need a different algorithm (dates → canonical format) or
        # don't benefit from clustering (amounts are distinct values).
        resolver_summaries: Dict[str, Any] = {}
        try:
            from app.services.entity_resolver import EntityResolver

            resolver = EntityResolver(self._store._client)
            resolver_summaries = await resolver.resolve_all_supported(
                collection=collection,
            )
        except Exception as exc:
            errors.append(f"entity_resolution: {exc}")
            logger.warning("Entity resolution failed: %s", exc)

        # Aggregate merge stats across all types for the summary log line.
        resolver_total_merged = sum(
            (s.get("clusters_merged", 0) or 0)
            for s in resolver_summaries.values()
            if isinstance(s, dict)
        )
        resolver_total_removed = sum(
            (s.get("nodes_removed", 0) or 0)
            for s in resolver_summaries.values()
            if isinstance(s, dict)
        )

        # Step 4: Log extraction summary
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        total_parse_failures = sum(
            e._parse_failures for e in [
                self._definitions, self._relationships,
                self._objects, self._topics,
            ]
        )
        total_empty = sum(
            e._empty_responses for e in [
                self._definitions, self._relationships,
                self._objects, self._topics,
            ]
        )
        total_validation = sum(
            e._validation_failures for e in [
                self._definitions, self._relationships,
                self._objects, self._topics,
            ]
        )

        logger.info(
            "Document %s extraction complete: %d triples, %d parse_failures, "
            "%d empty_responses, %d validation_failures, %d contradictions, "
            "%d consensus_predicates, normalize=%s, untyped_backfilled=%d, "
            "person_clusters_merged=%d nodes_removed=%d, %dms",
            document_id,
            total_triples,
            total_parse_failures,
            total_empty,
            total_validation,
            contradictions_found,
            total_consensus,
            normalize_summary,
            untyped_backfilled,
            resolver_total_merged,
            resolver_total_removed,
            elapsed_ms,
        )

        # Step 5: Auto-embed the subset of entities touched by this
        # extraction (fire-and-forget). The subset path uses the
        # idempotent /entities/upsert-subset endpoint, so it costs O(touched)
        # instead of O(scope) and can run safely while other extractions
        # are landing — only colliding with the rare full re-embed cron
        # via the shared asyncio.Lock in entity_embedding.
        if (
            settings.auto_entity_embedding_enabled
            and total_triples > 0
            and all_subject_uris
        ):
            asyncio.create_task(
                _safe_populate_embeddings(
                    collection=collection,
                    subset_uris=tuple(all_subject_uris),
                )
            )

        return {
            "success": True,
            "document_uri": document_uri,
            "triples_created": total_triples,
            "contradictions_found": contradictions_found,
            "chunks_processed": len(chunks),
            "extraction_time_ms": elapsed_ms,
            "parse_failures": total_parse_failures,
            "empty_responses": total_empty,
            "validation_failures": total_validation,
            "errors": errors,
        }


async def _safe_populate_embeddings(
    collection: str,
    subset_uris: tuple,
) -> None:
    """Wrap populate_entity_embeddings_subset so a failure in the
    fire-and-forget task does not surface as an unawaited-exception warning.
    """
    try:
        from app.services.entity_embedding import populate_entity_embeddings_subset
        upserted = await populate_entity_embeddings_subset(
            scope=collection, collection=collection, subset_uris=subset_uris,
        )
        logger.info("Auto entity embedding refreshed %d entities", upserted)
    except Exception as exc:
        logger.warning("Auto entity embedding failed: %s", exc, exc_info=True)
