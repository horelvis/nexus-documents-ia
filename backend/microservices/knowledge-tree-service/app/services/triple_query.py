"""
TripleQuery — SPO query layer for TrustGraph on FalkorDB.

Provides 8 query patterns over the Node/Literal/Rel graph model,
plus aggregation helpers for stats and LLM context building.

All methods are async and enforce multi-tenant isolation via `user`
and optional `collection` scope.
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.falkordb_client import FalkorDBClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher fragment helpers
# ---------------------------------------------------------------------------

_OBJECT_EXPR = (
    "CASE WHEN o:Node THEN o.uri ELSE o.value END AS object, "
    "CASE WHEN o:Node THEN 'node' ELSE 'literal' END AS object_type"
)


def _col_where(alias: str, collection: Optional[str]) -> str:
    """Return an AND clause for collection filtering in a WHERE context."""
    if collection:
        return f" AND {alias}.collection = $collection"
    return ""


class TripleQuery:
    """SPO query service for TrustGraph on FalkorDB."""

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _row_to_triple(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a raw FalkorDB result row into a canonical triple dict."""
        triple: Dict[str, Any] = {
            "subject": row.get("subject"),
            "predicate": row.get("predicate"),
            "object": row.get("object"),
            "object_type": row.get("object_type", "literal"),
        }
        if "extraction_method" in row:
            triple["extraction_method"] = row["extraction_method"]
        if "source_chunk" in row:
            triple["source_chunk"] = row["source_chunk"]
        return triple

    def _base_params(
        self, user: str, collection: Optional[str], **extra: Any
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"user": user, **extra}
        if collection:
            params["collection"] = collection
        return params

    # ------------------------------------------------------------------
    # 1. by_subject
    # ------------------------------------------------------------------

    async def by_subject(
        self,
        subject_uri: str,
        user: str,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """All triples where subject = subject_uri."""
        col_filter = _col_where("s", collection)
        query = (
            "MATCH (s:Node {uri: $subject_uri, user: $user})"
            "-[r:Rel]->(o) "
            f"WHERE (o:Node OR o:Literal){col_filter} "
            "RETURN s.uri AS subject, r.uri AS predicate, "
            f"{_OBJECT_EXPR}, "
            "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk "
            "LIMIT $limit"
        )
        params = self._base_params(
            user, collection, subject_uri=subject_uri, limit=limit
        )
        rows = await self._client.execute_cypher(query, params=params)
        return [self._row_to_triple(r) for r in rows]

    # ------------------------------------------------------------------
    # 2. by_predicate
    # ------------------------------------------------------------------

    async def by_predicate(
        self,
        predicate_uri: str,
        user: str,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """All triples with the given predicate URI."""
        col_filter = _col_where("s", collection)
        query = (
            "MATCH (s:Node {user: $user})"
            "-[r:Rel {uri: $predicate_uri}]->(o) "
            f"WHERE (o:Node OR o:Literal){col_filter} "
            "RETURN s.uri AS subject, r.uri AS predicate, "
            f"{_OBJECT_EXPR}, "
            "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk "
            "LIMIT $limit"
        )
        params = self._base_params(
            user, collection, predicate_uri=predicate_uri, limit=limit
        )
        rows = await self._client.execute_cypher(query, params=params)
        return [self._row_to_triple(r) for r in rows]

    # ------------------------------------------------------------------
    # 3. by_object_value
    # ------------------------------------------------------------------

    async def by_object_value(
        self,
        value: str,
        user: str,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """All triples pointing to a :Literal with the given value."""
        col_filter_s = _col_where("s", collection)
        col_filter_o = _col_where("o", collection)
        query = (
            "MATCH (s:Node {user: $user})"
            "-[r:Rel]->(o:Literal {value: $value, user: $user}) "
            f"WHERE true{col_filter_s}{col_filter_o} "
            "RETURN s.uri AS subject, r.uri AS predicate, "
            "o.value AS object, 'literal' AS object_type, "
            "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk "
            "LIMIT $limit"
        )
        params = self._base_params(user, collection, value=value, limit=limit)
        rows = await self._client.execute_cypher(query, params=params)
        return [self._row_to_triple(r) for r in rows]

    # ------------------------------------------------------------------
    # 4. by_object_node
    # ------------------------------------------------------------------

    async def by_object_node(
        self,
        object_uri: str,
        user: str,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """All triples pointing to a :Node with the given URI (inbound edges)."""
        col_filter = _col_where("s", collection)
        query = (
            "MATCH (s:Node {user: $user})"
            "-[r:Rel]->(o:Node {uri: $object_uri, user: $user}) "
            f"WHERE true{col_filter} "
            "RETURN s.uri AS subject, r.uri AS predicate, "
            "o.uri AS object, 'node' AS object_type, "
            "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk "
            "LIMIT $limit"
        )
        params = self._base_params(user, collection, object_uri=object_uri, limit=limit)
        rows = await self._client.execute_cypher(query, params=params)
        return [self._row_to_triple(r) for r in rows]

    # ------------------------------------------------------------------
    # 5. by_spo
    # ------------------------------------------------------------------

    async def by_spo(
        self,
        subject_uri: str,
        predicate_uri: str,
        user: str,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Exact S-P-O lookup — returns all matching triples."""
        col_filter = _col_where("s", collection)
        query = (
            "MATCH (s:Node {uri: $subject_uri, user: $user})"
            "-[r:Rel {uri: $predicate_uri}]->(o) "
            f"WHERE (o:Node OR o:Literal){col_filter} "
            "RETURN s.uri AS subject, r.uri AS predicate, "
            f"{_OBJECT_EXPR}, "
            "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk"
        )
        params = self._base_params(
            user, collection, subject_uri=subject_uri, predicate_uri=predicate_uri
        )
        rows = await self._client.execute_cypher(query, params=params)
        return [self._row_to_triple(r) for r in rows]

    # ------------------------------------------------------------------
    # 6. by_subject_predicate (delegates to by_spo)
    # ------------------------------------------------------------------

    async def by_subject_predicate(
        self,
        subject_uri: str,
        predicate_uri: str,
        user: str,
    ) -> List[Dict[str, Any]]:
        """All objects for a given subject + predicate (delegates to by_spo)."""
        return await self.by_spo(subject_uri, predicate_uri, user)

    # ------------------------------------------------------------------
    # 7. by_predicate_object
    # ------------------------------------------------------------------

    async def by_predicate_object(
        self,
        predicate_uri: str,
        object_value: str,
        user: str,
        object_is_node: bool = False,
    ) -> List[Dict[str, Any]]:
        """All subjects that have predicate_uri → object_value."""
        if object_is_node:
            query = (
                "MATCH (s:Node {user: $user})"
                "-[r:Rel {uri: $predicate_uri}]->(o:Node {uri: $object_value, user: $user}) "
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.uri AS object, 'node' AS object_type, "
                "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk"
            )
        else:
            query = (
                "MATCH (s:Node {user: $user})"
                "-[r:Rel {uri: $predicate_uri}]->(o:Literal {value: $object_value, user: $user}) "
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.value AS object, 'literal' AS object_type, "
                "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk"
            )
        params: Dict[str, Any] = {
            "predicate_uri": predicate_uri,
            "object_value": object_value,
            "user": user,
        }
        rows = await self._client.execute_cypher(query, params=params)
        return [self._row_to_triple(r) for r in rows]

    # ------------------------------------------------------------------
    # 8. neighbors
    # ------------------------------------------------------------------

    async def neighbors(
        self,
        uri: str,
        user: str,
        max_hops: int = 2,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """All nodes within max_hops (outgoing + incoming) from uri.

        Returns simplified dicts with the neighbor URI.

        Note: FalkorDB does not support parameterized variable-length path bounds,
        so max_hops is inlined into the query string as a literal integer.
        """
        # max_hops must be inlined — FalkorDB rejects parameterized *1..$n bounds
        query = (
            f"MATCH (start:Node {{uri: $uri, user: $user}})"
            f"-[:Rel*1..{max_hops}]-(neighbor:Node) "
            f"WHERE neighbor.user = $user AND neighbor.uri <> $uri "
            f"WITH DISTINCT neighbor "
            f"RETURN neighbor.uri AS uri "
            f"LIMIT $limit"
        )
        params: Dict[str, Any] = {
            "uri": uri,
            "user": user,
            "limit": limit,
        }
        rows = await self._client.execute_cypher(query, params=params)
        return [{"uri": r.get("uri")} for r in rows if r.get("uri")]

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    async def get_stats(
        self,
        user: str,
        collection: Optional[str] = None,
    ) -> Dict[str, int]:
        """Count nodes, literals, and relationships for user+collection."""
        col_filter = _col_where("n", collection)
        col_filter_s = _col_where("s", collection)

        node_query = (
            f"MATCH (n:Node {{user: $user}}) WHERE true{col_filter} RETURN count(n) AS cnt"
        )
        lit_query = (
            f"MATCH (n:Literal {{user: $user}}) WHERE true{col_filter} RETURN count(n) AS cnt"
        )
        rel_query = (
            "MATCH (s:Node {user: $user})-[r:Rel]->(o) "
            f"WHERE (o:Node OR o:Literal){col_filter_s} "
            "RETURN count(r) AS cnt"
        )

        params: Dict[str, Any] = {"user": user}
        if collection:
            params["collection"] = collection

        node_rows = await self._client.execute_cypher(node_query, params=params)
        lit_rows = await self._client.execute_cypher(lit_query, params=params)
        rel_rows = await self._client.execute_cypher(rel_query, params=params)

        return {
            "nodes": int(node_rows[0]["cnt"]) if node_rows else 0,
            "literals": int(lit_rows[0]["cnt"]) if lit_rows else 0,
            "rels": int(rel_rows[0]["cnt"]) if rel_rows else 0,
        }

    # ------------------------------------------------------------------
    # build_context
    # ------------------------------------------------------------------

    async def build_context(
        self,
        user: str,
        limit: int = 20,
    ) -> str:
        """Build a text context for LLM consumption from the user's graph.

        Returns a markdown-formatted string with:
        - Total entity/literal/relationship counts
        - Entity type breakdown (via core/type predicate)
        - Top entities by connection count
        """
        from app.services.uri_builder import URIBuilder

        type_pred_uri = URIBuilder.predicate("core", "type")
        label_pred_uri = URIBuilder.predicate("core", "label")

        # --- Totals ---
        stats = await self.get_stats(user)
        total_nodes = stats["nodes"]
        total_literals = stats["literals"]
        total_rels = stats["rels"]

        # --- Entity type breakdown ---
        type_query = (
            "MATCH (s:Node {user: $user})"
            "-[r:Rel {uri: $type_pred}]->(o:Literal {user: $user}) "
            "RETURN o.value AS entity_type, count(s) AS cnt "
            "ORDER BY cnt DESC"
        )
        type_rows = await self._client.execute_cypher(
            type_query,
            params={"user": user, "type_pred": type_pred_uri},
        )

        type_parts = [
            f"{r['entity_type']} ({r['cnt']})"
            for r in type_rows
            if r.get("entity_type")
        ]

        # --- Top entities by outgoing connection count ---
        top_query = (
            "MATCH (s:Node {user: $user})-[r:Rel]->(o) "
            "WHERE (o:Node OR o:Literal) "
            "WITH s, count(r) AS conn_count "
            "ORDER BY conn_count DESC "
            "LIMIT $limit "
            "OPTIONAL MATCH (s)-[lr:Rel {uri: $label_pred}]->(lbl:Literal {user: $user}) "
            "RETURN "
            "CASE WHEN lbl IS NOT NULL THEN lbl.value ELSE s.uri END AS display_name, "
            "conn_count"
        )
        top_rows = await self._client.execute_cypher(
            top_query,
            params={
                "user": user,
                "limit": limit,
                "label_pred": label_pred_uri,
            },
        )

        # --- Assemble output ---
        lines: List[str] = [
            "## Knowledge Graph Context",
            f"**Totals:** {total_nodes} entities, {total_literals} values, {total_rels} relationships",
        ]

        if type_parts:
            lines.append(f"**Entity types:** {', '.join(type_parts)}")

        if top_rows:
            lines.append("**Top entities:**")
            for idx, row in enumerate(top_rows, start=1):
                display = row.get("display_name") or "unknown"
                conns = row.get("conn_count", 0)
                lines.append(f"  {idx}. {display} ({conns} connections)")

        return "\n".join(lines)
