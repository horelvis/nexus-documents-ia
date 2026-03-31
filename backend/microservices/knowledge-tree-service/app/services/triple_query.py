"""
TripleQuery — SPO query layer for TrustGraph on FalkorDB.

Provides 8 query patterns over the Node/Literal/Rel graph model,
plus aggregation helpers for stats and LLM context building.

All methods are async and enforce multi-tenant isolation via `user`
and optional `collection` scope.
"""

import logging
import re
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
        if "confidence" in row and row["confidence"] is not None:
            triple["confidence"] = row["confidence"]
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
    # batch_neighbors  (BFS subgraph traversal)
    # ------------------------------------------------------------------

    async def batch_neighbors(
        self,
        seed_uris: List[str],
        user: str,
        collection: Optional[str] = None,
        max_hops: int = 2,
        max_edges: int = 150,
        exclude_predicates: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """BFS subgraph traversal starting from seed_uris.

        At each hop, queries all frontier nodes in a single UNWIND query.
        Only Node→Node edges are traversed (Literal leaves are excluded).
        Predicates matching any pattern in exclude_predicates (regex) are
        dropped.  ``core/label`` predicates are always skipped as they are
        resolved separately.

        Returns a dict with:
          - edges: list of canonical triple dicts (subject, predicate,
                   object, object_type, extraction_method, source_chunk)
          - entities_visited: number of unique node URIs expanded
          - hops_used: number of BFS rounds actually executed
        """
        if not seed_uris:
            return {"edges": [], "entities_visited": 0, "hops_used": 0}

        # Compile exclude patterns once
        _exclude_compiled: List[re.Pattern] = []
        for pat in (exclude_predicates or []):
            try:
                _exclude_compiled.append(re.compile(pat))
            except re.error:
                logger.warning("batch_neighbors: invalid exclude pattern %r", pat)

        # Always skip core/label — resolved separately
        _LABEL_SUFFIX = "/core/label"

        def _is_excluded(predicate_uri: str) -> bool:
            if predicate_uri and predicate_uri.endswith(_LABEL_SUFFIX):
                return True
            for pat in _exclude_compiled:
                if pat.search(predicate_uri or ""):
                    return True
            return False

        col_filter = _col_where("s", collection)

        all_edges: List[Dict[str, Any]] = []
        visited: set = set(seed_uris)
        frontier: List[str] = list(seed_uris)
        hops_used = 0

        for _hop in range(max_hops):
            if not frontier:
                break
            if len(all_edges) >= max_edges:
                break

            # Single UNWIND query for the entire frontier.
            # Bidirectional: capture both outgoing (s→o) and incoming (o→s)
            # Node→Node edges so hub entities that are mostly targets are
            # reachable too.
            query = (
                "UNWIND $frontier AS seed_uri "
                "MATCH (s:Node {user: $user})"
                "-[r:Rel]-(o:Node {user: $user}) "
                f"WHERE (s.uri = seed_uri OR o.uri = seed_uri){col_filter} "
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.uri AS object, 'node' AS object_type, "
                "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk, "
                "r.confidence AS confidence "
                "LIMIT $query_limit"
            )
            # Safety limit: allow headroom for post-query predicate filtering
            query_limit = max_edges * 3
            params = self._base_params(user, collection, frontier=frontier, query_limit=query_limit)
            rows = await self._client.execute_cypher(query, params=params)

            new_frontier: List[str] = []
            hop_had_results = False

            for row in rows:
                if len(all_edges) >= max_edges:
                    break
                predicate = row.get("predicate") or ""
                if _is_excluded(predicate):
                    continue
                triple = self._row_to_triple(row)
                all_edges.append(triple)
                hop_had_results = True

                # Bidirectional: expand frontier from both sides of the edge
                subj_uri = row.get("subject")
                obj_uri = row.get("object")
                for uri in (subj_uri, obj_uri):
                    if uri and uri not in visited:
                        visited.add(uri)
                        new_frontier.append(uri)

            if hop_had_results:
                hops_used += 1

            frontier = new_frontier

        # Fetch Node→Literal properties for all visited entities.
        # Two passes: (1) essential props for every entity (label, type, def)
        # and (2) remaining literals with a cap.
        all_entity_uris = list(visited)
        if all_entity_uris:
            # Pass 1: Essential properties (no limit — one per entity per pred)
            essential_query = (
                "UNWIND $uris AS entity_uri "
                "MATCH (s:Node {uri: entity_uri, user: $user})"
                "-[r:Rel]->(o:Literal) "
                "WHERE r.uri ENDS WITH '/core/label' "
                "   OR r.uri ENDS WITH '/core/type' "
                "   OR r.uri ENDS WITH '/core/definition' "
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.value AS object, 'literal' AS object_type, "
                "r.extraction_method AS extraction_method, "
                "r.source_chunk AS source_chunk"
            )
            essential_params = self._base_params(user, collection, uris=all_entity_uris)
            essential_rows = await self._client.execute_cypher(essential_query, params=essential_params)
            for row in essential_rows:
                all_edges.append(self._row_to_triple(row))

            # Pass 2: Other literals (capped)
            other_query = (
                "UNWIND $uris AS entity_uri "
                "MATCH (s:Node {uri: entity_uri, user: $user})"
                "-[r:Rel]->(o:Literal) "
                "WHERE NOT (r.uri ENDS WITH '/core/label' "
                "        OR r.uri ENDS WITH '/core/type' "
                "        OR r.uri ENDS WITH '/core/definition') "
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.value AS object, 'literal' AS object_type, "
                "r.extraction_method AS extraction_method, "
                "r.source_chunk AS source_chunk "
                "LIMIT $lit_limit"
            )
            other_params = self._base_params(
                user, collection, uris=all_entity_uris, lit_limit=len(all_entity_uris) * 5
            )
            other_rows = await self._client.execute_cypher(other_query, params=other_params)
            for row in other_rows:
                predicate = row.get("predicate") or ""
                skip = False
                for pat in _exclude_compiled:
                    if pat.search(predicate or ""):
                        skip = True
                        break
                if skip:
                    continue
                all_edges.append(self._row_to_triple(row))

        return {
            "edges": all_edges,
            "entities_visited": len(visited) - len(seed_uris),
            "hops_used": hops_used,
        }

    # ------------------------------------------------------------------
    # trace_sources
    # ------------------------------------------------------------------

    async def trace_sources(
        self,
        edges: List[Dict[str, str]],
        user: str,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Trace edges back to their source document chunks.

        For each edge, queries the :Rel for source_chunk and confidence,
        parses the source_chunk URI to extract document_id and chunk_offset.
        """
        if not edges:
            return []

        col_filter = _col_where("r", collection)
        results = []

        for edge in edges:
            s_uri = edge.get("subject_uri", "")
            p_uri = edge.get("predicate_uri", "")
            o_uri = edge.get("object_uri", "")

            if not s_uri or not p_uri:
                continue

            query = (
                "MATCH (s:Node {uri: $s_uri, user: $user})"
                "-[r:Rel {uri: $p_uri}]->"
                "(o {user: $user}) "
                f"WHERE (o.uri = $o_uri OR o.value = $o_uri){col_filter} "
                "RETURN r.source_chunk AS source_chunk, r.confidence AS confidence "
                "LIMIT 1"
            )
            params = {"s_uri": s_uri, "p_uri": p_uri, "o_uri": o_uri, "user": user}
            if collection:
                params["collection"] = collection

            rows = await self._client.execute_cypher(query, params=params)
            if not rows:
                continue

            source_chunk = rows[0].get("source_chunk") or ""
            confidence = rows[0].get("confidence")

            doc_id = ""
            chunk_offset = 0
            if source_chunk and "#offset=" in source_chunk:
                doc_part = source_chunk.split("#")[0]
                doc_id = doc_part.rsplit("/", 1)[-1] if "/" in doc_part else ""
                try:
                    chunk_offset = int(source_chunk.split("offset=")[-1])
                except ValueError:
                    chunk_offset = 0

            if doc_id:
                results.append({
                    "subject_uri": s_uri,
                    "predicate_uri": p_uri,
                    "object_uri": o_uri,
                    "document_id": doc_id,
                    "chunk_offset": chunk_offset,
                    "confidence": confidence,
                    "source_chunk": source_chunk,
                })

        return results

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
