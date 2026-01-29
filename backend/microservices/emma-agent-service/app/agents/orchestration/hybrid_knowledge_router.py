"""
Hybrid Knowledge Router - 2-Stage routing for knowledge source classification.

.. deprecated:: 2.0.0
    This module is deprecated in favor of Multi-Pipeline RAG sectors.
    Use ACTIVE_SECTOR env var for domain-specific query routing.
    See: emma-agent-service/app/agents/langgraph/sectors/

Combines the best of both worlds:
- Stage 1: SemanticKnowledgeRouter (FastEmbed, ~1-3ms) for high-confidence queries
- Stage 2: SetFitKnowledgeClassifier (SetFit ML, ~5-8ms) for ambiguous queries

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HYBRID KNOWLEDGE ROUTER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Query                                                                       │
│    │                                                                         │
│    ▼                                                                         │
│  ┌────────────────────────────────────────────────────────────┐             │
│  │  STAGE 1: Semantic Router (Fast-Path)                      │             │
│  │  - ~1-3ms latency                                          │             │
│  │  - Uses FastEmbed (ONNX optimized)                         │             │
│  │  - Good for clear-cut queries                              │             │
│  └────────────────────────────────────────────────────────────┘             │
│    │                                                                         │
│    │ confidence >= threshold (0.9)?                                          │
│    │                                                                         │
│    ├─► YES: Return semantic result (80% of queries, ~1-3ms)                  │
│    │                                                                         │
│    ▼ NO: Ambiguous query                                                     │
│  ┌────────────────────────────────────────────────────────────┐             │
│  │  STAGE 2: SetFit ML Classifier (Fallback)                  │             │
│  │  - ~5-8ms additional latency                               │             │
│  │  - Fine-tuned on real user queries                         │             │
│  │  - Handles edge cases and learns from corrections          │             │
│  └────────────────────────────────────────────────────────────┘             │
│    │                                                                         │
│    ▼                                                                         │
│  Return ML result (20% of queries, ~8-10ms total)                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Benefits:
- 80% of queries resolved in ~1-3ms (fast path)
- 20% of ambiguous queries get accurate ML classification (~8-10ms)
- ML classifier learns from corrections to improve over time
- Semantic router can be updated with new utterances without retraining

Usage:
    from app.agents.orchestration import (
        HybridKnowledgeRouter,
        get_hybrid_knowledge_router,
        classify_knowledge_source_hybrid,
    )

    # Quick classification
    result = await classify_knowledge_source_hybrid(query)

    if result.needs_public_search:
        # Use legal_search tool
        ...
    if result.needs_tenant_search:
        # Use SIL/Weaviate search
        ...
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from .knowledge_source_router import (
    KnowledgeSource,
    KnowledgeSourceResult,
    SemanticKnowledgeRouter,
    get_knowledge_source_router,
)

logger = logging.getLogger(__name__)


@dataclass
class HybridClassificationResult:
    """
    Result from hybrid knowledge source classification.

    Contains the final source, confidence, and metadata about routing decision.
    """
    source: KnowledgeSource
    confidence: float

    # Routing metadata
    stage_used: int  # 1 = semantic, 2 = ML
    semantic_confidence: float  # Confidence from Stage 1
    ml_used: bool  # Whether ML classifier was invoked

    # Timing
    total_latency_ms: float
    semantic_latency_ms: float
    ml_latency_ms: float

    # Debug info
    semantic_route_name: Optional[str] = None
    ml_fallback_used: bool = False  # Whether ML model itself fell back to keywords

    @property
    def needs_tenant_search(self) -> bool:
        """Whether to search in tenant documents."""
        return self.source in [KnowledgeSource.TENANT_DOCUMENTS, KnowledgeSource.HYBRID]

    @property
    def needs_public_search(self) -> bool:
        """Whether to search in public knowledge (legal_search)."""
        return self.source in [KnowledgeSource.PUBLIC_KNOWLEDGE, KnowledgeSource.HYBRID]

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "source": self.source.value,
            "confidence": self.confidence,
            "stage_used": self.stage_used,
            "semantic_confidence": self.semantic_confidence,
            "ml_used": self.ml_used,
            "total_latency_ms": self.total_latency_ms,
            "semantic_latency_ms": self.semantic_latency_ms,
            "ml_latency_ms": self.ml_latency_ms,
            "semantic_route_name": self.semantic_route_name,
            "ml_fallback_used": self.ml_fallback_used,
            "needs_tenant_search": self.needs_tenant_search,
            "needs_public_search": self.needs_public_search,
        }


class HybridKnowledgeRouter:
    """
    Two-stage routing: fast semantic + ML fallback.

    Best of both worlds:
    - ~1-3ms for 80% of queries (clear cases)
    - ~8-10ms for 20% of queries (ambiguous)
    - Learns from corrections to improve semantic routes
    """

    # Default threshold for fast-path (skip ML fallback)
    DEFAULT_THRESHOLD = 0.9

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        enable_ml_fallback: bool = True,
    ):
        """
        Initialize the hybrid router.

        Args:
            threshold: Confidence threshold for fast-path (default 0.9)
            enable_ml_fallback: Whether to use ML classifier for low-confidence queries
        """
        self.threshold = threshold
        self.enable_ml_fallback = enable_ml_fallback

        # Routers (lazy initialized)
        self._semantic_router: Optional[SemanticKnowledgeRouter] = None
        self._ml_classifier = None  # SetFitKnowledgeClassifier
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize both routers.

        Returns:
            True if at least semantic router initialized successfully
        """
        if self._initialized:
            return True

        try:
            # Initialize semantic router (Stage 1)
            self._semantic_router = get_knowledge_source_router()
            logger.info("✅ HybridKnowledgeRouter: Semantic router ready")

            # Initialize ML classifier (Stage 2)
            if self.enable_ml_fallback:
                try:
                    from app.services.nexus_router.knowledge_classifier import (
                        get_knowledge_classifier,
                    )
                    self._ml_classifier = get_knowledge_classifier()
                    await self._ml_classifier.initialize()
                    logger.info("✅ HybridKnowledgeRouter: ML classifier ready")
                except Exception as e:
                    logger.warning(f"ML classifier initialization failed: {e}. Using semantic-only mode.")
                    self._ml_classifier = None

            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize HybridKnowledgeRouter: {e}")
            return False

    async def classify(self, query: str) -> HybridClassificationResult:
        """
        Classify a query into a knowledge source using 2-stage routing.

        Args:
            query: User's query text

        Returns:
            HybridClassificationResult with source, confidence, and metadata
        """
        if not self._initialized:
            await self.initialize()

        total_start = time.perf_counter()

        # =================================================================
        # STAGE 1: Semantic Router (Fast-Path)
        # =================================================================
        semantic_start = time.perf_counter()
        semantic_result = self._semantic_router.classify(query)
        semantic_latency = (time.perf_counter() - semantic_start) * 1000

        # Check if we can use fast-path
        if semantic_result.confidence >= self.threshold:
            total_latency = (time.perf_counter() - total_start) * 1000

            logger.info(
                f"🚀 KnowledgeRouter FAST-PATH: {semantic_result.source.value} "
                f"(conf={semantic_result.confidence:.2f}, latency={total_latency:.1f}ms) "
                f"for: '{query[:50]}...'"
            )

            return HybridClassificationResult(
                source=semantic_result.source,
                confidence=semantic_result.confidence,
                stage_used=1,
                semantic_confidence=semantic_result.confidence,
                ml_used=False,
                total_latency_ms=total_latency,
                semantic_latency_ms=semantic_latency,
                ml_latency_ms=0.0,
                semantic_route_name=semantic_result.route_name,
                ml_fallback_used=False,
            )

        # =================================================================
        # STAGE 2: ML Classifier (Fallback for ambiguous queries)
        # =================================================================
        if self._ml_classifier is None or not self.enable_ml_fallback:
            # No ML classifier - use semantic result with low confidence warning
            total_latency = (time.perf_counter() - total_start) * 1000

            logger.warning(
                f"⚠️ KnowledgeRouter LOW-CONF (no ML): {semantic_result.source.value} "
                f"(conf={semantic_result.confidence:.2f}, latency={total_latency:.1f}ms) "
                f"for: '{query[:50]}...'"
            )

            return HybridClassificationResult(
                source=semantic_result.source,
                confidence=semantic_result.confidence,
                stage_used=1,
                semantic_confidence=semantic_result.confidence,
                ml_used=False,
                total_latency_ms=total_latency,
                semantic_latency_ms=semantic_latency,
                ml_latency_ms=0.0,
                semantic_route_name=semantic_result.route_name,
                ml_fallback_used=False,
            )

        # Use ML classifier for ambiguous query
        ml_start = time.perf_counter()
        ml_result = self._ml_classifier.classify(query, return_all_scores=True)
        ml_latency = (time.perf_counter() - ml_start) * 1000

        total_latency = (time.perf_counter() - total_start) * 1000

        logger.info(
            f"🧠 KnowledgeRouter ML-FALLBACK: {ml_result.source.value} "
            f"(conf={ml_result.confidence:.2f}, semantic_conf={semantic_result.confidence:.2f}, "
            f"latency={total_latency:.1f}ms) for: '{query[:50]}...'"
        )

        return HybridClassificationResult(
            source=ml_result.source,
            confidence=ml_result.confidence,
            stage_used=2,
            semantic_confidence=semantic_result.confidence,
            ml_used=True,
            total_latency_ms=total_latency,
            semantic_latency_ms=semantic_latency,
            ml_latency_ms=ml_latency,
            semantic_route_name=semantic_result.route_name,
            ml_fallback_used=ml_result.fallback_used,
        )

    def get_status(self) -> dict:
        """
        Get router status.

        Returns:
            Status dict
        """
        ml_status = None
        if self._ml_classifier is not None:
            ml_status = self._ml_classifier.get_status()

        return {
            "initialized": self._initialized,
            "threshold": self.threshold,
            "enable_ml_fallback": self.enable_ml_fallback,
            "semantic_router_ready": self._semantic_router is not None,
            "ml_classifier_ready": self._ml_classifier is not None,
            "ml_classifier_status": ml_status,
        }


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_hybrid_router: Optional[HybridKnowledgeRouter] = None


def get_hybrid_knowledge_router(
    threshold: float = HybridKnowledgeRouter.DEFAULT_THRESHOLD,
    enable_ml_fallback: bool = True,
) -> HybridKnowledgeRouter:
    """
    Get or create the hybrid knowledge router singleton.

    Args:
        threshold: Confidence threshold for fast-path
        enable_ml_fallback: Whether to use ML classifier for low-confidence queries

    Returns:
        HybridKnowledgeRouter instance
    """
    global _hybrid_router
    if _hybrid_router is None:
        _hybrid_router = HybridKnowledgeRouter(
            threshold=threshold,
            enable_ml_fallback=enable_ml_fallback,
        )
    return _hybrid_router


async def classify_knowledge_source_hybrid(query: str) -> HybridClassificationResult:
    """
    Convenience function to classify a query's knowledge source.

    Args:
        query: User's query text

    Returns:
        HybridClassificationResult with source and metadata
    """
    router = get_hybrid_knowledge_router()
    return await router.classify(query)


async def preload_hybrid_knowledge_router() -> None:
    """
    Preload the hybrid knowledge router at service startup.

    This initializes both semantic and ML routers,
    preventing delay on first user request.
    """
    start = time.perf_counter()

    logger.info("🚀 Preloading HybridKnowledgeRouter...")

    try:
        router = get_hybrid_knowledge_router()
        await router.initialize()
        elapsed = time.perf_counter() - start
        logger.info(f"✅ HybridKnowledgeRouter preloaded in {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"❌ Failed to preload HybridKnowledgeRouter: {e}")
        logger.warning("⚠️ First request will experience delay while loading router")
