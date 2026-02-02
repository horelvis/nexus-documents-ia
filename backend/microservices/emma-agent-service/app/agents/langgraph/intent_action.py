"""
Action Intent Classifier — Semantic pre-routing

Separates ACTION classification (generate, analyze, search, verify)
from DOMAIN classification (labor, fiscal, contract). This fixes the
docgen routing problem where "genera un contrato laboral" would tie
on labor/contract/docgen keywords and never reach docgen_agent.

Uses the same fastembed encoder as SectorQAIndex (all-MiniLM-L6-v2),
pre-embeds action intent questions at startup, and classifies via
cosine similarity in ~3ms per query.

Usage:
    classifier = get_action_classifier()
    intent = classifier.classify("genera un contrato laboral")
    # → ActionIntent(id="document_generation", action="generate",
    #                priority_agent="docgen_agent", confidence=0.85)
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ActionIntent:
    """Result of action intent classification."""
    id: str
    action: str
    priority_agent: Optional[str]
    confidence: float
    description: str


def _find_project_root() -> str:
    """Find project root (directory containing both 'app/' and 'config/')."""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isdir(os.path.join(current, "app")) and os.path.isdir(os.path.join(current, "config")):
            return current
        current = os.path.dirname(current)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


_PROJECT_ROOT = _find_project_root()
CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "sector_qa", "action_intents.yaml")


class ActionIntentClassifier:
    """
    Embedding-based action intent classifier.

    Pre-embeds all questions from action_intents.yaml at initialization,
    then uses cosine similarity for fast intent matching at query time.
    Reuses the same fastembed model as SectorQAIndex (already in memory).
    """

    def __init__(self):
        self._embeddings: Optional[np.ndarray] = None
        self._intent_indices: List[int] = []
        self._intents: List[dict] = []
        self._encode = None
        self._initialized = False

    def initialize(self):
        """Load model and pre-embed action intent questions."""
        if self._initialized:
            return

        # Reuse the same base model as SectorQAIndex
        from fastembed import TextEmbedding
        from .sectors.qa_index import BASE_MODEL

        encoder = TextEmbedding(BASE_MODEL)
        self._encode = lambda texts: list(encoder.embed(texts))

        # Load action_intents.yaml
        if not os.path.exists(CONFIG_PATH):
            logger.warning(f"Action intents config not found: {CONFIG_PATH}")
            self._initialized = True
            return

        with open(CONFIG_PATH) as f:
            data = yaml.safe_load(f)

        # Embed all questions
        texts = []
        intent_indices = []
        for i, intent in enumerate(data.get("intents", [])):
            for q in intent.get("questions", []):
                texts.append(q)
                intent_indices.append(i)

        if not texts:
            self._initialized = True
            return

        embeddings = self._encode(texts)
        self._embeddings = np.array(embeddings, dtype=np.float32)
        # Normalize for fast cosine similarity via dot product
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        self._embeddings = self._embeddings / np.where(norms > 0, norms, 1)

        self._intent_indices = intent_indices
        self._intents = data["intents"]
        self._initialized = True

        logger.info(
            f"✅ ActionIntentClassifier: {len(self._intents)} intents, "
            f"{len(texts)} questions pre-embedded"
        )

    def classify(self, query: str, threshold: float = 0.70) -> Optional[ActionIntent]:
        """
        Classify the action intent of a query.

        Args:
            query: User query text
            threshold: Minimum similarity score (default 0.70)

        Returns:
            ActionIntent if match found above threshold, None otherwise
        """
        if not self._initialized:
            self.initialize()
        if self._embeddings is None or len(self._embeddings) == 0:
            return None

        # Encode and normalize query
        query_emb = np.array(self._encode([query])[0], dtype=np.float32)
        norm = np.linalg.norm(query_emb)
        if norm > 0:
            query_emb = query_emb / norm

        # Cosine similarity (embeddings already normalized)
        scores = self._embeddings @ query_emb

        # Dedupe: max score per intent
        intent_scores: Dict[int, float] = {}
        for idx, score in enumerate(scores):
            i_idx = self._intent_indices[idx]
            if i_idx not in intent_scores or score > intent_scores[i_idx]:
                intent_scores[i_idx] = float(score)

        # Find best match
        if not intent_scores:
            return None

        best_idx, best_score = max(intent_scores.items(), key=lambda x: x[1])

        if best_score < threshold:
            logger.debug(
                f"ActionIntent: best match '{self._intents[best_idx]['id']}' "
                f"score={best_score:.3f} < threshold={threshold}"
            )
            return None

        intent = self._intents[best_idx]
        priority_agent = intent.get("priority_agent")
        # YAML null → Python None
        if priority_agent is None or priority_agent == "null":
            priority_agent = None

        result = ActionIntent(
            id=intent["id"],
            action=intent["action"],
            priority_agent=priority_agent,
            confidence=best_score,
            description=intent.get("description", ""),
        )

        logger.info(
            f"🎯 ActionIntent: '{result.action}' (id={result.id}, "
            f"priority={result.priority_agent}, confidence={result.confidence:.3f})"
        )
        return result


# Singleton
_classifier: Optional[ActionIntentClassifier] = None


def get_action_classifier() -> ActionIntentClassifier:
    """Get or create the global ActionIntentClassifier singleton."""
    global _classifier
    if _classifier is None:
        _classifier = ActionIntentClassifier()
        try:
            _classifier.initialize()
        except Exception as e:
            logger.error(f"Failed to init ActionIntentClassifier: {e}")
            # Return uninitialized — classify() will return None
    return _classifier
