"""
NexusRouter Intent Classifier

Fast intent classification using SetFit models.

Features:
- ~5ms inference latency
- Confidence scores for all intents
- Fallback to keyword matching if model not available
- Hot-reload support for model updates
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schemas import (
    Intent,
    NexusRouterConfig,
    ClassificationStats,
)

logger = logging.getLogger(__name__)


# NOTE: No hardcoded keyword patterns.
# The SetFit model MUST be trained before using NexusRouter.
# Training can be triggered via:
#   - POST /router/train (admin API)
#   - Celery task after connector sync
#   - Manual training script
#
# Without a trained model, all queries default to SEARCH intent
# with low confidence, which forces document search as a safe fallback.


class IntentClassifier:
    """
    Classifies user queries into intents using SetFit.

    Provides fast (~5ms) classification with confidence scores.
    Falls back to keyword matching if model is not available.
    """

    def __init__(self, config: Optional[NexusRouterConfig] = None):
        """
        Initialize the classifier.

        Args:
            config: Router configuration
        """
        self.config = config or NexusRouterConfig()
        self._model = None
        self._model_version: Optional[str] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize the classifier by loading the model.

        Returns:
            True if model loaded, False if using fallback
        """
        if self._initialized:
            return self._model is not None

        try:
            model_path = Path(self.config.model_path) / "current"

            if model_path.exists():
                from setfit import SetFitModel

                # Follow symlink
                if model_path.is_symlink():
                    model_path = model_path.resolve()
                    self._model_version = model_path.name

                logger.info(f"Loading SetFit model from {model_path}")
                self._model = SetFitModel.from_pretrained(str(model_path))
                self._initialized = True
                logger.info(f"IntentClassifier initialized with model {self._model_version}")
                return True

            else:
                logger.warning(
                    f"Model not found at {model_path}. Using keyword fallback."
                )
                self._initialized = True
                return False

        except ImportError:
            logger.warning("SetFit not installed. Using keyword fallback.")
            self._initialized = True
            return False

        except Exception as e:
            logger.error(f"Failed to load model: {e}. Using keyword fallback.")
            self._initialized = True
            return False

    def classify(
        self,
        query: str,
        return_all_scores: bool = False,
    ) -> Tuple[Intent, float, Optional[Dict[str, float]]]:
        """
        Classify a query into an intent.

        Args:
            query: User query text
            return_all_scores: Also return scores for all intents

        Returns:
            Tuple of (intent, confidence, optional_all_scores)
        """
        start_time = time.perf_counter()

        # Normalize query
        query_clean = query.strip().lower()

        if self._model is not None:
            # Use SetFit model
            intent, confidence, all_scores = self._classify_with_model(query_clean)
        else:
            # No model trained - use safe fallback (SEARCH)
            intent, confidence, all_scores = self._classify_without_model(query_clean)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"Classified '{query[:50]}...' as {intent.value} "
            f"(confidence={confidence:.2f}, time={elapsed_ms:.1f}ms)"
        )

        if return_all_scores:
            return intent, confidence, all_scores
        return intent, confidence, None

    def _classify_with_model(
        self,
        query: str,
    ) -> Tuple[Intent, float, Dict[str, float]]:
        """
        Classify using the SetFit model.

        Args:
            query: Normalized query text

        Returns:
            Tuple of (intent, confidence, all_scores)
        """
        try:
            # Get prediction with probabilities
            predictions = self._model.predict([query])
            predicted_label = predictions[0]

            # Get probabilities for all classes
            # SetFit uses predict_proba for this
            all_scores = {}
            confidence = 0.9  # Default confidence

            if hasattr(self._model, "predict_proba"):
                proba = self._model.predict_proba([query])[0]

                # Get actual label order from model head
                if hasattr(self._model, "model_head") and hasattr(self._model.model_head, "classes_"):
                    model_labels = list(self._model.model_head.classes_)
                else:
                    # Fallback to enum order (may not match)
                    model_labels = [intent.value for intent in Intent]

                # Build scores dict using model's label order
                if len(proba) == len(model_labels):
                    all_scores = {
                        model_labels[i]: float(proba[i])
                        for i in range(len(model_labels))
                    }
                    confidence = all_scores.get(predicted_label, 0.9)
                else:
                    # Fallback: just use high confidence for predicted label
                    all_scores = {predicted_label: 0.9}
                    confidence = 0.9
            else:
                all_scores = {predicted_label: 0.9}
                confidence = 0.9

            # Convert label to Intent enum
            try:
                intent = Intent(predicted_label)
            except ValueError:
                logger.warning(f"Unknown label '{predicted_label}', defaulting to SEARCH")
                intent = Intent.SEARCH
                confidence = 0.5

            return intent, confidence, all_scores

        except Exception as e:
            logger.warning(f"Model prediction failed: {e}. Using safe fallback.")
            return self._classify_without_model(query)

    def _classify_without_model(
        self,
        query: str,
    ) -> Tuple[Intent, float, Dict[str, float]]:
        """
        Fallback classification when no model is trained.

        Returns SEARCH intent with low confidence as a safe default.
        This forces document search, which is better than potentially
        missing relevant documents.

        IMPORTANT: Train the SetFit model for accurate classification!
        Use POST /router/train to trigger training.

        Args:
            query: Normalized query text

        Returns:
            Tuple of (intent, confidence, all_scores)
        """
        logger.warning(
            f"No trained model available. Defaulting to SEARCH intent. "
            f"Train the model via POST /router/train for accurate classification."
        )

        # Default all intents to low scores
        default_scores = {intent.value: 0.1 for intent in Intent}
        default_scores[Intent.SEARCH.value] = 0.3

        # Always return SEARCH as safe fallback
        return Intent.SEARCH, 0.3, default_scores

    def get_detailed_classification(
        self,
        query: str,
    ) -> ClassificationStats:
        """
        Get detailed classification with timing and all scores.

        Useful for debugging and analysis.

        Args:
            query: User query text

        Returns:
            ClassificationStats with full details
        """
        start_time = time.perf_counter()

        intent, confidence, all_scores = self.classify(query, return_all_scores=True)

        classification_time = (time.perf_counter() - start_time) * 1000

        # Build top intents list
        top_intents = []
        if all_scores:
            sorted_scores = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
            top_intents = [
                {"intent": k, "score": v}
                for k, v in sorted_scores[:3]
            ]

        return ClassificationStats(
            query=query,
            intent=intent,
            confidence=confidence,
            top_intents=top_intents,
            classification_time_ms=classification_time,
            model_version=self._model_version,
        )

    async def reload_model(self) -> bool:
        """
        Reload the model (hot-reload support).

        Useful after retraining without service restart.

        Returns:
            True if reload successful
        """
        self._model = None
        self._model_version = None
        self._initialized = False

        return await self.initialize()

    def get_status(self) -> Dict[str, Any]:
        """
        Get classifier status.

        Returns:
            Status dict
        """
        return {
            "initialized": self._initialized,
            "model_loaded": self._model is not None,
            "model_version": self._model_version,
            "using_fallback": self._model is None and self._initialized,
            "model_path": self.config.model_path,
        }


# Singleton instance
intent_classifier = IntentClassifier()
