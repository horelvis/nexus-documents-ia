"""
Memory Protocol for Emma.

This module provides persistent memory capabilities for Emma:

1. ConversationMemory - Short-term session memory (Redis, 30min TTL)
2. PreferencesStore - Long-term user preferences (Redis, 7day TTL)
3. UserFactsService - Cross-session persistent facts (PostgreSQL + Redis cache)
4. FactExtractor - Hybrid regex + LLM fact extraction
5. MemoryService - Unified interface for all memory operations

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

    # User facts (cross-session memory)
    from app.services.memory import get_user_facts_service
    facts_service = get_user_facts_service()
    facts = await facts_service.get_user_facts(tenant_id, user_id)
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
from .user_facts import (
    UserFactsService,
    get_user_facts_service,
)
from .fact_extractor import (
    extract_and_save_facts,
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
    # User Facts (cross-session)
    "UserFactsService",
    "get_user_facts_service",
    "extract_and_save_facts",
    # Unified Service
    "MemoryService",
    "get_memory_service",
]
