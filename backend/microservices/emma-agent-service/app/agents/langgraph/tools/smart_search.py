"""
Emma ReAct Agent — SmartSearch Tool

Unified multi-store search that orchestrates 3 data stores:
  1. Weaviate (hybrid vector+keyword) — tenant documents
  2. PublicKnowledge (hybrid) — BOE legislation
  3. Apache AGE (knowledge graph) — entity relationships

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
    "factura", "contrato", "nomina", "nómina", "informe",
    "expediente", "documento", "archivo", "carpeta",
    "acta", "presupuesto", "certificado", "escrito",
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
        description="Filtrar por persona asociada (nombre completo o parcial).",
    )
    domain_filter: Optional[str] = Field(
        default=None,
        description="Filtrar por dominio: legal, fiscal, laboral, medical, etc.",
    )
    folder_filter: Optional[str] = Field(
        default=None,
        description="Filtrar por ruta de carpeta (ej: /Contratos/ACME).",
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
            "Búsqueda inteligente unificada en documentos del usuario Y legislación española (BOE). "
            "Detecta automáticamente qué buscar y filtra por tipo de documento (facturas, contratos, "
            "nóminas, informes, etc.) y por persona. Usa esto para: 'facturas de Javier', "
            "'contratos de 2024', 'nóminas del departamento X', o cualquier búsqueda documental/legal. "
            "Para CONTAR documentos (cuántos hay), usa structural_query en su lugar."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return SmartSearchInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        from app.clients.weaviate_client import get_weaviate_client
        from app.core.config import settings

        tenant_id = context.get("tenant_id", "")
        if not tenant_id:
            return ToolResult.from_error("No tenant_id in context")

        query = arguments["query"]
        scope = arguments.get("scope", "auto")
        person_filter = arguments.get("person_filter")
        domain_filter = arguments.get("domain_filter")
        folder_filter = arguments.get("folder_filter")
        limit = arguments.get("limit", 10)

        # Get sector config for entity patterns and re-rank weights
        sector_config = context.get("sector_config")
        sector_config_dict = sector_config if isinstance(sector_config, dict) else {}

        # ── Step 1: Entity extraction (regex, ~3ms) ──
        entities = self._extract_entities(query, sector_config_dict)

        # ── Step 1b: Query expansion for BM25 stemming gap ──
        expanded_query = _expand_query_spanish(query)
        if expanded_query != query:
            logger.info(f"🔍 Query expanded: '{query}' → '{expanded_query}'")

        # ── Step 2: Scope detection (rules, no LLM) ──
        search_docs, search_legislation = self._detect_scope(scope, query, entities)

        # ── Step 3: Filter enrichment from entities ──
        enriched_person = person_filter
        enriched_semantic_type = None
        enriched_domain = domain_filter

        if not enriched_person and "persona" in entities:
            enriched_person = entities["persona"][0]

        query_lower = query.lower()
        for keyword, sem_type in _SEMANTIC_TYPE_KEYWORDS.items():
            if keyword in query_lower:
                enriched_semantic_type = sem_type
                break

        # ── Step 4: Graph expansion (optional, ~20-50ms) ──
        graph_doc_ids: Set[str] = set()
        graph_boe_ids: List[str] = []

        if settings.smart_search_graph_enabled and entities and sector_config_dict.get("graph_name"):
            graph_doc_ids, graph_boe_ids = await self._expand_graph(
                query, entities, sector_config_dict, tenant_id
            )

        # Also try person-based graph lookup
        if settings.smart_search_graph_enabled and enriched_person:
            person_doc_ids = await self._get_documents_by_person(tenant_id, enriched_person)
            graph_doc_ids.update(person_doc_ids)

        # ── Step 5: Parallel search (asyncio.gather) ──
        client = get_weaviate_client()
        alpha = sector_config_dict.get("hybrid_alpha", 0.5) if sector_config_dict else 0.5

        search_tasks = []

        dropped_filters: List[str] = []

        if search_docs:
            search_tasks.append(self._search_documents(
                client, tenant_id, expanded_query, limit, alpha,
                person_filter=enriched_person,
                domain_filter=enriched_domain,
                semantic_type_filter=enriched_semantic_type,
                folder_filter=folder_filter,
                dropped_filters=dropped_filters,
            ))

        if search_legislation:
            legislation_domain = enriched_domain or ""
            boe_ids = graph_boe_ids if graph_boe_ids else None
            search_tasks.append(self._search_legislation(
                client, expanded_query, min(limit, 8), legislation_domain, boe_ids
            ))

        if not search_tasks:
            return ToolResult(
                output="No se pudo determinar el ámbito de búsqueda.",
                sources=[], data={"result_count": 0},
            )

        raw_results_groups = await asyncio.gather(*search_tasks, return_exceptions=True)

        # ── Step 6: Merge + deduplicate ──
        all_results: List[Dict[str, Any]] = []
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
            all_results = _rerank_results(
                all_results, graph_doc_ids, entities, rerank_weights
            )

        # Trim to requested limit
        all_results = all_results[:limit]

        # ── Step 8: Format for LLM ──
        return self._format_results(query, all_results, dropped_filters=dropped_filters)

    # ─── Private helpers ──────────────────────────────────────────────

    def _extract_entities(
        self, query: str, sector_config: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """Extract entities using sector patterns + generic patterns."""
        from app.agents.langgraph.sectors.entity_extractor import extract_entities

        patterns = sector_config.get("entity_patterns", {})
        if not patterns:
            # Fallback: use documental patterns which cover persona/nif/fecha
            from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS
            documental = SECTOR_CONFIGS.get("documental")
            if documental:
                patterns = documental.entity_patterns

        return extract_entities(query, patterns) if patterns else {}

    def _detect_scope(
        self, scope: str, query: str, entities: Dict[str, List[str]]
    ) -> tuple[bool, bool]:
        """Determine whether to search documents, legislation, or both."""
        if scope == "documents":
            return True, False
        if scope == "legislation":
            return False, True
        if scope == "all":
            return True, True

        # scope == "auto" — heuristic detection
        query_lower = query.lower()
        has_legal = any(kw in query_lower for kw in _LEGISLATION_KEYWORDS)
        has_legal = has_legal or bool(entities.get("ley")) or bool(entities.get("articulo")) or bool(entities.get("boe"))

        has_docs = any(kw in query_lower for kw in _DOCUMENT_KEYWORDS)
        has_docs = has_docs or bool(entities.get("persona")) or bool(entities.get("nif"))

        if has_legal and has_docs:
            return True, True
        if has_legal:
            return False, True
        if has_docs:
            return True, False

        # Default: search documents (most common use case)
        return True, False

    async def _expand_graph(
        self,
        query: str,
        entities: Dict[str, List[str]],
        sector_config: Dict[str, Any],
        tenant_id: str,
    ) -> tuple[Set[str], List[str]]:
        """Expand context via Apache AGE graph. Returns (doc_ids, boe_ids)."""
        doc_ids: Set[str] = set()
        boe_ids: List[str] = []

        try:
            from app.agents.langgraph.sectors.graph_expander import expand_with_sector_graph

            graph_result = await expand_with_sector_graph(
                query=query,
                entities=entities,
                sector_config=sector_config,
                tenant_id=tenant_id,
            )

            for entity in graph_result.get("related_entities", []):
                # Extract document_id from graph nodes
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

    async def _get_documents_by_person(
        self, tenant_id: str, person_name: str
    ) -> Set[str]:
        """Get document IDs linked to a person via knowledge graph."""
        doc_ids: Set[str] = set()
        try:
            from app.clients.knowledge_tree_client import get_knowledge_tree_client

            client = get_knowledge_tree_client()
            result = await client.get_documents_by_person(tenant_id, person_name)
            doc_ids.update(result)
        except Exception as e:
            logger.debug(f"Person graph lookup skipped: {e}")
        return doc_ids

    async def _search_documents(
        self,
        client: Any,
        tenant_id: str,
        query: str,
        limit: int,
        alpha: float,
        person_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        semantic_type_filter: Optional[str] = None,
        folder_filter: Optional[str] = None,
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
                tenant_id=tenant_id,
                query=query,
                limit=limit,
                alpha=alpha,
                person_filter=person_filter,
                domain_filter=domain_filter,
                semantic_type_filter=semantic_type_filter,
                folder_filter=folder_filter,
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
                        tenant_id=tenant_id,
                        query=query,
                        limit=limit,
                        alpha=alpha,
                        domain_filter=domain_filter,
                        semantic_type_filter=semantic_type_filter,
                        folder_filter=folder_filter,
                    )
                    if results:
                        logger.info(f"✅ Without person filter: {len(results)} results")

                # Attempt 2: Also drop domain_filter
                if not results and domain_filter:
                    logger.info(f"🔄 0 results with domain={domain_filter} — retrying with semantic_type only")
                    dropped_filters.append(f"domain={domain_filter}")
                    results = await client.hybrid_search(
                        tenant_id=tenant_id,
                        query=query,
                        limit=limit,
                        alpha=alpha,
                        semantic_type_filter=semantic_type_filter,
                        folder_filter=folder_filter,
                    )
                    if results:
                        logger.info(f"✅ With semantic_type only: {len(results)} results")

                # Attempt 3: Drop all enrichment filters
                if not results:
                    logger.info("🔄 All enrichment filters returned 0 — retrying without any filters")
                    results = await client.hybrid_search(
                        tenant_id=tenant_id,
                        query=query,
                        limit=limit,
                        alpha=alpha,
                        folder_filter=folder_filter,
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

    def _format_results(
        self, query: str, results: List[Dict[str, Any]],
        dropped_filters: Optional[List[str]] = None,
    ) -> ToolResult:
        """Format unified results for LLM consumption."""
        doc_count = sum(1 for r in results if r["type"] == "tenant_document")
        leg_count = sum(1 for r in results if r["type"] == "legislation")

        parts = [f"Se encontraron {len(results)} resultados"]
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
            sources.append(source)

        return ToolResult(
            output="\n".join(parts),
            sources=sources,
            data={"result_count": len(results), "doc_count": doc_count, "leg_count": leg_count},
        )


# ─── Multi-Signal Re-Ranking (Phase 4) ──────────────────────────────


def _rerank_results(
    results: List[Dict[str, Any]],
    graph_document_ids: Set[str],
    query_entities: Dict[str, List[str]],
    weights: Dict[str, float],
) -> List[Dict[str, Any]]:
    """
    Re-rank results using 5 signals with sector-tunable weights.

    Signals:
      - similarity (0-1): Raw hybrid score from Weaviate
      - quality (0-1): quality_score from DocumentIntelligence
      - graph (0 or 1): Whether the document was found via knowledge graph
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

        # Signal 3: Graph presence
        doc_id = result.get("document_id", "")
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
