"""
Learning System Constants

Named constants replacing magic numbers across the learning system.
Organized by category for easy reference and maintenance.

Naming Convention:
- TTL values: *_TTL_SECONDS or *_TTL_DAYS
- Thresholds: *_THRESHOLD or *_MIN_* / *_MAX_*
- Limits: MAX_* or *_LIMIT
- Scores: *_SCORE or *_WEIGHT

Usage:
    from app.core.learning_constants import (
        REDIS_TRAINING_ACTIVE_TTL_SECONDS,
        KNOWLEDGE_INITIAL_SCORE,
    )

Version 1.0 - January 2026
"""

from enum import Enum
from typing import Final


# =============================================================================
# Redis TTL Constants
# =============================================================================

# Training active flag TTL (1 hour)
REDIS_TRAINING_ACTIVE_TTL_SECONDS: Final[int] = 3600

# Learning statistics TTL (30 days)
REDIS_LEARNING_STATS_TTL_DAYS: Final[int] = 30
REDIS_LEARNING_STATS_TTL_SECONDS: Final[int] = REDIS_LEARNING_STATS_TTL_DAYS * 24 * 60 * 60

# User interactions TTL (30 days)
REDIS_INTERACTION_TTL_DAYS: Final[int] = 30
REDIS_INTERACTION_TTL_SECONDS: Final[int] = REDIS_INTERACTION_TTL_DAYS * 24 * 60 * 60

# User learning profile TTL (30 days)
REDIS_PROFILE_TTL_DAYS: Final[int] = 30
REDIS_PROFILE_TTL_SECONDS: Final[int] = REDIS_PROFILE_TTL_DAYS * 24 * 60 * 60

# Cache TTL for profile (1 hour)
PROFILE_CACHE_TTL_HOURS: Final[int] = 1
PROFILE_CACHE_TTL_SECONDS: Final[int] = PROFILE_CACHE_TTL_HOURS * 60 * 60


# =============================================================================
# Knowledge Classification Scores
# =============================================================================

# Initial base score for keyword matching (fallback classification)
KNOWLEDGE_INITIAL_SCORE: Final[float] = 0.3

# Score boost per keyword match in fallback mode
KNOWLEDGE_PUBLIC_KEYWORD_BOOST: Final[float] = 0.15
KNOWLEDGE_TENANT_KEYWORD_BOOST: Final[float] = 0.15
KNOWLEDGE_HYBRID_KEYWORD_BOOST: Final[float] = 0.2

# Maximum confidence for fallback classification
KNOWLEDGE_MAX_FALLBACK_CONFIDENCE: Final[float] = 0.85

# Default confidence when model prediction succeeds without probabilities
KNOWLEDGE_DEFAULT_MODEL_CONFIDENCE: Final[float] = 0.85

# Minimum confidence for low-confidence fallback
KNOWLEDGE_LOW_CONFIDENCE_FALLBACK: Final[float] = 0.5


# =============================================================================
# List Limits
# =============================================================================

# Maximum frequent queries to store per user
MAX_FREQUENT_QUERIES: Final[int] = 50

# Maximum frequent documents to store per user
MAX_FREQUENT_DOCUMENTS: Final[int] = 20

# Maximum interactions to store per user in Redis
MAX_INTERACTIONS_PER_USER: Final[int] = 1000

# Interaction buffer threshold before profile update
INTERACTION_BUFFER_THRESHOLD: Final[int] = 5


# =============================================================================
# LoRA Training Defaults
# =============================================================================

# LoRA rank (controls adapter size)
DEFAULT_LORA_RANK: Final[int] = 16

# LoRA alpha (scaling factor)
DEFAULT_LORA_ALPHA: Final[int] = 32

# LoRA dropout rate
DEFAULT_LORA_DROPOUT: Final[float] = 0.05

# Target modules for LoRA (Qwen/LLaMA architecture)
DEFAULT_LORA_TARGET_MODULES: Final[tuple] = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
)


# =============================================================================
# Training Timeouts
# =============================================================================

# Fine-tuning timeout (2 hours)
FINETUNING_TIMEOUT_SECONDS: Final[int] = 7200

# Subprocess communication timeout
SUBPROCESS_TIMEOUT_SECONDS: Final[int] = 300


# =============================================================================
# Ranking Weights (User Preference Learning)
# =============================================================================

# Default ranking weights for personalized search
DEFAULT_RANKING_WEIGHT_RECENCY: Final[float] = 0.3
DEFAULT_RANKING_WEIGHT_FREQUENCY: Final[float] = 0.3
DEFAULT_RANKING_WEIGHT_RELEVANCE: Final[float] = 0.4

# Maximum weight adjustment from feedback
MAX_RANKING_WEIGHT: Final[float] = 0.6
MIN_RANKING_WEIGHT: Final[float] = 0.1

# Weight adjustment per feedback
FEEDBACK_WEIGHT_ADJUSTMENT: Final[float] = 0.02


# =============================================================================
# Training Data Quality
# =============================================================================

# Minimum success rate for training
MIN_SUCCESS_RATE_FOR_TRAINING: Final[float] = 0.7

# Minimum examples per knowledge source
MIN_EXAMPLES_PER_SOURCE: Final[int] = 5

# Correction weight multiplier (corrections count 2x in training)
CORRECTION_WEIGHT_MULTIPLIER: Final[int] = 2


# =============================================================================
# Training Schedule
# =============================================================================

# Minimum hours between training runs
MIN_HOURS_BETWEEN_TRAINING: Final[int] = 24


# =============================================================================
# Token Limits
# =============================================================================

# Maximum tokens for training example
MAX_TRAINING_EXAMPLE_TOKENS: Final[int] = 512


# =============================================================================
# Logging and Metrics
# =============================================================================

# Log truncation length for query previews
LOG_QUERY_PREVIEW_LENGTH: Final[int] = 50

# Metrics aggregation window (seconds)
METRICS_WINDOW_SECONDS: Final[int] = 300


# =============================================================================
# Learning States
# =============================================================================

class LearningState(str, Enum):
    """
    State of the continuous learning system.

    State machine:
        IDLE → COLLECTING → READY_TO_TRAIN → TRAINING → DEPLOYING → IDLE
                                                ↓
                                              ERROR
    """
    IDLE = "idle"
    COLLECTING = "collecting"
    READY_TO_TRAIN = "ready_to_train"
    TRAINING = "training"
    DEPLOYING = "deploying"
    ERROR = "error"


# =============================================================================
# Route Types (SLM Router)
# =============================================================================

class RouteType(str, Enum):
    """
    Query routing types for SLM Router.

    Determines the data source for answering:
    - GRAPH_ONLY: Structural queries (counts, existence)
    - VECTOR_ONLY: Semantic search in documents
    - HYBRID: Both structure and content needed
    - ASK_CLARIFY: Ambiguous query, needs clarification
    """
    GRAPH_ONLY = "GRAPH_ONLY"
    VECTOR_ONLY = "VECTOR_ONLY"
    HYBRID = "HYBRID"
    ASK_CLARIFY = "ASK_CLARIFY"

    @classmethod
    def all_routes(cls) -> list:
        """Get all route types."""
        return [r.value for r in cls]


# =============================================================================
# Knowledge Source Types
# =============================================================================

class KnowledgeSource(str, Enum):
    """
    Knowledge source classification for RAG routing.

    Determines where to search for information:
    - TENANT_DOCUMENTS: Search in user's uploaded documents
    - PUBLIC_KNOWLEDGE: Search in public legislation/BOE
    - HYBRID: Search in both sources
    """
    TENANT_DOCUMENTS = "tenant_documents"
    PUBLIC_KNOWLEDGE = "public_knowledge"
    HYBRID = "hybrid"

    @classmethod
    def all_sources(cls) -> list:
        """Get all knowledge sources."""
        return [s.value for s in cls]
