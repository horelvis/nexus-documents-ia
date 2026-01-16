"""
Tests for Preference Learning Service

Covers:
- User interaction recording
- Profile creation and updates
- Ranking weight adjustments based on feedback
- User context retrieval
"""

import pytest
import asyncio
from typing import Dict, Any
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.memory.learning_service import (
    PreferenceLearningService,
    UserInteraction,
    UserLearningProfile,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def learning_service():
    """Create a PreferenceLearningService instance for testing."""
    service = PreferenceLearningService()
    service._initialized = True
    service._redis_client = AsyncMock()
    return service


@pytest.fixture
def sample_interaction():
    """Create a sample user interaction."""
    return UserInteraction(
        interaction_type="query",
        query_text="What are the contract terms?",
        intent_detected="contract_analysis",
        session_id="session-123",
        results_shown=10,
        selected_document_ids=["doc-1", "doc-2"]
    )


@pytest.fixture
def sample_profile():
    """Create a sample user learning profile."""
    return UserLearningProfile(
        user_id="user-123",
        tenant_id="tenant-456",
        response_style="detailed",
        expertise_level="technical",
        preferred_language="es",
        total_queries=50,
        total_document_views=100,
        ranking_weights={"recency": 0.3, "frequency": 0.3, "relevance": 0.4}
    )


# ============================================================================
# Unit Tests
# ============================================================================

class TestUserInteraction:
    """Tests for UserInteraction dataclass."""

    def test_query_interaction(self):
        """Test creating a query interaction."""
        interaction = UserInteraction(
            interaction_type="query",
            query_text="Test query",
            intent_detected="search"
        )
        assert interaction.interaction_type == "query"
        assert interaction.query_text == "Test query"
        assert interaction.intent_detected == "search"

    def test_document_view_interaction(self):
        """Test creating a document view interaction."""
        interaction = UserInteraction(
            interaction_type="document_view",
            document_id="doc-123",
            dwell_time_seconds=120,
            scroll_depth_percentage=75.0
        )
        assert interaction.interaction_type == "document_view"
        assert interaction.document_id == "doc-123"
        assert interaction.dwell_time_seconds == 120

    def test_feedback_interaction(self):
        """Test creating a feedback interaction."""
        interaction = UserInteraction(
            interaction_type="feedback",
            feedback_rating=5,
            feedback_text="Very helpful response"
        )
        assert interaction.interaction_type == "feedback"
        assert interaction.feedback_rating == 5


class TestUserLearningProfile:
    """Tests for UserLearningProfile dataclass."""

    def test_default_profile(self):
        """Test default profile values."""
        profile = UserLearningProfile(
            user_id="user-1",
            tenant_id="tenant-1"
        )
        assert profile.response_style == "balanced"
        assert profile.expertise_level == "general"
        assert profile.preferred_language == "es"
        assert profile.total_queries == 0
        assert profile.ranking_weights == {"recency": 0.3, "frequency": 0.3, "relevance": 0.4}

    def test_custom_profile(self):
        """Test custom profile values."""
        profile = UserLearningProfile(
            user_id="user-2",
            tenant_id="tenant-2",
            response_style="concise",
            expertise_level="expert",
            total_queries=100
        )
        assert profile.response_style == "concise"
        assert profile.expertise_level == "expert"
        assert profile.total_queries == 100


class TestPreferenceLearningService:
    """Tests for PreferenceLearningService."""

    @pytest.mark.asyncio
    async def test_record_interaction_query(self, learning_service, sample_interaction):
        """Test recording a query interaction."""
        learning_service._redis_client.lpush = AsyncMock(return_value=1)
        learning_service._redis_client.ltrim = AsyncMock()
        learning_service._redis_client.expire = AsyncMock()

        await learning_service.record_interaction(
            user_id="user-123",
            tenant_id="tenant-456",
            interaction=sample_interaction
        )

        # Verify interaction was buffered
        key = "tenant-456:user-123"
        assert key in learning_service._interaction_buffer
        assert len(learning_service._interaction_buffer[key]) == 1

    @pytest.mark.asyncio
    async def test_get_user_profile_default(self, learning_service):
        """Test getting a default profile for new user."""
        learning_service._redis_client.get = AsyncMock(return_value=None)
        learning_service._redis_client.set = AsyncMock()

        profile = await learning_service.get_user_profile(
            user_id="new-user",
            tenant_id="tenant-123"
        )

        assert profile.user_id == "new-user"
        assert profile.tenant_id == "tenant-123"
        assert profile.response_style == "balanced"

    @pytest.mark.asyncio
    async def test_adjust_weights_positive_feedback(self, learning_service, sample_profile):
        """Test weight adjustment for positive feedback."""
        original_relevance = sample_profile.ranking_weights.get("relevance", 0.4)

        await learning_service._adjust_weights_from_feedback(
            profile=sample_profile,
            rating=5  # Positive feedback
        )

        # Relevance should increase for positive feedback
        assert sample_profile.ranking_weights["relevance"] > original_relevance

    @pytest.mark.asyncio
    async def test_adjust_weights_negative_feedback(self, learning_service, sample_profile):
        """Test weight adjustment for negative feedback."""
        original_recency = sample_profile.ranking_weights.get("recency", 0.3)

        await learning_service._adjust_weights_from_feedback(
            profile=sample_profile,
            rating=1  # Negative feedback
        )

        # Recency/frequency should increase for negative feedback
        assert sample_profile.ranking_weights["recency"] >= original_recency

    @pytest.mark.asyncio
    async def test_get_personalized_ranking_weights(self, learning_service):
        """Test getting personalized ranking weights."""
        learning_service._redis_client.get = AsyncMock(return_value=None)
        learning_service._redis_client.set = AsyncMock()

        weights = await learning_service.get_personalized_ranking_weights(
            user_id="user-123",
            tenant_id="tenant-456"
        )

        assert "recency" in weights
        assert "frequency" in weights
        assert "relevance" in weights
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_get_user_context_for_emma(self, learning_service):
        """Test getting user context for Emma."""
        learning_service._redis_client.get = AsyncMock(return_value=None)
        learning_service._redis_client.set = AsyncMock()

        context = await learning_service.get_user_context_for_emma(
            user_id="user-123",
            tenant_id="tenant-456"
        )

        assert "preferences" in context
        assert "frequent_queries" in context
        assert "ranking_weights" in context
        assert context["learning_enabled"] is True

    @pytest.mark.asyncio
    async def test_update_preferences(self, learning_service):
        """Test updating explicit preferences."""
        learning_service._redis_client.get = AsyncMock(return_value=None)
        learning_service._redis_client.set = AsyncMock()

        profile = await learning_service.update_preferences(
            user_id="user-123",
            tenant_id="tenant-456",
            response_style="concise",
            expertise_level="expert",
            preferred_language="en"
        )

        assert profile.response_style == "concise"
        assert profile.expertise_level == "expert"
        assert profile.preferred_language == "en"


class TestProfileNormalization:
    """Tests for weight normalization."""

    @pytest.mark.asyncio
    async def test_weights_sum_to_one(self, learning_service, sample_profile):
        """Test that weights always sum to 1.0 after adjustment."""
        # Apply multiple feedback adjustments
        for _ in range(10):
            await learning_service._adjust_weights_from_feedback(sample_profile, 5)

        total = sum(sample_profile.ranking_weights.values())
        assert total == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_weights_dont_exceed_limits(self, learning_service, sample_profile):
        """Test that individual weights don't exceed limits."""
        # Apply many positive feedbacks
        for _ in range(50):
            await learning_service._adjust_weights_from_feedback(sample_profile, 5)

        # Relevance should be capped
        assert sample_profile.ranking_weights["relevance"] <= 0.6


# ============================================================================
# Integration Tests (require Redis)
# ============================================================================

@pytest.mark.integration
class TestLearningServiceIntegration:
    """Integration tests that require Redis connection."""

    @pytest.mark.asyncio
    async def test_full_interaction_flow(self):
        """Test complete flow: record interaction -> process -> get profile."""
        # This test would require a real Redis instance
        # Skipped in unit tests, run in integration test suite
        pytest.skip("Requires Redis connection")


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
