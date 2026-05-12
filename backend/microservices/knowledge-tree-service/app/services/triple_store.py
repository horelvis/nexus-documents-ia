"""
TripleStore — Core CRUD layer for TrustGraph on FalkorDB.

Provides atomic operations for Node, Literal, and Rel management.
All methods are async and operate within collection scope.

Graph model:
  :Node   — named entity or document with a canonical URI
  :Literal — scalar value (string, date, etc.) deduped by (value, collection)
  :Rel    — edge connecting subject :Node to object :Node or :Literal,
             carrying provenance metadata (predicate URI, extraction method, etc.)
"""

import logging
from typing import Optional

from app.services.falkordb_client import FalkorDBClient
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)


class TripleStore:
    """CRUD operations for TrustGraph nodes, literals, and relationships."""

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    async def merge_node(self, uri: str, collection: str) -> None:
        """MERGE a :Node by URI, setting created_at on first creation.

        Idempotent — safe to call multiple times with the same URI.
        """
        query = (
            "MERGE (n:Node {uri: $uri, collection: $collection}) "
            "ON CREATE SET n.created_at = timestamp()"
        )
        await self._client.execute_cypher(
            query,
            params={"uri": uri, "collection": collection},
        )

    # ------------------------------------------------------------------
    # Literal operations
    # ------------------------------------------------------------------

    async def merge_chunk_node(
        self,
        chunk_uri: str,
        document_uri: str,
        chunk_offset: int,
        collection: str,
    ) -> None:
        """MERGE a :Chunk node and link it to its parent document.

        The :Chunk node carries only the offset + a timestamp; the actual
        chunk text lives in Weaviate (Nouxcube_documents collection) and
        is resolved on demand via _resolve_chunk_texts on the Emma side.

        The edge uses the reserved predicate `core/of-document` to mark the
        chunk→document hierarchy so graph queries can traverse upward from
        any chunk to its document without URI parsing.

        Idempotent — MERGE on (uri, collection).
        """
        await self._client.execute_cypher(
            "MERGE (c:Chunk {uri: $chunk_uri, collection: $col}) "
            "ON CREATE SET c.created_at = timestamp(), c.offset = $offset "
            "MERGE (d:Node {uri: $doc_uri, collection: $col}) "
            "ON CREATE SET d.created_at = timestamp() "
            "MERGE (c)-[r:Rel {uri: $of_doc_pred, collection: $col}]->(d) "
            "ON CREATE SET r.extraction_method = 'structural', r.confidence = 1.0",
            params={
                "chunk_uri": chunk_uri,
                "doc_uri": document_uri,
                "offset": chunk_offset,
                "col": collection,
                "of_doc_pred": "nouxcube://predicate/core/of-document",
            },
        )

    async def merge_literal(self, value: str, collection: str) -> None:
        """MERGE a :Literal deduped by (value, collection).

        Values are stripped of leading/trailing whitespace before storage
        to prevent "Madrid" vs "Madrid " creating separate nodes.

        Idempotent — multiple calls with the same arguments produce a
        single node in the graph.
        """
        normalized_value = value.strip() if value else value
        query = (
            "MERGE (:Literal {value: $value, collection: $collection})"
        )
        await self._client.execute_cypher(
            query,
            params={"value": normalized_value, "collection": collection},
        )

    # ------------------------------------------------------------------
    # Relationship operations
    # ------------------------------------------------------------------

    async def create_rel(
        self,
        subject_uri: str,
        predicate_uri: str,
        object_value: str,
        collection: str,
        object_is_node: bool,
        extraction_method: str,
        source_chunk: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> None:
        """MERGE a :Rel edge from subject :Node to object :Node or :Literal.

        Uses MERGE on (subject, predicate_uri, object, collection) to
        prevent duplicate edges for the same fact. Additional metadata
        (extraction_method, source_chunk, timestamps) is set on first creation.

        Args:
            subject_uri:       URI of the subject :Node.
            predicate_uri:     URI of the predicate (ontology term).
            object_value:      URI if object_is_node=True, literal value otherwise.
            collection:        Collection scope.
            object_is_node:    True → object is a :Node matched by URI.
                               False → object is a :Literal matched by (value, collection).
            extraction_method: How this triple was extracted (e.g. "ner", "llm", "regex").
            source_chunk:      Source chunk ID for provenance.
            valid_from:        ISO date string — temporal validity start.
            valid_until:       ISO date string — temporal validity end.
        """
        if object_is_node:
            query = (
                "MATCH (s:Node {uri: $s_uri, collection: $collection}) "
                "MATCH (o:Node {uri: $o_uri, collection: $collection}) "
                "MERGE (s)-[r:Rel {uri: $p_uri, collection: $collection}]->(o) "
                "ON CREATE SET r.extraction_method = $extraction_method, "
                "r.source_chunk = $source_chunk, "
                "r.valid_from = $valid_from, r.valid_until = $valid_until"
            )
            params = {
                "s_uri": subject_uri,
                "o_uri": object_value,
                "p_uri": predicate_uri,
                "collection": collection,
                "extraction_method": extraction_method,
                "source_chunk": source_chunk,
                "valid_from": valid_from,
                "valid_until": valid_until,
            }
        else:
            query = (
                "MATCH (s:Node {uri: $s_uri, collection: $collection}) "
                "MATCH (o:Literal {value: $o_val, collection: $collection}) "
                "MERGE (s)-[r:Rel {uri: $p_uri, collection: $collection}]->(o) "
                "ON CREATE SET r.extraction_method = $extraction_method, "
                "r.source_chunk = $source_chunk, "
                "r.valid_from = $valid_from, r.valid_until = $valid_until"
            )
            params = {
                "s_uri": subject_uri,
                "o_val": object_value,
                "p_uri": predicate_uri,
                "collection": collection,
                "extraction_method": extraction_method,
                "source_chunk": source_chunk,
                "valid_from": valid_from,
                "valid_until": valid_until,
            }

        await self._client.execute_cypher(query, params=params)

    # ------------------------------------------------------------------
    # High-level triple operations
    # ------------------------------------------------------------------

    async def store_triple(
        self,
        subject_name: str,
        predicate_ontology: str,
        predicate_name: str,
        object_value: str,
        object_is_node: bool,
        collection: str,
        extraction_method: str,
        source_chunk: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> str:
        """High-level: merge subject Node, merge object Node/Literal, create Rel.

        Args:
            subject_name:      Human-readable entity name (normalized to URI slug).
            predicate_ontology: Ontology namespace (e.g. "core", "legal").
            predicate_name:    Predicate term within the ontology.
            object_value:      Entity name if object_is_node=True, scalar value otherwise.
            object_is_node:    Controls whether object is merged as :Node or :Literal.
            collection:        Collection scope.
            extraction_method: Provenance extraction method.
            source_chunk:      Optional source chunk ID.
            valid_from:        Optional temporal validity start.
            valid_until:       Optional temporal validity end.

        Returns:
            subject_uri — the canonical URI of the subject node.
        """
        subject_uri = URIBuilder.entity(collection, subject_name)
        predicate_uri = URIBuilder.predicate(predicate_ontology, predicate_name)

        # Merge subject node
        await self.merge_node(subject_uri, collection)

        # Merge object and resolve value for create_rel
        if object_is_node:
            object_uri = URIBuilder.entity(collection, object_value)
            await self.merge_node(object_uri, collection)
            rel_object_value = object_uri
        else:
            stripped_value = object_value.strip() if object_value else object_value
            await self.merge_literal(stripped_value, collection)
            rel_object_value = stripped_value

        # Create relationship
        await self.create_rel(
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_value=rel_object_value,
            collection=collection,
            object_is_node=object_is_node,
            extraction_method=extraction_method,
            source_chunk=source_chunk,
            valid_from=valid_from,
            valid_until=valid_until,
        )

        return subject_uri

    # Predicates where at most one Literal should exist per subject :Node.
    # Prevents cross-chunk duplicate definitions like
    # "Código de Comercio (BOE-A-1885-6627)" vs
    # "Código de Comercio, con referencia BOE-A-1885-6627".
    _UNIQUE_PREDICATES = {
        "nouxcube://predicate/core/definition",
        "nouxcube://predicate/core/label",
    }

    async def batch_store_triples(
        self, triples: list, collection: str
    ) -> int:
        """Store multiple triples in batched Cypher UNWIND queries.

        Each triple dict must have:
          s_uri, p_uri, method, chunk, object_is_entity
          + o_uri (if entity) or o_val (if literal)

        Returns the number of triples stored.
        """
        if not triples:
            return 0

        node_triples = [t for t in triples if t.get("object_is_entity")]
        literal_triples = [t for t in triples if not t.get("object_is_entity")]

        # Split literals into unique-per-entity vs regular
        unique_lits = [t for t in literal_triples if t["p_uri"] in self._UNIQUE_PREDICATES]
        regular_lits = [t for t in literal_triples if t["p_uri"] not in self._UNIQUE_PREDICATES]

        # Deduplicate unique literals within this batch: one per (subject, predicate)
        if unique_lits:
            seen_unique: set = set()
            deduped: list = []
            for t in unique_lits:
                ukey = (t["s_uri"], t["p_uri"])
                if ukey not in seen_unique:
                    seen_unique.add(ukey)
                    deduped.append(t)
            unique_lits = deduped

        stored = 0

        if node_triples:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "MERGE (o:Node {uri: t.o_uri, collection: $col}) "
                "ON CREATE SET o.created_at = timestamp() "
                "MERGE (s)-[r:Rel {uri: t.p_uri, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
                {"triples": node_triples, "col": collection},
            )
            stored += len(node_triples)

        # Unique-per-entity literals: skip if a Rel with this predicate already
        # exists from the subject to any Literal (cross-chunk dedup).
        if unique_lits:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "WITH s, t "
                "OPTIONAL MATCH (s)-[ex:Rel {uri: t.p_uri, collection: $col}]->(:Literal) "
                "WITH s, t, ex WHERE ex IS NULL "
                "MERGE (o:Literal {value: t.o_val, collection: $col}) "
                "MERGE (s)-[r:Rel {uri: t.p_uri, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
                {"triples": unique_lits, "col": collection},
            )
            stored += len(unique_lits)

        if regular_lits:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "MERGE (o:Literal {value: t.o_val, collection: $col}) "
                "MERGE (s)-[r:Rel {uri: t.p_uri, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
                {"triples": regular_lits, "col": collection},
            )
            stored += len(regular_lits)

        return stored

    async def normalize_unique_predicates_for_subjects(
        self,
        subject_uris: list,
        collection: str,
    ) -> dict:
        """Post-extraction cleanup for predicates that should be unique per entity.

        FalkorDB's `MERGE (s)-[:Rel {uri, collection}]->(o)` does not dedup
        across separate transactions, so per-chunk extraction batches leave
        duplicate `(s, p, o)` edges. Cross-extractor disagreement (e.g. one
        chunk says `type=person`, another says `type=organization`) also
        stacks both edges on the same node.

        This runs once per document after all chunks land and:
          - `core/type`: majority-vote on object value, then dedup so each
            subject has exactly one type edge.
          - `core/definition`: keep the single highest-confidence edge.
          - `core/label`: keep every **distinct** label value (aliases are
            legitimate) but dedup `(s, p, value)` repeats so each variant
            appears once.

        Returns a dict with per-predicate deletion counts (for logs).
        """
        if not subject_uris:
            return {"type_minority_drops": 0, "type_dups": 0,
                    "label_dups": 0, "definition_drops": 0}

        TYPE_PRED = "nouxcube://predicate/core/type"
        LABEL_PRED = "nouxcube://predicate/core/label"
        DEFN_PRED = "nouxcube://predicate/core/definition"

        deleted = {"type_minority_drops": 0, "type_dups": 0,
                   "label_dups": 0, "definition_drops": 0}

        # ── 1. core/type majority vote (uses pre-dedup counts) ────────────
        rows = await self._client.execute_cypher(
            "MATCH (s:Node)-[r:Rel {uri: $pred, collection: $col}]->(t:Literal) "
            "WHERE s.uri IN $uris AND s.collection = $col "
            "RETURN s.uri AS subj, t.value AS type_val, count(r) AS cnt",
            params={"pred": TYPE_PRED, "col": collection, "uris": subject_uris},
        )
        # Group by subject → pick majority type value (ties broken by alphabetical
        # for determinism)
        from collections import defaultdict
        counts_by_subj: dict = defaultdict(dict)
        for row in rows or []:
            counts_by_subj[row["subj"]][row["type_val"]] = row["cnt"]

        for subj, type_counts in counts_by_subj.items():
            dominant = max(type_counts.items(), key=lambda kv: (kv[1], -ord(kv[0][0]) if kv[0] else 0))[0]
            losers = [t for t in type_counts if t != dominant]
            if losers:
                del_rows = await self._client.execute_cypher(
                    "MATCH (s:Node {uri: $subj, collection: $col})"
                    "-[r:Rel {uri: $pred, collection: $col}]->(t:Literal) "
                    "WHERE t.value IN $losers "
                    "WITH r, count(r) AS _c "
                    "DELETE r "
                    "RETURN _c AS n",
                    params={"subj": subj, "col": collection, "pred": TYPE_PRED, "losers": losers},
                )
                if del_rows:
                    deleted["type_minority_drops"] += int(del_rows[0].get("n", 0) or 0)

        # ── 2. Dedup (s, p, o) repeats across unique predicates ──────────
        for pred_uri, key in [(TYPE_PRED, "type_dups"),
                              (LABEL_PRED, "label_dups")]:
            dedup_rows = await self._client.execute_cypher(
                "MATCH (s:Node)-[r:Rel {uri: $pred, collection: $col}]->(o:Literal) "
                "WHERE s.uri IN $uris AND s.collection = $col "
                "WITH s, o, collect(r) AS rels "
                "WHERE size(rels) > 1 "
                "UNWIND rels[1..] AS dup "
                "DELETE dup "
                "RETURN count(dup) AS n",
                params={"pred": pred_uri, "col": collection, "uris": subject_uris},
            )
            if dedup_rows:
                deleted[key] += int(dedup_rows[0].get("n", 0) or 0)

        # ── 3. core/definition: keep single highest-confidence per subject ──
        defn_rows = await self._client.execute_cypher(
            "MATCH (s:Node)-[r:Rel {uri: $pred, collection: $col}]->(o:Literal) "
            "WHERE s.uri IN $uris AND s.collection = $col "
            "WITH s, r, r.confidence AS conf "
            "ORDER BY conf DESC "
            "WITH s, collect(r) AS rels "
            "WHERE size(rels) > 1 "
            "UNWIND rels[1..] AS dup "
            "DELETE dup "
            "RETURN count(dup) AS n",
            params={"pred": DEFN_PRED, "col": collection, "uris": subject_uris},
        )
        if defn_rows:
            deleted["definition_drops"] += int(defn_rows[0].get("n", 0) or 0)

        return deleted

    async def assign_default_type_to_untyped_nodes(
        self,
        subject_uris: list,
        collection: str,
        default_type: str = "other",
    ) -> int:
        """Backstop: ensure every :Node has at least one core/type edge.

        The 4 LLM extractors occasionally emit subjects with no `core/type`
        triple — fragments like address tokens, billing concepts, or
        license-plate substrings get linked through relationships but
        never typed. Untyped nodes are invisible to `EntityResolver`
        (which is type-scoped over person/organization/place) and look
        like orphans in the graph.

        This pass runs AFTER `normalize_unique_predicates_for_subjects`
        and BEFORE `EntityResolver`, assigning `core/type → "other"` to
        any node missing a type. "other" is the explicit "no algorithm
        for me" bucket that the resolver already skips, so the backstop
        makes orphans visible without triggering accidental clustering.

        Uses `extraction_method='system'` and a moderate confidence
        (0.50) so a real extractor evidence in a future doc — when
        someone IS typed as person/org — can still take precedence via
        the normalize majority-vote pass.
        """
        if not subject_uris:
            return 0

        TYPE_PRED = "nouxcube://predicate/core/type"
        ENTITY_PREFIX = "nouxcube://entity/"

        # Guard against backfilling non-entity :Node records (PROV-O
        # extraction nodes, document nodes, folder nodes — these all share
        # the :Node label but legitimately have no core/type).
        rows = await self._client.execute_cypher(
            "MATCH (s:Node) "
            "WHERE s.uri IN $uris AND s.collection = $col "
            "  AND s.uri STARTS WITH $entity_prefix "
            "OPTIONAL MATCH (s)-[t:Rel {uri: $pred, collection: $col}]->(:Literal) "
            "WITH s, count(t) AS type_count "
            "WHERE type_count = 0 "
            "MERGE (lit:Literal {value: $default, collection: $col}) "
            "MERGE (s)-[r:Rel {uri: $pred, collection: $col}]->(lit) "
            "ON CREATE SET r.extraction_method = 'system', r.confidence = 0.50 "
            "RETURN count(s) AS n",
            params={
                "uris": subject_uris,
                "col": collection,
                "pred": TYPE_PRED,
                "default": default_type,
                "entity_prefix": ENTITY_PREFIX,
            },
        )
        if rows:
            return int(rows[0].get("n", 0) or 0)
        return 0

    async def batch_store_provenance(
        self, records: list, collection: str
    ) -> int:
        """Store multiple provenance records in 2 UNWIND queries.

        Each record dict: extraction_uri, document_uri, derived_from_uri,
        method, model, timestamp, chunk_text, chunk_offset
        """
        if not records:
            return 0

        # Query 1: Create extraction nodes + derived-from edges
        await self._client.execute_cypher(
            "UNWIND $records AS r "
            "MERGE (e:Node {uri: r.extraction_uri, collection: $col}) "
            "ON CREATE SET e.created_at = timestamp() "
            "WITH e, r "
            "MATCH (d:Node {uri: r.document_uri, collection: $col}) "
            "MERGE (e)-[rel:Rel {uri: r.derived_from_uri, collection: $col}]->(d) "
            "ON CREATE SET rel.extraction_method = 'system'",
            {"records": records, "col": collection},
        )

        # Query 2: Create all literal metadata (5 per record)
        flat = []
        for r in records:
            uri = r["extraction_uri"]
            for pred, val in [
                ("method", r["method"]),
                ("model", r["model"]),
                ("timestamp", r["timestamp"]),
                ("chunk-text", r["chunk_text"]),
                ("chunk-offset", r["chunk_offset"]),
            ]:
                flat.append({
                    "e_uri": uri,
                    "p_uri": f"nouxcube://predicate/prov/{pred}",
                    "val": val,
                })

        if flat:
            await self._client.execute_cypher(
                "UNWIND $lits AS l "
                "MATCH (e:Node {uri: l.e_uri, collection: $col}) "
                "MERGE (lit:Literal {value: l.val, collection: $col}) "
                "MERGE (e)-[r:Rel {uri: l.p_uri, collection: $col}]->(lit) "
                "ON CREATE SET r.extraction_method = 'system'",
                {"lits": flat, "col": collection},
            )

        return len(records)

    async def store_document_node(
        self,
        document_id: str,
        collection: str,
        title: str,
        file_path: str,
        semantic_type: Optional[str] = None,
    ) -> str:
        """Create a document :Node with standard metadata triples.

        Creates the following triples (all as Literals except core/contained-in):
          core/type        → "document"
          core/label       → title
          core/semantic-type → semantic_type  (if provided)
          core/contained-in → folder URI      (Node, derived from file_path)

        Args:
            document_id:   Unique document identifier.
            collection:    Collection scope.
            title:         Human-readable document title.
            file_path:     File system path (used to derive folder URI).
            semantic_type: Optional semantic type (e.g. "factura", "contrato").

        Returns:
            doc_uri — the canonical URI of the document node.
        """
        import os

        doc_uri = URIBuilder.document(collection, document_id)
        folder_path = os.path.dirname(file_path) or "/"
        folder_uri = URIBuilder.folder(collection, folder_path)

        # Merge the document node itself
        await self.merge_node(doc_uri, collection)

        # core/type → "document" (Literal)
        await self._store_doc_literal_triple(
            doc_uri, "core", "type", "document", collection
        )

        # core/label → title (Literal)
        await self._store_doc_literal_triple(
            doc_uri, "core", "label", title, collection
        )

        # core/semantic-type → semantic_type (Literal, optional)
        if semantic_type:
            await self._store_doc_literal_triple(
                doc_uri, "core", "semantic-type", semantic_type, collection
            )

        # core/contained-in → folder (Node)
        await self.merge_node(folder_uri, collection)
        folder_pred_uri = URIBuilder.predicate("core", "contained-in")
        await self.create_rel(
            subject_uri=doc_uri,
            predicate_uri=folder_pred_uri,
            object_value=folder_uri,
            collection=collection,
            object_is_node=True,
            extraction_method="system",
            source_chunk=None,
            valid_from=None,
            valid_until=None,
        )

        return doc_uri

    async def _store_doc_literal_triple(
        self,
        subject_uri: str,
        ontology: str,
        predicate_name: str,
        value: str,
        collection: str,
    ) -> None:
        """Internal helper: merge Literal and create Rel from an existing Node URI."""
        await self.merge_literal(value, collection)
        predicate_uri = URIBuilder.predicate(ontology, predicate_name)
        await self.create_rel(
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_value=value,
            collection=collection,
            object_is_node=False,
            extraction_method="system",
            source_chunk=None,
            valid_from=None,
            valid_until=None,
        )

    # ------------------------------------------------------------------
    # Cleanup operations
    # ------------------------------------------------------------------

    async def clear_collection(self, collection: str) -> None:
        """DETACH DELETE all nodes and literals for collection scope."""
        query = (
            "MATCH (n) "
            "WHERE (n:Node OR n:Literal) "
            "AND n.collection = $collection "
            "DETACH DELETE n"
        )
        await self._client.execute_cypher(
            query, params={"collection": collection}
        )

    async def clear_scope(self) -> None:
        """DETACH DELETE all nodes and literals in the graph.

        Formerly `clear_tenant`; renamed after tenancy + role-based ACL removal.
        No longer scoped by user — deletes the entire graph.
        """
        query = (
            "MATCH (n) "
            "WHERE (n:Node OR n:Literal) "
            "DETACH DELETE n"
        )
        await self._client.execute_cypher(query, params={})
