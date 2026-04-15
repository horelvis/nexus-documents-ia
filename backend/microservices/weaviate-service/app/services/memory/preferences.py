"""
User Preferences Storage for Emma.

Provides long-term storage for user preferences and learning data.
Uses Redis with longer TTL for persistence across sessions.

Key format: emma:pref:{user_id}
TTL: 7 days by default (configurable)
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

import redis.asyncio as redis

from app.core.config import settings
from .types import UserPreferences

logger = logging.getLogger(__name__)


class PreferencesStore:
    """
    Redis-backed user preferences storage.

    Stores user preferences with longer TTL than conversations.
    Supports preference updates and learning data accumulation.
    """

    # Key prefix for Redis
    KEY_PREFIX = "emma:pref"
    # Default TTL: 7 days
    DEFAULT_TTL_SECONDS = 604800  # 7 * 24 * 60 * 60

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS
    ):
        """Initialize preferences store."""
        self._redis_url = redis_url or settings.redis_url
        self._ttl = ttl_seconds
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"✅ PreferencesStore connected to Redis")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _make_key(self, user_id: str) -> str:
        """Generate Redis key for user preferences."""
        return f"{self.KEY_PREFIX}:{user_id}"

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """Get user preferences, creating defaults if not found."""
        await self.connect()

        key = self._make_key(user_id)
        data = await self._redis.get(key)

        if data:
            try:
                prefs = UserPreferences.from_dict(json.loads(data))
                logger.debug(f"Loaded preferences for user {user_id}")
                return prefs
            except Exception as e:
                logger.warning(f"Failed to load preferences for {user_id}: {e}")

        # Create default preferences — tenant_id retained as dataclass field (empty)
        prefs = UserPreferences(
            tenant_id="",
            user_id=user_id
        )
        logger.debug(f"Created default preferences for user {user_id}")
        return prefs

    async def save_preferences(self, prefs: UserPreferences) -> bool:
        """Save user preferences to Redis."""
        await self.connect()

        try:
            key = self._make_key(prefs.user_id)
            data = json.dumps(prefs.to_dict())

            await self._redis.setex(key, self._ttl, data)
            logger.debug(f"Saved preferences for user {prefs.user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save preferences for {prefs.user_id}: {e}")
            return False

    async def update_preference(
        self,
        user_id: str,
        key: str,
        value: any
    ) -> UserPreferences:
        """Update a single preference value."""
        prefs = await self.get_preferences(user_id)

        # Update attribute if it exists
        if hasattr(prefs, key):
            setattr(prefs, key, value)
        else:
            # Store in custom_settings
            prefs.custom_settings[key] = value

        await self.save_preferences(prefs)
        return prefs

    async def record_query(self, user_id: str, query: str) -> None:
        """Record a user query for learning."""
        prefs = await self.get_preferences(user_id)
        prefs.record_query(query)
        await self.save_preferences(prefs)

    async def record_document_access(self, user_id: str, document_id: str) -> None:
        """Record document access for relevance."""
        prefs = await self.get_preferences(user_id)
        prefs.record_document_access(document_id)
        await self.save_preferences(prefs)

    async def get_frequent_queries(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[str]:
        """Get user's most frequent queries."""
        prefs = await self.get_preferences(user_id)
        return prefs.frequent_queries[:limit]

    async def get_frequent_documents(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[str]:
        """Get user's most accessed documents."""
        prefs = await self.get_preferences(user_id)
        return prefs.frequent_documents[:limit]

    async def delete_preferences(self, user_id: str) -> bool:
        """Delete user preferences."""
        await self.connect()

        try:
            key = self._make_key(user_id)
            await self._redis.delete(key)
            logger.info(f"Deleted preferences for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete preferences for {user_id}: {e}")
            return False


# Singleton instance
_preferences_store: Optional[PreferencesStore] = None


def get_preferences_store() -> PreferencesStore:
    """Get the global PreferencesStore singleton."""
    global _preferences_store
    if _preferences_store is None:
        _preferences_store = PreferencesStore()
    return _preferences_store
