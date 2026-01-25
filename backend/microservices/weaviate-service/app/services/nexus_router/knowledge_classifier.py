"""
NexusRouter Knowledge Source Classifier

SetFit-based classification for knowledge sources (Stage 2 of 2-stage routing).

Features:
- ~5-8ms inference latency
- Confidence scores for all knowledge sources
- Fallback to TENANT_DOCUMENTS if model not available
- Hot-reload support for model updates
- Learning from user corrections

Used when SemanticKnowledgeRouter (Stage 1) has low confidence (<0.9).

Version 1.1 - January 2026 (Refactored with centralized config)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from app.core.learning_config import learning_settings
from app.core.learning_constants import (
    KNOWLEDGE_INITIAL_SCORE,
    KNOWLEDGE_PUBLIC_KEYWORD_BOOST,
    KNOWLEDGE_TENANT_KEYWORD_BOOST,
    KNOWLEDGE_HYBRID_KEYWORD_BOOST,
    KNOWLEDGE_MAX_FALLBACK_CONFIDENCE,
    KNOWLEDGE_DEFAULT_MODEL_CONFIDENCE,
    KNOWLEDGE_LOW_CONFIDENCE_FALLBACK,
    LOG_QUERY_PREVIEW_LENGTH,
)
from app.core.learning_exceptions import UnknownLabelError

logger = logging.getLogger(__name__)


class KnowledgeSource(str, Enum):
    """
    Knowledge source classification for RAG routing.

    Determines where to search for information:
    - TENANT_DOCUMENTS: Search in user's uploaded documents (Weaviate)
    - PUBLIC_KNOWLEDGE: Search in public legislation/BOE (legal_search tool)
    - HYBRID: Search in both sources (compare user docs against law)
    """
    TENANT_DOCUMENTS = "tenant_documents"
    PUBLIC_KNOWLEDGE = "public_knowledge"
    HYBRID = "hybrid"

    @classmethod
    def all_sources(cls) -> List["KnowledgeSource"]:
        """Get all knowledge sources."""
        return [cls.TENANT_DOCUMENTS, cls.PUBLIC_KNOWLEDGE, cls.HYBRID]


@dataclass
class KnowledgeClassification:
    """
    Result from knowledge source classification.

    Contains the predicted source, confidence score, and metadata.
    """
    source: KnowledgeSource
    confidence: float
    all_scores: Dict[str, float] = field(default_factory=dict)

    # Optional metadata for debugging
    model_version: Optional[str] = None
    classification_time_ms: float = 0.0
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "source": self.source.value,
            "confidence": self.confidence,
            "all_scores": self.all_scores,
            "model_version": self.model_version,
            "classification_time_ms": self.classification_time_ms,
            "fallback_used": self.fallback_used,
        }

    @property
    def needs_tenant_search(self) -> bool:
        """Whether to search in tenant documents."""
        return self.source in [KnowledgeSource.TENANT_DOCUMENTS, KnowledgeSource.HYBRID]

    @property
    def needs_public_search(self) -> bool:
        """Whether to search in public knowledge (legal_search)."""
        return self.source in [KnowledgeSource.PUBLIC_KNOWLEDGE, KnowledgeSource.HYBRID]


@dataclass
class KnowledgeTrainingExample:
    """
    Single training example for knowledge source classifier.

    Contains query text, source label, and optional metadata.
    """
    text: str
    source: KnowledgeSource
    source_type: str = "unknown"  # "seed", "collected", "corrected", "synthetic"
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None

    # Context about the classification
    predicted_source: Optional[KnowledgeSource] = None  # What was predicted
    was_correct: bool = True  # Whether prediction matched actual

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "text": self.text,
            "source": self.source.value,
            "source_type": self.source_type,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "predicted_source": self.predicted_source.value if self.predicted_source else None,
            "was_correct": self.was_correct,
        }


@dataclass
class KnowledgeClassifierConfig:
    """
    Configuration for Knowledge Source Classifier.

    Note: Default values loaded from centralized learning_settings.
    """
    # Model settings - defaults from centralized config
    model_base: str = None  # type: ignore
    model_path: str = None  # type: ignore

    # Classification thresholds
    confidence_threshold: float = None  # type: ignore

    # Training settings
    num_iterations: int = 20
    batch_size: int = 16
    eval_split: float = None  # type: ignore

    # Minimum examples per source for training
    min_examples_per_source: int = None  # type: ignore

    def __post_init__(self):
        """Load defaults from centralized settings if not provided."""
        if self.model_base is None:
            self.model_base = learning_settings.setfit_base_model
        if self.model_path is None:
            self.model_path = str(learning_settings.get_knowledge_source_model_path())
        if self.confidence_threshold is None:
            self.confidence_threshold = learning_settings.confidence_threshold
        if self.eval_split is None:
            self.eval_split = learning_settings.knowledge_train_eval_split
        if self.min_examples_per_source is None:
            self.min_examples_per_source = learning_settings.knowledge_min_examples_per_source


# =============================================================================
# SEED DATA - Initial utterances for few-shot learning
# =============================================================================

KNOWLEDGE_SOURCE_SEEDS: Dict[str, List[str]] = {
    "tenant_documents": [
        # === Spanish - User's Own Documents ===
        "Busca en mis documentos",
        "Analiza mi contrato",
        "Qué dice mi factura",
        "Revisa mi archivo",
        "Documentos de mi empresa",
        "Mis contratos",
        "Mi nómina",
        "Facturas de este mes",
        "En mi contrato de arrendamiento",
        "Mi acuerdo de confidencialidad",
        "Revisa mis documentos",
        "Busca en mis facturas",
        "Los contratos que tengo",
        "Mi última factura",
        "Archivos que subí",
        # === English ===
        "Search my documents",
        "Analyze my contract",
        "What does my invoice say",
        "Review my file",
        "My company documents",
        "My contracts",
        "Files I uploaded",
    ],
    "public_knowledge": [
        # === Spanish - Legal/BOE/Legislation ===
        "Según la ley",
        "El estatuto de los trabajadores dice",
        "Qué dice el BOE",
        "Artículo del código civil",
        "Derecho laboral",
        "Normativa fiscal",
        "Legislación vigente",
        "Días de vacaciones por ley",
        "Derechos del trabajador",
        "Cuántos días de vacaciones corresponden",
        "Ley de protección de datos",
        "RGPD",
        "LOPDGDD",
        "Derecho a indemnización",
        "Despido improcedente ley",
        "Salario mínimo interprofesional",
        "SMI actual",
        "Horas extras máximas por ley",
        # === English ===
        "According to the law",
        "The labor statute says",
        "Legal requirements",
        "Tax regulations",
        "What does the law say",
        "Minimum wage by law",
    ],
    "hybrid": [
        # === Spanish - Compare User Docs vs Law ===
        "Compara mi contrato con la ley",
        "Mi contrato cumple con el estatuto",
        "Revisa si mi documento es legal",
        "Analiza mi contrato según la normativa",
        "Cumple mi nómina con el convenio",
        "Mi contrato respeta la ley",
        "Es legal mi contrato",
        "Verifica que mi documento cumpla",
        "Mi acuerdo cumple con el RGPD",
        "Mi nómina cumple con el salario mínimo",
        "Audita mi contrato contra la normativa",
        # === English ===
        "Compare my contract with the law",
        "Does my contract comply with regulations",
        "Is my contract legal",
        "Verify my document against the law",
    ],
}


class SetFitKnowledgeClassifier:
    """
    Classifies user queries into knowledge sources using SetFit.

    Stage 2 of 2-stage routing strategy:
    - Called when SemanticKnowledgeRouter has low confidence (<0.9)
    - Provides more accurate classification for ambiguous queries
    - Learns from user corrections over time

    Provides fast (~5-8ms) classification with confidence scores.
    Falls back to TENANT_DOCUMENTS if model is not available.
    """

    def __init__(self, config: Optional[KnowledgeClassifierConfig] = None):
        """
        Initialize the classifier.

        Args:
            config: Classifier configuration
        """
        self.config = config or KnowledgeClassifierConfig()
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

                logger.info(f"Loading SetFit knowledge model from {model_path}")
                self._model = SetFitModel.from_pretrained(str(model_path))
                self._initialized = True
                logger.info(f"✅ SetFitKnowledgeClassifier initialized (version: {self._model_version})")
                return True

            else:
                logger.info(
                    f"Knowledge model not found at {model_path}. "
                    f"Using seed-based training on first use."
                )
                self._initialized = True
                return False

        except ImportError:
            logger.warning("SetFit not installed. Using fallback classification.")
            self._initialized = True
            return False

        except Exception as e:
            logger.error(f"Failed to load knowledge model: {e}. Using fallback.")
            self._initialized = True
            return False

    def classify(
        self,
        query: str,
        return_all_scores: bool = False,
    ) -> KnowledgeClassification:
        """
        Classify a query into a knowledge source.

        Args:
            query: User query text
            return_all_scores: Include all scores in result

        Returns:
            KnowledgeClassification with source and confidence
        """
        start_time = time.perf_counter()

        # Normalize query
        query_clean = query.strip().lower()

        if self._model is not None:
            # Use SetFit model
            source, confidence, all_scores = self._classify_with_model(query_clean)
            fallback_used = False
        else:
            # No model trained - use simple keyword-based fallback
            source, confidence, all_scores = self._classify_without_model(query_clean)
            fallback_used = True

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(
            f"Knowledge classified '{query[:50]}...' as {source.value} "
            f"(confidence={confidence:.2f}, time={elapsed_ms:.1f}ms, fallback={fallback_used})"
        )

        return KnowledgeClassification(
            source=source,
            confidence=confidence,
            all_scores=all_scores if return_all_scores else {},
            model_version=self._model_version,
            classification_time_ms=elapsed_ms,
            fallback_used=fallback_used,
        )

    def _classify_with_model(
        self,
        query: str,
    ) -> Tuple[KnowledgeSource, float, Dict[str, float]]:
        """
        Classify using the SetFit model.

        Args:
            query: Normalized query text

        Returns:
            Tuple of (source, confidence, all_scores)
        """
        try:
            # Get prediction
            predictions = self._model.predict([query])
            predicted_label = predictions[0]

            # Get probabilities for all classes
            all_scores = {}
            confidence = KNOWLEDGE_DEFAULT_MODEL_CONFIDENCE

            if hasattr(self._model, "predict_proba"):
                proba = self._model.predict_proba([query])[0]

                # Get actual label order from model head
                if hasattr(self._model, "model_head") and hasattr(self._model.model_head, "classes_"):
                    model_labels = list(self._model.model_head.classes_)
                else:
                    model_labels = [s.value for s in KnowledgeSource]

                # Build scores dict
                if len(proba) == len(model_labels):
                    all_scores = {
                        model_labels[i]: float(proba[i])
                        for i in range(len(model_labels))
                    }
                    confidence = all_scores.get(predicted_label, KNOWLEDGE_DEFAULT_MODEL_CONFIDENCE)
                else:
                    all_scores = {predicted_label: KNOWLEDGE_DEFAULT_MODEL_CONFIDENCE}

            # Convert label to KnowledgeSource enum
            try:
                source = KnowledgeSource(predicted_label)
            except ValueError:
                logger.warning(f"Unknown label '{predicted_label}', defaulting to TENANT_DOCUMENTS")
                source = KnowledgeSource.TENANT_DOCUMENTS
                confidence = KNOWLEDGE_LOW_CONFIDENCE_FALLBACK

            return source, confidence, all_scores

        except Exception as e:
            logger.warning(f"Model prediction failed: {e}. Using fallback.")
            return self._classify_without_model(query)

    def _classify_without_model(
        self,
        query: str,
    ) -> Tuple[KnowledgeSource, float, Dict[str, float]]:
        """
        Fallback classification when no model is trained.

        Uses simple keyword matching from seed data.

        Args:
            query: Normalized query text

        Returns:
            Tuple of (source, confidence, all_scores)
        """
        # Keywords that strongly indicate public knowledge
        public_keywords = [
            "ley", "law", "estatuto", "statute", "boe", "código", "code",
            "normativa", "regulation", "legislación", "legislation",
            "por ley", "by law", "según la ley", "according to law",
            "rgpd", "gdpr", "lopdgdd", "smi", "salario mínimo",
            "minimum wage", "legal", "derechos", "rights",
            "indemnización", "severance", "vacaciones por ley",
            "holidays by law", "despido", "termination",
        ]

        # Keywords that strongly indicate hybrid (comparison)
        hybrid_keywords = [
            "cumple", "comply", "compara", "compare",
            "legal mi", "is my", "mi contrato con la ley",
            "my contract with the law", "verifica", "verify",
            "audita", "audit", "respeta la ley", "respects the law",
            "según la normativa", "against regulation",
            "cumple con el", "complies with",
        ]

        # Keywords for tenant documents
        tenant_keywords = [
            "mi ", "my ", "mis ", "my ", "mío", "mine",
            "nuestro", "our", "empresa", "company",
            "subí", "uploaded", "cargué", "loaded",
            "tengo", "i have", "archivo", "file",
        ]

        query_lower = query.lower()

        # Score each source based on keyword matches
        # Using constants instead of magic numbers
        scores = {
            KnowledgeSource.TENANT_DOCUMENTS.value: KNOWLEDGE_INITIAL_SCORE,
            KnowledgeSource.PUBLIC_KNOWLEDGE.value: KNOWLEDGE_INITIAL_SCORE,
            KnowledgeSource.HYBRID.value: KNOWLEDGE_INITIAL_SCORE,
        }

        # Check for hybrid first (more specific patterns)
        for kw in hybrid_keywords:
            if kw in query_lower:
                scores[KnowledgeSource.HYBRID.value] += KNOWLEDGE_HYBRID_KEYWORD_BOOST

        # Check for public knowledge
        for kw in public_keywords:
            if kw in query_lower:
                scores[KnowledgeSource.PUBLIC_KNOWLEDGE.value] += KNOWLEDGE_PUBLIC_KEYWORD_BOOST

        # Check for tenant documents
        for kw in tenant_keywords:
            if kw in query_lower:
                scores[KnowledgeSource.TENANT_DOCUMENTS.value] += KNOWLEDGE_TENANT_KEYWORD_BOOST

        # Find highest scoring source
        best_source = max(scores, key=scores.get)
        confidence = min(scores[best_source], KNOWLEDGE_MAX_FALLBACK_CONFIDENCE)

        # Normalize scores
        total = sum(scores.values())
        normalized_scores = {k: v / total for k, v in scores.items()}

        return KnowledgeSource(best_source), confidence, normalized_scores

    async def reload_model(self) -> bool:
        """
        Reload the model (hot-reload support).

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
            "seed_examples": {
                source: len(examples)
                for source, examples in KNOWLEDGE_SOURCE_SEEDS.items()
            },
        }


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_knowledge_classifier: Optional[SetFitKnowledgeClassifier] = None


def get_knowledge_classifier() -> SetFitKnowledgeClassifier:
    """
    Get or create the knowledge classifier singleton.
    """
    global _knowledge_classifier
    if _knowledge_classifier is None:
        _knowledge_classifier = SetFitKnowledgeClassifier()
    return _knowledge_classifier


async def initialize_knowledge_classifier() -> bool:
    """
    Initialize the knowledge classifier singleton.

    Returns:
        True if model loaded, False if using fallback
    """
    classifier = get_knowledge_classifier()
    return await classifier.initialize()
