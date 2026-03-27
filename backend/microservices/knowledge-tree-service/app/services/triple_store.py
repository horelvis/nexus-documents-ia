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

    async def merge_literal(self, value: str, user: str, collection: str) -> None:
        """MERGE a :Literal deduped by (value, user, collection).

        Idempotent — multiple calls with the same arguments produce a
        single node in the graph.
        """
        query = (
            "MERGE (:Literal {value: $value, user: $user, collection: $collection})"
        )
        await self._client.execute_cypher(
            query,
            params={"value": value, "user": user, "collection": collection},
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
        """CREATE a :Rel edge from subject :Node to object :Node or :Literal.

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
        rel_props = {
            "uri": predicate_uri,
            "user": user,
            "collection": collection,
            "extraction_method": extraction_method,
            "source_chunk": source_chunk,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }

        if object_is_node:
            query = (
                "MATCH (s:Node {uri: $s_uri, user: $user, collection: $collection}) "
                "MATCH (o:Node {uri: $o_uri, user: $user, collection: $collection}) "
                "CREATE (s)-[:Rel {uri: $p_uri, user: $user, collection: $collection, "
                "extraction_method: $extraction_method, source_chunk: $source_chunk, "
                "valid_from: $valid_from, valid_until: $valid_until}]->(o)"
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
                "CREATE (s)-[:Rel {uri: $p_uri, user: $user, collection: $collection, "
                "extraction_method: $extraction_method, source_chunk: $source_chunk, "
                "valid_from: $valid_from, valid_until: $valid_until}]->(o)"
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
            await self.merge_literal(object_value, user, collection)
            rel_object_value = object_value

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

    async def store_document_node(
        self,
        document_id: str,
        user: str,
        collection: str,
        title: str,
        file_path: str,
        semantic_type: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> str:
        """Create a document :Node with standard metadata triples.

        Creates the following triples (all as Literals except core/contained-in):
          core/type        → "document"
          core/label       → title
          core/semantic-type → semantic_type  (if provided)
          core/domain      → domain           (if provided)
          core/contained-in → folder URI      (Node, derived from file_path)

        Args:
            document_id:   Unique document identifier.
            user:          Tenant/user identifier.
            collection:    Collection scope.
            title:         Human-readable document title.
            file_path:     File system path (used to derive folder URI).
            semantic_type: Optional semantic type (e.g. "factura", "contrato").
            domain:        Optional business domain (e.g. "legal", "fiscal").

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

        # core/domain → domain (Literal, optional)
        if domain:
            await self._store_doc_literal_triple(
                doc_uri, "core", "domain", domain, user, collection
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
