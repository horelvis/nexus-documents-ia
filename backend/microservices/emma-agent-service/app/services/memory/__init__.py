"""
Memory Protocol for Emma.

This module provides persistent memory capabilities for Emma:

1. ConversationMemory - Short-term session memory (Redis, 30min TTL)
2. PreferencesStore - Long-term user preferences (Redis, 7day TTL)
3. MemoryService - Unified interface for all memory operations

Usage:
    from app.services.memory import get_memory_service

    memory = get_memory_service()
    await memory.initialize()

    # Store conversation
    await memory.add_exchange(
        tenant_id="...",
        session_id="...",
        user_message="Hello",
        assistant_message="Hi there!"
    )

    # Get history for LLM
    history = await memory.get_conversation_history(tenant_id, session_id)

    # Record user preferences
    await memory.record_query(tenant_id, user_id, query)
"""

from .types import (
    Message,
    MessageRole,
    ConversationContext,
    UserPreferences,
)
from .conversation import (
    ConversationMemory,
    get_conversation_memory,
)
from .preferences import (
    PreferencesStore,
    get_preferences_store,
)
from .service import (
    MemoryService,
    get_memory_service,
)

__all__ = [
    # Types
    "Message",
    "MessageRole",
    "ConversationContext",
    "UserPreferences",
    # Conversation Memory
    "ConversationMemory",
    "get_conversation_memory",
    # Preferences Store
    "PreferencesStore",
    "get_preferences_store",
    # Unified Service
    "MemoryService",
    "get_memory_service",
]
