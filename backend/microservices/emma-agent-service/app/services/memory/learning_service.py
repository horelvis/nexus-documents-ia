"""
Preference Learning Service for Emma AI.

Learns user preferences from interactions to personalize responses.
Integrates with the existing preference system and persists to PostgreSQL.

Version 1.2 - 2026 (Multi-tenancy removed — user_id-only scoping)
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import Counter
from dataclasses import dataclass, field
import json

from app.core.learning_config import learning_settings
from app.core.learning_constants import (
    MAX_FREQUENT_QUERIES,
    MAX_FREQUENT_DOCUMENTS,
    MAX_INTERACTIONS_PER_USER,
    INTERACTION_BUFFER_THRESHOLD,
    PROFILE_CACHE_TTL_HOURS,
    REDIS_INTERACTION_TTL_SECONDS,
    REDIS_PROFILE_TTL_SECONDS,
    DEFAULT_RANKING_WEIGHT_RECENCY,
    DEFAULT_RANKING_WEIGHT_FREQUENCY,
    DEFAULT_RANKING_WEIGHT_RELEVANCE,
    MAX_RANKING_WEIGHT,
    FEEDBACK_WEIGHT_ADJUSTMENT,
)

logger = logging.getLogger(__name__)

# Singleton instance
_learning_service: Optional["PreferenceLearningService"] = None


def get_learning_service() -> "PreferenceLearningService":
    """Get or create the singleton PreferenceLearningService instance."""
    global _learning_service
    if _learning_service is None:
        _learning_service = PreferenceLearningService()
    return _learning_service


@dataclass
class UserInteraction:
    """Represents a user interaction for learning."""
    interaction_type: str  # query, document_view, document_download, feedback
    query_text: Optional[str] = None
    document_id: Optional[str] = None
    intent_detected: Optional[str] = None
    dwell_time_seconds: Optional[int] = None
    scroll_depth_percentage: Optional[float] = None
    actions_taken: List[str] = field(default_factory=list)
    results_shown: Optional[int] = None
    results_clicked: Optional[int] = None
    selected_document_ids: List[str] = field(default_factory=list)
    feedback_rating: Optional[int] = None
    feedback_text: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class UserLearningProfile:
    """User learning profile with preferences and metrics."""
    user_id: str

    # Explicit preferences
    response_style: str = "balanced"
    expertise_level: str = "general"
    preferred_language: str = "es"

    # Learned preferences
    preferred_document_types: List[str] = field(default_factory=list)
    preferred_topics: List[str] = field(default_factory=list)
    search_patterns: Dict[str, Any] = field(default_factory=dict)

    # Metrics
    total_queries: int = 0
    total_document_views: int = 0
    avg_session_duration_seconds: int = 0

    # Ranking weights
    ranking_weights: Dict[str, float] = field(
        default_factory=lambda: {"recency": 0.3, "frequency": 0.3, "relevance": 0.4}
    )

    # Quick access
    frequent_document_ids: List[str] = field(default_factory=list)
    frequent_queries: List[str] = field(default_factory=list)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PreferenceLearningService:
    """
    Service for learning user preferences from interactions.

    Tracks user behavior and updates their learning profile:
    - Query patterns
    - Document access patterns
    - Feedback ratings
    - Interaction metrics

    Uses this data to personalize RAG results and Emma responses.
    """

    def __init__(self):
        self._redis_client = None
        self._initialized = False

        # Cache for active profiles (TTL from constants)
        self._profile_cache: Dict[str, UserLearningProfile] = {}
        self._cache_ttl = timedelta(hours=PROFILE_CACHE_TTL_HOURS)
        self._cache_timestamps: Dict[str, datetime] = {}

        # Interaction buffer for batch updates
        self._interaction_buffer: Dict[str, List[UserInteraction]] = {}
        self._buffer_threshold = INTERACTION_BUFFER_THRESHOLD

        # Default weights for ranking (from constants)
        self._default_weights = {
            "recency": DEFAULT_RANKING_WEIGHT_RECENCY,
            "frequency": DEFAULT_RANKING_WEIGHT_FREQUENCY,
            "relevance": DEFAULT_RANKING_WEIGHT_RELEVANCE,
        }

    async def initialize(self) -> None:
        """Initialize the service and Redis connection."""
        if self._initialized:
            return

        try:
            import redis.asyncio as redis
            from app.core.config import settings

            self._redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            self._initialized = True
            logger.info("✅ PreferenceLearningService initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize PreferenceLearningService: {e}")
            raise

    async def record_interaction(
        self,
        user_id: str,
        interaction: UserInteraction
    ) -> None:
        """
        Record a user interaction for learning.

        Interactions are buffered and processed in batches to avoid
        excessive database writes.
        """
        if not self._initialized:
            await self.initialize()

        try:
            key = user_id

            # Add to buffer
            if key not in self._interaction_buffer:
                self._interaction_buffer[key] = []
            self._interaction_buffer[key].append(interaction)

            # Store interaction in Redis for persistence
            await self._store_interaction_redis(user_id, interaction)

            # Check if we should update profile
            if len(self._interaction_buffer[key]) >= self._buffer_threshold:
                await self._process_interaction_buffer(user_id)

            logger.debug(
                f"📝 Recorded interaction: {interaction.interaction_type} "
                f"for user {user_id[:8]}..."
            )

        except Exception as e:
            logger.warning(f"⚠️ Failed to record interaction: {e}")

    async def _store_interaction_redis(
        self,
        user_id: str,
        interaction: UserInteraction
    ) -> None:
        """Store interaction in Redis for later processing."""
        try:
            key = f"emma:interactions:{user_id}"

            interaction_data = {
                "type": interaction.interaction_type,
                "query": interaction.query_text,
                "document_id": interaction.document_id,
                "intent": interaction.intent_detected,
                "dwell_time": interaction.dwell_time_seconds,
                "scroll_depth": interaction.scroll_depth_percentage,
                "actions": interaction.actions_taken,
                "results_shown": interaction.results_shown,
                "results_clicked": interaction.results_clicked,
                "selected_docs": interaction.selected_document_ids,
                "rating": interaction.feedback_rating,
                "feedback": interaction.feedback_text,
                "session_id": interaction.session_id,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Add to list (keep last N interactions)
            await self._redis_client.lpush(key, json.dumps(interaction_data))
            await self._redis_client.ltrim(key, 0, MAX_INTERACTIONS_PER_USER - 1)
            await self._redis_client.expire(key, REDIS_INTERACTION_TTL_SECONDS)

        except Exception as e:
            logger.warning(f"⚠️ Failed to store interaction in Redis: {e}")

    async def _process_interaction_buffer(
        self,
        user_id: str
    ) -> None:
        """Process buffered interactions and update user profile."""
        key = user_id
        interactions = self._interaction_buffer.get(key, [])

        if not interactions:
            return

        try:
            # Get or create profile
            profile = await self.get_user_profile(user_id)

            # Process interactions
            for interaction in interactions:
                await self._apply_interaction_to_profile(profile, interaction)

            # Save updated profile
            await self._save_profile(profile)

            # Clear buffer
            self._interaction_buffer[key] = []

            logger.debug(f"📊 Updated profile for user {user_id[:8]}... from {len(interactions)} interactions")

        except Exception as e:
            logger.warning(f"⚠️ Failed to process interaction buffer: {e}")

    async def _apply_interaction_to_profile(
        self,
        profile: UserLearningProfile,
        interaction: UserInteraction
    ) -> None:
        """Apply a single interaction to update the profile."""
        if interaction.interaction_type == "query":
            profile.total_queries += 1

            # Record frequent queries
            if interaction.query_text:
                query = interaction.query_text.strip()
                if query and query not in profile.frequent_queries:
                    profile.frequent_queries.insert(0, query)
                    profile.frequent_queries = profile.frequent_queries[:MAX_FREQUENT_QUERIES]

            # Record selected documents
            for doc_id in interaction.selected_document_ids:
                if doc_id not in profile.frequent_document_ids:
                    profile.frequent_document_ids.insert(0, doc_id)
                    profile.frequent_document_ids = profile.frequent_document_ids[:MAX_FREQUENT_DOCUMENTS]

            # Update search patterns
            if interaction.intent_detected:
                if "intents" not in profile.search_patterns:
                    profile.search_patterns["intents"] = {}
                intents = profile.search_patterns["intents"]
                intents[interaction.intent_detected] = intents.get(interaction.intent_detected, 0) + 1

        elif interaction.interaction_type == "document_view":
            profile.total_document_views += 1

            # Record document access
            if interaction.document_id:
                if interaction.document_id not in profile.frequent_document_ids:
                    profile.frequent_document_ids.insert(0, interaction.document_id)
                    profile.frequent_document_ids = profile.frequent_document_ids[:MAX_FREQUENT_DOCUMENTS]

        elif interaction.interaction_type == "feedback":
            # Adjust weights based on feedback
            if interaction.feedback_rating:
                await self._adjust_weights_from_feedback(
                    profile, interaction.feedback_rating
                )

        profile.updated_at = datetime.utcnow()

    async def _adjust_weights_from_feedback(
        self,
        profile: UserLearningProfile,
        rating: int
    ) -> None:
        """
        Adjust ranking weights based on feedback.

        Positive feedback (4-5): Increase relevance weight
        Negative feedback (1-2): Increase recency/frequency weights
        """
        if rating >= 4:
            # User liked the results - increase relevance
            current_relevance = profile.ranking_weights.get("relevance", DEFAULT_RANKING_WEIGHT_RELEVANCE)
            profile.ranking_weights["relevance"] = min(MAX_RANKING_WEIGHT, current_relevance + FEEDBACK_WEIGHT_ADJUSTMENT)
        elif rating <= 2:
            # User didn't like results - try different approach
            current_recency = profile.ranking_weights.get("recency", DEFAULT_RANKING_WEIGHT_RECENCY)
            current_frequency = profile.ranking_weights.get("frequency", DEFAULT_RANKING_WEIGHT_FREQUENCY)
            profile.ranking_weights["recency"] = min(MAX_RANKING_WEIGHT, current_recency + FEEDBACK_WEIGHT_ADJUSTMENT)
            profile.ranking_weights["frequency"] = min(MAX_RANKING_WEIGHT, current_frequency + FEEDBACK_WEIGHT_ADJUSTMENT)

        # Normalize weights to sum to 1.0
        total = sum(profile.ranking_weights.values())
        if total > 0:
            for key in profile.ranking_weights:
                profile.ranking_weights[key] /= total

    async def get_user_profile(
        self,
        user_id: str
    ) -> UserLearningProfile:
        """
        Get user learning profile.

        Checks cache first, then Redis, then creates default.
        """
        if not self._initialized:
            await self.initialize()

        cache_key = user_id

        # Check cache
        if cache_key in self._profile_cache:
            cache_time = self._cache_timestamps.get(cache_key)
            if cache_time and datetime.utcnow() - cache_time < self._cache_ttl:
                return self._profile_cache[cache_key]

        # Try to load from Redis
        profile = await self._load_profile_from_redis(user_id)

        if not profile:
            # Create default profile
            profile = UserLearningProfile(
                user_id=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            await self._save_profile(profile)

        # Update cache
        self._profile_cache[cache_key] = profile
        self._cache_timestamps[cache_key] = datetime.utcnow()

        return profile

    async def _load_profile_from_redis(
        self,
        user_id: str
    ) -> Optional[UserLearningProfile]:
        """Load user profile from Redis."""
        try:
            key = f"emma:learning:{user_id}"
            data = await self._redis_client.get(key)

            if not data:
                return None

            profile_dict = json.loads(data)
            return UserLearningProfile(
                user_id=profile_dict.get("user_id", user_id),
                response_style=profile_dict.get("response_style", "balanced"),
                expertise_level=profile_dict.get("expertise_level", "general"),
                preferred_language=profile_dict.get("preferred_language", "es"),
                preferred_document_types=profile_dict.get("preferred_document_types", []),
                preferred_topics=profile_dict.get("preferred_topics", []),
                search_patterns=profile_dict.get("search_patterns", {}),
                total_queries=profile_dict.get("total_queries", 0),
                total_document_views=profile_dict.get("total_document_views", 0),
                avg_session_duration_seconds=profile_dict.get("avg_session_duration_seconds", 0),
                ranking_weights=profile_dict.get("ranking_weights", self._default_weights.copy()),
                frequent_document_ids=profile_dict.get("frequent_document_ids", []),
                frequent_queries=profile_dict.get("frequent_queries", []),
            )

        except Exception as e:
            logger.warning(f"⚠️ Failed to load profile from Redis: {e}")
            return None

    async def _save_profile(self, profile: UserLearningProfile) -> None:
        """Save user profile to Redis."""
        try:
            key = f"emma:learning:{profile.user_id}"

            profile_dict = {
                "user_id": profile.user_id,
                "response_style": profile.response_style,
                "expertise_level": profile.expertise_level,
                "preferred_language": profile.preferred_language,
                "preferred_document_types": profile.preferred_document_types,
                "preferred_topics": profile.preferred_topics,
                "search_patterns": profile.search_patterns,
                "total_queries": profile.total_queries,
                "total_document_views": profile.total_document_views,
                "avg_session_duration_seconds": profile.avg_session_duration_seconds,
                "ranking_weights": profile.ranking_weights,
                "frequent_document_ids": profile.frequent_document_ids,
                "frequent_queries": profile.frequent_queries,
                "updated_at": datetime.utcnow().isoformat()
            }

            await self._redis_client.set(
                key,
                json.dumps(profile_dict),
                ex=REDIS_PROFILE_TTL_SECONDS
            )

            # Update cache
            cache_key = profile.user_id
            self._profile_cache[cache_key] = profile
            self._cache_timestamps[cache_key] = datetime.utcnow()

        except Exception as e:
            logger.warning(f"⚠️ Failed to save profile to Redis: {e}")

    async def get_personalized_ranking_weights(
        self,
        user_id: str
    ) -> Dict[str, float]:
        """
        Get personalized ranking weights for a user.

        Used by RAG pipeline to adjust result ranking.
        """
        profile = await self.get_user_profile(user_id)
        return profile.ranking_weights.copy()

    async def get_user_context_for_emma(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get enriched user context for Emma.

        Returns preferences, frequent documents/queries, and learned patterns.
        """
        profile = await self.get_user_profile(user_id)

        return {
            "preferences": {
                "response_style": profile.response_style,
                "expertise_level": profile.expertise_level,
                "language": profile.preferred_language,
            },
            "frequent_queries": profile.frequent_queries[:5],
            "frequent_documents": profile.frequent_document_ids[:5],
            "preferred_topics": profile.preferred_topics[:5],
            "ranking_weights": profile.ranking_weights,
            "metrics": {
                "total_queries": profile.total_queries,
                "total_document_views": profile.total_document_views,
            },
            "search_patterns": profile.search_patterns,
            "learning_enabled": True
        }

    async def update_preferences(
        self,
        user_id: str,
        response_style: Optional[str] = None,
        expertise_level: Optional[str] = None,
        preferred_language: Optional[str] = None
    ) -> UserLearningProfile:
        """
        Update explicit user preferences.

        These are preferences the user sets directly, not learned.
        """
        profile = await self.get_user_profile(user_id)

        if response_style:
            profile.response_style = response_style
        if expertise_level:
            profile.expertise_level = expertise_level
        if preferred_language:
            profile.preferred_language = preferred_language

        profile.updated_at = datetime.utcnow()
        await self._save_profile(profile)

        return profile

    async def flush_interactions(
        self,
        user_id: str
    ) -> None:
        """
        Flush pending interactions and update profile.

        Called when user session ends or periodically.
        """
        await self._process_interaction_buffer(user_id)

    async def get_learning_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get learning statistics for a user."""
        profile = await self.get_user_profile(user_id)

        return {
            "user_id": user_id,
            "total_queries": profile.total_queries,
            "total_document_views": profile.total_document_views,
            "frequent_queries_count": len(profile.frequent_queries),
            "frequent_documents_count": len(profile.frequent_document_ids),
            "search_patterns": profile.search_patterns,
            "ranking_weights": profile.ranking_weights,
            "learning_enabled": True,
            "profile_age_days": (datetime.utcnow() - (profile.created_at or datetime.utcnow())).days if profile.created_at else 0
        }
