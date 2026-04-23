"""Entity resolution for person nodes.

The 4 LLM extractors often emit slightly different labels for the same
real-world person ('Juan Pérez', 'Juan P.', 'J. Pérez', …). Each label
produces a distinct URI slug via URIBuilder.normalize_name, so the graph
ends up with multiple nodes representing one individual.

This module clusters duplicates via an LLM call (prompt
`trustgraph_entity_resolution_persons`) and MERGEs them: all incoming
and outgoing `:Rel` edges of each duplicate are repointed to the cluster's
canonical URI, then the duplicate `:Node` is deleted.

Only person entities are in scope (filtered by the `core/type → "person"`
relationship). Other entity types can be added by parameterizing the type
filter.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import os

import httpx

from app.core.config import settings
from app.services.falkordb_client import FalkorDBClient

logger = logging.getLogger(__name__)


class EntityResolver:
    """LLM-based clusterer + merger for duplicate person entities."""

    PROMPT_NAME = "trustgraph_entity_resolution_persons"
    TYPE_PREDICATE_URI = "nouxcube://predicate/core/type"
    LABEL_PREDICATE_URI = "nouxcube://predicate/core/label"

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client
        self._langfuse_prompt: Optional[str] = None
        self._sglang_url = getattr(
            settings,
            "SGLANG_BASE_URL",
            os.getenv("SGLANG_BASE_URL", "http://sglang:8000/v1"),
        ).rstrip("/")
        self._model = getattr(
            settings,
            "SGLANG_MODEL",
            os.getenv("SGLANG_MODEL", "Qwen/Qwen3-8B"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve_persons(
        self,
        user: str,
        collection: str,
    ) -> Dict[str, Any]:
        """Cluster duplicate person URIs in a collection and merge each cluster.

        Runs in two phases:
            1. Deterministic pre-dedup: prefix + small-edit-distance matches
               on slugs catch obvious truncations and typos without an LLM
               round-trip (e.g. 'horelvi' ⊂ 'horelvis').
            2. LLM semantic clustering on whatever remains: honorifics, name
               order, abbreviations that no heuristic would confidently merge.

        Returns a summary dict with counts of clusters found, nodes merged,
        and edges repointed.
        """
        persons = await self._fetch_persons(user=user, collection=collection)
        if len(persons) < 2:
            return {
                "persons_scanned": len(persons),
                "clusters_merged": 0,
                "nodes_removed": 0,
                "edges_repointed": 0,
            }

        # Phase 1 — deterministic pre-dedup
        heuristic_clusters, remaining = self._heuristic_cluster(persons)

        # Phase 2 — LLM handles what the heuristic didn't touch
        llm_clusters: List[Dict[str, Any]] = []
        if len(remaining) >= 2:
            llm_clusters = await self._cluster_via_llm(remaining)

        all_clusters = heuristic_clusters + llm_clusters
        total_edges_repointed = 0
        total_nodes_removed = 0

        for cluster in all_clusters:
            canonical_uri = cluster.get("canonical_uri", "").strip()
            member_uris = [
                m.strip() for m in cluster.get("member_uris", []) if m and isinstance(m, str)
            ]
            if not canonical_uri or not member_uris:
                continue

            duplicates = [u for u in member_uris if u != canonical_uri]
            if not duplicates:
                continue

            for dup_uri in duplicates:
                repointed = await self._merge_node(
                    duplicate_uri=dup_uri,
                    canonical_uri=canonical_uri,
                    user=user,
                    collection=collection,
                )
                total_edges_repointed += repointed
                total_nodes_removed += 1
                logger.info(
                    "EntityResolver: merged %s → %s (%d edges repointed)",
                    dup_uri,
                    canonical_uri,
                    repointed,
                )

        return {
            "persons_scanned": len(persons),
            "heuristic_clusters": len(heuristic_clusters),
            "llm_clusters": len(llm_clusters),
            "clusters_merged": sum(
                1 for c in all_clusters
                if len(c.get("member_uris", [])) > 1
            ),
            "nodes_removed": total_nodes_removed,
            "edges_repointed": total_edges_repointed,
        }

    # ------------------------------------------------------------------
    # Internals — deterministic heuristics
    # ------------------------------------------------------------------

    _HEURISTIC_MIN_LEN = 4  # minimum slug length to apply prefix/edit-distance rules
    _MAX_EDIT_DIST = 2      # maximum Levenshtein distance for fuzzy match

    @staticmethod
    def _slug_from_uri(uri: str) -> str:
        """Extract the trailing slug from a nouxcube entity URI."""
        return uri.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Classic DP Levenshtein distance. O(len(a)*len(b))."""
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            curr = [i] + [0] * len(b)
            for j, cb in enumerate(b, 1):
                curr[j] = min(
                    curr[j - 1] + 1,
                    prev[j] + 1,
                    prev[j - 1] + (0 if ca == cb else 1),
                )
            prev = curr
        return prev[-1]

    @classmethod
    def _same_person_heuristic(cls, slug_a: str, slug_b: str) -> bool:
        """True if slug_a and slug_b almost certainly represent the same person.

        Rules (either one sufficient):
          - One slug is a prefix of the other, and the shorter is ≥ 4 chars.
            Catches truncations: 'horelvi' ⊂ 'horelvis',
            'horelvis-c' ⊂ 'horelvis-c-35-88'.
          - Levenshtein distance ≤ 2 AND both ≥ 4 chars. Catches typos:
            'horelvis' ~ 'horelviz' (1 edit).
        """
        if slug_a == slug_b:
            return True
        short, long = (slug_a, slug_b) if len(slug_a) <= len(slug_b) else (slug_b, slug_a)
        if len(short) < cls._HEURISTIC_MIN_LEN:
            return False
        if long.startswith(short + "-") or long == short:
            return True
        if cls._levenshtein(slug_a, slug_b) <= cls._MAX_EDIT_DIST:
            return True
        return False

    @classmethod
    def _heuristic_cluster(
        cls,
        persons: List[Dict[str, str]],
    ) -> tuple:
        """Union-find over persons using `_same_person_heuristic` on slugs.

        Returns (clusters, remaining) where clusters is the usual LLM-shape
        list of {canonical_uri, canonical_label, member_uris} for each
        non-singleton cluster the heuristic built, and remaining is the
        singletons that still need LLM review.
        """
        n = len(persons)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        slugs = [cls._slug_from_uri(p["uri"]) for p in persons]
        for i in range(n):
            for j in range(i + 1, n):
                if cls._same_person_heuristic(slugs[i], slugs[j]):
                    union(i, j)

        groups: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        clusters: List[Dict[str, Any]] = []
        remaining: List[Dict[str, str]] = []
        for members in groups.values():
            if len(members) == 1:
                remaining.append(persons[members[0]])
                continue
            # Canonical = longest label; break ties by longest slug
            members_sorted = sorted(
                members,
                key=lambda idx: (
                    -len(persons[idx].get("label") or ""),
                    -len(slugs[idx]),
                ),
            )
            canonical_idx = members_sorted[0]
            clusters.append({
                "canonical_uri": persons[canonical_idx]["uri"],
                "canonical_label": persons[canonical_idx].get("label", ""),
                "member_uris": [persons[idx]["uri"] for idx in members],
            })
        return clusters, remaining

    # ------------------------------------------------------------------
    # Internals — fetch + LLM
    # ------------------------------------------------------------------

    async def _fetch_persons(
        self, user: str, collection: str,
    ) -> List[Dict[str, str]]:
        """Return all person nodes in the collection as [{uri, label}]."""
        query = (
            "MATCH (n:Node)-[rt:Rel {uri: $type_pred}]->(t:Literal) "
            "WHERE n.user = $user AND n.collection = $collection "
            "  AND t.value = 'person' "
            "OPTIONAL MATCH (n)-[rl:Rel {uri: $label_pred}]->(lab:Literal) "
            "RETURN n.uri AS uri, collect(lab.value)[0] AS label"
        )
        params = {
            "user": user,
            "collection": collection,
            "type_pred": self.TYPE_PREDICATE_URI,
            "label_pred": self.LABEL_PREDICATE_URI,
        }
        rows = await self._client.execute_cypher(query, params=params)
        persons: List[Dict[str, str]] = []
        for row in rows or []:
            uri = row.get("uri")
            if not uri:
                continue
            label = row.get("label") or self._fallback_label(uri)
            persons.append({"uri": uri, "label": str(label)})
        return persons

    @staticmethod
    def _fallback_label(uri: str) -> str:
        tail = uri.rstrip("/").rsplit("/", 1)[-1]
        return tail.replace("-", " ").title() if tail else uri

    async def _cluster_via_llm(
        self, persons: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Ask the LLM to cluster duplicates. Returns the clusters list."""
        prompt_template = self._get_prompt()
        persons_json = json.dumps(persons, ensure_ascii=False)
        prompt = prompt_template.replace("{{persons_json}}", persons_json)

        raw = await self._call_llm(prompt)
        return self._parse_clusters(raw)

    def _get_prompt(self) -> str:
        if self._langfuse_prompt is not None:
            return self._langfuse_prompt
        try:
            from app.services.langfuse_client import get_langfuse  # type: ignore

            langfuse = get_langfuse()
            prompt_obj = langfuse.get_prompt(self.PROMPT_NAME, label="production")
            self._langfuse_prompt = prompt_obj.compile()
            return self._langfuse_prompt
        except Exception as exc:
            logger.warning(
                "EntityResolver: Langfuse prompt '%s' unavailable (%s), falling back to inline prompt",
                self.PROMPT_NAME,
                exc,
            )
            # Minimal inline fallback keeps the service functional in degraded
            # mode. Real content belongs in Langfuse (see
            # scripts/seed_entity_resolution_prompt.py).
            return (
                "Agrupa las personas duplicadas (misma persona con labels distintos). "
                "Solo agrupa si estás seguro. Responde JSON: "
                '{"clusters": [{"canonical_uri": "...", "canonical_label": "...", '
                '"member_uris": ["...", "..."]}]}\n\n{{persons_json}}'
            )

    async def _call_llm(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._sglang_url}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning_content", "")
        return content or ""

    def _parse_clusters(self, raw: str) -> List[Dict[str, Any]]:
        """Strip markdown fences + parse. Accept both {clusters:[...]} and bare list."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip()).strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("EntityResolver: LLM response not valid JSON: %s", exc)
            return []
        if isinstance(parsed, dict):
            return parsed.get("clusters", []) or []
        if isinstance(parsed, list):
            return parsed
        return []

    # ------------------------------------------------------------------
    # Internals — graph merge
    # ------------------------------------------------------------------

    async def _merge_node(
        self,
        duplicate_uri: str,
        canonical_uri: str,
        user: str,
        collection: str,
    ) -> int:
        """Repoint every :Rel of `duplicate_uri` to `canonical_uri` and delete the node.

        Returns the number of edges repointed (incoming + outgoing).
        """
        # Ensure the canonical node exists — may not if the LLM picked one that
        # was never the duplicate target.
        await self._client.execute_cypher(
            "MERGE (n:Node {uri: $uri, user: $user, collection: $collection}) "
            "ON CREATE SET n.created_at = timestamp()",
            params={"uri": canonical_uri, "user": user, "collection": collection},
        )

        # Repoint outgoing edges (duplicate)-[r]->(target)
        # Use two-step: CREATE new edges, then delete old ones. FalkorDB does
        # not support setting relationship properties from another rel in one
        # statement, so we copy the predicate URI + key metadata explicitly.
        outgoing_q = (
            "MATCH (d:Node {uri: $dup, user: $user, collection: $collection})"
            "-[r:Rel]->(t) "
            "MATCH (c:Node {uri: $can, user: $user, collection: $collection}) "
            "CREATE (c)-[r2:Rel]->(t) "
            "SET r2.uri = r.uri, r2.method = r.method, r2.source_chunk = r.source_chunk, "
            "    r2.confidence = r.confidence, r2.user = r.user, r2.collection = r.collection "
            "DELETE r "
            "RETURN count(r2) AS repointed"
        )
        out_rows = await self._client.execute_cypher(
            outgoing_q,
            params={
                "dup": duplicate_uri,
                "can": canonical_uri,
                "user": user,
                "collection": collection,
            },
        )
        out_count = (out_rows[0].get("repointed") if out_rows else 0) or 0

        # Repoint incoming edges (src)-[r]->(duplicate)
        incoming_q = (
            "MATCH (s)-[r:Rel]->(d:Node {uri: $dup, user: $user, collection: $collection}) "
            "MATCH (c:Node {uri: $can, user: $user, collection: $collection}) "
            "CREATE (s)-[r2:Rel]->(c) "
            "SET r2.uri = r.uri, r2.method = r.method, r2.source_chunk = r.source_chunk, "
            "    r2.confidence = r.confidence, r2.user = r.user, r2.collection = r.collection "
            "DELETE r "
            "RETURN count(r2) AS repointed"
        )
        in_rows = await self._client.execute_cypher(
            incoming_q,
            params={
                "dup": duplicate_uri,
                "can": canonical_uri,
                "user": user,
                "collection": collection,
            },
        )
        in_count = (in_rows[0].get("repointed") if in_rows else 0) or 0

        # Delete the now-orphan duplicate node
        await self._client.execute_cypher(
            "MATCH (d:Node {uri: $dup, user: $user, collection: $collection}) DELETE d",
            params={"dup": duplicate_uri, "user": user, "collection": collection},
        )

        return int(out_count) + int(in_count)
