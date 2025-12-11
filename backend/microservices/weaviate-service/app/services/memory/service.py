"""
Unified Memory Service for Emma.

Provides a single interface for all memory operations, combining:
- ConversationMemory (short-term session history)
- PreferencesStore (long-term user preferences)

This is the recommended interface for EmmaService integration.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

from .conversation import ConversationMemory, get_conversation_memory
from .preferences import PreferencesStore, get_preferences_store
from .types import ConversationContext, UserPreferences, MessageRole

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Unified memory service combining conversation and preference storage.

    Provides convenience methods for common Emma operations:
    - Session management
    - Conversation history retrieval
    - User preference management
    - Learning data recording
    """

    def __init__(
        self,
        conversation_memory: Optional[ConversationMemory] = None,
        preferences_store: Optional[PreferencesStore] = None
    ):
        """
        Initialize memory service.

        Args:
            conversation_memory: ConversationMemory instance (uses singleton if None)
            preferences_store: PreferencesStore instance (uses singleton if None)
        """
        self._conversation = conversation_memory or get_conversation_memory()
        self._preferences = preferences_store or get_preferences_store()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all memory stores."""
        if self._initialized:
            return

        await self._conversation.connect()
        await self._preferences.connect()
        self._initialized = True
        logger.info("✅ MemoryService initialized")

    async def close(self) -> None:
        """Close all memory store connections."""
        await self._conversation.close()
        await self._preferences.close()
        self._initialized = False

    # =========================================================================
    # Conversation Memory Operations
    # =========================================================================

    async def get_conversation_history(
        self,
        tenant_id: str,
        session_id: str,
        max_messages: int = 20
    ) -> List[Dict[str, str]]:
        """
        Get conversation history for LLM context.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            max_messages: Maximum messages to return

        Returns:
            List of messages in LLM format [{"role": "user", "content": "..."}]
        """
        return await self._conversation.get_history_for_llm(
            tenant_id, session_id, max_messages
        )

    async def get_context(
        self,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None
    ) -> ConversationContext:
        """
        Get full conversation context.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            user_id: Optional user identifier

        Returns:
            ConversationContext with full history
        """
        return await self._conversation.get_context(tenant_id, session_id, user_id)

    async def add_exchange(
        self,
        tenant_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        user_id: Optional[str] = None,
        **metadata
    ) -> ConversationContext:
        """
        Add a user-assistant exchange to conversation history.

        This is the primary method for storing conversation turns.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            user_message: User's query
            assistant_message: Emma's response
            user_id: Optional user identifier
            **metadata: Additional metadata (tools_used, etc.)

        Returns:
            Updated ConversationContext
        """
        context = await self._conversation.add_exchange(
            tenant_id, session_id,
            user_message, assistant_message,
            user_id, **metadata
        )

        # Also record query for learning if user_id provided
        if user_id:
            await self._preferences.record_query(tenant_id, user_id, user_message)

        return context

    async def add_tool_result(
        self,
        tenant_id: str,
        session_id: str,
        tool_name: str,
        result: str,
        **metadata
    ) -> ConversationContext:
        """
        Add a tool result to conversation.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            tool_name: Name of the tool that was executed
            result: Tool result content
            **metadata: Additional metadata

        Returns:
            Updated ConversationContext
        """
        context = await self._conversation.get_context(tenant_id, session_id)
        context.add_tool_message(tool_name, result, **metadata)
        await self._conversation.save_context(context)
        return context

    async def clear_session(self, tenant_id: str, session_id: str) -> bool:
        """Clear a conversation session."""
        return await self._conversation.clear_session(tenant_id, session_id)

    async def extend_session(self, tenant_id: str, session_id: str) -> bool:
        """Extend TTL for an active session."""
        return await self._conversation.extend_ttl(tenant_id, session_id)

    # =========================================================================
    # User Preferences Operations
    # =========================================================================

    async def get_preferences(
        self,
        tenant_id: str,
        user_id: str
    ) -> UserPreferences:
        """
        Get user preferences.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            UserPreferences for the user
        """
        return await self._preferences.get_preferences(tenant_id, user_id)

    async def update_preference(
        self,
        tenant_id: str,
        user_id: str,
        key: str,
        value: Any
    ) -> UserPreferences:
        """
        Update a single preference.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            key: Preference key
            value: New value

        Returns:
            Updated UserPreferences
        """
        return await self._preferences.update_preference(
            tenant_id, user_id, key, value
        )

    async def record_query(
        self,
        tenant_id: str,
        user_id: str,
        query: str
    ) -> None:
        """Record a query for learning."""
        await self._preferences.record_query(tenant_id, user_id, query)

    async def record_document_access(
        self,
        tenant_id: str,
        user_id: str,
        document_id: str
    ) -> None:
        """Record document access for relevance."""
        await self._preferences.record_document_access(tenant_id, user_id, document_id)

    async def get_user_context(
        self,
        tenant_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get combined user context for personalization.

        Returns preferences and learning data useful for personalizing responses.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            Dictionary with user context:
            - name: User's display name
            - language: Preferred language
            - preferences: Response style and expertise level
            - frequent_queries: Recent queries
            - frequent_documents: Frequently accessed docs
            - custom_settings: Any custom settings
        """
        prefs = await self._preferences.get_preferences(tenant_id, user_id)
        return {
            # Personalization fields
            "name": prefs.display_name,
            "language": prefs.preferred_language or prefs.language,
            "preferences": {
                "response_style": prefs.response_style,
                "expertise_level": prefs.expertise_level,
            },
            # Display preferences
            "visualization_preference": prefs.visualization_preference,
            "enable_suggestions": prefs.enable_suggestions,
            # Learning data
            "frequent_queries": prefs.frequent_queries[:5],
            "frequent_documents": prefs.frequent_documents[:5],
            "favorite_tools": prefs.favorite_tools,
            "custom_settings": prefs.custom_settings
        }

    # =========================================================================
    # Combined Operations
    # =========================================================================

    async def get_full_context(
        self,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None,
        max_history: int = 20
    ) -> Dict[str, Any]:
        """
        Get full context for Emma query processing.

        Combines conversation history and user preferences into a single
        context object suitable for LLM system prompts.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            user_id: Optional user identifier
            max_history: Maximum conversation history messages

        Returns:
            Dictionary with:
            - history: Conversation history for LLM
            - active_documents: Documents in current context
            - user_context: User preferences (if user_id provided)
        """
        context = await self._conversation.get_context(tenant_id, session_id, user_id)

        result = {
            "history": context.get_history_for_llm(max_history),
            "active_documents": context.active_documents,
            "session_metadata": context.metadata
        }

        if user_id:
            result["user_context"] = await self.get_user_context(tenant_id, user_id)

        return result


# Singleton instance
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get the global MemoryService singleton."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


async def initialize_memory_service() -> MemoryService:
    """Initialize and return the global memory service."""
    service = get_memory_service()
    await service.initialize()
    return service
