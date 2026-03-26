"""
Cross-Encoder Reranker for SmartSearch

Adds neural cross-encoder reranking as a post-processing step after the
existing 5-signal heuristic reranking. Cross-encoders evaluate (query, passage)
pairs jointly with full cross-attention, achieving much higher precision than
bi-encoders or heuristic scoring.

Architecture decision: FlashRank on CPU (~5ms/passage) because GPU memory is
fully allocated to SGLang (18.5GB) + BGE-M3/Jina embeddings (2.7GB) = 21.2GB
of 24GB RTX 4090. FlashRank uses ONNX quantized models that run efficiently
on CPU without competing for GPU resources.

Model: ms-marco-MultiBERT-L-12 (multilingual) is required for Spanish legal
text. The default ms-marco-MiniLM-L-12-v2 is English-only (MS MARCO dataset)
and produces unreliable scores for non-English queries.

Pipeline integration:
    SmartSearch._rerank_results() (5-signal, ~1ms)
    → CrossEncoderReranker.rerank() (neural, ~50-150ms for 50 passages)
    → Final combined score: 0.6 * cross_encoder + 0.4 * heuristic

Usage:
    from app.agents.langgraph.reranker import get_reranker

    reranker = get_reranker()
    reranked = reranker.rerank(query, results, top_k=10)
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Singleton
_reranker_instance: Optional["CrossEncoderReranker"] = None

# Default to multilingual model for Spanish legal text
_DEFAULT_MODEL = "ms-marco-MultiBERT-L-12"


class CrossEncoderReranker:
    """Cross-encoder reranker using FlashRank (CPU-optimized ONNX).

    Uses ms-marco-MultiBERT-L-12 (multilingual, ~400MB ONNX) by default
    for Spanish legal text. Loads on first use, reuses the cached model.
    Scores are normalized to [0, 1].
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        self._model_name = model_name
        self._ranker = None
        self._available = True

    def _ensure_loaded(self) -> bool:
        """Lazy-load FlashRank model on first call."""
        if self._ranker is not None:
            return True
        if not self._available:
            return False

        try:
            from flashrank import Ranker, RerankRequest
            t0 = time.perf_counter()
            self._ranker = Ranker(model_name=self._model_name)
            load_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"✅ CrossEncoderReranker loaded: {self._model_name} ({load_ms:.0f}ms)")
            return True
        except ImportError:
            logger.warning(
                "⚠️ flashrank not installed — cross-encoder reranking disabled. "
                "Install with: pip install flashrank"
            )
            self._available = False
            return False
        except Exception as e:
            logger.error(f"❌ Failed to load FlashRank model: {e}")
            self._available = False
            return False

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 10,
        heuristic_weight: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """Rerank results using cross-encoder scores combined with heuristic scores.

        Args:
            query: The search query.
            results: List of result dicts with at least "content" and "score" keys.
            top_k: Number of top results to return.
            heuristic_weight: Weight for the existing heuristic score (1 - this = cross-encoder weight).

        Returns:
            Reranked list of results, limited to top_k.
        """
        if not results:
            return results

        if not self._ensure_loaded():
            # Fallback: return as-is (heuristic-only)
            return results[:top_k]

        t0 = time.perf_counter()

        try:
            from flashrank import RerankRequest

            # Build passages for FlashRank
            passages = []
            for r in results:
                text = r.get("content", "") or r.get("title", "")
                # FlashRank expects {"text": ...} dicts
                passages.append({"text": text[:512]})  # Truncate for efficiency

            request = RerankRequest(query=query, passages=passages)
            rerank_results = self._ranker.rerank(request)

            # Map cross-encoder scores back to results
            # FlashRank returns results in reranked order with "score" field
            ce_scores = {}
            for rr in rerank_results:
                # FlashRank result has "text" and "score"
                idx = rr.get("id", None)
                if idx is not None:
                    ce_scores[idx] = rr.get("score", 0.0)
                else:
                    # Match by text content
                    text = rr.get("text", "")
                    for i, p in enumerate(passages):
                        if p["text"] == text and i not in ce_scores:
                            ce_scores[i] = rr.get("score", 0.0)
                            break

            # Combine cross-encoder score with heuristic score
            # Note: FlashRank returns numpy.float32 — cast to Python float
            # to prevent "Object of type float32 is not JSON serializable"
            ce_weight = 1.0 - heuristic_weight
            for i, result in enumerate(results):
                ce_score = float(ce_scores.get(i, 0.0))
                heuristic_score = float(result.get("_rerank_score", result.get("score", 0.0)) or 0.0)

                combined = ce_weight * ce_score + heuristic_weight * heuristic_score
                result["_cross_encoder_score"] = ce_score
                result["_combined_score"] = combined
                result["score"] = combined

            # Sort by combined score
            results.sort(key=lambda r: r.get("_combined_score", 0), reverse=True)

            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"🔀 Cross-encoder reranked {len(results)} results → top {top_k} "
                f"in {elapsed_ms:.0f}ms (CE weight={ce_weight:.1f}, heuristic={heuristic_weight:.1f})"
            )

            return results[:top_k]

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.error(f"Cross-encoder reranking failed in {elapsed_ms:.0f}ms (fallback to heuristic): {e}")
            return results[:top_k]


def get_reranker(
    model_name: str = _DEFAULT_MODEL,
) -> CrossEncoderReranker:
    """Get or create the singleton reranker instance."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = CrossEncoderReranker(model_name=model_name)
    return _reranker_instance
