"""
NexusRouter Action Router

Main entry point for query classification and action routing.

Combines:
1. IntentClassifier - Determines user intent
2. EntityExtractor - Extracts entities and context
3. Action mapping - Decides what action to take

Usage:
    from app.services.nexus_router import nexus_router

    result = await nexus_router.classify(
        query="¿Cuántos contratos tengo?",
        tenant_id="tenant-123"
    )

    if result.needs_search:
        # Force search before LLM
        search_results = await search(...)
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .schemas import (
    Intent,
    RequiredAction,
    IntentClassification,
    NexusRouterConfig,
    RouterMetrics,
    get_action_for_intent,
)
from .intent_classifier import IntentClassifier, intent_classifier
from .entity_extractor import EntityExtractor, entity_extractor

logger = logging.getLogger(__name__)


class ActionRouter:
    """
    Main NexusRouter class that coordinates classification and action routing.

    This is the primary entry point for the routing system.

    Flow:
    1. Classify intent using SetFit (or fallback)
    2. Extract entities using spaCy
    3. Map intent + confidence to required action
    4. Return IntentClassification with all info
    """

    def __init__(
        self,
        config: Optional[NexusRouterConfig] = None,
        classifier: Optional[IntentClassifier] = None,
        extractor: Optional[EntityExtractor] = None,
    ):
        """
        Initialize the action router.

        Args:
            config: Router configuration
            classifier: Intent classifier instance (uses singleton if not provided)
            extractor: Entity extractor instance (uses singleton if not provided)
        """
        self.config = config or NexusRouterConfig()
        self._classifier = classifier or intent_classifier
        self._extractor = extractor or entity_extractor
        self._initialized = False

        # Metrics tracking
        self._metrics = RouterMetrics()

    async def initialize(self) -> bool:
        """
        Initialize all components.

        Returns:
            True if all components initialized successfully
        """
        if self._initialized:
            return True

        logger.info("Initializing NexusRouter ActionRouter...")

        # Initialize classifier
        classifier_ok = await self._classifier.initialize()
        logger.info(f"Classifier initialized: {classifier_ok}")

        # Initialize extractor
        extractor_ok = await self._extractor.initialize()
        logger.info(f"Extractor initialized: {extractor_ok}")

        self._initialized = True
        logger.info("NexusRouter ActionRouter initialized")

        return True

    async def classify(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntentClassification:
        """
        Classify a query and determine the required action.

        This is the main entry point for the NexusRouter.

        Args:
            query: User query text
            tenant_id: Optional tenant ID for context
            context: Optional additional context

        Returns:
            IntentClassification with intent, confidence, entities, and action
        """
        start_time = time.perf_counter()

        if not self._initialized:
            await self.initialize()

        # 1. Classify intent
        intent, confidence, all_scores = self._classifier.classify(
            query, return_all_scores=True
        )

        # 2. Extract entities
        entities_result = self._extractor.extract(query)

        # 3. Determine required action
        required_action = get_action_for_intent(
            intent,
            confidence,
            threshold=self.config.confidence_threshold,
        )

        # 4. Apply high-confidence override for force search
        if confidence >= self.config.force_search_threshold:
            # High confidence - trust the classification
            pass
        elif intent in Intent.document_intents():
            # Lower confidence but document-related - safer to search
            required_action = RequiredAction.FORCE_SEARCH

        # 5. Build classification result
        total_time_ms = (time.perf_counter() - start_time) * 1000

        classification = IntentClassification(
            intent=intent,
            confidence=confidence,
            entities=entities_result.get("entities", []),
            document_types=entities_result.get("document_types", []),
            required_action=required_action,
            model_version=self._classifier._model_version,
            classification_time_ms=total_time_ms,
            raw_scores=all_scores,
        )

        # 6. Update metrics
        self._update_metrics(classification)

        logger.info(
            f"🎯 NexusRouter: '{query[:50]}...' → "
            f"{intent.value} ({confidence:.2f}) → {required_action.value} "
            f"[{total_time_ms:.1f}ms]"
        )

        return classification

    def _update_metrics(self, classification: IntentClassification) -> None:
        """Update internal metrics."""
        self._metrics.total_classifications += 1

        intent_key = classification.intent.value
        self._metrics.classifications_by_intent[intent_key] = \
            self._metrics.classifications_by_intent.get(intent_key, 0) + 1

        # Update running averages
        n = self._metrics.total_classifications
        self._metrics.avg_confidence = (
            (self._metrics.avg_confidence * (n - 1) + classification.confidence) / n
        )
        self._metrics.avg_latency_ms = (
            (self._metrics.avg_latency_ms * (n - 1) + classification.classification_time_ms) / n
        )

        if classification.needs_search:
            self._metrics.forced_searches += 1
        else:
            self._metrics.direct_responses += 1

    async def classify_batch(
        self,
        queries: List[str],
        tenant_id: Optional[str] = None,
    ) -> List[IntentClassification]:
        """
        Classify multiple queries.

        Args:
            queries: List of query texts
            tenant_id: Optional tenant ID

        Returns:
            List of IntentClassification results
        """
        results = []
        for query in queries:
            result = await self.classify(query, tenant_id)
            results.append(result)
        return results

    def should_force_search(
        self,
        classification: IntentClassification,
    ) -> bool:
        """
        Determine if search should be forced based on classification.

        Helper method for integration with Emma.

        Args:
            classification: Classification result

        Returns:
            True if search should be forced
        """
        return classification.needs_search

    def get_search_params(
        self,
        classification: IntentClassification,
        query: str,
    ) -> Dict[str, Any]:
        """
        Get search parameters based on classification.

        Provides search hints like document types and filters.

        Args:
            classification: Classification result
            query: Original query

        Returns:
            Dict with search parameters
        """
        params = {
            "query": query,
            "top_k": 10,
        }

        # Add document type filter if detected
        if classification.document_types:
            params["doc_type_filter"] = classification.document_types

        # Adjust top_k based on intent
        if classification.intent == Intent.COUNT:
            params["top_k"] = 100  # Need more for counting
            params["count_only"] = True
        elif classification.intent == Intent.LIST:
            params["top_k"] = 50
            params["return_list"] = True
        elif classification.intent == Intent.ANALYZE:
            params["top_k"] = 5  # Focus on fewer, more relevant docs

        return params

    def get_metrics(self) -> RouterMetrics:
        """
        Get current metrics.

        Returns:
            RouterMetrics instance
        """
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset metrics to initial state."""
        self._metrics = RouterMetrics()

    async def reload_model(self) -> bool:
        """
        Reload the classification model.

        Useful after retraining.

        Returns:
            True if reload successful
        """
        return await self._classifier.reload_model()

    def get_status(self) -> Dict[str, Any]:
        """
        Get router status.

        Returns:
            Status dict with component status
        """
        return {
            "initialized": self._initialized,
            "classifier": self._classifier.get_status(),
            "extractor": self._extractor.get_status(),
            "metrics": self._metrics.to_dict(),
            "config": self.config.to_dict(),
        }


# Singleton instance
action_router = ActionRouter()
nexus_router = action_router  # Alias for convenience
