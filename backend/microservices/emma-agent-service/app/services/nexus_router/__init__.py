"""
NexusRouter - ML-based Intent Classification for Emma AI.

Provides intent classification using SetFit (few-shot classification)
to determine user intent and required actions.

This is a simplified version - full ML model training is done separately.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    """User intent types"""
    SEARCH = "search"
    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    QUESTION = "question"
    COMMAND = "command"
    GREETING = "greeting"
    FEEDBACK = "feedback"
    UNKNOWN = "unknown"


class RequiredAction(str, Enum):
    """Required actions based on intent"""
    RAG_SEARCH = "rag_search"
    DOCUMENT_ANALYSIS = "document_analysis"
    GRAPH_QUERY = "graph_query"
    DIRECT_RESPONSE = "direct_response"
    CLARIFICATION = "clarification"
    TOOL_CALL = "tool_call"


@dataclass
class IntentClassification:
    """Result of intent classification"""
    intent: Intent
    confidence: float
    required_action: RequiredAction
    entities: List[str]
    metadata: dict


class NexusRouter:
    """
    ML-based intent classification router.

    Uses pattern matching for initial release, with ML model
    (SetFit) integration planned for future versions.
    """

    def __init__(self):
        self._initialized = False
        self._model = None

        # Simple keyword patterns for intent classification
        self._intent_patterns = {
            Intent.SEARCH: ["buscar", "encontrar", "search", "find", "mostrar", "show"],
            Intent.ANALYZE: ["analizar", "analyze", "revisar", "review", "evaluar"],
            Intent.SUMMARIZE: ["resumir", "summarize", "resumen", "summary"],
            Intent.COMPARE: ["comparar", "compare", "diferencias", "difference"],
            Intent.GREETING: ["hola", "hello", "buenos días", "hi", "hey"],
            Intent.QUESTION: ["qué", "cuál", "cómo", "por qué", "what", "which", "how", "why", "?"],
        }

    async def initialize(self):
        """Initialize the router."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ NexusRouter initialized (pattern-based)")

    async def classify(self, query: str) -> IntentClassification:
        """
        Classify user intent from query.

        Args:
            query: User query text

        Returns:
            IntentClassification with detected intent and action
        """
        query_lower = query.lower()

        # Simple pattern-based classification
        detected_intent = Intent.UNKNOWN
        confidence = 0.5

        for intent, patterns in self._intent_patterns.items():
            for pattern in patterns:
                if pattern in query_lower:
                    detected_intent = intent
                    confidence = 0.8
                    break
            if detected_intent != Intent.UNKNOWN:
                break

        # Map intent to action
        action_map = {
            Intent.SEARCH: RequiredAction.RAG_SEARCH,
            Intent.ANALYZE: RequiredAction.DOCUMENT_ANALYSIS,
            Intent.SUMMARIZE: RequiredAction.RAG_SEARCH,
            Intent.COMPARE: RequiredAction.DOCUMENT_ANALYSIS,
            Intent.GREETING: RequiredAction.DIRECT_RESPONSE,
            Intent.QUESTION: RequiredAction.RAG_SEARCH,
            Intent.UNKNOWN: RequiredAction.RAG_SEARCH,
        }

        return IntentClassification(
            intent=detected_intent,
            confidence=confidence,
            required_action=action_map.get(detected_intent, RequiredAction.RAG_SEARCH),
            entities=[],
            metadata={"method": "pattern_matching"}
        )


# Singleton instance
nexus_router = NexusRouter()


def get_nexus_router() -> NexusRouter:
    """Get the NexusRouter singleton."""
    return nexus_router


__all__ = [
    "NexusRouter",
    "nexus_router",
    "get_nexus_router",
    "Intent",
    "RequiredAction",
    "IntentClassification",
]
