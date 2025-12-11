"""
User Preferences Storage for Emma.

Provides long-term storage for user preferences and learning data.
Uses Redis with longer TTL for persistence across sessions.

Key format: emma:pref:{tenant_id}:{user_id}
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
        """
        Initialize preferences store.

        Args:
            redis_url: Redis connection URL. Uses settings if not provided.
            ttl_seconds: TTL for preference data in seconds.
        """
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

    def _make_key(self, tenant_id: str, user_id: str) -> str:
        """Generate Redis key for user preferences."""
        return f"{self.KEY_PREFIX}:{tenant_id}:{user_id}"

    async def get_preferences(
        self,
        tenant_id: str,
        user_id: str
    ) -> UserPreferences:
        """
        Get user preferences, creating defaults if not found.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            UserPreferences (existing or default)
        """
        await self.connect()

        key = self._make_key(tenant_id, user_id)
        data = await self._redis.get(key)

        if data:
            try:
                prefs = UserPreferences.from_dict(json.loads(data))
                logger.debug(f"Loaded preferences for user {user_id}")
                return prefs
            except Exception as e:
                logger.warning(f"Failed to load preferences for {user_id}: {e}")

        # Create default preferences
        prefs = UserPreferences(
            tenant_id=tenant_id,
            user_id=user_id
        )
        logger.debug(f"Created default preferences for user {user_id}")
        return prefs

    async def save_preferences(self, prefs: UserPreferences) -> bool:
        """
        Save user preferences to Redis.

        Args:
            prefs: UserPreferences to save

        Returns:
            True if saved successfully
        """
        await self.connect()

        try:
            key = self._make_key(prefs.tenant_id, prefs.user_id)
            data = json.dumps(prefs.to_dict())

            await self._redis.setex(key, self._ttl, data)
            logger.debug(f"Saved preferences for user {prefs.user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save preferences for {prefs.user_id}: {e}")
            return False

    async def update_preference(
        self,
        tenant_id: str,
        user_id: str,
        key: str,
        value: any
    ) -> UserPreferences:
        """
        Update a single preference value.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            key: Preference key to update
            value: New value

        Returns:
            Updated UserPreferences
        """
        prefs = await self.get_preferences(tenant_id, user_id)

        # Update attribute if it exists
        if hasattr(prefs, key):
            setattr(prefs, key, value)
        else:
            # Store in custom_settings
            prefs.custom_settings[key] = value

        await self.save_preferences(prefs)
        return prefs

    async def record_query(
        self,
        tenant_id: str,
        user_id: str,
        query: str
    ) -> None:
        """
        Record a user query for learning.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            query: The query to record
        """
        prefs = await self.get_preferences(tenant_id, user_id)
        prefs.record_query(query)
        await self.save_preferences(prefs)

    async def record_document_access(
        self,
        tenant_id: str,
        user_id: str,
        document_id: str
    ) -> None:
        """
        Record document access for relevance.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            document_id: Document ID that was accessed
        """
        prefs = await self.get_preferences(tenant_id, user_id)
        prefs.record_document_access(document_id)
        await self.save_preferences(prefs)

    async def get_frequent_queries(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 10
    ) -> List[str]:
        """
        Get user's most frequent queries.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            limit: Maximum queries to return

        Returns:
            List of recent queries
        """
        prefs = await self.get_preferences(tenant_id, user_id)
        return prefs.frequent_queries[:limit]

    async def get_frequent_documents(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 10
    ) -> List[str]:
        """
        Get user's most accessed documents.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            limit: Maximum document IDs to return

        Returns:
            List of frequently accessed document IDs
        """
        prefs = await self.get_preferences(tenant_id, user_id)
        return prefs.frequent_documents[:limit]

    async def delete_preferences(self, tenant_id: str, user_id: str) -> bool:
        """
        Delete user preferences.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            True if deleted successfully
        """
        await self.connect()

        try:
            key = self._make_key(tenant_id, user_id)
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
