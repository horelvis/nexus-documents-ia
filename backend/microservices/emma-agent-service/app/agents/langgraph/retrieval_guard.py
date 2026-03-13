"""
Retrieval Guard — Post-retrieval quality assessment for anti-hallucination.

Evaluates search results AFTER reranking, BEFORE they reach the LLM.
Pure score-based assessment — no entity analysis (that's SmartSearch's job).

Detects:
  - No results at all
  - Very low relevance scores (top result below threshold)
  - Single-source dependency (all results from one document)

Confidence levels:
  LOW:    0 results OR top_score < threshold
  MEDIUM: single source (all results from same doc)
  HIGH:   everything else (default — don't interfere)

Design: conservative, CPU-only (~1ms), no LLM. LOW triggers Quality Gate 4
which blocks terminate and forces a retry. MEDIUM only injects warnings.

Pipeline position:
  Entity Extraction → Search → Rerank → [RETRIEVAL GUARD] → Format → LLM
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Hardcoded fallback warnings ───
_FALLBACK_LOW_QUALITY = (
    "⚠️ CALIDAD BAJA: Los resultados tienen baja relevancia respecto a la consulta. "
    "Considera reformular la búsqueda o indicar al usuario que la información es limitada."
)
_FALLBACK_SINGLE_SOURCE = (
    "⚠️ FUENTE ÚNICA: Todos los resultados provienen del mismo documento. "
    "Indica esta limitación al usuario."
)
_FALLBACK_CORRECTIVE = (
    "La calidad de los resultados de búsqueda es baja. "
    "Antes de responder, intenta: "
    "1) Reformular la búsqueda con términos más específicos, "
    "2) Probar smart_search con otros filtros o web_search, "
    "3) Si no hay información relevante, indícalo claramente al usuario "
    "sin inventar datos."
)


@dataclass
class RetrievalQuality:
    """Assessment of retrieval quality for a search result set."""

    top_score: float = 0.0
    mean_score: float = 0.0
    result_count: int = 0
    unique_docs: int = 0

    confidence: str = "high"  # "high" | "medium" | "low"
    warnings: List[str] = field(default_factory=list)
    corrective_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for ToolResult.data."""
        return {
            "confidence": self.confidence,
            "top_score": round(self.top_score, 3),
            "mean_score": round(self.mean_score, 3),
            "unique_docs": self.unique_docs,
            "result_count": self.result_count,
        }


async def _resolve_warning(prompt_key: str, fallback: str) -> str:
    """Resolve a warning message via Langfuse → YAML → hardcoded fallback."""
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        prompt_client = get_langfuse_prompt_client()
        cached = await prompt_client.get_prompt(prompt_key, fallback=fallback)
        return cached.content.strip() if cached else fallback
    except Exception as e:
        logger.debug(f"Warning resolution failed for '{prompt_key}': {e}")
        return fallback


async def assess_retrieval_quality(
    query: str,
    results: List[Dict[str, Any]],
    entities: Optional[Dict[str, List[str]]] = None,
) -> RetrievalQuality:
    """Assess retrieval quality based on scores and document diversity.

    Args:
        query: Original user query (for logging).
        results: Reranked search results (list of dicts with score, content, etc.).
        entities: Unused — kept for API compatibility with smart_search caller.

    Returns:
        RetrievalQuality with confidence level and warnings.
    """
    rq = RetrievalQuality()
    rq.result_count = len(results)

    # ── No results: always LOW ──
    if not results:
        rq.confidence = "low"
        rq.warnings = [await _resolve_warning("emma_guard_low_quality", _FALLBACK_LOW_QUALITY)]
        rq.corrective_message = await _resolve_warning("emma_guard_corrective", _FALLBACK_CORRECTIVE)
        logger.info("🛡️ Retrieval guard: confidence=low (0 results)")
        return rq

    # ── Core metrics ──
    scores = [(r.get("score") or 0) for r in results]
    rq.top_score = scores[0]
    rq.mean_score = sum(scores) / len(scores)
    rq.unique_docs = len({
        r.get("document_id", "") for r in results if r.get("document_id")
    })

    # ── Evaluate ──
    low_score = rq.top_score < settings.retrieval_guard_low_top_score
    single_source = rq.unique_docs == 1 and rq.result_count > 1

    # ── Build warnings ──
    warnings: List[str] = []

    if low_score:
        warnings.append(await _resolve_warning(
            "emma_guard_low_quality", _FALLBACK_LOW_QUALITY,
        ))

    if single_source:
        warnings.append(await _resolve_warning(
            "emma_guard_single_source", _FALLBACK_SINGLE_SOURCE,
        ))

    rq.warnings = warnings

    # ── Confidence verdict ──
    if low_score:
        rq.confidence = "low"
        rq.corrective_message = await _resolve_warning(
            "emma_guard_corrective", _FALLBACK_CORRECTIVE,
        )
    elif single_source:
        rq.confidence = "medium"
    else:
        rq.confidence = "high"

    logger.info(
        f"🛡️ Retrieval guard: confidence={rq.confidence}, "
        f"top_score={rq.top_score:.3f}, mean_score={rq.mean_score:.3f}, "
        f"unique_docs={rq.unique_docs}, warnings={len(warnings)}"
    )

    return rq
