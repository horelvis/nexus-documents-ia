"""
Cross-Encoder Reranker for SmartSearch

Adds neural cross-encoder reranking as a post-processing step after the
existing 5-signal heuristic reranking. Cross-encoders evaluate (query, passage)
pairs jointly with full cross-attention, achieving much higher precision than
bi-encoders or heuristic scoring.

Architecture decision: FlashRank on CPU (~5ms/passage) because GPU memory is
fully allocated to vLLM (18.5GB) + BGE-M3/Jina embeddings (2.7GB) = 21.2GB
of 24GB RTX 4090. FlashRank uses ONNX quantized models that run efficiently
on CPU without competing for GPU resources.

Pipeline integration:
    SmartSearch._rerank_results() (5-signal, ~1ms)
    → CrossEncoderReranker.rerank() (neural, ~50-100ms for 50 passages)
    → Final combined score: 0.6 * cross_encoder + 0.4 * heuristic

Usage:
    from app.agents.langgraph.reranker import get_reranker

    reranker = get_reranker()
    reranked = reranker.rerank(query, results, top_k=10)
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Singleton
_reranker_instance: Optional["CrossEncoderReranker"] = None


class CrossEncoderReranker:
    """Cross-encoder reranker using FlashRank (CPU-optimized ONNX).

    FlashRank loads ms-marco-MiniLM-L-12-v2 (~33MB ONNX) on first use.
    Subsequent calls reuse the cached model. Scores are normalized to [0, 1].
    """

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2"):
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
            self._ranker = Ranker(model_name=self._model_name)
            logger.info(f"✅ CrossEncoderReranker loaded: {self._model_name}")
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

            logger.info(
                f"🔀 Cross-encoder reranked {len(results)} results → top {top_k} "
                f"(CE weight={ce_weight:.1f}, heuristic={heuristic_weight:.1f})"
            )

            return results[:top_k]

        except Exception as e:
            logger.error(f"Cross-encoder reranking failed (fallback to heuristic): {e}")
            return results[:top_k]


def get_reranker(
    model_name: str = "ms-marco-MiniLM-L-12-v2",
) -> CrossEncoderReranker:
    """Get or create the singleton reranker instance."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = CrossEncoderReranker(model_name=model_name)
    return _reranker_instance
