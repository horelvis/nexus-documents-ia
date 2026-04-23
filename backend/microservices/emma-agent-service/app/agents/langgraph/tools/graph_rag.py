"""
Emma ReAct Agent — Graph RAG Tool

7-stage pipeline that retrieves knowledge-graph context for the ReAct agent:

  Stage 1: Entity retrieval
           Concept embeddings → Weaviate TrustGraphEntities vector search
           → Deduplicate by entity_uri, sort by score

  Stage 2: BFS subgraph
           Seed URIs → KTS /triples/neighbors
           → Edge list

  Stage 3: Label resolution
           Collect unique URIs from edges → TTL-cache lookup or
           KTS query_triples(predicate=core/label) → humanize fallback

  Stage 4: Semantic pre-filter
           Build edge descriptions → batch embed via intelligence-docs-service
           → cosine similarity against concept embeddings
           → keep top graph_rag_prefilter_limit edges

  Stage 5: LLM edge scoring
           Format edges → planner model + Langfuse prompt trustgraph_edge_scoring
           → parse JSON [{"id": ..., "score": N}]
           → keep top graph_rag_edge_limit by score

  Stage 6: Context formatting
           Render as markdown with Entities + Relationships sections
           → ToolResult(output=text, data={entities, expanded_doc_ids, avg_score})

  Stage 7: Source provenance resolution
           Scored edges → KTS /triples/trace-sources
           → Resolve document_id, chunk_offset, confidence per edge
           → Append "### Fuentes" section + source_evidence in data
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Type

import httpx
from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult
from app.agents.langgraph.tools.concept_extractor import extract_concepts, ConceptResult
from app.core.config import settings
from app.clients.weaviate_client import get_weaviate_client
from app.clients.knowledge_tree_client import get_knowledge_tree_client
from app.agents.llm_models import get_planner_model
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label resolution TTL cache (module-level singleton, initialized lazily)
# ---------------------------------------------------------------------------

_label_cache: Optional[Any] = None  # cachetools.TTLCache or dict fallback


def _get_label_cache(ttl: int) -> Any:
    """Return (or lazily create) the label TTL cache."""
    global _label_cache
    if _label_cache is None:
        try:
            from cachetools import TTLCache
            _label_cache = TTLCache(maxsize=2000, ttl=ttl)
        except ImportError:
            logger.warning("cachetools not available — using dict fallback for label cache")
            _label_cache = _DictTTLCache(maxsize=2000, ttl=ttl)
    return _label_cache


class _DictTTLCache:
    """Minimal TTL cache fallback when cachetools is absent."""

    def __init__(self, maxsize: int, ttl: int):
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str, default=None):
        entry = self._store.get(key)
        if entry is None:
            return default
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return default
        return value

    def __setitem__(self, key: str, value: Any):
        if len(self._store) >= self._maxsize:
            # Evict oldest entry
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[key] = (value, time.time())

    def __contains__(self, key: str):
        return self.get(key) is not None

    def __getitem__(self, key: str):
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


class GraphRAGInput(BaseModel):
    query: str = Field(
        description="Consulta en lenguaje natural para buscar relaciones entre entidades en el grafo de conocimiento"
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _build_edge_description(
    subject_label: str,
    predicate_name: str,
    object_label: str,
    confidence: Optional[float] = None,
    source_chunk: Optional[str] = None,
) -> str:
    """Build a human-readable edge description for embedding / LLM scoring.

    Includes confidence and source citation when available.
    """
    desc = f"{subject_label}, {predicate_name}, {object_label}"
    if confidence is not None:
        desc += f" [conf: {confidence:.2f}]"
    if source_chunk:
        doc_part = source_chunk.split("#")[0].rsplit("/", 1)[-1] if source_chunk else ""
        offset_part = source_chunk.split("offset=")[-1] if "offset=" in source_chunk else ""
        if doc_part:
            desc += f" [fuente: {doc_part}#{offset_part}]"
    return desc


def _humanize_uri(uri: str) -> str:
    """Extract readable label from a URI by taking its last path segment.

    E.g. 'nouxcube://entity/lgt' → 'lgt'
         'nouxcube://predicate/legal/regula' → 'regula'
    """
    if not uri:
        return uri
    # Handle both 'nouxcube://...' and 'http://...' URIs
    segment = uri.rstrip("/").split("/")[-1]
    # Replace hyphens/underscores with spaces and capitalize
    return segment.replace("-", " ").replace("_", " ").title()


def _extract_predicate_name(predicate_uri: str) -> str:
    """Extract human name from predicate URI.

    'nouxcube://predicate/legal/empleado-de' → 'empleado de'
    """
    return _humanize_uri(predicate_uri).lower()


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two vectors (pure Python, no numpy)."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def _parse_scoring_json(content: str) -> List[Dict[str, Any]]:
    """Parse LLM JSON response for edge scoring.

    Handles markdown code blocks and thinking tags.
    Returns list of {"id": str, "score": float}.
    """
    if not content:
        return []

    # Strip thinking tags
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # Strip markdown code blocks
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if md_match:
        content = md_match.group(1).strip()

    # Find first JSON array
    arr_match = re.search(r"\[[\s\S]*\]", content)
    if not arr_match:
        logger.warning(f"graph_rag: no JSON array in scoring response: {content[:200]}")
        return []

    try:
        data = json.loads(arr_match.group(0))
        if not isinstance(data, list):
            return []
        result = []
        for item in data:
            if isinstance(item, dict) and "id" in item and "score" in item:
                try:
                    result.append({"id": str(item["id"]), "score": float(item["score"])})
                except (TypeError, ValueError):
                    pass
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"graph_rag: JSON decode error in scoring: {e}")
        return []


# ---------------------------------------------------------------------------
# Stage 7b helper: resolve chunk text for source evidence
# ---------------------------------------------------------------------------


async def _resolve_chunk_texts(
    source_evidence: List[Dict[str, Any]],
    weaviate_client: Any,
    user_roles: List[str],
    user_id: Optional[str] = None,
    max_snippet_chars: int = 300,
) -> None:
    """Fetch chunk content for each source and add chunk_text field.

    Groups by document_id to minimize HTTP calls. Modifies source_evidence
    in-place. Failures are silently skipped (chunk_text stays absent).
    """
    # Group sources by document_id
    doc_chunks: Dict[str, List[Dict[str, Any]]] = {}
    for src in source_evidence:
        doc_id = src.get("document_id", "")
        if doc_id:
            doc_chunks.setdefault(doc_id, []).append(src)

    # Fetch chunks per document (parallel)
    import asyncio as _asyncio

    async def _fetch_and_assign(doc_id: str, sources: List[Dict[str, Any]]):
        try:
            chunks = await weaviate_client.get_document_chunks(
                document_id=doc_id,
                user_roles=user_roles,
                user_id=user_id,
            )
            # Build offset→content map
            chunk_map = {}
            for ch in (chunks if isinstance(chunks, list) else chunks.get("chunks", [])):
                idx = ch.get("chunk_index")
                if idx is not None:
                    chunk_map[idx] = ch.get("content", "")

            for src in sources:
                offset = src.get("chunk_offset")
                text = chunk_map.get(offset, "")
                if text:
                    # Strip metadata prefix [CONTEXTO]...[CONTENIDO]
                    if "[CONTENIDO]" in text:
                        text = text.split("[CONTENIDO]", 1)[1].strip()
                    src["chunk_text"] = text[:max_snippet_chars]
        except Exception as exc:
            logger.warning("graph_rag: chunk fetch failed for doc %s: %s", doc_id, exc)

    await _asyncio.gather(
        *[_fetch_and_assign(doc_id, srcs) for doc_id, srcs in doc_chunks.items()],
        return_exceptions=True,
    )


# ---------------------------------------------------------------------------
# Stage 4 helper: batch embed edge descriptions
# ---------------------------------------------------------------------------


async def _resolve_authority_weights(
    edges: List[Dict[str, Any]],
    kts_client,
) -> Dict[int, float]:
    """Resolve authority weights for edges by source document semantic_type.

    Returns dict mapping edge index to authority weight (0.0-1.0).
    Default 0.50 for edges without resolvable authority.
    """
    DEFAULT_AUTHORITY = 0.50

    # Collect unique document URIs from source_chunk metadata
    doc_uris: set = set()
    for edge in edges:
        chunk = edge.get("source_chunk", "")
        if chunk and "#" in chunk:
            doc_uris.add(chunk.split("#")[0])

    if not doc_uris:
        return {i: DEFAULT_AUTHORITY for i in range(len(edges))}

    # For each document, get its semantic-type, then look up authority weight
    authority_by_doc: Dict[str, float] = {}
    for doc_uri in doc_uris:
        try:
            # Get semantic-type of document
            type_result = await kts_client.query_triples(
                subject_uri=doc_uri,
                predicate_uri="nouxcube://predicate/core/semantic-type",
                limit=1,
            )
            triples = type_result.get("triples", [])
            if not triples:
                continue
            sem_type = triples[0].get("object", "desconocido")

            # Look up authority weight for this semantic_type
            aw_result = await kts_client.query_triples(
                subject_uri=f"nouxcube://entity/_system/{sem_type}",
                predicate_uri="nouxcube://predicate/trust/authority-weight",
                limit=1,
            )
            aw_triples = aw_result.get("triples", [])
            if aw_triples:
                try:
                    authority_by_doc[doc_uri] = float(aw_triples[0].get("object", DEFAULT_AUTHORITY))
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

    # Map authority to each edge
    result = {}
    for i, edge in enumerate(edges):
        chunk = edge.get("source_chunk", "")
        if chunk and "#" in chunk:
            doc_uri = chunk.split("#")[0]
            result[i] = authority_by_doc.get(doc_uri, DEFAULT_AUTHORITY)
        else:
            result[i] = DEFAULT_AUTHORITY
    return result


async def _batch_embed_edges(descriptions: List[str]) -> List[List[float]]:
    """Batch embed edge descriptions via intelligence-docs-service.

    Returns list of embedding vectors (same order as input).
    Returns empty list on failure.
    """
    if not descriptions:
        return []

    import os
    base = os.getenv("INTELLIGENCE_DOCS_SERVICE_URL", settings.text_extraction_service_url)
    url = f"{base}/embed"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                url,
                json={"texts": descriptions, "task": "retrieval.passage"},
                headers={
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                },
            )
            response.raise_for_status()
            data = response.json()
            vectors: List[List[float]] = data.get("embeddings", [])

        if len(vectors) != len(descriptions):
            logger.warning(
                f"graph_rag: embed returned {len(vectors)} vectors for {len(descriptions)} descriptions"
            )
            return []

        return vectors

    except Exception as e:
        logger.warning(f"graph_rag: edge embedding failed: {type(e).__name__}: {e}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------


class GraphRAGTool(EmmaTool):
    """Busca relaciones entre entidades en el grafo de conocimiento.

    7-stage pipeline:
      1. Entity retrieval via Weaviate TrustGraphEntities
      2. BFS subgraph expansion via KTS /triples/neighbors
      3. Label resolution with TTL cache
      4. Semantic pre-filter (embedding similarity)
      5. LLM edge scoring
      6. Markdown context formatting
      7. Source provenance resolution via KTS /triples/trace-sources
    """

    @property
    def name(self) -> str:
        return "graph_rag"

    @property
    def description(self) -> str:
        return (
            "Busca relaciones entre personas, empresas, leyes o conceptos en el grafo de conocimiento. "
            "Usa ANTES que smart_search para preguntas sobre vínculos o conexiones."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return GraphRAGInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        if not settings.graph_rag_enabled:
            return ToolResult(output="", data={}, success=True)

        query: str = arguments["query"]
        user_roles: List[str] = context.get("user_roles", [])
        user_id: Optional[str] = context.get("user_id")

        # ── Stage 1: Entity retrieval ────────────────────────────────────────

        # Re-use concepts computed earlier in the pipeline if available
        cached_concepts: Optional[ConceptResult] = context.get("_concepts")
        if cached_concepts is not None:
            concepts = cached_concepts
        else:
            concepts = await extract_concepts(query)

        if not concepts.embeddings:
            # No embeddings available — cannot do vector entity search
            return ToolResult(
                output="No se encontraron entidades en el grafo de conocimiento para esta consulta.",
                data={},
                success=True,
            )

        weaviate_client = get_weaviate_client()
        kts_client = get_knowledge_tree_client()

        # Search entities by each concept embedding, then deduplicate
        all_entity_hits: Dict[str, Dict[str, Any]] = {}  # entity_uri → best hit

        for concept, embedding in concepts.embeddings.items():
            try:
                hits = await weaviate_client.search_entities_by_embedding(
                    embedding=embedding,
                    limit=settings.graph_rag_entity_limit,
                )
                for hit in hits:
                    uri = hit.get("entity_uri", "")
                    if not uri:
                        continue
                    existing = all_entity_hits.get(uri)
                    if existing is None or hit.get("score", 0.0) > existing.get("score", 0.0):
                        all_entity_hits[uri] = hit
            except Exception as e:
                logger.warning(f"graph_rag: entity search failed for concept '{concept}': {e}")

        if not all_entity_hits:
            return ToolResult(
                output="No se encontraron entidades en el grafo de conocimiento para esta consulta.",
                data={},
                success=True,
            )

        # Sort by score, limit to entity_limit
        top_entities = sorted(
            all_entity_hits.values(),
            key=lambda e: e.get("score", 0.0),
            reverse=True,
        )[: settings.graph_rag_entity_limit]

        # ── Stage 2: BFS subgraph ────────────────────────────────────────────

        seed_uris = [e["entity_uri"] for e in top_entities if e.get("entity_uri")]

        try:
            neighbors_result = await kts_client.batch_neighbors(
                seed_uris=seed_uris,
                max_hops=settings.graph_rag_max_hops,
                max_edges=settings.graph_rag_max_edges,
            )
            edges: List[Dict[str, Any]] = neighbors_result.get("edges", [])
        except Exception as e:
            logger.warning(f"graph_rag: BFS subgraph failed: {e}")
            edges = []

        if not edges:
            # Return just entities even without relationships
            return _format_entities_only(top_entities)

        # ── Stage 2b: Confidence pre-filter ─────────────────────────────
        confidence_threshold = settings.graph_rag_confidence_threshold
        if confidence_threshold > 0:
            edges = [
                e for e in edges
                if (e.get("confidence") or 1.0) >= confidence_threshold
            ]
            if not edges:
                return _format_entities_only(top_entities)

        # ── Stage 2.5: LLM-Guided Expansion ─────────────────────────────────
        if settings.guided_expansion_enabled and edges:
            try:
                # Summarize current subgraph for the planner
                entity_names = list(set(
                    e.get("subject", "").split("/")[-1].replace("-", " ")
                    for e in edges[:20]
                ))[:15]
                rel_types = list(set(
                    e.get("predicate", "").split("/")[-1]
                    for e in edges[:20]
                ))[:10]

                from langchain_core.messages import SystemMessage, HumanMessage
                from app.services.langfuse_prompt_client import PromptNotFoundError as _PNF
                _GUIDED_EXPANSION_FALLBACK = (
                    "Given the user query and current subgraph, determine if more traversal is needed. "
                    'Respond with JSON: {"sufficient": true/false, "expand_from": ["uri1"], "reason": "..."}'
                )
                langfuse_client = get_langfuse_prompt_client()
                try:
                    expansion_prompt = await langfuse_client.get_prompt(
                        "trustgraph_guided_expansion"
                    )
                    system_content = expansion_prompt.content
                except _PNF:
                    system_content = _GUIDED_EXPANSION_FALLBACK

                planner = get_planner_model()

                user_msg = (
                    f"Query: {query}\n\n"
                    f"Current entities ({len(entity_names)}): {', '.join(entity_names)}\n"
                    f"Relationship types: {', '.join(rel_types)}\n"
                    f"Total edges: {len(edges)}"
                )

                response = await planner.ainvoke([
                    SystemMessage(content=system_content),
                    HumanMessage(content=user_msg),
                ])

                try:
                    raw = (response.content or "").strip()
                    # Strip thinking tags and markdown code blocks
                    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                    md = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                    if md:
                        raw = md.group(1).strip()
                    expansion = json.loads(raw)
                    if not expansion.get("sufficient", True):
                        expand_uris = expansion.get("expand_from", [])[:3]
                        remaining_budget = settings.graph_rag_max_edges - len(edges)
                        if expand_uris and remaining_budget <= 0:
                            logger.info("Guided expansion: skipped, edge budget exhausted (%d/%d)", len(edges), settings.graph_rag_max_edges)
                        elif expand_uris and remaining_budget > 0:
                            logger.info(
                                "Guided expansion: expanding from %d URIs (reason: %s)",
                                len(expand_uris), expansion.get("reason", "")[:100]
                            )
                            extra_result = await kts_client.batch_neighbors(
                                seed_uris=expand_uris,
                                max_hops=settings.guided_expansion_max_hops,
                                max_edges=remaining_budget,
                            )
                            extra_edges = extra_result.get("edges", [])
                            existing_keys = {
                                (e.get("subject", ""), e.get("predicate", ""), e.get("object", ""))
                                for e in edges
                            }
                            added = 0
                            for ee in extra_edges:
                                key = (ee.get("subject", ""), ee.get("predicate", ""), ee.get("object", ""))
                                if key not in existing_keys:
                                    edges.append(ee)
                                    existing_keys.add(key)
                                    added += 1
                            logger.info("Guided expansion added %d new edges (total: %d)", added, len(edges))
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.debug("Guided expansion: planner response not valid JSON, skipping")

            except Exception as exc:
                logger.warning("Guided expansion failed, continuing: %s", exc)

        # ── Stage 3: Label resolution ────────────────────────────────────────

        cache = _get_label_cache(settings.graph_rag_label_cache_ttl)

        # Collect all unique URIs appearing in edges
        # BFS returns keys as "subject"/"predicate"/"object" (not *_uri)
        unique_uris: set = set()
        for edge in edges:
            for key in ("subject_uri", "subject", "object_uri", "object"):
                uri = edge.get(key, "")
                if uri and uri.startswith("nouxcube://"):
                    unique_uris.add(uri)
        for e in top_entities:
            uri = e.get("entity_uri", "")
            if uri:
                unique_uris.add(uri)

        labels: Dict[str, str] = {}
        label_predicate = "nouxcube://predicate/core/label"

        for uri in unique_uris:
            # 1. Check TTL cache
            cached_label = cache.get(uri) if hasattr(cache, "get") else None
            if cached_label is None and uri in cache:
                cached_label = cache[uri]

            if cached_label is not None:
                labels[uri] = cached_label
                continue

            # 2. Try known entity data from Weaviate hits
            hit = all_entity_hits.get(uri)
            if hit and hit.get("label"):
                lbl = hit["label"]
                cache[uri] = lbl
                labels[uri] = lbl
                continue

            # 3. Query KTS for core/label triple
            try:
                triple_result = await kts_client.query_triples(
                    subject_uri=uri,
                    predicate_uri=label_predicate,
                    limit=1,
                )
                triples = triple_result.get("triples", [])
                if triples:
                    lbl = triples[0].get("object_value", "") or _humanize_uri(uri)
                else:
                    lbl = _humanize_uri(uri)
            except Exception:
                lbl = _humanize_uri(uri)

            cache[uri] = lbl
            labels[uri] = lbl

        # ── Stage 4: Semantic pre-filter ─────────────────────────────────────

        # Build edge descriptions
        edge_descriptions: List[str] = []
        for edge in edges:
            s_uri = edge.get("subject_uri") or edge.get("subject", "")
            p_uri = edge.get("predicate_uri") or edge.get("predicate", "")
            o_uri = edge.get("object_uri") or edge.get("object", "")
            s_label = labels.get(s_uri, _humanize_uri(s_uri))
            p_name = _extract_predicate_name(p_uri)
            o_label = labels.get(o_uri, _humanize_uri(o_uri))
            edge_descriptions.append(_build_edge_description(
                s_label, p_name, o_label,
                confidence=edge.get("confidence"),
                source_chunk=edge.get("source_chunk"),
            ))

        # Batch embed descriptions
        desc_embeddings = await _batch_embed_edges(edge_descriptions)

        if desc_embeddings and concepts.embeddings:
            # Concept embeddings as list of vectors
            concept_vectors = list(concepts.embeddings.values())

            # Score each edge by max cosine similarity against any concept embedding
            scored_edges: List[Tuple[int, float]] = []
            for idx, desc_vec in enumerate(desc_embeddings):
                max_sim = max(
                    _cosine_similarity(desc_vec, cv) for cv in concept_vectors
                )
                scored_edges.append((idx, max_sim))

            # Sort by similarity and keep top prefilter_limit
            scored_edges.sort(key=lambda x: x[1], reverse=True)
            prefilter_indices = [idx for idx, _ in scored_edges[: settings.graph_rag_prefilter_limit]]
            filtered_edges = [edges[i] for i in prefilter_indices]
            filtered_descriptions = [edge_descriptions[i] for i in prefilter_indices]

            # ── Composite 5-signal scoring ───────────────────────────────────
            # Build similarity map: original edge index → similarity score
            sim_map = {idx: sim for idx, sim in scored_edges}

            authority_map: Dict[int, float] = {}
            if settings.authority_weights_enabled:
                try:
                    authority_map = await _resolve_authority_weights(
                        filtered_edges, kts_client
                    )
                except Exception as exc:
                    logger.warning("Authority weight resolution failed: %s", exc)

            for i, edge in enumerate(filtered_edges):
                orig_idx = prefilter_indices[i]
                semantic_sim = sim_map.get(orig_idx, 0.0)
                confidence = (edge.get("confidence") or 0.0)
                authority = authority_map.get(i, 0.50)
                consensus = min(1.0, (edge.get("consensus_count") or 1) / 3)
                recency = 0.5  # default — edges lack timestamps

                composite = (
                    0.35 * semantic_sim +
                    0.20 * confidence +
                    0.20 * authority +
                    0.15 * consensus +
                    0.10 * recency
                )
                edge["_composite_score"] = round(composite, 4)
                edge["_authority"] = authority
                edge["_consensus"] = round(consensus, 2)
                edge["_semantic_sim"] = round(semantic_sim, 4)

            # Re-sort by composite score
            filtered_edges.sort(key=lambda e: e.get("_composite_score", 0), reverse=True)
        else:
            # No embeddings available — keep all (up to prefilter_limit)
            filtered_edges = edges[: settings.graph_rag_prefilter_limit]
            filtered_descriptions = edge_descriptions[: settings.graph_rag_prefilter_limit]

        if not filtered_edges:
            return _format_entities_only(top_entities)

        # ── Stage 5: LLM edge scoring ────────────────────────────────────────

        scored_final_edges = await _llm_score_edges(
            query=query,
            edges=filtered_edges,
            descriptions=filtered_descriptions,
            edge_limit=settings.graph_rag_edge_limit,
        )

        # ── Stage 6: Context formatting ──────────────────────────────────────

        result = _format_context(
            query=query,
            top_entities=top_entities,
            scored_edges=scored_final_edges,
            labels=labels,
        )

        # ── Stage 7: Source provenance resolution ────────────────────────
        source_evidence = []
        try:
            trace_edges = []
            for edge in scored_final_edges:
                trace_edges.append({
                    "subject_uri": edge.get("subject_uri") or edge.get("subject", ""),
                    "predicate_uri": edge.get("predicate_uri") or edge.get("predicate", ""),
                    "object_uri": edge.get("object_uri") or edge.get("object", ""),
                })

            logger.info(f"graph_rag: Stage 7 — tracing {len(trace_edges)} edges for provenance")
            if trace_edges:
                for te in trace_edges[:3]:
                    logger.info(f"graph_rag: trace edge sample: s={te['subject_uri'][:60]} p={te['predicate_uri'][:60]} o={te['object_uri'][:60]}")
            if trace_edges:
                raw_sources = await kts_client.trace_sources(
                    edges=trace_edges,
                )
                logger.info(f"graph_rag: Stage 7 — got {len(raw_sources) if isinstance(raw_sources, list) else len(raw_sources.get('sources', []))} source(s)")

                for src in (raw_sources if isinstance(raw_sources, list) else raw_sources.get("sources", [])):
                    doc_uri = f"nouxcube://document/default/{src['document_id']}"
                    doc_title = labels.get(doc_uri, src["document_id"][:12])
                    s_label = labels.get(src["subject_uri"], _humanize_uri(src["subject_uri"]))
                    p_name = _extract_predicate_name(src["predicate_uri"])
                    o_label = labels.get(src["object_uri"], _humanize_uri(src["object_uri"]))

                    source_evidence.append({
                        "document_id": src["document_id"],
                        "document_title": doc_title,
                        "chunk_offset": src["chunk_offset"],
                        "relationship": f"{s_label} {p_name} {o_label}",
                        "confidence": src.get("confidence"),
                        # URIs preserved for evidence_graph construction in
                        # /emma/explainability/trace (Piece A, 2026-04-23).
                        "subject_uri": src["subject_uri"],
                        "predicate_uri": src["predicate_uri"],
                        "object_uri": src["object_uri"],
                        "subject_label": s_label,
                        "object_label": o_label,
                        "predicate_name": p_name,
                    })
        except Exception as e:
            logger.warning(f"graph_rag: source resolution failed: {e}", exc_info=True)

        # ── Stage 7b: Resolve chunk text for source evidence ────────────
        if source_evidence:
            try:
                await _resolve_chunk_texts(source_evidence, weaviate_client, user_roles, user_id)
            except Exception as e:
                logger.warning(f"graph_rag: chunk text resolution failed: {e}")

            sources_text = "\n\n### Fuentes\n"
            for src in source_evidence[:10]:
                conf_str = f" (conf: {src['confidence']:.2f})" if src.get('confidence') is not None else ""
                sources_text += f"- \"{src['relationship']}\" — {src['document_title']} chunk {src['chunk_offset']}{conf_str}\n"
            result.output += sources_text
            result.data["source_evidence"] = source_evidence

        return result


# ---------------------------------------------------------------------------
# Stage 5: LLM edge scoring
# ---------------------------------------------------------------------------


async def _llm_score_edges(
    query: str,
    edges: List[Dict[str, Any]],
    descriptions: List[str],
    edge_limit: int,
) -> List[Dict[str, Any]]:
    """Call planner LLM with Langfuse prompt to score edges.

    Returns edges sorted by LLM score (top edge_limit).
    Falls back to returning all edges in original order on any failure.
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    # Build edge ID map for scoring
    edge_id_map: Dict[str, Dict[str, Any]] = {}
    edge_lines: List[str] = []
    for edge, desc in zip(edges, descriptions):
        s = edge.get("subject_uri") or edge.get("subject", "")
        p = edge.get("predicate_uri") or edge.get("predicate", "")
        o = edge.get("object_uri") or edge.get("object", "")
        edge_id = f"{s}@@{p}@@{o}"
        edge_id_map[edge_id] = edge
        edge_lines.append(f"{edge_id} | {desc}")

    edges_text = "\n".join(edge_lines)
    user_content = f"Query: {query}\n\nEdges:\n{edges_text}"

    try:
        langfuse_client = get_langfuse_prompt_client()
        prompt_cached = await langfuse_client.get_prompt("trustgraph_edge_scoring")
        system_content = prompt_cached.content if prompt_cached else (
            "You are a knowledge graph assistant. "
            "Score each edge by relevance to the query (0-1). "
            "Return JSON array: [{\"id\": \"<edge_id>\", \"score\": <float>}]. "
            "Only return JSON, no other text."
        )

        model = get_planner_model()
        response = await model.ainvoke([
            SystemMessage(content=system_content),
            HumanMessage(content=user_content),
        ])

        content = (response.content or "").strip()
        scored_items = _parse_scoring_json(content)

        if scored_items:
            # Sort by LLM score descending
            scored_items.sort(key=lambda x: x["score"], reverse=True)
            # Reconstruct edge list from IDs
            result_edges = []
            for item in scored_items[:edge_limit]:
                edge = edge_id_map.get(item["id"])
                if edge is not None:
                    edge_with_score = dict(edge)
                    edge_with_score["_llm_score"] = item["score"]
                    result_edges.append(edge_with_score)
            if result_edges:
                return result_edges

    except Exception as e:
        logger.warning(f"graph_rag: LLM edge scoring failed: {e}")

    # Fallback: return edges as-is (up to edge_limit)
    for edge in edges[:edge_limit]:
        if "_llm_score" not in edge:
            edge["_llm_score"] = 0.5  # neutral fallback score
    return edges[:edge_limit]


# ---------------------------------------------------------------------------
# Stage 6: Context formatting helpers
# ---------------------------------------------------------------------------


def _format_entities_only(entities: List[Dict[str, Any]]) -> ToolResult:
    """Format result when we have entities but no edges."""
    if not entities:
        return ToolResult(output="", data={}, success=True)

    entity_list = []
    for e in entities[:10]:
        entity_list.append({
            "name": e.get("label", _humanize_uri(e.get("entity_uri", ""))),
            "type": e.get("entity_type", "entity"),
            "definition": e.get("definition", ""),
        })

    output = "## Knowledge Graph Context\n\n### Entities\n"
    output += json.dumps(entity_list, ensure_ascii=False, indent=2)
    output += "\n\n### Relationships\nNo se encontraron relaciones relevantes.\n"

    return ToolResult(
        output=output,
        data={
            "entities": entity_list,
            "expanded_doc_ids": [],
            "avg_score": 0.0,
        },
        success=True,
    )


def _format_context(
    query: str,
    top_entities: List[Dict[str, Any]],
    scored_edges: List[Dict[str, Any]],
    labels: Dict[str, str],
) -> ToolResult:
    """Format final markdown context from entities and scored edges."""

    # Build entity list
    entity_list = []
    for e in top_entities[:10]:
        entity_list.append({
            "name": e.get("label", _humanize_uri(e.get("entity_uri", ""))),
            "type": e.get("entity_type", "entity"),
            "definition": e.get("definition", ""),
        })

    # Build relationship list
    relationship_list = []
    scores = []
    for edge in scored_edges:
        s_uri = edge.get("subject_uri") or edge.get("subject", "")
        p_uri = edge.get("predicate_uri") or edge.get("predicate", "")
        o_uri = edge.get("object_uri") or edge.get("object", "")
        score = edge.get("_llm_score", 0.5)
        confidence = edge.get("confidence")
        source = edge.get("source_chunk", "")

        s_label = labels.get(s_uri, _humanize_uri(s_uri))
        p_name = _extract_predicate_name(p_uri)
        o_label = labels.get(o_uri, _humanize_uri(o_uri))

        # Parse source for human-readable citation
        doc_id = source.split("#")[0].rsplit("/", 1)[-1] if source else ""
        chunk_offset = source.split("offset=")[-1] if source and "offset=" in source else ""

        rel: Dict[str, Any] = {
            "subject": s_label,
            "predicate": p_name,
            "object": o_label,
            "score": round(score, 4),
        }
        if confidence is not None:
            rel["confidence"] = round(confidence, 2)
        if doc_id:
            rel["source"] = f"{doc_id}#{chunk_offset}"

        relationship_list.append(rel)
        scores.append(score)

    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Collect expanded document IDs from edge metadata
    expanded_doc_ids: List[str] = []
    for edge in scored_edges:
        doc_id = edge.get("source_document_id") or edge.get("document_id")
        if doc_id and doc_id not in expanded_doc_ids:
            expanded_doc_ids.append(doc_id)

    # ── Detect multi-hop chains ──────────────────────────────────────────
    adjacency: Dict[str, List[Dict]] = {}
    for edge in scored_edges:
        subj = edge.get("subject_uri") or edge.get("subject", "")
        if subj:
            adjacency.setdefault(subj, []).append(edge)

    chains_found = []
    seed_entities = [e.get("entity_uri", "") for e in top_entities[:5]]
    for seed_uri in seed_entities:
        if seed_uri not in adjacency:
            continue
        for edge1 in adjacency[seed_uri][:5]:
            hop2_uri = edge1.get("object_uri") or edge1.get("object", "")
            if hop2_uri and hop2_uri in adjacency:
                for edge2 in adjacency[hop2_uri][:3]:
                    p1 = _extract_predicate_name(edge1.get("predicate_uri") or edge1.get("predicate", ""))
                    p2 = _extract_predicate_name(edge2.get("predicate_uri") or edge2.get("predicate", ""))
                    o2 = edge2.get("object_uri") or edge2.get("object", "")
                    chain = {
                        "path": [
                            labels.get(seed_uri, _humanize_uri(seed_uri)),
                            p1,
                            labels.get(hop2_uri, _humanize_uri(hop2_uri)),
                            p2,
                            labels.get(o2, _humanize_uri(o2)),
                        ],
                        "confidence": min(
                            edge1.get("confidence") or 0,
                            edge2.get("confidence") or 0,
                        ),
                    }
                    chains_found.append(chain)

    # Build chain text for markdown output
    chain_text = ""
    if chains_found:
        chain_text = "\n\n### Cadenas de relacion encontradas\n"
        for chain in chains_found[:5]:
            path_str = " → ".join(str(p) for p in chain["path"])
            chain_text += f"- {path_str} (confianza: {chain['confidence']:.2f})\n"

    # Render markdown
    output = "## Knowledge Graph Context\n\n"
    output += "### Entities\n"
    output += json.dumps(entity_list, ensure_ascii=False, indent=2)
    output += "\n\n### Relationships\n"
    output += json.dumps(relationship_list, ensure_ascii=False, indent=2)
    output += chain_text
    output += "\n"

    return ToolResult(
        output=output,
        data={
            "entities": entity_list,
            "expanded_doc_ids": expanded_doc_ids,
            "avg_score": round(avg_score, 4),
        },
        success=True,
    )
