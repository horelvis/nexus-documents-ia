"""
TripleStore — Core CRUD layer for TrustGraph on FalkorDB.

Provides atomic operations for Node, Literal, and Rel management.
All methods are async and operate within user+collection scope for
multi-tenant isolation.

Graph model:
  :Node   — named entity or document with a canonical URI
  :Literal — scalar value (string, date, etc.) deduped by (value, user, collection)
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

    async def merge_node(self, uri: str, user: str, collection: str) -> None:
        """MERGE a :Node by URI, setting created_at on first creation.

        Idempotent — safe to call multiple times with the same URI.
        """
        query = (
            "MERGE (n:Node {uri: $uri, user: $user, collection: $collection}) "
            "ON CREATE SET n.created_at = timestamp()"
        )
        await self._client.execute_cypher(
            query,
            params={"uri": uri, "user": user, "collection": collection},
        )

    # ------------------------------------------------------------------
    # Literal operations
    # ------------------------------------------------------------------

    async def merge_chunk_node(
        self,
        chunk_uri: str,
        document_uri: str,
        chunk_offset: int,
        user: str,
        collection: str,
    ) -> None:
        """MERGE a :Chunk node and link it to its parent document.

        The :Chunk node carries only the offset + a timestamp; the actual
        chunk text lives in Weaviate (Nouxcube_documents collection) and
        is resolved on demand via _resolve_chunk_texts on the Emma side.

        The edge uses the reserved predicate `core/of-document` to mark the
        chunk→document hierarchy so graph queries can traverse upward from
        any chunk to its document without URI parsing.

        Idempotent — MERGE on (uri, user, collection).
        """
        await self._client.execute_cypher(
            "MERGE (c:Chunk {uri: $chunk_uri, user: $user, collection: $col}) "
            "ON CREATE SET c.created_at = timestamp(), c.offset = $offset "
            "MERGE (d:Node {uri: $doc_uri, user: $user, collection: $col}) "
            "ON CREATE SET d.created_at = timestamp() "
            "MERGE (c)-[r:Rel {uri: $of_doc_pred, user: $user, collection: $col}]->(d) "
            "ON CREATE SET r.extraction_method = 'structural', r.confidence = 1.0",
            params={
                "chunk_uri": chunk_uri,
                "doc_uri": document_uri,
                "offset": chunk_offset,
                "user": user,
                "col": collection,
                "of_doc_pred": "nouxcube://predicate/core/of-document",
            },
        )

    async def merge_literal(self, value: str, user: str, collection: str) -> None:
        """MERGE a :Literal deduped by (value, user, collection).

        Values are stripped of leading/trailing whitespace before storage
        to prevent "Madrid" vs "Madrid " creating separate nodes.

        Idempotent — multiple calls with the same arguments produce a
        single node in the graph.
        """
        normalized_value = value.strip() if value else value
        query = (
            "MERGE (:Literal {value: $value, user: $user, collection: $collection})"
        )
        await self._client.execute_cypher(
            query,
            params={"value": normalized_value, "user": user, "collection": collection},
        )

    # ------------------------------------------------------------------
    # Relationship operations
    # ------------------------------------------------------------------

    async def create_rel(
        self,
        subject_uri: str,
        predicate_uri: str,
        object_value: str,
        user: str,
        collection: str,
        object_is_node: bool,
        extraction_method: str,
        source_chunk: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> None:
        """MERGE a :Rel edge from subject :Node to object :Node or :Literal.

        Uses MERGE on (subject, predicate_uri, object, user, collection) to
        prevent duplicate edges for the same fact. Additional metadata
        (extraction_method, source_chunk, timestamps) is set on first creation.

        Args:
            subject_uri:       URI of the subject :Node.
            predicate_uri:     URI of the predicate (ontology term).
            object_value:      URI if object_is_node=True, literal value otherwise.
            user:              Tenant/user identifier.
            collection:        Collection scope.
            object_is_node:    True → object is a :Node matched by URI.
                               False → object is a :Literal matched by (value, user, collection).
            extraction_method: How this triple was extracted (e.g. "ner", "llm", "regex").
            source_chunk:      Source chunk ID for provenance.
            valid_from:        ISO date string — temporal validity start.
            valid_until:       ISO date string — temporal validity end.
        """
        if object_is_node:
            query = (
                "MATCH (s:Node {uri: $s_uri, user: $user, collection: $collection}) "
                "MATCH (o:Node {uri: $o_uri, user: $user, collection: $collection}) "
                "MERGE (s)-[r:Rel {uri: $p_uri, user: $user, collection: $collection}]->(o) "
                "ON CREATE SET r.extraction_method = $extraction_method, "
                "r.source_chunk = $source_chunk, "
                "r.valid_from = $valid_from, r.valid_until = $valid_until"
            )
            params = {
                "s_uri": subject_uri,
                "o_uri": object_value,
                "p_uri": predicate_uri,
                "user": user,
                "collection": collection,
                "extraction_method": extraction_method,
                "source_chunk": source_chunk,
                "valid_from": valid_from,
                "valid_until": valid_until,
            }
        else:
            query = (
                "MATCH (s:Node {uri: $s_uri, user: $user, collection: $collection}) "
                "MATCH (o:Literal {value: $o_val, user: $user, collection: $collection}) "
                "MERGE (s)-[r:Rel {uri: $p_uri, user: $user, collection: $collection}]->(o) "
                "ON CREATE SET r.extraction_method = $extraction_method, "
                "r.source_chunk = $source_chunk, "
                "r.valid_from = $valid_from, r.valid_until = $valid_until"
            )
            params = {
                "s_uri": subject_uri,
                "o_val": object_value,
                "p_uri": predicate_uri,
                "user": user,
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
        user: str,
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
            user:              Tenant/user identifier.
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
        await self.merge_node(subject_uri, user, collection)

        # Merge object and resolve value for create_rel
        if object_is_node:
            object_uri = URIBuilder.entity(collection, object_value)
            await self.merge_node(object_uri, user, collection)
            rel_object_value = object_uri
        else:
            stripped_value = object_value.strip() if object_value else object_value
            await self.merge_literal(stripped_value, user, collection)
            rel_object_value = stripped_value

        # Create relationship
        await self.create_rel(
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_value=rel_object_value,
            user=user,
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
        self, triples: list, user: str, collection: str
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
                "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "MERGE (o:Node {uri: t.o_uri, user: $user, collection: $col}) "
                "ON CREATE SET o.created_at = timestamp() "
                "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
                {"triples": node_triples, "user": user, "col": collection},
            )
            stored += len(node_triples)

        # Unique-per-entity literals: skip if a Rel with this predicate already
        # exists from the subject to any Literal (cross-chunk dedup).
        if unique_lits:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "WITH s, t "
                "OPTIONAL MATCH (s)-[ex:Rel {uri: t.p_uri, user: $user, collection: $col}]->(:Literal) "
                "WITH s, t, ex WHERE ex IS NULL "
                "MERGE (o:Literal {value: t.o_val, user: $user, collection: $col}) "
                "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
                {"triples": unique_lits, "user": user, "col": collection},
            )
            stored += len(unique_lits)

        if regular_lits:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "MERGE (o:Literal {value: t.o_val, user: $user, collection: $col}) "
                "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
                {"triples": regular_lits, "user": user, "col": collection},
            )
            stored += len(regular_lits)

        return stored

    async def batch_store_provenance(
        self, records: list, user: str, collection: str
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
            "MERGE (e:Node {uri: r.extraction_uri, user: $user, collection: $col}) "
            "ON CREATE SET e.created_at = timestamp() "
            "WITH e, r "
            "MATCH (d:Node {uri: r.document_uri, user: $user, collection: $col}) "
            "MERGE (e)-[rel:Rel {uri: r.derived_from_uri, user: $user, collection: $col}]->(d) "
            "ON CREATE SET rel.extraction_method = 'system'",
            {"records": records, "user": user, "col": collection},
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
                "MATCH (e:Node {uri: l.e_uri, user: $user, collection: $col}) "
                "MERGE (lit:Literal {value: l.val, user: $user, collection: $col}) "
                "MERGE (e)-[r:Rel {uri: l.p_uri, user: $user, collection: $col}]->(lit) "
                "ON CREATE SET r.extraction_method = 'system'",
                {"lits": flat, "user": user, "col": collection},
            )

        return len(records)

    async def store_document_node(
        self,
        document_id: str,
        user: str,
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
            user:          Tenant/user identifier.
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
        await self.merge_node(doc_uri, user, collection)

        # core/type → "document" (Literal)
        await self._store_doc_literal_triple(
            doc_uri, "core", "type", "document", user, collection
        )

        # core/label → title (Literal)
        await self._store_doc_literal_triple(
            doc_uri, "core", "label", title, user, collection
        )

        # core/semantic-type → semantic_type (Literal, optional)
        if semantic_type:
            await self._store_doc_literal_triple(
                doc_uri, "core", "semantic-type", semantic_type, user, collection
            )

        # core/contained-in → folder (Node)
        await self.merge_node(folder_uri, user, collection)
        folder_pred_uri = URIBuilder.predicate("core", "contained-in")
        await self.create_rel(
            subject_uri=doc_uri,
            predicate_uri=folder_pred_uri,
            object_value=folder_uri,
            user=user,
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
        user: str,
        collection: str,
    ) -> None:
        """Internal helper: merge Literal and create Rel from an existing Node URI."""
        await self.merge_literal(value, user, collection)
        predicate_uri = URIBuilder.predicate(ontology, predicate_name)
        await self.create_rel(
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_value=value,
            user=user,
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

    async def clear_collection(self, user: str, collection: str) -> None:
        """DETACH DELETE all nodes and literals for user+collection scope."""
        query = (
            "MATCH (n) "
            "WHERE (n:Node OR n:Literal) "
            "AND n.user = $user AND n.collection = $collection "
            "DETACH DELETE n"
        )
        await self._client.execute_cypher(
            query, params={"user": user, "collection": collection}
        )

    async def clear_tenant(self, user: str) -> None:
        """DETACH DELETE all nodes and literals for a given user/tenant."""
        query = (
            "MATCH (n) "
            "WHERE (n:Node OR n:Literal) AND n.user = $user "
            "DETACH DELETE n"
        )
        await self._client.execute_cypher(query, params={"user": user})
