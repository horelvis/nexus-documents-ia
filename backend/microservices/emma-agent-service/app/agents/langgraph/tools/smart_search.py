"""
Emma ReAct Agent — SmartSearch Tool

Unified multi-store search that orchestrates 3 data stores:
  1. Weaviate (hybrid vector+keyword) — tenant documents
  2. PublicKnowledge (hybrid) — BOE legislation
  3. FalkorDB (knowledge graph) — entity relationships

Pipeline:
  Entity extraction (regex ~3ms)
  → Scope detection (rules, no LLM)
  → Filter enrichment (entities → Weaviate filters)
  → Graph expansion (optional, ~20-50ms)
  → Parallel search (asyncio.gather, ~100ms)
  → Merge + deduplicate
  → Multi-signal re-rank (~1ms)
  → Format for LLM

Replaces search_documents + search_legislation with a single tool
so the LLM doesn't have to choose which store to query.
"""

import asyncio
import logging
import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)

# Default re-rank weights when no sector is configured
_DEFAULT_RERANK_WEIGHTS = {
    "similarity": 0.40,
    "quality": 0.20,
    "graph": 0.20,
    "recency": 0.10,
    "entity": 0.10,
}

# Semantic type keywords — map query terms to Weaviate semantic_type values
_SEMANTIC_TYPE_KEYWORDS: Dict[str, str] = {
    "factura": "factura", "facturas": "factura",
    "contrato": "contrato", "contratos": "contrato",
    "nomina": "nomina", "nómina": "nomina", "nóminas": "nomina", "nominas": "nomina",
    "informe": "informe", "informes": "informe",
    "expediente": "expediente", "expedientes": "expediente",
    "acta": "acta", "actas": "acta",
    "presupuesto": "presupuesto", "presupuestos": "presupuesto",
    "certificado": "certificado", "certificados": "certificado",
    "escritura": "escritura", "escrituras": "escritura",
    "recurso": "recurso", "recursos": "recurso",
    "sentencia": "sentencia", "sentencias": "sentencia",
    "demanda": "demanda", "demandas": "demanda",
}

# Keywords that signal legislation scope
_LEGISLATION_KEYWORDS = {
    "ley", "leyes", "artículo", "articulo", "art.", "art ",
    "boe", "real decreto", "estatuto", "normativa", "reglamento",
    "legislación", "legislacion", "código", "codigo",
    "disposición", "disposicion", "ley orgánica", "ley organica",
}

# Keywords that signal document scope
_DOCUMENT_KEYWORDS = {
    "factura", "facturas",
    "contrato", "contratos",
    "nomina", "nominas", "nómina", "nóminas",
    "informe", "informes",
    "expediente", "expedientes",
    "documento", "documentos",
    "archivo", "archivos",
    "carpeta", "carpetas",
    "acta", "actas",
    "presupuesto", "presupuestos",
    "certificado", "certificados",
    "escrito", "escritos",
    "persona", "nif", "cliente", "proveedor", "empleado",
}


# ─── Spanish Stemming Expansion (2-tier: static dict + Snowball) ────

_SPANISH_STEM_MAP: Dict[str, str] = {
    # plural → singular
    "facturas": "factura", "contratos": "contrato",
    "nominas": "nomina", "nóminas": "nomina",
    "informes": "informe", "expedientes": "expediente",
    "actas": "acta", "presupuestos": "presupuesto",
    "certificados": "certificado", "escrituras": "escritura",
    "recursos": "recurso", "sentencias": "sentencia",
    "demandas": "demanda", "documentos": "documento",
    # adjetivos
    "laborales": "laboral", "fiscales": "fiscal",
    "legales": "legal", "comerciales": "comercial",
    "vigentes": "vigente", "pendientes": "pendiente",
    # participios
    "firmado": "firma", "firmados": "firma", "firmadas": "firma",
    "pagada": "pago", "pagadas": "pago", "pagados": "pago",
    "vencidos": "vencimiento", "vencidas": "vencimiento",
}

_snowball_stemmer = None
_SCOPE_LOW_CONFIDENCE = 0.10
_SCOPE_MIN_SIGNAL = 0.03
_SCOPE_MARGIN = 0.05
_DOC_REQUEST_PATTERNS = (
    "documentos de",
    "documentos sobre",
    "documentos del",
    "informes de",
    "contratos de",
    "facturas de",
    "expedientes de",
)


def _normalize_for_match(text: str) -> str:
    """Normalize text for robust keyword matching (case/accents/spacing)."""
    normalized = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", no_accents.lower()).strip()


def _contains_keyword(query: str, keyword: str) -> bool:
    """Word-boundary keyword/phrase match (avoids substring false positives)."""
    q_norm = _normalize_for_match(query)
    kw_norm = _normalize_for_match(keyword)
    if not q_norm or not kw_norm:
        return False
    pattern = rf"(?<!\w){re.escape(kw_norm)}(?!\w)"
    return re.search(pattern, q_norm) is not None


def _count_keyword_matches(query: str, keywords: Set[str]) -> int:
    """Count how many configured keywords match as full tokens/phrases."""
    return sum(1 for kw in keywords if _contains_keyword(query, kw))


def _get_snowball_stemmer():
    """Lazy-load NLTK Snowball stemmer for Spanish."""
    global _snowball_stemmer
    if _snowball_stemmer is None:
        try:
            from nltk.stem.snowball import SnowballStemmer
            _snowball_stemmer = SnowballStemmer("spanish")
        except ImportError:
            logger.debug("NLTK Snowball not available, using static stems only")
    return _snowball_stemmer


def _expand_query_spanish(query: str) -> str:
    """Expand query with stem variants for better BM25 recall.

    Tier 1 (~0ms): Static dictionary of common Spanish inflections.
    Tier 2 (~2ms): Snowball stemmer as fallback for uncovered terms.
    """
    words = query.split()
    expanded = []
    seen: Set[str] = set()
    for word in words:
        expanded.append(word)
        seen.add(word.lower())
        # Tier 1: static dictionary
        stem = _SPANISH_STEM_MAP.get(word.lower())
        if stem and stem.lower() not in seen:
            expanded.append(stem)
            seen.add(stem.lower())
            continue
        # Tier 2: Snowball stemmer
        stemmer = _get_snowball_stemmer()
        if stemmer:
            stemmed = stemmer.stem(word.lower())
            if stemmed != word.lower() and stemmed not in seen:
                expanded.append(stemmed)
                seen.add(stemmed)
    return " ".join(expanded)


# Words that indicate the LLM is misusing person_filter for topics/concepts
_NOT_PERSON_KEYWORDS = {
    "política", "politica", "privacidad", "protección", "proteccion",
    "datos", "documento", "documentos", "cumplimiento", "compliance",
    "factura", "facturas", "contrato", "contratos", "nómina", "nomina",
    "informe", "informes", "laboral", "fiscal", "legal", "mercantil",
    "servicio", "servicios", "análisis", "analisis", "búsqueda", "busqueda",
    "sistema", "empresa", "departamento", "ley", "artículo", "articulo",
    "normativa", "reglamento", "expediente", "acta", "presupuesto",
    "seguridad", "salud", "médico", "medico", "tratamiento", "rgpd",
}


def _sanitize_person_filter(value: str) -> Optional[str]:
    """Reject person_filter values that are clearly not person names.

    The LLM sometimes passes thematic text (e.g. "protección de datos")
    as person_filter. This function detects and discards those.
    """
    if not value or not value.strip():
        return None

    words = value.strip().split()

    # Person names are 1-4 words max
    if len(words) > 4:
        logger.info(f"🚫 person_filter rejected (too many words): '{value}'")
        return None

    # Check if any word is a known non-person keyword
    value_lower = {w.lower() for w in words}
    overlap = value_lower & _NOT_PERSON_KEYWORDS
    if overlap:
        logger.info(f"🚫 person_filter rejected (topic keywords: {overlap}): '{value}'")
        return None

    return value.strip()


class SmartSearchInput(BaseModel):
    """Input for unified multi-store search."""
    query: str = Field(
        description="Consulta en lenguaje natural. Sé específico: incluye nombres, "
        "fechas, tipos de documento, o referencias legales."
    )
    scope: str = Field(
        default="auto",
        description="Ámbito de búsqueda: 'documents' (solo documentos del tenant), "
        "'legislation' (solo legislación BOE), 'all' (ambos), "
        "'auto' (detección automática basada en la consulta).",
    )
    person_filter: Optional[str] = Field(
        default=None,
        description="Nombre de una PERSONA HUMANA (ej: 'Javier Martínez', 'García López'). "
        "NO uses este campo para temas, conceptos, o tipos de documento. "
        "Solo para nombres propios de personas físicas.",
    )
    domain_filter: Optional[str] = Field(
        default=None,
        description="Filtrar por dominio: legal, fiscal, laboral, medical, etc.",
    )
    folder_filter: Optional[str] = Field(
        default=None,
        description="Filtrar por ruta de carpeta (ej: /Contratos/ACME).",
    )
    date_from: Optional[str] = Field(
        default=None,
        description="Fecha mínima (ISO 8601, ej: '2026-02-01'). Filtra documentos creados desde esta fecha.",
    )
    date_to: Optional[str] = Field(
        default=None,
        description="Fecha máxima (ISO 8601, ej: '2026-03-04'). Filtra documentos creados hasta esta fecha.",
    )
    limit: int = Field(
        default=10, ge=1, le=20,
        description="Número máximo de resultados totales.",
    )


class SmartSearchTool(EmmaTool):
    """Unified multi-store search with entity extraction, graph expansion, and re-ranking."""

    @property
    def name(self) -> str:
        return "smart_search"

    @property
    def description(self) -> str:
        return (
            "Búsqueda inteligente en todos los documentos y conocimiento disponible. "
            "Filtra por tipo, persona, fechas. Para contar documentos usa structural_query."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return SmartSearchInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.weaviate_client import get_weaviate_client
        from app.core.config import settings

        user_roles: List[str] = context.get("user_roles", [])
        user_id: Optional[str] = context.get("user_id")

        query = arguments["query"]
        scope = arguments.get("scope", "auto")
        person_filter = arguments.get("person_filter")
        domain_filter = arguments.get("domain_filter")
        folder_filter = arguments.get("folder_filter")
        date_from = arguments.get("date_from")
        date_to = arguments.get("date_to")
        limit = arguments.get("limit", 10)

        # Validate person_filter — reject non-person values
        if person_filter:
            person_filter = _sanitize_person_filter(person_filter)

        # Get sector config for entity patterns and re-rank weights
        sector_config = context.get("sector_config")
        sector_config_dict = sector_config if isinstance(sector_config, dict) else {}

        # ── Step 1: Entity extraction (regex, ~3ms) ──
        entities = self._extract_entities(query, sector_config_dict)

        # ── Step 1b: Query expansion for BM25 stemming gap ──
        expanded_query = _expand_query_spanish(query)
        if expanded_query != query:
            logger.info(f"🔍 Query expanded: '{query}' → '{expanded_query}'")

        # ── Step 2: Scope detection with confidence scoring ──
        scope_decision = self._detect_scope(scope, query, entities)
        search_docs = scope_decision["search_docs"]
        search_legislation = scope_decision["search_legislation"]
        entity_confidence = self._score_entities(entities)
        scope_decision["entity_confidence"] = entity_confidence
        logger.info(
            "🔎 Scope decision: docs=%s legal=%s confidence=%.2f docs_score=%.2f legal_score=%.2f reason=%s",
            search_docs,
            search_legislation,
            scope_decision["confidence"],
            scope_decision["docs_score"],
            scope_decision["legal_score"],
            scope_decision["reason"],
        )

        # ── Step 3: Filter enrichment from entities ──
        enriched_person = person_filter
        enriched_semantic_type = None
        enriched_domain = domain_filter

        if not enriched_person and "persona" in entities:
            candidate = _sanitize_person_filter(entities["persona"][0])
            if candidate:
                enriched_person = candidate

        for keyword, sem_type in _SEMANTIC_TYPE_KEYWORDS.items():
            if _contains_keyword(query, keyword):
                enriched_semantic_type = sem_type
                break

        # ── Step 4: Graph expansion (optional, ~20-50ms / ~100-200ms for GraphRAG) ──
        graph_doc_ids: Set[str] = set()
        graph_boe_ids: List[str] = []
        graph_context_text: str = ""  # GraphRAG structured subgraph context

        if settings.graphrag_enabled and entities:
            # GraphRAG: multi-hop subgraph extraction (Phase 5)
            graph_context_text, sg_doc_ids, sg_boe_ids = await self._extract_subgraph(
                entities,
            )
            graph_doc_ids.update(sg_doc_ids)
            graph_boe_ids.extend(sg_boe_ids)

        elif settings.smart_search_graph_enabled and entities and sector_config_dict.get("graph_name"):
            # Legacy: flat graph expansion (document IDs only)
            graph_doc_ids, graph_boe_ids = await self._expand_graph(
                query, entities, sector_config_dict
            )

        # Also try person-based graph lookup
        if settings.smart_search_graph_enabled and enriched_person:
            person_doc_ids = await self._get_documents_by_person(enriched_person)
            graph_doc_ids.update(person_doc_ids)

        # ── Step 4b: Query decomposition (Phase 3) ──
        if self._is_complex_query(query):
            sub_queries = await self._decompose_query(query)
            if sub_queries:
                decompose_client = get_weaviate_client()
                decompose_alpha = sector_config_dict.get("hybrid_alpha", 0.5) if sector_config_dict else 0.5

                async def _run_sub_query(sq: Dict[str, str]) -> List[Dict[str, Any]]:
                    sq_scope = sq.get("scope", "auto")
                    sq_results: List[Dict[str, Any]] = []
                    if sq_scope in ("documents", "auto"):
                        sq_results.extend(await self._search_documents(
                            decompose_client, user_roles, user_id, sq["query"], limit, decompose_alpha,
                            person_filter=enriched_person,
                            domain_filter=enriched_domain,
                            semantic_type_filter=enriched_semantic_type,
                            date_from=date_from, date_to=date_to,
                        ))
                    if sq_scope in ("legislation", "auto"):
                        sq_results.extend(await self._search_legislation(
                            decompose_client, sq["query"], min(limit, 8),
                            enriched_domain or "", None,
                        ))
                    return sq_results

                sub_results = await asyncio.gather(*[_run_sub_query(sq) for sq in sub_queries])
                merged = self._merge_and_dedup(list(sub_results))
                if merged:
                    logger.info(
                        f"Decomposed '{query[:60]}' into {len(sub_queries)} sub-queries "
                        f"→ {len(merged)} merged results"
                    )
                    # Trim to limit, assess quality, and format
                    merged = merged[:limit]
                    from .base import ToolResult as _TR
                    from ..retrieval_guard import assess_retrieval_quality as _arq
                    retrieval_quality = await _arq(query=query, results=merged, entities=entities)
                    return self._format_results(
                        query, merged,
                        dropped_filters=dropped_filters,
                        retrieval_quality=retrieval_quality,
                        graph_context=graph_context_text,
                        scope_decision=scope_decision,
                        date_from=date_from,
                        date_to=date_to,
                        person_filter=enriched_person,
                    )

        # ── Step 5: Parallel search (asyncio.gather) ──
        client = get_weaviate_client()
        alpha = sector_config_dict.get("hybrid_alpha", 0.5) if sector_config_dict else 0.5

        search_tasks = []

        dropped_filters: List[str] = []

        # Pre-computed concepts from graph_rag pipeline (Phase 2)
        concepts_result = context.get("_concepts")

        # Collect doc results separately so multi-concept and single-query paths
        # can both feed into the same merge step below.
        pre_fetched_doc_results: Optional[List[Dict[str, Any]]] = None

        if search_docs:
            # Multi-concept search (Phase 2): parallel per-concept hybrid search
            if (
                settings.smart_search_multi_concept
                and concepts_result is not None
                and hasattr(concepts_result, "low_level")
                and concepts_result.low_level
            ):
                logger.info(
                    f"🔀 Multi-concept search: {len(concepts_result.low_level)} concepts"
                )
                pre_fetched_doc_results = await self._multi_concept_search(
                    concepts=concepts_result.low_level,
                    weaviate_client=client,
                    user_roles=user_roles,
                    user_id=user_id,
                    expanded_query=expanded_query,
                    alpha=alpha,
                    enriched_person=enriched_person,
                    enriched_domain=enriched_domain,
                    enriched_semantic_type=enriched_semantic_type,
                    folder_filter=folder_filter,
                    date_from=date_from,
                    date_to=date_to,
                    total_limit=limit,
                )
            else:
                # Original single-query hybrid search (fallback)
                search_tasks.append(self._search_documents(
                    client, user_roles, user_id, expanded_query, limit, alpha,
                    person_filter=enriched_person,
                    domain_filter=enriched_domain,
                    semantic_type_filter=enriched_semantic_type,
                    folder_filter=folder_filter,
                    date_from=date_from,
                    date_to=date_to,
                    dropped_filters=dropped_filters,
                ))

        if search_legislation:
            legislation_domain = enriched_domain or ""
            boe_ids = graph_boe_ids if graph_boe_ids else None
            search_tasks.append(self._search_legislation(
                client, expanded_query, min(limit, 8), legislation_domain, boe_ids
            ))

        if not search_tasks and pre_fetched_doc_results is None:
            return ToolResult(
                output="No se pudo determinar el ámbito de búsqueda.",
                sources=[], data={"result_count": 0},
            )

        # Run remaining search tasks (legislation or single-query docs)
        raw_results_groups = await asyncio.gather(*search_tasks, return_exceptions=True)

        # ── Step 6: Merge + deduplicate ──
        all_results: List[Dict[str, Any]] = []

        # Inject pre-fetched multi-concept doc results
        if pre_fetched_doc_results is not None:
            all_results.extend(pre_fetched_doc_results)

        for group in raw_results_groups:
            if isinstance(group, Exception):
                logger.warning(f"Search sub-task failed: {group}")
                continue
            all_results.extend(group)

        all_results = self._deduplicate(all_results)

        if not all_results:
            return ToolResult(
                output=f"No se encontraron resultados para: '{query}'",
                sources=[], data={"result_count": 0},
            )

        # ── Step 7: Multi-signal re-rank (Phases 3+4, ~1ms) ──
        if settings.smart_search_rerank_enabled:
            rerank_weights = self._get_rerank_weights(sector_config_dict)
            graph_rag_data = context.get("_graph_rag_data")
            all_results = _rerank_results(
                all_results, graph_doc_ids, entities, rerank_weights,
                graph_rag_data=graph_rag_data,
            )

        # ── Step 7b: Cross-encoder re-rank (neural, ~50-100ms) ──
        if settings.smart_search_cross_encoder_enabled:
            try:
                from app.agents.langgraph.reranker import get_reranker
                reranker = get_reranker(model_name=settings.smart_search_cross_encoder_model)
                all_results = reranker.rerank(
                    query=query,
                    results=all_results,
                    top_k=limit,
                    heuristic_weight=1.0 - settings.smart_search_cross_encoder_weight,
                )
            except Exception as e:
                logger.warning(f"Cross-encoder reranking failed (non-fatal): {e}")

        # Trim to requested limit
        all_results = all_results[:limit]

        # ── Step 7c: Parent-child expansion (swap content → parent_content) ──
        seen_parents: set = set()
        expanded_results: List[Dict[str, Any]] = []
        for r in all_results:
            parent_content = (r.get("metadata") or {}).get("parent_content") or r.get("parent_content")
            parent_id = (r.get("metadata") or {}).get("parent_chunk_id") or r.get("parent_chunk_id")
            if parent_content and parent_id:
                if parent_id in seen_parents:
                    continue  # Dedup: one parent per unique parent_chunk_id
                seen_parents.add(parent_id)
                r["content"] = parent_content[:1500]  # Use parent for LLM context
            expanded_results.append(r)
        all_results = expanded_results if expanded_results else all_results

        # ── Step 7d: Retrieval quality assessment ──
        from ..retrieval_guard import assess_retrieval_quality
        retrieval_quality = await assess_retrieval_quality(
            query=query, results=all_results, entities=entities,
        )

        # ── Step 8: Format for LLM ──
        return self._format_results(
            query, all_results,
            dropped_filters=dropped_filters,
            retrieval_quality=retrieval_quality,
            graph_context=graph_context_text,
            scope_decision=scope_decision,
            date_from=date_from,
            date_to=date_to,
            person_filter=enriched_person,
        )

    # ─── Private helpers ──────────────────────────────────────────────

    def _extract_entities(
        self, query: str, sector_config: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """Extract entities using unified patterns (all domains merged)."""
        from app.agents.langgraph.sectors.entity_extractor import extract_entities

        patterns = sector_config.get("entity_patterns", {})
        if not patterns:
            from app.agents.langgraph.sectors.config import UNIFIED_ENTITY_PATTERNS
            patterns = UNIFIED_ENTITY_PATTERNS

        return extract_entities(query, patterns) if patterns else {}

    def _detect_scope(
        self, scope: str, query: str, entities: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Determine search scope with confidence scoring and controlled fallback."""
        if scope == "documents":
            return {
                "search_docs": True,
                "search_legislation": False,
                "docs_score": 1.0,
                "legal_score": 0.0,
                "confidence": 1.0,
                "reason": "explicit_scope_documents",
            }
        if scope == "legislation":
            return {
                "search_docs": False,
                "search_legislation": True,
                "docs_score": 0.0,
                "legal_score": 1.0,
                "confidence": 1.0,
                "reason": "explicit_scope_legislation",
            }
        if scope == "all":
            return {
                "search_docs": True,
                "search_legislation": True,
                "docs_score": 0.8,
                "legal_score": 0.8,
                "confidence": 1.0,
                "reason": "explicit_scope_all",
            }

        # scope == "auto" — weighted signals
        legal_kw = _count_keyword_matches(query, _LEGISLATION_KEYWORDS)
        docs_kw = _count_keyword_matches(query, _DOCUMENT_KEYWORDS)
        legal_entity = int(bool(entities.get("ley"))) + int(bool(entities.get("articulo"))) + int(bool(entities.get("boe")))
        docs_entity = (
            int(bool(entities.get("persona")))
            + int(bool(entities.get("nif")))
            + int(bool(entities.get("fecha")))
            + int(bool(entities.get("importe")))
            + int(bool(entities.get("referencia")))
        )

        legal_score = min(1.0, (0.18 * legal_kw) + (0.22 * legal_entity))
        docs_score = min(1.0, (0.15 * docs_kw) + (0.20 * docs_entity))

        if docs_score == 0.0 and legal_score == 0.0:
            return {
                "search_docs": True,
                "search_legislation": True,
                "docs_score": 0.0,
                "legal_score": 0.0,
                "confidence": 0.2,
                "reason": "no_scope_signals",
            }

        # Mixed explicit evidence on both sides: preserve recall querying both.
        # Exception: "documentos de/sobre X" with only weak legal lexical hints
        # should stay in documents scope (e.g., "documentos de normativa interna").
        q_norm = _normalize_for_match(query)
        doc_request_context = any(p in q_norm for p in _DOC_REQUEST_PATTERNS)
        if doc_request_context and docs_kw > 0 and legal_entity == 0 and legal_kw <= 1:
            return {
                "search_docs": True,
                "search_legislation": False,
                "docs_score": docs_score,
                "legal_score": legal_score,
                "confidence": min(1.0, docs_score + 0.2),
                "reason": "doc_request_context_override",
            }

        if (docs_kw + docs_entity) > 0 and (legal_kw + legal_entity) > 0:
            return {
                "search_docs": True,
                "search_legislation": True,
                "docs_score": docs_score,
                "legal_score": legal_score,
                "confidence": min(1.0, max(docs_score, legal_score)),
                "reason": "mixed_scope_signals",
            }

        diff = abs(docs_score - legal_score)
        max_score = max(docs_score, legal_score)
        confidence = min(1.0, (0.55 * max_score) + (0.45 * diff))

        # Low confidence / mixed evidence: query both scopes to preserve recall.
        if confidence < _SCOPE_LOW_CONFIDENCE or max_score < _SCOPE_MIN_SIGNAL or diff < _SCOPE_MARGIN:
            return {
                "search_docs": True,
                "search_legislation": True,
                "docs_score": docs_score,
                "legal_score": legal_score,
                "confidence": confidence,
                "reason": "low_confidence_fallback_all",
            }

        search_docs = docs_score > legal_score
        return {
            "search_docs": search_docs,
            "search_legislation": not search_docs,
            "docs_score": docs_score,
            "legal_score": legal_score,
            "confidence": confidence,
            "reason": "high_confidence_auto_scope",
        }

    def _score_entities(self, entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """Compute lightweight confidence for extracted entities."""
        if not entities:
            return {"overall": 0.0, "by_type": {}, "count": 0}

        by_type: Dict[str, float] = {}
        weighted_sum = 0.0
        total_values = 0

        for entity_type, values in entities.items():
            if not values:
                continue
            total_values += len(values)

            if entity_type in {"ley", "articulo", "boe", "nif", "fecha", "importe"}:
                conf = 0.9
            elif entity_type in {"persona", "referencia"}:
                conf = 0.75
            else:
                conf = 0.7

            by_type[entity_type] = conf
            weighted_sum += conf * len(values)

        overall = (weighted_sum / total_values) if total_values else 0.0
        return {"overall": round(overall, 3), "by_type": by_type, "count": total_values}

    async def _extract_subgraph(
        self,
        entities: Dict[str, List[str]],
    ) -> tuple:
        """Extract multi-hop subgraph via GraphRAG (Phase 5).

        Returns:
            (graph_context_text, doc_ids, boe_ids) — formatted text, doc IDs for
            re-ranking, BOE IDs for legislation filtering.
        """
        try:
            from app.clients.knowledge_tree_client import get_knowledge_tree_client
            from app.core.config import settings
            from .subgraph_formatter import format_subgraph

            client = get_knowledge_tree_client()

            # Build entity seeds from extracted entities
            seeds = []
            for etype, values in entities.items():
                for val in values[:3]:
                    seeds.append({"value": val, "type": etype})

            if not seeds:
                return "", set(), []

            subgraph = await client.extract_subgraph(
                entities=seeds,
                max_hops=settings.graphrag_max_hops,
                max_nodes=settings.graphrag_max_nodes,
                include_legal=settings.graphrag_include_legal,
            )

            nodes = subgraph.get("nodes", [])
            if not nodes:
                return "", set(), []

            # Extract doc IDs and BOE IDs for re-ranking/filtering
            doc_ids = {
                n["properties"]["document_id"]
                for n in nodes
                if n.get("properties", {}).get("document_id")
            }
            boe_ids = [
                n["properties"]["boe_id"]
                for n in nodes
                if n.get("properties", {}).get("boe_id")
            ]

            # Format for LLM
            context_text = format_subgraph(
                subgraph, token_budget=settings.graphrag_token_budget,
            ) or ""

            logger.info(
                f"GraphRAG: {len(nodes)} nodes, {len(subgraph.get('edges', []))} edges, "
                f"{len(doc_ids)} docs, {len(boe_ids)} laws "
                f"({subgraph.get('latency_ms', 0)}ms)"
            )

            return context_text, doc_ids, boe_ids

        except Exception as e:
            logger.warning(f"GraphRAG subgraph extraction failed (non-fatal): {e}")
            return "", set(), []

    async def _expand_graph(
        self,
        query: str,
        entities: Dict[str, List[str]],
        sector_config: Dict[str, Any],
    ) -> tuple[Set[str], List[str]]:
        """Expand context via FalkorDB knowledge graph. Returns (doc_ids, boe_ids)."""
        doc_ids: Set[str] = set()
        boe_ids: List[str] = []

        try:
            from app.agents.langgraph.sectors.graph_expander import expand_with_sector_graph

            graph_result = await expand_with_sector_graph(
                query=query,
                entities=entities,
                sector_config=sector_config,
            )

            # Include document IDs from entity lookups (Phase 1)
            for did in graph_result.get("expanded_doc_ids", []):
                if did:
                    doc_ids.add(did)

            # Include document IDs and BOE IDs from subgraph nodes (Phase 2)
            for entity in graph_result.get("related_entities", []):
                if isinstance(entity, dict):
                    did = entity.get("document_id") or entity.get("doc_id", "")
                    if did:
                        doc_ids.add(did)
                    bid = entity.get("boe_id", "")
                    if bid and bid not in boe_ids:
                        boe_ids.append(bid)

        except Exception as e:
            logger.warning(f"Graph expansion failed (non-fatal): {e}")

        return doc_ids, boe_ids

    async def _multi_concept_search(
        self,
        concepts: list,
        weaviate_client: Any,
        user_roles: List[str],
        user_id: Optional[str],
        expanded_query: str,
        alpha: float,
        enriched_person: Optional[str],
        enriched_domain: Optional[str],
        enriched_semantic_type: Optional[str],
        folder_filter: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
        total_limit: int,
    ) -> List[Dict[str, Any]]:
        """Run independent hybrid search per concept, merge + dedup.

        For each low-level concept, runs hybrid_search with the concept as the
        query. Results are merged and deduplicated by document_id, keeping the
        highest score per document.
        """
        if not concepts:
            return []

        per_concept_limit = max(3, total_limit // len(concepts))
        tasks = []
        for concept in concepts:
            tasks.append(
                weaviate_client.hybrid_search(
                    user_roles=user_roles,
                    user_id=user_id,
                    query=concept,
                    limit=per_concept_limit,
                    alpha=alpha,
                    person_filter=enriched_person,
                    domain_filter=enriched_domain,
                    semantic_type_filter=enriched_semantic_type,
                    folder_filter=folder_filter,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge + dedup by document_id, keep highest score
        merged: Dict[str, Any] = {}
        for result_list in results:
            if isinstance(result_list, Exception):
                logger.warning(f"Multi-concept search partial failure: {result_list}")
                continue
            if not isinstance(result_list, list):
                continue
            for r in result_list:
                doc_id = r.document_id if hasattr(r, "document_id") else r.get("document_id", "")
                if not doc_id:
                    continue
                r_score = r.score if hasattr(r, "score") else r.get("score", 0)
                existing_score = 0.0
                if doc_id in merged:
                    ex = merged[doc_id]
                    existing_score = ex.score if hasattr(ex, "score") else ex.get("score", 0)
                if doc_id not in merged or r_score > existing_score:
                    merged[doc_id] = r

        deduped = sorted(
            merged.values(),
            key=lambda d: d.score if hasattr(d, "score") else d.get("score", 0),
            reverse=True,
        )

        # Convert SearchResult objects to dicts (same format as _search_documents)
        formatted = []
        for r in deduped[:total_limit]:
            if hasattr(r, "document_id"):
                # SearchResult object
                formatted.append({
                    "document_id": r.document_id,
                    "title": r.metadata.get("title", "Sin título"),
                    "content": r.content[:500] if r.content else "",
                    "score": r.score,
                    "type": "tenant_document",
                    "quality_score": r.metadata.get("quality_score", 0.0),
                    "domain": r.metadata.get("domain", ""),
                    "semantic_type": r.metadata.get("semantic_type", ""),
                    "associated_person": r.metadata.get("associated_person", ""),
                    "created_at": r.metadata.get("created_at", ""),
                    "folder_path": r.metadata.get("folder_path", ""),
                    "document_type": r.metadata.get("document_type", ""),
                    "tags": r.metadata.get("tags", []),
                    "chunk_index": r.metadata.get("chunk_index"),
                    "page_number": r.metadata.get("page_number"),
                    "excerpt": (r.content[:200] if r.content else ""),
                })
            else:
                formatted.append(r)

        return formatted

    async def _get_documents_by_person(
        self, person_name: str
    ) -> Set[str]:
        """Get document IDs linked to a person via knowledge graph."""
        doc_ids: Set[str] = set()
        try:
            from app.clients.knowledge_tree_client import get_knowledge_tree_client

            client = get_knowledge_tree_client()
            result = await client.get_documents_by_person(person_name)
            doc_ids.update(result)
        except Exception as e:
            logger.debug(f"Person graph lookup skipped: {e}")
        return doc_ids

    async def _search_documents(
        self,
        client: Any,
        user_roles: List[str],
        user_id: Optional[str],
        query: str,
        limit: int,
        alpha: float,
        person_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        semantic_type_filter: Optional[str] = None,
        folder_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        dropped_filters: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search tenant documents via Weaviate hybrid search.

        Implements enrichment-filter fallback: if enrichment filters
        (semantic_type, domain, person) yield 0 results, retries without
        them so that un-enriched collections still return useful data.

        dropped_filters: mutable list — names of filters that had to be
        dropped during progressive fallback (e.g. ["person", "domain"]).
        """
        if dropped_filters is None:
            dropped_filters = []
        has_enrichment = bool(person_filter or domain_filter or semantic_type_filter)

        if has_enrichment:
            filters_desc = ", ".join(
                f"{k}={v}" for k, v in [
                    ("person", person_filter), ("domain", domain_filter),
                    ("semantic_type", semantic_type_filter),
                ] if v
            )
            logger.info(f"🔍 SmartSearch enrichment filters: {filters_desc}")

        try:
            results = await client.hybrid_search(
                query=query,
                user_roles=user_roles,
                user_id=user_id,
                limit=limit,
                alpha=alpha,
                person_filter=person_filter,
                domain_filter=domain_filter,
                semantic_type_filter=semantic_type_filter,
                folder_filter=folder_filter,
                date_from=date_from,
                date_to=date_to,
            )

            if has_enrichment:
                logger.info(f"✅ Enrichment search returned {len(results)} results")

            # Progressive fallback: drop filters one by one (least reliable first)
            # Priority order to drop: person → domain → semantic_type
            if not results and has_enrichment:
                # Attempt 1: Drop person_filter (often empty in Weaviate)
                if person_filter:
                    logger.info(f"🔄 0 results with person={person_filter} — retrying without person filter")
                    dropped_filters.append(f"person={person_filter}")
                    results = await client.hybrid_search(
                        query=query,
                        user_roles=user_roles,
                        user_id=user_id,
                        limit=limit,
                        alpha=alpha,
                        domain_filter=domain_filter,
                        semantic_type_filter=semantic_type_filter,
                        folder_filter=folder_filter,
                        date_from=date_from,
                        date_to=date_to,
                    )
                    if results:
                        logger.info(f"✅ Without person filter: {len(results)} results")

                # Attempt 2: Also drop domain_filter
                if not results and domain_filter:
                    logger.info(f"🔄 0 results with domain={domain_filter} — retrying with semantic_type only")
                    dropped_filters.append(f"domain={domain_filter}")
                    results = await client.hybrid_search(
                        query=query,
                        user_roles=user_roles,
                        user_id=user_id,
                        limit=limit,
                        alpha=alpha,
                        semantic_type_filter=semantic_type_filter,
                        folder_filter=folder_filter,
                        date_from=date_from,
                        date_to=date_to,
                    )
                    if results:
                        logger.info(f"✅ With semantic_type only: {len(results)} results")

                # Attempt 3: Drop all enrichment filters
                if not results:
                    logger.info("🔄 All enrichment filters returned 0 — retrying without any filters")
                    results = await client.hybrid_search(
                        query=query,
                        user_roles=user_roles,
                        user_id=user_id,
                        limit=limit,
                        alpha=alpha,
                        folder_filter=folder_filter,
                        date_from=date_from,
                        date_to=date_to,
                    )

            return [
                {
                    "document_id": r.document_id,
                    "title": r.metadata.get("title", "Sin título"),
                    "content": r.content[:500] if r.content else "",
                    "score": r.score,
                    "type": "tenant_document",
                    "quality_score": r.metadata.get("quality_score", 0.0),
                    "domain": r.metadata.get("domain", ""),
                    "semantic_type": r.metadata.get("semantic_type", ""),
                    "associated_person": r.metadata.get("associated_person", ""),
                    "created_at": r.metadata.get("created_at", ""),
                    "folder_path": r.metadata.get("folder_path", ""),
                    "document_type": r.metadata.get("document_type", ""),
                    "tags": r.metadata.get("tags", []),
                    # Chunk-level source attribution
                    "chunk_index": r.metadata.get("chunk_index"),
                    "page_number": r.metadata.get("page_number"),
                    "excerpt": (r.content[:200] if r.content else ""),
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []

    async def _search_legislation(
        self,
        client: Any,
        query: str,
        limit: int,
        domain: str,
        boe_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search BOE PublicKnowledge legislation."""
        try:
            results = await client.search_public_knowledge(
                query=query,
                limit=limit,
                domain=domain,
                boe_ids=boe_ids,
            )
            return [
                {
                    "document_id": r.document_id or r.metadata.get("boe_id", ""),
                    "title": r.metadata.get("title", r.metadata.get("law_name", "Legislación")),
                    "content": r.content[:600] if r.content else "",
                    "score": r.score,
                    "type": "legislation",
                    "quality_score": 0.8,  # Legislation has inherent quality
                    "boe_id": r.metadata.get("boe_id", ""),
                    "article": r.metadata.get("article_number", ""),
                    "domain": r.metadata.get("category", domain),
                    "semantic_type": "legislacion",
                    "associated_person": "",
                    "created_at": "",
                    "folder_path": "",
                    "document_type": "legislation",
                    "tags": r.metadata.get("topics", []),
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Legislation search failed: {e}")
            return []

    def _deduplicate(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate results in two passes, keeping highest score per doc.

        Pass 1 – by ``document_id``: collapses different chunks of the same
        document into a single result.

        Pass 2 – by ``(title, folder_path)``: collapses copies of the same
        physical file that were indexed with different ``document_id`` values
        (e.g. Google Drive allows multiple files with the same name).  This
        prevents the LLM from over-counting documents.
        """
        # --- Pass 1: dedup by document_id ---
        by_docid: Dict[str, Dict[str, Any]] = {}
        for r in results:
            doc_id = r.get("document_id", "")
            if not doc_id:
                by_docid[str(id(r))] = r
                continue
            score = r.get("score") or 0
            if doc_id not in by_docid or score > (by_docid[doc_id].get("score") or 0):
                by_docid[doc_id] = r

        # --- Pass 2: dedup by title + folder_path ---
        by_title: Dict[str, Dict[str, Any]] = {}
        for r in by_docid.values():
            title = (r.get("title") or "").strip()
            folder = (r.get("folder_path") or "").strip()
            key = f"{title}||{folder}" if title else str(id(r))
            score = r.get("score") or 0
            if key not in by_title or score > (by_title[key].get("score") or 0):
                by_title[key] = r

        return sorted(by_title.values(), key=lambda r: r.get("score") or 0, reverse=True)

    def _get_rerank_weights(self, sector_config: Dict[str, Any]) -> Dict[str, float]:
        """Get re-rank weights from sector config or defaults."""
        return sector_config.get("rerank_weights", _DEFAULT_RERANK_WEIGHTS)

    def _is_complex_query(self, query: str) -> bool:
        """Detect queries that would benefit from decomposition."""
        if len(query) < 80:
            return False

        query_lower = query.lower()

        # Scope mixing: document + legislation keywords
        has_doc = any(kw in query_lower for kw in ("contrato", "factura", "nómina", "documento"))
        has_leg = any(kw in query_lower for kw in ("ley", "estatuto", "código", "real decreto", "artículo", "boe"))
        if has_doc and has_leg:
            return True

        # Conjunction with distinct topics
        conjunctions = (" y ", " además ", " también ", " por otro lado ", " comparar ", " compara ")
        if any(c in query_lower for c in conjunctions) and len(query) > 100:
            return True

        return False

    async def _decompose_query(self, query: str) -> List[Dict[str, str]]:
        """Decompose complex query into sub-queries via PLANNER LLM (~100ms)."""
        try:
            from app.services.langfuse_prompt_client import get_langfuse_prompt_client
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_planner_model

            client = get_langfuse_prompt_client()
            cached = await client.get_prompt("emma_smart_search_decompose")
            prompt_content = cached.content.replace("{query}", query)

            model = get_planner_model().bind(temperature=0.1, max_tokens=300)
            response = await model.ainvoke([
                SystemMessage(content=prompt_content),
                HumanMessage(content=f"/no_think\n{query}"),
            ])

            import json as _json
            content = (response.content or "").strip()
            # Strip thinking tags if present
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            sub_queries = _json.loads(content)

            if isinstance(sub_queries, list) and len(sub_queries) >= 2:
                return sub_queries[:3]  # Cap at 3
        except Exception as e:
            logger.warning(f"Query decomposition failed: {e}")

        return []  # Fallback: no decomposition

    def _merge_and_dedup(self, result_sets: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Merge results from multiple sub-queries, dedup by document_id."""
        seen: Set[str] = set()
        merged: List[Dict[str, Any]] = []
        for results in result_sets:
            for r in results:
                doc_id = r.get("document_id", "")
                key = doc_id or r.get("title", "")
                if key and key not in seen:
                    seen.add(key)
                    merged.append(r)
        # Sort by score descending
        merged.sort(key=lambda r: r.get("score") or 0, reverse=True)
        return merged

    def _evaluate_results(
        self,
        query: str,
        results: List[Dict[str, Any]],
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        person_filter: Optional[str] = None,
        dropped_filters: Optional[List[str]] = None,
    ) -> str:
        """Inline evaluation of search results for immediate agent feedback.

        Heuristic checks (~0ms, no LLM):
        1. Temporal mismatch — dates in results vs requested range
        2. Entity coverage — query entities in result titles/content
        3. Relevance distribution — average score, single-source bias
        4. Filter drop notice — which filters were dropped
        """
        feedback = []

        # 1. Temporal check
        if date_from or date_to:
            result_dates = [r.get("created_at", "") for r in results if r.get("created_at")]
            if result_dates:
                in_range = sum(1 for d in result_dates
                               if (not date_from or d >= date_from) and (not date_to or d <= date_to))
                if in_range == 0:
                    feedback.append(
                        f"- Temporal: Filtro {date_from or '?'}→{date_to or '?'} "
                        f"pero 0 resultados en rango. Reformula con otros términos."
                    )
                elif in_range < len(result_dates):
                    feedback.append(
                        f"- Temporal: {in_range}/{len(result_dates)} resultados en el rango solicitado."
                    )

        # 2. Entity coverage
        if person_filter and results:
            matches = sum(1 for r in results
                          if person_filter.lower() in (r.get("title", "") + r.get("content", "")).lower())
            if matches == 0:
                feedback.append(f"- Persona/Entidad: '{person_filter}' no aparece en ningún resultado.")

        # 3. Relevance
        if results:
            scores = [r.get("score") or 0 for r in results]
            avg_score = sum(scores) / len(scores) if scores else 0
            if avg_score < 0.4:
                feedback.append(
                    f"- Relevancia: promedio {avg_score:.2f} (bajo). "
                    f"Reformula con términos más específicos."
                )
            doc_ids = set(r.get("document_id", "") for r in results if r.get("document_id"))
            if len(doc_ids) == 1 and len(results) > 1:
                feedback.append("- Fuente única: todos los resultados del mismo documento.")

        # 4. Filter drops
        if dropped_filters:
            feedback.append(f"- Filtros descartados (sin resultados): {', '.join(dropped_filters)}.")

        if not feedback:
            return ""

        return "\n⚠️ EVALUACIÓN DE RESULTADOS:\n" + "\n".join(feedback)

    def _format_results(
        self, query: str, results: List[Dict[str, Any]],
        dropped_filters: Optional[List[str]] = None,
        retrieval_quality: Any = None,
        graph_context: str = "",
        scope_decision: Optional[Dict[str, Any]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        person_filter: Optional[str] = None,
    ) -> ToolResult:
        """Format unified results for LLM consumption."""
        doc_count = sum(1 for r in results if r["type"] == "tenant_document")
        leg_count = sum(1 for r in results if r["type"] == "legislation")

        parts = []

        # Prepend GraphRAG subgraph context if available
        if graph_context:
            parts.append(graph_context)
            parts.append("")  # Blank line separator

        parts.append(f"Se encontraron {len(results)} resultados")
        if doc_count and leg_count:
            parts[0] += f" ({doc_count} documentos, {leg_count} legislación)"
        parts[0] += f" para '{query}':\n"

        # Warn LLM about dropped filters so it doesn't misattribute results
        if dropped_filters:
            dropped_desc = ", ".join(dropped_filters)
            parts.append(
                f"⚠️ NOTA: No se encontraron resultados con los filtros: {dropped_desc}. "
                f"Los resultados mostrados son generales (sin esos filtros). "
                f"Si el usuario preguntó por una persona específica, indica que NO se encontraron "
                f"documentos de ese tipo asociados a esa persona.\n"
            )

        sources = []

        for i, r in enumerate(results, 1):
            title = r["title"]
            score = r.get("score", 0)
            doc_id = r.get("document_id", "")
            content = r.get("content", "")

            if r["type"] == "legislation":
                boe_id = r.get("boe_id", "")
                article = r.get("article", "")
                header = f"**{i}. [LEY] {title}**"
                if boe_id:
                    header += f" ({boe_id})"
                if article:
                    header += f" — Art. {article}"
                parts.append(header)
            else:
                parts.append(f"**{i}. {title}** (relevancia: {score:.2f})")
                if doc_id:
                    parts.append(f"   ID: {doc_id}")

            if content:
                parts.append(f"   Contenido: {content}")
            parts.append("")

            source = {
                "title": title,
                "document_id": doc_id,
                "score": score,
                "type": r["type"],
            }
            if r["type"] == "legislation":
                source["boe_id"] = r.get("boe_id", "")
                source["article"] = r.get("article", "")
            else:
                source["metadata"] = {
                    k: v for k, v in r.items()
                    if k in ("document_type", "created_at", "tags", "folder_path")
                }
            # Chunk-level source attribution (page, excerpt)
            if r.get("page_number") is not None:
                source["page"] = r["page_number"]
            if r.get("chunk_index") is not None:
                source["chunk_index"] = r["chunk_index"]
            if r.get("excerpt"):
                source["excerpt"] = r["excerpt"]
            sources.append(source)

        # Inject retrieval guard warnings into output
        if retrieval_quality and retrieval_quality.warnings:
            parts.append("---")
            for w in retrieval_quality.warnings:
                parts.append(w)

        # Inline retrieval feedback (Phase 2 Retrieval Intelligence)
        from app.core.config import settings as _settings
        if _settings.smart_search_feedback_enabled:
            eval_text = self._evaluate_results(
                query=query, results=results,
                date_from=date_from, date_to=date_to,
                person_filter=person_filter, dropped_filters=dropped_filters,
            )
            if eval_text:
                parts.append(eval_text)

        data = {"result_count": len(results), "doc_count": doc_count, "leg_count": leg_count}
        if retrieval_quality:
            data["retrieval_quality"] = retrieval_quality.to_dict()
        if scope_decision:
            data["scope_decision"] = scope_decision

        return ToolResult(
            output="\n".join(parts),
            sources=sources,
            data=data,
        )


# ─── Multi-Signal Re-Ranking (Phase 4) ──────────────────────────────


def _rerank_results(
    results: List[Dict[str, Any]],
    graph_document_ids: Set[str],
    query_entities: Dict[str, List[str]],
    weights: Dict[str, float],
    graph_rag_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Re-rank results using 5 signals with sector-tunable weights.

    Signals:
      - similarity (0-1): Raw hybrid score from Weaviate
      - quality (0-1): quality_score from DocumentIntelligence
      - graph (0-1): Continuous score from Graph RAG provenance (Phase 2),
                     or binary 0/1 from entity match (backward compat)
      - recency (0-1): Exponential decay, half-life 90 days
      - entity (0-1): Fraction of query entities matching document metadata
    """
    w_sim = weights.get("similarity", 0.40)
    w_qual = weights.get("quality", 0.20)
    w_graph = weights.get("graph", 0.20)
    w_rec = weights.get("recency", 0.10)
    w_ent = weights.get("entity", 0.10)

    now = datetime.now(timezone.utc)
    half_life_days = 90.0

    # Flatten all entity values for matching
    all_entity_values = []
    for values in query_entities.values():
        all_entity_values.extend(v.lower() for v in values)

    for result in results:
        # Signal 1: Similarity (normalize to 0-1 range)
        raw_score = result.get("score") or 0.0
        sim_score = min(max(float(raw_score), 0.0), 1.0)

        # Signal 2: Quality
        qual_score = float(result.get("quality_score", 0.0) or 0.0)

        # Signal 3: Graph presence — continuous score from Graph RAG (Phase 2)
        doc_id = result.get("document_id", "")
        if graph_rag_data and graph_rag_data.get("expanded_doc_ids"):
            graph_avg = float(graph_rag_data.get("avg_score", 0.5))
            graph_doc_set = set(graph_rag_data["expanded_doc_ids"])
            if doc_id in graph_doc_set:
                # Continuous score from graph_rag (confidence-aware via pre-filter)
                graph_score = graph_avg
            elif doc_id in graph_document_ids:
                graph_score = 1.0  # Binary fallback from entity match
            else:
                graph_score = 0.0
        else:
            # Binary fallback (backward compat)
            graph_score = 1.0 if doc_id in graph_document_ids else 0.0

        # Signal 4: Recency (exponential decay)
        rec_score = 0.5  # default for unknown dates
        created_str = result.get("created_at", "")
        if created_str:
            try:
                if isinstance(created_str, datetime):
                    created = created_str
                else:
                    created = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days_old = (now - created).total_seconds() / 86400.0
                rec_score = math.exp(-0.693 * days_old / half_life_days)
            except (ValueError, TypeError):
                pass

        # Signal 5: Entity match
        ent_score = 0.0
        if all_entity_values:
            matches = 0
            # Check entity values against document metadata text
            match_fields = [
                str(result.get("title", "")),
                str(result.get("associated_person", "")),
                str(result.get("domain", "")),
                str(result.get("semantic_type", "")),
                str(result.get("folder_path", "")),
                str(result.get("content", "")),
            ]
            combined_text = " ".join(match_fields).lower()
            for ev in all_entity_values:
                if ev in combined_text:
                    matches += 1
            ent_score = matches / len(all_entity_values)

        # Composite score
        composite = (
            w_sim * sim_score
            + w_qual * qual_score
            + w_graph * graph_score
            + w_rec * rec_score
            + w_ent * ent_score
        )
        result["_rerank_score"] = composite
        result["score"] = composite  # Replace raw score with composite

    results.sort(key=lambda r: r.get("_rerank_score", 0), reverse=True)
    return results
