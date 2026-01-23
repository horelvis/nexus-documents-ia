"""
NexusRouter Schemas - Data models for intent classification

Defines all the data structures used by the NexusRouter system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Intent(str, Enum):
    """
    User intent categories.

    Each intent maps to a specific action pattern:
    - SEARCH: Document retrieval required
    - COUNT: Count aggregation needed
    - LIST: List enumeration needed
    - ANALYZE: Deep content analysis
    - COMPARE: Multi-document comparison
    - SUMMARIZE: Content summarization
    - EXTRACT: Structured extraction
    - CHAT: General conversation (no docs needed)
    """
    SEARCH = "search"
    COUNT = "count"
    LIST = "list"
    ANALYZE = "analyze"
    COMPARE = "compare"
    SUMMARIZE = "summarize"
    EXTRACT = "extract"
    CHAT = "chat"

    @classmethod
    def document_intents(cls) -> List["Intent"]:
        """Intents that require document retrieval."""
        return [cls.SEARCH, cls.COUNT, cls.LIST, cls.ANALYZE, cls.COMPARE, cls.SUMMARIZE, cls.EXTRACT]

    @classmethod
    def chat_intents(cls) -> List["Intent"]:
        """Intents that don't need documents."""
        return [cls.CHAT]


class RequiredAction(str, Enum):
    """
    Actions to take based on classification.

    - FORCE_SEARCH: Execute search BEFORE invoking LLM
    - FORCE_SEARCH_COUNT: Search and count results
    - FORCE_SEARCH_LIST: Search and format as list
    - FORCE_GET_DOCUMENT: Get specific document by ID
    - FOCUSED_RAG: RAG on specific documents only
    - DIRECT_RESPONSE: Let LLM respond directly
    """
    FORCE_SEARCH = "force_search"
    FORCE_SEARCH_COUNT = "force_search_count"
    FORCE_SEARCH_LIST = "force_search_list"
    FORCE_GET_DOCUMENT = "force_get_document"
    FOCUSED_RAG = "focused_rag"
    DIRECT_RESPONSE = "direct_response"


@dataclass
class IntentClassification:
    """
    Result from intent classification.

    Contains the predicted intent, confidence score, extracted entities,
    and the recommended action to take.
    """
    intent: Intent
    confidence: float
    entities: List[str] = field(default_factory=list)
    document_types: List[str] = field(default_factory=list)
    required_action: RequiredAction = RequiredAction.DIRECT_RESPONSE

    # Optional metadata for debugging
    model_version: Optional[str] = None
    classification_time_ms: float = 0.0
    raw_scores: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "document_types": self.document_types,
            "required_action": self.required_action.value,
            "model_version": self.model_version,
            "classification_time_ms": self.classification_time_ms,
        }

    @property
    def needs_search(self) -> bool:
        """Whether this classification requires document search."""
        return self.required_action in [
            RequiredAction.FORCE_SEARCH,
            RequiredAction.FORCE_SEARCH_COUNT,
            RequiredAction.FORCE_SEARCH_LIST,
            RequiredAction.FOCUSED_RAG,
        ]


@dataclass
class TrainingExample:
    """
    Single training example for SetFit.

    Contains query text, intent label, and optional source metadata.
    """
    text: str
    intent: Intent
    source: str = "unknown"  # "historical", "synthetic", "manual"
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None

    # Optional metadata for analysis
    entities: List[str] = field(default_factory=list)
    document_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "text": self.text,
            "intent": self.intent.value,
            "source": self.source,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "entities": self.entities,
            "document_types": self.document_types,
        }


@dataclass
class TrainingDataset:
    """
    Complete training dataset for SetFit.

    Contains train/eval splits and metadata about data sources.
    """
    train_examples: List[TrainingExample]
    eval_examples: List[TrainingExample]

    # Statistics
    total_examples: int = 0
    examples_per_intent: Dict[str, int] = field(default_factory=dict)
    sources: Dict[str, int] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    tenant_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate statistics after initialization."""
        self.total_examples = len(self.train_examples) + len(self.eval_examples)

        # Count by intent
        intent_counts = {}
        source_counts = {}

        for example in self.train_examples + self.eval_examples:
            intent_counts[example.intent.value] = intent_counts.get(example.intent.value, 0) + 1
            source_counts[example.source] = source_counts.get(example.source, 0) + 1

        self.examples_per_intent = intent_counts
        self.sources = source_counts

    def to_huggingface_format(self) -> Dict[str, List]:
        """Convert to HuggingFace Dataset format."""
        return {
            "train": {
                "text": [ex.text for ex in self.train_examples],
                "label": [ex.intent.value for ex in self.train_examples],
            },
            "eval": {
                "text": [ex.text for ex in self.eval_examples],
                "label": [ex.intent.value for ex in self.eval_examples],
            }
        }


@dataclass
class NexusRouterConfig:
    """
    Configuration for NexusRouter.

    Controls model paths, thresholds, and training parameters.
    """
    # Model settings
    model_base: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    model_path: str = "/app/models/nexus_router"

    # Classification thresholds
    confidence_threshold: float = 0.70  # Min confidence to trust classification
    force_search_threshold: float = 0.80  # Higher threshold to force search

    # Training settings
    num_iterations: int = 20
    batch_size: int = 16
    eval_split: float = 0.2  # 20% for evaluation
    min_examples_per_intent: int = 8  # Minimum examples needed per intent

    # Synthetic data generation
    synthetic_multiplier: int = 3  # Generate 3x synthetic examples per real example

    # Retraining triggers
    min_new_documents: int = 100  # Retrain after N new documents
    min_new_queries: int = 50  # Retrain after N new queries
    retrain_cooldown_hours: int = 24  # Don't retrain more often than this

    # spaCy NER model for entity extraction
    spacy_model_es: str = "es_core_news_md"
    spacy_model_en: str = "en_core_web_md"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_base": self.model_base,
            "model_path": self.model_path,
            "confidence_threshold": self.confidence_threshold,
            "force_search_threshold": self.force_search_threshold,
            "num_iterations": self.num_iterations,
            "batch_size": self.batch_size,
            "eval_split": self.eval_split,
            "min_examples_per_intent": self.min_examples_per_intent,
        }


@dataclass
class ModelMetadata:
    """
    Metadata for a trained model version.

    Stored alongside the model for versioning and tracking.
    """
    version: str
    created_at: datetime
    accuracy: float
    f1_score: float

    # Training data info
    training_examples: int
    eval_examples: int
    examples_per_intent: Dict[str, int]
    sources: Dict[str, int]
    tenant_ids: List[str]

    # Model info
    base_model: str
    config: NexusRouterConfig

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "accuracy": self.accuracy,
            "f1_score": self.f1_score,
            "training_examples": self.training_examples,
            "eval_examples": self.eval_examples,
            "examples_per_intent": self.examples_per_intent,
            "sources": self.sources,
            "tenant_ids": self.tenant_ids,
            "base_model": self.base_model,
            "config": self.config.to_dict(),
        }


@dataclass
class RouterMetrics:
    """
    Real-time metrics for the router.

    Used for monitoring and admin dashboards.
    """
    total_classifications: int = 0
    classifications_by_intent: Dict[str, int] = field(default_factory=dict)

    avg_confidence: float = 0.0
    avg_latency_ms: float = 0.0

    forced_searches: int = 0
    direct_responses: int = 0

    # Time window
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "total_classifications": self.total_classifications,
            "classifications_by_intent": self.classifications_by_intent,
            "avg_confidence": self.avg_confidence,
            "avg_latency_ms": self.avg_latency_ms,
            "forced_searches": self.forced_searches,
            "direct_responses": self.direct_responses,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
        }


@dataclass
class ClassificationStats:
    """
    Detailed statistics for a single classification.

    Used for debugging and analysis.
    """
    query: str
    intent: Intent
    confidence: float

    # Alternatives
    top_intents: List[Dict[str, float]] = field(default_factory=list)

    # Extracted entities
    entities: List[str] = field(default_factory=list)
    entity_types: Dict[str, str] = field(default_factory=dict)

    # Timing
    classification_time_ms: float = 0.0
    entity_extraction_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Model info
    model_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "query": self.query,
            "intent": self.intent.value,
            "confidence": self.confidence,
            "top_intents": self.top_intents,
            "entities": self.entities,
            "entity_types": self.entity_types,
            "classification_time_ms": self.classification_time_ms,
            "entity_extraction_time_ms": self.entity_extraction_time_ms,
            "total_time_ms": self.total_time_ms,
            "model_version": self.model_version,
        }


# =============================================================================
# Intent to Action Mapping
# =============================================================================

INTENT_ACTION_MAP: Dict[Intent, RequiredAction] = {
    Intent.SEARCH: RequiredAction.FORCE_SEARCH,
    Intent.COUNT: RequiredAction.FORCE_SEARCH_COUNT,
    Intent.LIST: RequiredAction.FORCE_SEARCH_LIST,
    Intent.ANALYZE: RequiredAction.FOCUSED_RAG,
    Intent.COMPARE: RequiredAction.FOCUSED_RAG,
    Intent.SUMMARIZE: RequiredAction.FOCUSED_RAG,
    Intent.EXTRACT: RequiredAction.FOCUSED_RAG,
    Intent.CHAT: RequiredAction.DIRECT_RESPONSE,
}


def get_action_for_intent(intent: Intent, confidence: float, threshold: float = 0.70) -> RequiredAction:
    """
    Get the required action for an intent.

    If confidence is below threshold AND intent is document-related,
    default to FORCE_SEARCH as it's safer to search than to miss relevant documents.
    For CHAT intent, always use DIRECT_RESPONSE regardless of confidence.
    """
    # CHAT intent always goes to direct response regardless of confidence
    if intent == Intent.CHAT:
        return RequiredAction.DIRECT_RESPONSE

    if confidence < threshold:
        # Low confidence on document intent - default to search to be safe
        return RequiredAction.FORCE_SEARCH

    return INTENT_ACTION_MAP.get(intent, RequiredAction.FORCE_SEARCH)
