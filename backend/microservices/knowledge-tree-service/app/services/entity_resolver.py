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
    """LLM-based clusterer + merger for duplicate entity nodes.

    Originally for persons; now parameterized over entity type. Supported
    types have both a heuristic tuning profile and a Langfuse prompt.
    Types not in SUPPORTED_TYPES (e.g. 'amount', 'date', 'other') are
    either not suitable for clustering (amounts are distinct values) or
    need a different approach (dates need canonical-format normalization,
    not clustering).
    """

    TYPE_PREDICATE_URI = "nouxcube://predicate/core/type"
    LABEL_PREDICATE_URI = "nouxcube://predicate/core/label"

    # Type-specific config: Langfuse prompt name + heuristic parameters.
    # min_len is the minimum slug length to apply prefix/edit-distance rules
    # (shorter labels like "NY" can't be reliably deduped by heuristic).
    # max_edit_dist caps fuzzy matching — tighter for types where short
    # string variations more often indicate distinct entities.
    # `stop_slugs` are single-token slugs that must NOT be used as the
    # "short" side of a prefix match. Guards against generic place words
    # fusing unrelated street names (e.g. 'calle' ⊂ 'calle-azarbe' and
    # 'calle' ⊂ 'calle-compos' would transitively merge Azarbe with
    # Compostela under union-find — a clear false positive).
    SUPPORTED_TYPES: Dict[str, Dict[str, Any]] = {
        "person": {
            "prompt": "trustgraph_entity_resolution_persons",
            "min_len": 4,
            "max_edit_dist": 2,
            "stop_slugs": set(),
        },
        "organization": {
            "prompt": "trustgraph_entity_resolution_organizations",
            "min_len": 4,
            "max_edit_dist": 2,
            "stop_slugs": {"banco", "empresa", "grupo", "sociedad"},
        },
        "place": {
            "prompt": "trustgraph_entity_resolution_places",
            "min_len": 5,
            "max_edit_dist": 1,
            "stop_slugs": {
                "calle", "avenida", "avda", "plaza", "paseo",
                "carretera", "crta", "ctra", "camino", "ronda",
                "pasaje", "pza", "urbanizacion", "urb",
            },
        },
    }

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

    async def resolve_entities_of_type(
        self,
        collection: str,
        entity_type: str,
    ) -> Dict[str, Any]:
        """Cluster duplicate entity URIs of a given type and merge each cluster.

        Runs in two phases:
            1. Deterministic pre-dedup: prefix + small-edit-distance matches
               on slugs catch obvious truncations and typos without an LLM
               round-trip (e.g. 'horelvi' ⊂ 'horelvis', 'imovistar-plus' vs
               'mimovistar-plus').
            2. LLM semantic clustering on whatever remains: honorifics,
               corporate suffixes, brand aliases, abbreviations that no
               heuristic would confidently merge.

        Returns a summary dict with counts of clusters found, nodes merged,
        and edges repointed.
        """
        config = self.SUPPORTED_TYPES.get(entity_type)
        if not config:
            return {
                "entity_type": entity_type,
                "error": "unsupported entity type",
                "supported": list(self.SUPPORTED_TYPES.keys()),
            }

        entities = await self._fetch_entities(
            collection=collection, entity_type=entity_type,
        )
        if len(entities) < 2:
            return {
                "entity_type": entity_type,
                "entities_scanned": len(entities),
                "clusters_merged": 0,
                "nodes_removed": 0,
                "edges_repointed": 0,
            }

        # Phase 1 — deterministic pre-dedup (type-specific thresholds)
        heuristic_clusters, remaining = self._heuristic_cluster(
            entities,
            min_len=config["min_len"],
            max_edit_dist=config["max_edit_dist"],
            stop_slugs=config.get("stop_slugs"),
        )

        # Phase 2 — LLM handles what the heuristic didn't touch
        llm_clusters: List[Dict[str, Any]] = []
        if len(remaining) >= 2:
            llm_clusters = await self._cluster_via_llm(
                remaining, prompt_name=config["prompt"],
            )

        all_clusters = heuristic_clusters + llm_clusters

        # Type-specific safety net. For places, two labels with mismatched
        # numeric tokens (street numbers) almost certainly point at distinct
        # addresses even when slug similarity or the LLM grouped them.
        if entity_type == "place":
            uri_to_label = {e["uri"]: e.get("label", "") for e in entities}
            all_clusters = self._reject_distinct_numeric_members(
                all_clusters, uri_to_label,
            )

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
                    collection=collection,
                )
                total_edges_repointed += repointed
                total_nodes_removed += 1
                logger.info(
                    "EntityResolver[%s]: merged %s → %s (%d edges repointed)",
                    entity_type,
                    dup_uri,
                    canonical_uri,
                    repointed,
                )

        return {
            "entity_type": entity_type,
            "entities_scanned": len(entities),
            "heuristic_clusters": len(heuristic_clusters),
            "llm_clusters": len(llm_clusters),
            "clusters_merged": sum(
                1 for c in all_clusters
                if len(c.get("member_uris", [])) > 1
            ),
            "nodes_removed": total_nodes_removed,
            "edges_repointed": total_edges_repointed,
        }

    async def resolve_persons(
        self, collection: str,
    ) -> Dict[str, Any]:
        """Backward-compat alias. Resolves 'person' entities."""
        result = await self.resolve_entities_of_type(
            collection=collection, entity_type="person",
        )
        # Preserve old key for any external caller that parses the JSON.
        if "entities_scanned" in result:
            result["persons_scanned"] = result["entities_scanned"]
        return result

    async def resolve_all_supported(
        self, collection: str,
    ) -> Dict[str, Any]:
        """Resolve every supported entity type. Returns per-type summaries."""
        results: Dict[str, Any] = {}
        for entity_type in self.SUPPORTED_TYPES.keys():
            results[entity_type] = await self.resolve_entities_of_type(
                collection=collection, entity_type=entity_type,
            )
        return results

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
    def _slugs_same_entity(
        cls,
        slug_a: str,
        slug_b: str,
        min_len: int,
        max_edit_dist: int,
        stop_slugs: Optional[set] = None,
    ) -> bool:
        """True if two slugs almost certainly represent the same entity.

        Rules (either one sufficient):
          - One slug is a prefix of the other at a `-` boundary and the
            shorter is ≥ min_len AND the shorter is not in `stop_slugs`.
            Catches truncations: 'horelvis' ⊂ 'horelvis-c-35-88'. Rejects
            generic prefixes: 'calle' ⊄ 'calle-azarbe' (because 'calle' is
            a place stop-slug).
          - Levenshtein distance ≤ max_edit_dist AND both ≥ min_len.
            Catches typos: 'horelvi' ~ 'horelvis' (1 edit).
        """
        if slug_a == slug_b:
            return True
        short, long = (slug_a, slug_b) if len(slug_a) <= len(slug_b) else (slug_b, slug_a)
        if len(short) < min_len:
            return False
        # Prefix rule — guarded by stop_slugs so generic words can't fuse
        # unrelated entities under union-find transitivity.
        if long.startswith(short + "-"):
            if stop_slugs and short in stop_slugs:
                return False
            return True
        if long == short:
            return True
        if cls._levenshtein(slug_a, slug_b) <= max_edit_dist:
            return True
        return False

    @classmethod
    def _heuristic_cluster(
        cls,
        entities: List[Dict[str, str]],
        min_len: int = _HEURISTIC_MIN_LEN,
        max_edit_dist: int = _MAX_EDIT_DIST,
        stop_slugs: Optional[set] = None,
    ) -> tuple:
        """Union-find over entities using the slug heuristic.

        Returns (clusters, remaining) where clusters is the LLM-shape list
        of {canonical_uri, canonical_label, member_uris} for each non-
        singleton cluster the heuristic built, and remaining is the
        singletons still needing LLM review.
        """
        n = len(entities)
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

        slugs = [cls._slug_from_uri(p["uri"]) for p in entities]
        for i in range(n):
            for j in range(i + 1, n):
                if cls._slugs_same_entity(
                    slugs[i], slugs[j],
                    min_len=min_len,
                    max_edit_dist=max_edit_dist,
                    stop_slugs=stop_slugs,
                ):
                    union(i, j)

        groups: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        clusters: List[Dict[str, Any]] = []
        remaining: List[Dict[str, str]] = []
        for members in groups.values():
            if len(members) == 1:
                remaining.append(entities[members[0]])
                continue
            # Canonical = longest label; break ties by longest slug
            members_sorted = sorted(
                members,
                key=lambda idx: (
                    -len(entities[idx].get("label") or ""),
                    -len(slugs[idx]),
                ),
            )
            canonical_idx = members_sorted[0]
            clusters.append({
                "canonical_uri": entities[canonical_idx]["uri"],
                "canonical_label": entities[canonical_idx].get("label", ""),
                "member_uris": [entities[idx]["uri"] for idx in members],
            })
        return clusters, remaining

    # ------------------------------------------------------------------
    # Internals — fetch + LLM
    # ------------------------------------------------------------------

    async def _fetch_entities(
        self, collection: str, entity_type: str,
    ) -> List[Dict[str, str]]:
        """Return all nodes of a given type in the collection as [{uri, label}]."""
        query = (
            "MATCH (n:Node)-[rt:Rel {uri: $type_pred}]->(t:Literal) "
            "WHERE n.collection = $collection "
            "  AND t.value = $entity_type "
            "WITH DISTINCT n "
            "OPTIONAL MATCH (n)-[rl:Rel {uri: $label_pred}]->(lab:Literal) "
            "RETURN n.uri AS uri, collect(lab.value)[0] AS label"
        )
        params = {
            "collection": collection,
            "entity_type": entity_type,
            "type_pred": self.TYPE_PREDICATE_URI,
            "label_pred": self.LABEL_PREDICATE_URI,
        }
        rows = await self._client.execute_cypher(query, params=params)
        entities: List[Dict[str, str]] = []
        for row in rows or []:
            uri = row.get("uri")
            if not uri:
                continue
            label = row.get("label") or self._fallback_label(uri)
            entities.append({"uri": uri, "label": str(label)})
        return entities

    @staticmethod
    def _fallback_label(uri: str) -> str:
        tail = uri.rstrip("/").rsplit("/", 1)[-1]
        return tail.replace("-", " ").title() if tail else uri

    async def _cluster_via_llm(
        self,
        entities: List[Dict[str, str]],
        prompt_name: str,
    ) -> List[Dict[str, Any]]:
        """Ask the LLM to cluster duplicates. Returns the clusters list."""
        prompt_template = self._get_prompt(prompt_name)
        entities_json = json.dumps(entities, ensure_ascii=False)
        # Both old and new placeholders supported: legacy {{persons_json}} +
        # generic {{entities_json}}. Prompts added from 2026-04-23 onward
        # use the generic placeholder.
        prompt = prompt_template.replace("{{entities_json}}", entities_json).replace(
            "{{persons_json}}", entities_json
        )

        raw = await self._call_llm(prompt)
        return self._parse_clusters(raw)

    def _get_prompt(self, prompt_name: str) -> str:
        cached = getattr(self, f"_prompt_cache_{prompt_name}", None)
        if cached is not None:
            return cached
        try:
            from app.services.langfuse_client import get_langfuse  # type: ignore

            langfuse = get_langfuse()
            prompt_obj = langfuse.get_prompt(prompt_name, label="production")
            compiled = prompt_obj.compile()
            setattr(self, f"_prompt_cache_{prompt_name}", compiled)
            return compiled
        except Exception as exc:
            logger.warning(
                "EntityResolver: Langfuse prompt '%s' unavailable (%s), falling back to inline prompt",
                prompt_name,
                exc,
            )
            # Minimal inline fallback keeps the service functional in degraded
            # mode. Real content belongs in Langfuse (see
            # scripts/seed_entity_resolution_prompt.py +
            # seed_entity_resolution_prompts_generic.py).
            return (
                "Agrupa las entidades duplicadas (misma entidad con labels distintos). "
                "Solo agrupa si estás seguro. Responde JSON: "
                '{"clusters": [{"canonical_uri": "...", "canonical_label": "...", '
                '"member_uris": ["...", "..."]}]}\n\n{{entities_json}}'
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
    # Internals — type-specific guards
    # ------------------------------------------------------------------

    _NUMERIC_TOKEN_RE = re.compile(r"\d+")

    @classmethod
    def _reject_distinct_numeric_members(
        cls,
        clusters: List[Dict[str, Any]],
        uri_to_label: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Drop cluster members whose numeric tokens conflict with the canonical.

        Used for `place` entities so two distinct addresses on the same
        street ('Calle Mayor 5' vs 'Calle Mayor 47') are never fused even
        if the LLM phase recommended the merge. The check is deliberately
        conservative: when only one side has numbers, the merge is allowed
        (the other label is treated as the unspecified parent address).
        Clusters that collapse to a single canonical-only member after
        filtering are dropped entirely so downstream merge skips them.
        """
        filtered: List[Dict[str, Any]] = []
        for cluster in clusters:
            canonical_uri = cluster.get("canonical_uri", "")
            canonical_nums = set(
                cls._NUMERIC_TOKEN_RE.findall(uri_to_label.get(canonical_uri, ""))
            )
            kept: List[str] = []
            for uri in cluster.get("member_uris", []):
                if uri == canonical_uri:
                    kept.append(uri)
                    continue
                member_nums = set(cls._NUMERIC_TOKEN_RE.findall(uri_to_label.get(uri, "")))
                if canonical_nums and member_nums and canonical_nums != member_nums:
                    logger.info(
                        "EntityResolver[place]: rejected merge %s ('%s') → %s ('%s') — distinct numeric tokens",
                        uri,
                        uri_to_label.get(uri, ""),
                        canonical_uri,
                        uri_to_label.get(canonical_uri, ""),
                    )
                    continue
                kept.append(uri)
            if len(kept) > 1:
                new_cluster = dict(cluster)
                new_cluster["member_uris"] = kept
                filtered.append(new_cluster)
        return filtered

    # ------------------------------------------------------------------
    # Internals — graph merge
    # ------------------------------------------------------------------

    async def _merge_node(
        self,
        duplicate_uri: str,
        canonical_uri: str,
        collection: str,
    ) -> int:
        """Repoint every :Rel of `duplicate_uri` to `canonical_uri` and delete the node.

        Returns the number of edges repointed (incoming + outgoing).
        """
        # Ensure the canonical node exists — may not if the LLM picked one that
        # was never the duplicate target.
        await self._client.execute_cypher(
            "MERGE (n:Node {uri: $uri, collection: $collection}) "
            "ON CREATE SET n.created_at = timestamp()",
            params={"uri": canonical_uri, "collection": collection},
        )

        # Repoint outgoing edges (duplicate)-[r]->(target)
        # Use two-step: CREATE new edges, then delete old ones. FalkorDB does
        # not support setting relationship properties from another rel in one
        # statement, so we copy the predicate URI + key metadata explicitly.
        outgoing_q = (
            "MATCH (d:Node {uri: $dup, collection: $collection})"
            "-[r:Rel]->(t) "
            "MATCH (c:Node {uri: $can, collection: $collection}) "
            "CREATE (c)-[r2:Rel]->(t) "
            "SET r2.uri = r.uri, r2.method = r.method, r2.source_chunk = r.source_chunk, "
            "    r2.confidence = r.confidence, r2.collection = r.collection "
            "DELETE r "
            "RETURN count(r2) AS repointed"
        )
        out_rows = await self._client.execute_cypher(
            outgoing_q,
            params={
                "dup": duplicate_uri,
                "can": canonical_uri,
                "collection": collection,
            },
        )
        out_count = (out_rows[0].get("repointed") if out_rows else 0) or 0

        # Repoint incoming edges (src)-[r]->(duplicate)
        incoming_q = (
            "MATCH (s)-[r:Rel]->(d:Node {uri: $dup, collection: $collection}) "
            "MATCH (c:Node {uri: $can, collection: $collection}) "
            "CREATE (s)-[r2:Rel]->(c) "
            "SET r2.uri = r.uri, r2.method = r.method, r2.source_chunk = r.source_chunk, "
            "    r2.confidence = r.confidence, r2.collection = r.collection "
            "DELETE r "
            "RETURN count(r2) AS repointed"
        )
        in_rows = await self._client.execute_cypher(
            incoming_q,
            params={
                "dup": duplicate_uri,
                "can": canonical_uri,
                "collection": collection,
            },
        )
        in_count = (in_rows[0].get("repointed") if in_rows else 0) or 0

        # Delete the now-orphan duplicate node
        await self._client.execute_cypher(
            "MATCH (d:Node {uri: $dup, collection: $collection}) DELETE d",
            params={"dup": duplicate_uri, "collection": collection},
        )

        return int(out_count) + int(in_count)
